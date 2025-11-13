# app_productividad_profesores.py
# Productividad de Profesionales · Rol Profesional / Administrativo
# Ajuste: "Paciente priorizado" (UI + DB + Carga masiva de atenciones)
# Streamlit 1.30+ (usa st.rerun)

import streamlit as st
import sqlite3, os, io
import pandas as pd
from datetime import datetime, date, time

APP_TITLE = "Productividad de Profesionales"
DB_PATH = os.getenv("DB_FILE", "data.db")

# ---------------------------------------------------------------------
# Helpers de UI (claves únicas) y lectura robusta
# ---------------------------------------------------------------------
def k(ns: str, name: str) -> str:
    """Genera una clave única para widgets."""
    return f"{ns}__{name}"

def read_table_file(uploaded):
    """
    Lee CSV/Excel con tolerancia de codificación.
    Reglas:
      - Si es Excel por extensión → pandas.read_excel
      - Si es texto → intenta utf-8, latin-1, cp1252
    """
    if uploaded is None:
        return None
    name = (uploaded.name or "").lower()
    # Excel por extensión
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(uploaded)
    # CSV / texto
    data = uploaded.read()
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            try:
                # Separador ; frecuente
                return pd.read_csv(io.BytesIO(data), encoding=enc, sep=";")
            except Exception:
                continue
    raise ValueError("No fue posible leer el archivo. Verifica delimitador/codificación.")

# ---------------------------------------------------------------------
# DB y Esquema (con migraciones simples)
# ---------------------------------------------------------------------
def db():
    cx = sqlite3.connect(DB_PATH, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    return cx

def col_in_table(cx, table, col):
    r = cx.execute(f"PRAGMA table_info({table})").fetchall()
    return any(x["name"] == col for x in r)

def ensure_schema():
    cx = db()
    with cx:
        # Usuarios (simple demo)
        cx.execute("""
        CREATE TABLE IF NOT EXISTS usuarios(
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin','Profesional'))
        )""")
        # Pacientes
        cx.execute("""
        CREATE TABLE IF NOT EXISTS pacientes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT UNIQUE NOT NULL,
            nombre TEXT,
            fecha_nacimiento TEXT,
            sexo TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            zona TEXT,
            priorizado INTEGER DEFAULT 0
        )""")
        # Profesionales
        cx.execute("""
        CREATE TABLE IF NOT EXISTS profesionales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT UNIQUE NOT NULL,
            nombre TEXT,
            telefono TEXT,
            email TEXT,
            programa TEXT,
            convenio TEXT
        )""")
        # Instituciones
        cx.execute("""
        CREATE TABLE IF NOT EXISTS instituciones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            departamento TEXT,
            municipio TEXT,
            localidad TEXT
        )""")
        # Atenciones
        cx.execute("""
        CREATE TABLE IF NOT EXISTS atenciones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            programa TEXT,
            convenio TEXT,
            institucion TEXT,
            departamento TEXT,
            municipio TEXT,
            localidad TEXT,
            profesional TEXT,
            documento TEXT,
            nombre TEXT,
            actividad TEXT,
            atendido INTEGER DEFAULT 0,
            registrado_panacea INTEGER DEFAULT 0,
            paciente_creado_panacea INTEGER DEFAULT 0,
            paciente_priorizado INTEGER DEFAULT 0,
            tipo_contacto TEXT,
            duracion_minutos INTEGER,
            observaciones TEXT,
            sexo TEXT,
            fecha_nacimiento TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            zona TEXT
        )""")
        # Viáticos
        cx.execute("""
        CREATE TABLE IF NOT EXISTS viaticos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            requiere INTEGER DEFAULT 0,
            origen TEXT,
            destino TEXT,
            valor REAL,
            observaciones TEXT,
            fecha TEXT
        )""")
        # Planificador
        cx.execute("""
        CREATE TABLE IF NOT EXISTS planificador(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            fecha TEXT,
            hora_ini TEXT,
            hora_fin TEXT,
            titulo TEXT,
            descripcion TEXT,
            programa TEXT,
            convenio TEXT,
            institucion TEXT
        )""")
        # Papelería
        cx.execute("""
        CREATE TABLE IF NOT EXISTS papeleria(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            item TEXT,
            cantidad INTEGER,
            estado TEXT, -- Solicitado|Aprobado|Entregado
            observaciones TEXT,
            fecha TEXT
        )""")
        # Migraciones seguras (por si ya existían tablas)
        # Pacientes: priorizado
        if not col_in_table(cx, "pacientes", "priorizado"):
            cx.execute("ALTER TABLE pacientes ADD COLUMN priorizado INTEGER DEFAULT 0")
        # Atenciones: paciente_priorizado
        if not col_in_table(cx, "atenciones", "paciente_priorizado"):
            cx.execute("ALTER TABLE atenciones ADD COLUMN paciente_priorizado INTEGER DEFAULT 0")
        # Usuarios demo
        if not cx.execute("SELECT 1 FROM usuarios WHERE username='admin'").fetchone():
            cx.execute("INSERT INTO usuarios(username,password,role) VALUES('admin','admin123','Admin')")
        if not cx.execute("SELECT 1 FROM usuarios WHERE username='pro'").fetchone():
            cx.execute("INSERT INTO usuarios(username,password,role) VALUES('pro','pro123','Profesional')")

# ---------------------------------------------------------------------
# Repos/Servicios
# ---------------------------------------------------------------------
def get_paciente(documento:str):
    cx = db()
    r = cx.execute("SELECT * FROM pacientes WHERE documento=?", (documento,)).fetchone()
    return r

def upsert_paciente(row:dict):
    """
    row keys esperadas:
    documento, nombre, fecha_nacimiento, sexo, telefono, email,
    direccion, localidad, municipio, departamento, zona, priorizado
    """
    cx = db()
    with cx:
        cur = cx.execute("SELECT id FROM pacientes WHERE documento=?", (row["documento"],)).fetchone()
        vals = (
            row.get("nombre"),
            row.get("fecha_nacimiento"),
            row.get("sexo"),
            row.get("telefono"),
            row.get("email"),
            row.get("direccion"),
            row.get("localidad"),
            row.get("municipio"),
            row.get("departamento"),
            row.get("zona"),
            int(row.get("priorizado") or 0),
            row["documento"]
        )
        if cur:
            cx.execute("""UPDATE pacientes SET
                nombre=?, fecha_nacimiento=?, sexo=?, telefono=?, email=?,
                direccion=?, localidad=?, municipio=?, departamento=?, zona=?,
                priorizado=?
                WHERE documento=?""", vals)
        else:
            cx.execute("""INSERT INTO pacientes(
                documento, nombre, fecha_nacimiento, sexo, telefono, email,
                direccion, localidad, municipio, departamento, zona, priorizado
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (
                row["documento"], row.get("nombre"), row.get("fecha_nacimiento"),
                row.get("sexo"), row.get("telefono"), row.get("email"),
                row.get("direccion"), row.get("localidad"), row.get("municipio"),
                row.get("departamento"), row.get("zona"), int(row.get("priorizado") or 0)
            ))

def insert_atencion(a:dict):
    cx = db()
    with cx:
        cx.execute("""INSERT INTO atenciones(
            fecha, programa, convenio, institucion, departamento, municipio, localidad,
            profesional, documento, nombre, actividad, atendido, registrado_panacea,
            paciente_creado_panacea, paciente_priorizado, tipo_contacto, duracion_minutos,
            observaciones, sexo, fecha_nacimiento, telefono, email, direccion, zona
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            a.get("fecha"), a.get("programa"), a.get("convenio"), a.get("institucion"),
            a.get("departamento"), a.get("municipio"), a.get("localidad"),
            a.get("profesional"), a.get("documento"), a.get("nombre"), a.get("actividad"),
            int(a.get("atendido") or 0), int(a.get("registrado_panacea") or 0),
            int(a.get("paciente_creado_panacea") or 0), int(a.get("paciente_priorizado") or 0),
            a.get("tipo_contacto"), int(a.get("duracion_minutos") or 0),
            a.get("observaciones"), a.get("sexo"), a.get("fecha_nacimiento"),
            a.get("telefono"), a.get("email"), a.get("direccion"), a.get("zona")
        ))

# ---------------------------------------------------------------------
# UI: Login
# ---------------------------------------------------------------------
def ui_login():
    st.subheader("Ingreso")
    u = st.text_input("Usuario", key=k("login","user"))
    p = st.text_input("Contraseña", type="password", key=k("login","pass"))
    if st.button("Ingresar", key=k("login","btn")):
        cx = db()
        row = cx.execute(
            "SELECT * FROM usuarios WHERE username=? AND password=?", (u, p)
        ).fetchone()
        if row:
            st.session_state["user"] = dict(row)
            st.success(f"Bienvenido {row['username']} · Rol {row['role']}")
            st.rerun()
        else:
            st.error("Credenciales inválidas")

# ---------------------------------------------------------------------
# UI: Registrar atenciones (incluye Paciente priorizado)
# ---------------------------------------------------------------------
ACTIVIDADES = [
    "VALORACION INICIAL POR PSICOLOGIA",
    "CONTIGO PROFE EN AULA",
    "PRIMEROS AUXILIOS PSICOLOGICO",
    "APOYO TERAPEUTICO Y SEGUIMIENTO"
]
TIPO_CONTACTO = ["Presencial","Virtual","Telefónico","Domiciliario","Otro"]

def ui_registrar_atenciones(user):
    st.markdown("### Registrar atenciones")

    with st.form(key=k("reg","form")):
        c1, c2, c3 = st.columns(3)
        programa = c1.text_input("Programa", key=k("reg","programa"))
        convenio = c2.text_input("Convenio", key=k("reg","convenio"))
        profesional = c3.text_input("Profesional", value=user["username"], key=k("reg","prof"))
        c4, c5, c6 = st.columns(3)
        institucion = c4.text_input("Institución", key=k("reg","inst"))
        departamento = c5.text_input("Departamento", key=k("reg","dpto"))
        municipio = c6.text_input("Municipio", key=k("reg","mpio"))
        c7, c8 = st.columns(2)
        localidad = c7.text_input("Localidad (Bogotá)", key=k("reg","loc"))
        fecha = c8.date_input("Fecha", value=date.today(), key=k("reg","fecha"))
        actividad = st.selectbox("Actividad/Plantilla", options=ACTIVIDADES, key=k("reg","act"))

        st.divider()
        st.markdown("**Paciente**")
        cc1, cc2, cc3 = st.columns([1,1,1])
        documento = cc1.text_input("Documento", key=k("reg","doc"))
        if cc2.form_submit_button("Buscar", use_container_width=True):
            if documento:
                r = get_paciente(documento)
                if r:
                    # Autorrelleno a session_state
                    st.session_state[k("reg","nombre")] = r["nombre"] or ""
                    st.session_state[k("reg","sexo")] = r["sexo"] or ""
                    st.session_state[k("reg","fec")] = r["fecha_nacimiento"] or ""
                    st.session_state[k("reg","tel")] = r["telefono"] or ""
                    st.session_state[k("reg","mail")] = r["email"] or ""
                    st.session_state[k("reg","dir")] = r["direccion"] or ""
                    st.session_state[k("reg","locpac")] = r["localidad"] or ""
                    st.session_state[k("reg","mpiopac")] = r["municipio"] or ""
                    st.session_state[k("reg","dptopac")] = r["departamento"] or ""
                    st.session_state[k("reg","zona")] = r["zona"] or ""
                    st.session_state[k("reg","prio")] = int(r["priorizado"] or 0)
                    st.success("Paciente encontrado y autocompletado.")
                else:
                    st.info("Paciente no existe. Completa los datos para crearlo al guardar.")
            else:
                st.warning("Digita un documento para buscar.")

        nombre = st.text_input("Nombre", value=st.session_state.get(k("reg","nombre"), ""), key=k("reg","nombre_in"))
        cpa1, cpa2, cpa3 = st.columns(3)
        sexo = cpa1.selectbox("Sexo", ["","M","F","Otro"], index=0, key=k("reg","sexo_in"),
                              placeholder="Selecciona…")
        fecha_nacimiento = cpa2.text_input("Fecha nacimiento (YYYY-MM-DD)",
                                           value=st.session_state.get(k("reg","fec"), ""), key=k("reg","fec_in"))
        telefono = cpa3.text_input("Teléfono", value=st.session_state.get(k("reg","tel"), ""), key=k("reg","tel_in"))
        cpa4, cpa5 = st.columns(2)
        email = cpa4.text_input("Email", value=st.session_state.get(k("reg","mail"), ""), key=k("reg","mail_in"))
        direccion = cpa5.text_input("Dirección", value=st.session_state.get(k("reg","dir"), ""), key=k("reg","dir_in"))
        cpa6, cpa7, cpa8 = st.columns(3)
        localidad_p = cpa6.text_input("Localidad", value=st.session_state.get(k("reg","locpac"), ""), key=k("reg","locp_in"))
        municipio_p = cpa7.text_input("Municipio", value=st.session_state.get(k("reg","mpiopac"), ""), key=k("reg","mpiop_in"))
        departamento_p = cpa8.text_input("Departamento", value=st.session_state.get(k("reg","dptopac"), ""), key=k("reg","dptop_in"))
        zona = st.selectbox("Zona (Rural/Urbana)", ["","Rural","Urbana"], index=0,
                            key=k("reg","zona_in"))
        # ✅ Nuevo check: Paciente priorizado
        paciente_priorizado = st.checkbox("Paciente priorizado", value=bool(st.session_state.get(k("reg","prio"), False)),
                                          key=k("reg","priorizado_chk"))

        st.divider()
        st.markdown("**Estado de la atención**")
        csa1, csa2, csa3 = st.columns(3)
        atendido = csa1.selectbox("Atendido", ["No","Sí"], index=0, key=k("reg","aten"))
        tipo_contacto = csa2.selectbox("Tipo de contacto", TIPO_CONTACTO, key=k("reg","tcont"))
        duracion = csa3.number_input("Duración (min)", min_value=0, step=5, key=k("reg","dur"))
        csa4, csa5 = st.columns(2)
        registrado_panacea = csa4.checkbox("Atención registrada en Panacea", key=k("reg","regp"))
        paciente_creado_panacea = csa5.checkbox("Paciente creado en Panacea", key=k("reg","pacp"))
        observaciones = st.text_area("Observaciones", key=k("reg","obs"))

        submitted = st.form_submit_button("Guardar atención", use_container_width=True)
        if submitted:
            if not documento or not nombre:
                st.error("Documento y nombre del paciente son obligatorios.")
            else:
                # Upsert Paciente, incluyendo priorizado ✅
                upsert_paciente({
                    "documento": documento,
                    "nombre": nombre,
                    "fecha_nacimiento": fecha_nacimiento,
                    "sexo": sexo,
                    "telefono": telefono,
                    "email": email,
                    "direccion": direccion,
                    "localidad": localidad_p,
                    "municipio": municipio_p,
                    "departamento": departamento_p,
                    "zona": zona,
                    "priorizado": 1 if paciente_priorizado else 0
                })
                # Insert atención (snapshot incluye paciente_priorizado) ✅
                insert_atencion({
                    "fecha": str(fecha),
                    "programa": programa,
                    "convenio": convenio,
                    "institucion": institucion,
                    "departamento": departamento,
                    "municipio": municipio,
                    "localidad": localidad,
                    "profesional": profesional,
                    "documento": documento,
                    "nombre": nombre,
                    "actividad": actividad,
                    "atendido": 1 if atendido == "Sí" else 0,
                    "registrado_panacea": 1 if registrado_panacea else 0,
                    "paciente_creado_panacea": 1 if paciente_creado_panacea else 0,
                    "paciente_priorizado": 1 if paciente_priorizado else 0,  # ✅
                    "tipo_contacto": tipo_contacto,
                    "duracion_minutos": duracion,
                    "observaciones": observaciones,
                    "sexo": sexo,
                    "fecha_nacimiento": fecha_nacimiento,
                    "telefono": telefono,
                    "email": email,
                    "direccion": direccion,
                    "zona": zona
                })
                st.success("Atención guardada correctamente.")

# ---------------------------------------------------------------------
# UI: Carga masiva (Pacientes, Profesionales, Atenciones)
# Incluye columna 'paciente_priorizado' para Atenciones ✅
# ---------------------------------------------------------------------
PLANTILLA_ATENCIONES_COLS = [
    "fecha","programa","convenio","institucion","departamento","municipio","localidad",
    "profesional","documento","nombre","actividad","atendido",
    "registrado_panacea","paciente_creado_panacea","paciente_priorizado",  # ✅ aquí
    "tipo_contacto","duracion_minutos","observaciones",
    "sexo","fecha_nacimiento","telefono","email","direccion","zona"
]

def ui_cargas_masivas(user):
    st.markdown("### Cargas masivas")

    st.markdown("**Plantillas de ejemplo (CSV):**")
    ctpl1, ctpl2, ctpl3 = st.columns(3)
    # Pacientes
    pac_tpl = pd.DataFrame([{
        "documento":"12345678","nombre":"Juan Pérez","fecha_nacimiento":"2008-05-14",
        "sexo":"M","telefono":"3001234567","email":"juan@example.com","direccion":"Calle 1 #2-3",
        "localidad":"Usaquén","municipio":"Bogotá","departamento":"Cundinamarca","zona":"Urbana","priorizado":1
    }])
    ctpl1.download_button("Plantilla pacientes.csv", pac_tpl.to_csv(index=False).encode("utf-8"),
                          file_name="plantilla_pacientes.csv", mime="text/csv", key=k("tpl","pac"))
    # Profesionales
    prof_tpl = pd.DataFrame([{
        "documento":"987654","nombre":"Profe Demo","telefono":"3009876543","email":"profe@example.com",
        "programa":"Programa Demo","convenio":"Convenio Demo"
    }])
    ctpl2.download_button("Plantilla profesionales.csv", prof_tpl.to_csv(index=False).encode("utf-8"),
                          file_name="plantilla_profesionales.csv", mime="text/csv", key=k("tpl","prof"))
    # Atenciones (incluye paciente_priorizado) ✅
    atn_tpl = pd.DataFrame([{
        "fecha":"2025-11-10","programa":"Programa Demo","convenio":"Convenio Demo","institucion":"Colegio A",
        "departamento":"Cundinamarca","municipio":"Bogotá","localidad":"Usaquén","profesional":user["username"],
        "documento":"12345678","nombre":"Juan Pérez","actividad":"VALORACION INICIAL POR PSICOLOGIA","atendido":"Si",
        "registrado_panacea":"No","paciente_creado_panacea":"Si","paciente_priorizado":"Si",  # ✅
        "tipo_contacto":"Presencial","duracion_minutos":30,"observaciones":"Demo","sexo":"M",
        "fecha_nacimiento":"2008-05-14","telefono":"3001234567","email":"juan@example.com",
        "direccion":"Calle 1 #2-3","zona":"Urbana"
    }])
    ctpl3.download_button("Plantilla atenciones.csv", atn_tpl.to_csv(index=False).encode("utf-8"),
                          file_name="plantilla_atenciones.csv", mime="text/csv", key=k("tpl","atn"))

    st.divider()
    tabs = st.tabs(["Pacientes","Profesionales","Atenciones"])

    # --- Pacientes
    with tabs[0]:
        up = st.file_uploader("Cargar Pacientes (CSV/Excel)", key=k("up","pac"))
        if st.button("Procesar Pacientes", key=k("btn","pac")):
            try:
                df = read_table_file(up)
                # Validación mínima
                need = {"documento","nombre"}
                if not need.issubset(set(map(str.lower, df.columns))):
                    st.error("El archivo debe contener al menos las columnas 'documento' y 'nombre'.")
                else:
                    # Normalizamos mínimo juego de columnas
                    low = {c.lower(): c for c in df.columns}
                    for _, r in df.iterrows():
                        row = {c: r[low[c]] if c in low else None for c in
                               ["documento","nombre","fecha_nacimiento","sexo","telefono","email",
                                "direccion","localidad","municipio","departamento","zona","priorizado"]}
                        # Map si priorizado viene como texto
                        pr = row.get("priorizado")
                        if isinstance(pr, str):
                            pr = 1 if pr.strip().lower() in ("si","sí","1","true","x") else 0
                        row["priorizado"] = int(pr or 0)
                        upsert_paciente(row)
                    st.success("Pacientes procesados.")
            except Exception as e:
                st.error(f"Error procesando pacientes: {e}")

    # --- Profesionales
    with tabs[1]:
        up = st.file_uploader("Cargar Profesionales (CSV/Excel)", key=k("up","prof"))
        if st.button("Procesar Profesionales", key=k("btn","prof")):
            try:
                df = read_table_file(up)
                need = {"documento","nombre"}
                if not need.issubset(set(map(str.lower, df.columns))):
                    st.error("El archivo debe contener al menos las columnas 'documento' y 'nombre'.")
                else:
                    cx = db()
                    low = {c.lower(): c for c in df.columns}
                    with cx:
                        for _, r in df.iterrows():
                            doc = str(r[low["documento"]])
                            nombre = str(r[low["nombre"]])
                            telefono = str(r[low.get("telefono","")]) if "telefono" in low else ""
                            email = str(r[low.get("email","")]) if "email" in low else ""
                            programa = str(r[low.get("programa","")]) if "programa" in low else ""
                            convenio = str(r[low.get("convenio","")]) if "convenio" in low else ""
                            cur = cx.execute("SELECT id FROM profesionales WHERE documento=?", (doc,)).fetchone()
                            if cur:
                                cx.execute("""UPDATE profesionales SET
                                    nombre=?, telefono=?, email=?, programa=?, convenio=?
                                    WHERE documento=?""", (nombre, telefono, email, programa, convenio, doc))
                            else:
                                cx.execute("""INSERT INTO profesionales(
                                    documento, nombre, telefono, email, programa, convenio
                                ) VALUES(?,?,?,?,?,?)""", (doc, nombre, telefono, email, programa, convenio))
                    st.success("Profesionales procesados.")
            except Exception as e:
                st.error(f"Error procesando profesionales: {e}")

    # --- Atenciones (incluye paciente_priorizado) ✅
    with tabs[2]:
        up = st.file_uploader("Cargar Atenciones (CSV/Excel)", key=k("up","atn"))
        st.caption("Columnas esperadas (mínimas): documento, nombre, fecha, actividad. "
                   "Opcionales: paciente_creado_panacea, registrado_panacea, paciente_priorizado, etc.")
        if st.button("Procesar Atenciones", key=k("btn","atn")):
            try:
                df = read_table_file(up)
                # Normalizar columnas a minúsculas y strip
                df.columns = [c.strip() for c in df.columns]
                low = {c.lower(): c for c in df.columns}

                # Validación mínima
                need = {"documento","nombre","fecha","actividad"}
                if not need.issubset(set(map(str.lower, df.columns))):
                    st.error("El archivo debe contener columnas mínimas: documento, nombre, fecha, actividad.")
                else:
                    for _, r in df.iterrows():
                        # Map base paciente
                        pac = {
                            "documento": str(r[low["documento"]]).strip(),
                            "nombre": str(r[low["nombre"]]).strip(),
                            "fecha_nacimiento": str(r[low["fecha_nacimiento"]]).strip() if "fecha_nacimiento" in low else "",
                            "sexo": str(r[low["sexo"]]).strip() if "sexo" in low else "",
                            "telefono": str(r[low["telefono"]]).strip() if "telefono" in low else "",
                            "email": str(r[low["email"]]).strip() if "email" in low else "",
                            "direccion": str(r[low["direccion"]]).strip() if "direccion" in low else "",
                            "localidad": str(r[low["localidad"]]).strip() if "localidad" in low else "",
                            "municipio": str(r[low["municipio"]]).strip() if "municipio" in low else "",
                            "departamento": str(r[low["departamento"]]).strip() if "departamento" in low else "",
                            "zona": str(r[low["zona"]]).strip() if "zona" in low else "",
                            "priorizado": 0
                        }
                        # priorizado puede venir como Si/No, 1/0, True/False
                        if "paciente_priorizado" in low:
                            pv = str(r[low["paciente_priorizado"]]).strip().lower()
                            pac["priorizado"] = 1 if pv in ("si","sí","1","true","x") else 0

                        upsert_paciente(pac)  # sincroniza ficha

                        # Map atención
                        def to_int_bool(val):
                            s = str(val).strip().lower()
                            return 1 if s in ("si","sí","1","true","x") else 0

                        atn = {
                            "fecha": str(r[low["fecha"]]).strip(),
                            "programa": str(r[low["programa"]]).strip() if "programa" in low else "",
                            "convenio": str(r[low["convenio"]]).strip() if "convenio" in low else "",
                            "institucion": str(r[low["institucion"]]).strip() if "institucion" in low else "",
                            "departamento": pac["departamento"],
                            "municipio": pac["municipio"],
                            "localidad": pac["localidad"],
                            "profesional": str(r[low["profesional"]]).strip() if "profesional" in low else user["username"],
                            "documento": pac["documento"],
                            "nombre": pac["nombre"],
                            "actividad": str(r[low["actividad"]]).strip(),
                            "atendido": to_int_bool(r[low["atendido"]]) if "atendido" in low else 0,
                            "registrado_panacea": to_int_bool(r[low["registrado_panacea"]]) if "registrado_panacea" in low else 0,
                            "paciente_creado_panacea": to_int_bool(r[low["paciente_creado_panacea"]]) if "paciente_creado_panacea" in low else 0,
                            "paciente_priorizado": pac["priorizado"],  # snapshot ✅
                            "tipo_contacto": str(r[low["tipo_contacto"]]).strip() if "tipo_contacto" in low else "",
                            "duracion_minutos": int(r[low["duracion_minutos"]]) if "duracion_minutos" in low and pd.notna(r[low["duracion_minutos"]]) else 0,
                            "observaciones": str(r[low["observaciones"]]).strip() if "observaciones" in low else "",
                            "sexo": pac["sexo"],
                            "fecha_nacimiento": pac["fecha_nacimiento"],
                            "telefono": pac["telefono"],
                            "email": pac["email"],
                            "direccion": pac["direccion"],
                            "zona": pac["zona"]
                        }
                        insert_atencion(atn)
                    st.success("Atenciones procesadas.")
            except Exception as e:
                st.error(f"Error procesando atenciones: {e}")

# ---------------------------------------------------------------------
# UI: Listado simple
# ---------------------------------------------------------------------
def ui_listado(user):
    st.markdown("### Listado de atenciones")
    cx = db()
    df = pd.read_sql_query("SELECT * FROM atenciones ORDER BY date(fecha) DESC, id DESC", cx)
    st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------------------
# UI: Viáticos, Planificador, Papelería (simples)
# ---------------------------------------------------------------------
def ui_viaticos(user):
    st.markdown("### Viáticos")
    with st.form(key=k("via","form")):
        req = st.selectbox("¿Requiere viáticos?", ["No","Sí"], key=k("via","req"))
        origen = st.text_input("Origen", key=k("via","ori"))
        destino = st.text_input("Destino", key=k("via","des"))
        valor = st.number_input("Valor", min_value=0.0, step=1000.0, key=k("via","val"))
        obs = st.text_area("Observaciones", key=k("via","obs"))
        if st.form_submit_button("Guardar viático", use_container_width=True):
            cx = db()
            with cx:
                cx.execute("""INSERT INTO viaticos(username,requiere,origen,destino,valor,observaciones,fecha)
                              VALUES(?,?,?,?,?,?,?)""",
                           (user["username"], 1 if req=="Sí" else 0, origen, destino, valor, obs, str(date.today())))
            st.success("Viático guardado.")
    st.subheader("Historial")
    cx = db()
    df = pd.read_sql_query("SELECT * FROM viaticos WHERE username=? ORDER BY id DESC", cx, params=(user["username"],))
    st.dataframe(df, use_container_width=True)

def ui_planificador(user):
    st.markdown("### Planificador")
    with st.form(key=k("pla","form")):
        f = st.date_input("Fecha", value=date.today(), key=k("pla","f"))
        h1 = st.time_input("Hora inicio", value=time(8,0), key=k("pla","h1"))
        h2 = st.time_input("Hora fin", value=time(9,0), key=k("pla","h2"))
        titulo = st.text_input("Título", key=k("pla","tit"))
        desc = st.text_area("Descripción", key=k("pla","des"))
        programa = st.text_input("Programa (opcional)", key=k("pla","prog"))
        convenio = st.text_input("Convenio (opcional)", key=k("pla","conv"))
        institucion = st.text_input("Institución (opcional)", key=k("pla","inst"))
        if st.form_submit_button("Guardar evento", use_container_width=True):
            cx = db()
            with cx:
                cx.execute("""INSERT INTO planificador(username,fecha,hora_ini,hora_fin,titulo,descripcion,programa,convenio,institucion)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           (user["username"], str(f), str(h1), str(h2), titulo, desc, programa, convenio, institucion))
            st.success("Evento guardado.")
    st.subheader("Mis eventos")
    cx = db()
    df = pd.read_sql_query("SELECT * FROM planificador WHERE username=? ORDER BY date(fecha) DESC, id DESC",
                           cx, params=(user["username"],))
    st.dataframe(df, use_container_width=True)

def ui_papeleria(user):
    st.markdown("### Papelería")
    with st.form(key=k("pap","form")):
        item = st.text_input("Item", key=k("pap","item"))
        cant = st.number_input("Cantidad", min_value=1, step=1, key=k("pap","cant"))
        estado = st.selectbox("Estado", ["Solicitado","Aprobado","Entregado"], key=k("pap","est"))
        obs = st.text_area("Observaciones", key=k("pap","obs"))
        if st.form_submit_button("Guardar solicitud", use_container_width=True):
            cx = db()
            with cx:
                cx.execute("""INSERT INTO papeleria(username,item,cantidad,estado,observaciones,fecha)
                              VALUES(?,?,?,?,?,?)""", (user["username"], item, cant, estado, obs, str(date.today())))
            st.success("Solicitud registrada.")
    st.subheader("Mis solicitudes")
    cx = db()
    df = pd.read_sql_query("SELECT * FROM papeleria WHERE username=? ORDER BY id DESC", cx, params=(user["username"],))
    st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_schema()
    st.title(APP_TITLE)

    user = st.session_state.get("user")
    if not user:
        ui_login()
        return

    # Tabs por rol
    if user["role"] == "Admin":
        tabs = st.tabs(["Registrar atenciones","Cargas masivas","Listado","Viáticos","Planificador","Papelería"])
    else:
        tabs = st.tabs(["Registrar atenciones","Cargas masivas","Listado","Viáticos","Planificador","Papelería"])

    with tabs[0]:
        ui_registrar_atenciones(user)
    with tabs[1]:
        ui_cargas_masivas(user)
    with tabs[2]:
        ui_listado(user)
    with tabs[3]:
        ui_viaticos(user)
    with tabs[4]:
        ui_planificador(user)
    with tabs[5]:
        ui_papeleria(user)

    st.sidebar.info(f"Usuario: **{user['username']}** · Rol: **{user['role']}**")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.pop("user", None)
        st.rerun()

if __name__ == "__main__":
    main()
