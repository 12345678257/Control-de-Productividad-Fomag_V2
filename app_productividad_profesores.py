# app_productividad_profesores.py
# -------------------------------------------------------------
# Productividad de Profesionales (SQLite, roles, viáticos, agenda)
# -------------------------------------------------------------

from datetime import datetime, date, time as dtime
from typing import Optional, Dict, Any, List

import io
import sqlite3

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_TITLE = "Productividad de Profesionales"
APP_ICON = "📊"
DB_SQLITE_PATH = "productividad_profesores.db"

ACTIVIDADES_PLANTILLAS = [
    "VALORACION INICIAL POR PSICOLOGIA",
    "CONTIGO PROFE EN AULA",
    "PRIMEROS AUXILIOS PSICOLOGICO",
    "APOYO TERAPEUTICO Y SEGUIMIENTO",
]

TIPOS_CONTACTO = ["Presencial", "Virtual", "Telefónico", "Otro"]

# Usuarios y roles simples en memoria
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "pro": {"password": "pro123", "role": "profesional"},
}

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")


def _now_tzless() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def success_toast(msg: str):
    st.toast(msg, icon="✅")


def warn_toast(msg: str):
    st.toast(msg, icon="⚠️")


def error_toast(msg: str):
    st.toast(msg, icon="❌")


def get_sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


SQLITE_CONN: sqlite3.Connection = get_sqlite_conn()

# Definición del esquema SQLite
SQLITE_DDL: Dict[str, str] = {
    "programas": """
        CREATE TABLE IF NOT EXISTS programas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1
        );
    """,
    "convenios": """
        CREATE TABLE IF NOT EXISTS convenios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            programa_id INTEGER NOT NULL,
            activo INTEGER DEFAULT 1,
            UNIQUE(nombre, programa_id),
            FOREIGN KEY(programa_id) REFERENCES programas(id)
        );
    """,
    "instituciones": """
        CREATE TABLE IF NOT EXISTS instituciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            activo INTEGER DEFAULT 1,
            UNIQUE(nombre, municipio, departamento)
        );
    """,
    "profesores": """
        CREATE TABLE IF NOT EXISTS profesores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            documento TEXT,
            email TEXT,
            programa_id INTEGER,
            convenio_id INTEGER,
            zona TEXT,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id)
        );
    """,
    "pacientes": """
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_documento TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            fecha_nacimiento TEXT,
            sexo TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            zona TEXT,
            activo INTEGER DEFAULT 1
        );
    """,
    "registros": """
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            programa_id INTEGER NOT NULL,
            convenio_id INTEGER NOT NULL,
            institucion_id INTEGER NOT NULL,
            profesor_id INTEGER NOT NULL,
            paciente_id INTEGER,
            localidad TEXT,
            municipio TEXT,
            departamento TEXT,
            numero_paciente TEXT,
            nombre_paciente TEXT,
            actividad TEXT,
            atendido INTEGER,
            registrado_panacea INTEGER,
            duracion_minutos INTEGER,
            tipo_contacto TEXT,
            pacientes_programados INTEGER NOT NULL,
            pacientes_atendidos INTEGER NOT NULL,
            observaciones TEXT,
            creado_por TEXT,
            creado_en TEXT,
            actualizado_en TEXT,
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id),
            FOREIGN KEY(institucion_id) REFERENCES instituciones(id),
            FOREIGN KEY(profesor_id) REFERENCES profesores(id),
            FOREIGN KEY(paciente_id) REFERENCES pacientes(id)
        );
    """,
    "viaticos": """
        CREATE TABLE IF NOT EXISTS viaticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            programa_id INTEGER,
            convenio_id INTEGER,
            institucion_id INTEGER,
            profesor_id INTEGER,
            requiere_viatico INTEGER NOT NULL,
            origen TEXT,
            destino TEXT,
            valor REAL,
            observaciones TEXT,
            creado_por TEXT,
            creado_en TEXT,
            actualizado_en TEXT,
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id),
            FOREIGN KEY(institucion_id) REFERENCES instituciones(id),
            FOREIGN KEY(profesor_id) REFERENCES profesores(id)
        );
    """,
    "agenda": """
        CREATE TABLE IF NOT EXISTS agenda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fin TEXT,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            programa_id INTEGER,
            convenio_id INTEGER,
            institucion_id INTEGER,
            profesor_id INTEGER,
            creado_por TEXT,
            creado_en TEXT,
            actualizado_en TEXT,
            FOREIGN KEY(programa_id) REFERENCES programas(id),
            FOREIGN KEY(convenio_id) REFERENCES convenios(id),
            FOREIGN KEY(institucion_id) REFERENCES instituciones(id),
            FOREIGN KEY(profesor_id) REFERENCES profesores(id)
        );
    """,
}


def ensure_sqlite_schema():
    """Crea o ajusta el esquema de SQLite si hace falta."""
    with SQLITE_CONN:
        for ddl in SQLITE_DDL.values():
            SQLITE_CONN.execute(ddl)

        # Asegurar columnas nuevas en registros si ya existía
        cur = SQLITE_CONN.execute("PRAGMA table_info(registros);")
        existing_reg = {row["name"] for row in cur.fetchall()}
        needed_reg = {
            "numero_paciente": "ALTER TABLE registros ADD COLUMN numero_paciente TEXT;",
            "nombre_paciente": "ALTER TABLE registros ADD COLUMN nombre_paciente TEXT;",
            "actividad": "ALTER TABLE registros ADD COLUMN actividad TEXT;",
            "atendido": "ALTER TABLE registros ADD COLUMN atendido INTEGER;",
            "registrado_panacea": "ALTER TABLE registros ADD COLUMN registrado_panacea INTEGER;",
            "duracion_minutos": "ALTER TABLE registros ADD COLUMN duracion_minutos INTEGER;",
            "tipo_contacto": "ALTER TABLE registros ADD COLUMN tipo_contacto TEXT;",
            "paciente_id": "ALTER TABLE registros ADD COLUMN paciente_id INTEGER;",
        }
        for col, stmt in needed_reg.items():
            if col not in existing_reg:
                SQLITE_CONN.execute(stmt)

        # Asegurar zona en pacientes
        cur = SQLITE_CONN.execute("PRAGMA table_info(pacientes);")
        existing_pac = {row["name"] for row in cur.fetchall()}
        if "zona" not in existing_pac:
            SQLITE_CONN.execute("ALTER TABLE pacientes ADD COLUMN zona TEXT;")

        # Asegurar zona en profesores
        cur = SQLITE_CONN.execute("PRAGMA table_info(profesores);")
        existing_prof = {row["name"] for row in cur.fetchall()}
        if "zona" not in existing_prof:
            SQLITE_CONN.execute("ALTER TABLE profesores ADD COLUMN zona TEXT;")


ensure_sqlite_schema()


# -------------------------------------------------------------
# Capa de acceso a datos
# -------------------------------------------------------------
class DataAccess:
    def __init__(self, sqlite_conn: sqlite3.Connection):
        self.sqlite = sqlite_conn

    # -------- Programas --------
    def list_programas(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM programas WHERE activo=1 ORDER BY nombre", self.sqlite
        )

    def upsert_programa(self, nombre: str) -> None:
        if not nombre:
            return
        nombre = nombre.strip()
        with self.sqlite:
            self.sqlite.execute(
                "INSERT OR IGNORE INTO programas(nombre, activo) VALUES(?,1)", (nombre,)
            )

    # -------- Convenios --------
    def list_convenios(self, programa_id: Optional[int] = None) -> pd.DataFrame:
        base = "SELECT * FROM convenios WHERE activo=1"
        params: List[Any] = []
        if programa_id:
            base += " AND programa_id=?"
            params.append(programa_id)
        base += " ORDER BY nombre"
        return pd.read_sql_query(base, self.sqlite, params=params)

    def upsert_convenio(self, nombre: str, programa_id: int) -> None:
        if not (nombre and programa_id):
            return
        nombre = nombre.strip()
        with self.sqlite:
            self.sqlite.execute(
                "INSERT OR IGNORE INTO convenios(nombre, programa_id, activo) VALUES(?,?,1)",
                (nombre, programa_id),
            )

    # -------- Instituciones --------
    def list_instituciones(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM instituciones WHERE activo=1 ORDER BY departamento, municipio, nombre",
            self.sqlite,
        )

    def upsert_institucion(
        self, nombre: str, localidad: Optional[str], municipio: Optional[str], departamento: Optional[str]
    ) -> None:
        if not nombre:
            return
        nombre = nombre.strip()
        with self.sqlite:
            self.sqlite.execute(
                """
                INSERT OR IGNORE INTO instituciones(nombre, localidad, municipio, departamento, activo)
                VALUES(?,?,?,?,1)
                """,
                (nombre, localidad or None, municipio or None, departamento or None),
            )

    # -------- Profesores --------
    def list_profesores(
        self, programa_id: Optional[int] = None, convenio_id: Optional[int] = None
    ) -> pd.DataFrame:
        base = "SELECT * FROM profesores WHERE activo=1"
        params: List[Any] = []
        if programa_id:
            base += " AND programa_id=?"
            params.append(programa_id)
        if convenio_id:
            base += " AND convenio_id=?"
            params.append(convenio_id)
        base += " ORDER BY nombre"
        return pd.read_sql_query(base, self.sqlite, params=params)

    def upsert_profesor(
        self,
        nombre: str,
        documento: Optional[str],
        email: Optional[str],
        programa_id: Optional[int],
        convenio_id: Optional[int],
        zona: Optional[str] = None,
    ) -> None:
        if not nombre:
            return
        nombre = nombre.strip()
        documento = documento.strip() if documento else None
        email = email.strip() if email else None
        with self.sqlite:
            self.sqlite.execute(
                """
                INSERT INTO profesores(nombre, documento, email, programa_id, convenio_id, zona, activo)
                VALUES(?,?,?,?,?,?,1)
                """,
                (nombre, documento, email, programa_id, convenio_id, zona),
            )

    # -------- Pacientes --------
    def list_pacientes(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM pacientes WHERE activo=1 ORDER BY nombre", self.sqlite
        )

    def get_paciente_por_documento(
        self, numero_documento: str
    ) -> Optional[Dict[str, Any]]:
        numero_documento = (numero_documento or "").strip()
        if not numero_documento:
            return None
        cur = self.sqlite.execute(
            "SELECT * FROM pacientes WHERE numero_documento=? AND activo=1",
            (numero_documento,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def upsert_paciente(
        self,
        numero_documento: str,
        nombre: str,
        fecha_nacimiento: Optional[str] = None,
        sexo: Optional[str] = None,
        telefono: Optional[str] = None,
        email: Optional[str] = None,
        direccion: Optional[str] = None,
        localidad: Optional[str] = None,
        municipio: Optional[str] = None,
        departamento: Optional[str] = None,
        zona: Optional[str] = None,
    ) -> int:
        numero_documento = (numero_documento or "").strip()
        nombre = (nombre or "").strip()
        if not numero_documento or not nombre:
            raise ValueError("Documento y nombre de paciente son obligatorios")

        cur = self.sqlite.execute(
            "SELECT id FROM pacientes WHERE numero_documento=?", (numero_documento,)
        )
        row = cur.fetchone()
        data_tuple = (
            nombre,
            fecha_nacimiento,
            sexo,
            telefono,
            email,
            direccion,
            localidad,
            municipio,
            departamento,
            zona,
        )
        if row:
            pac_id = int(row["id"])
            with self.sqlite:
                self.sqlite.execute(
                    """
                    UPDATE pacientes
                    SET nombre=?, fecha_nacimiento=?, sexo=?, telefono=?, email=?,
                        direccion=?, localidad=?, municipio=?, departamento=?, zona=?
                    WHERE id=?
                    """,
                    (*data_tuple, pac_id),
                )
            return pac_id
        with self.sqlite:
            cur2 = self.sqlite.execute(
                """
                INSERT INTO pacientes(
                    numero_documento, nombre, fecha_nacimiento, sexo, telefono,
                    email, direccion, localidad, municipio, departamento, zona, activo
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (numero_documento, *data_tuple),
            )
        return int(cur2.lastrowid)

    # -------- Registros de atenciones --------
    def insert_registro(
        self,
        fecha: date,
        programa_id: int,
        convenio_id: int,
        institucion_id: int,
        profesor_id: int,
        paciente_id: Optional[int],
        localidad: Optional[str],
        municipio: Optional[str],
        departamento: Optional[str],
        numero_paciente: str,
        nombre_paciente: str,
        actividad: str,
        atendido: bool,
        registrado_panacea: bool,
        duracion_minutos: Optional[int],
        tipo_contacto: Optional[str],
        observaciones: Optional[str],
        creado_por: Optional[str],
    ) -> None:
        pacientes_programados = 1
        pacientes_atendidos = 1 if atendido else 0
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "paciente_id": paciente_id,
            "localidad": localidad or None,
            "municipio": municipio or None,
            "departamento": departamento or None,
            "numero_paciente": (numero_paciente or "").strip() or None,
            "nombre_paciente": (nombre_paciente or "").strip() or None,
            "actividad": actividad,
            "atendido": 1 if atendido else 0,
            "registrado_panacea": 1 if registrado_panacea else 0,
            "duracion_minutos": int(duracion_minutos) if duracion_minutos is not None else None,
            "tipo_contacto": tipo_contacto or None,
            "pacientes_programados": pacientes_programados,
            "pacientes_atendidos": pacientes_atendidos,
            "observaciones": observaciones or None,
            "creado_por": creado_por,
            "creado_en": _now_tzless(),
            "actualizado_en": _now_tzless(),
        }
        cols = ",".join(row.keys())
        placeholders = ",".join(["?"] * len(row))
        with self.sqlite:
            self.sqlite.execute(
                f"INSERT INTO registros ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )

    def list_registros(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        base = (
            "SELECT r.*, "
            "p.nombre AS programa, "
            "c.nombre AS convenio, "
            "i.nombre AS institucion, "
            "f.nombre AS profesor, "
            "f.email AS profesor_email "
            "FROM registros r "
            "LEFT JOIN programas p ON p.id = r.programa_id "
            "LEFT JOIN convenios c ON c.id = r.convenio_id "
            "LEFT JOIN instituciones i ON i.id = r.institucion_id "
            "LEFT JOIN profesores f ON f.id = r.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            base += " AND date(r.fecha) >= date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            base += " AND date(r.fecha) <= date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                base += f" AND r.{k} = ?"
                params.append(filtros[k])
        if filtros.get("actividad"):
            base += " AND r.actividad = ?"
            params.append(filtros["actividad"])
        base += " ORDER BY r.fecha DESC, r.id DESC"
        df = pd.read_sql_query(base, self.sqlite, params=params)

        if not df.empty:
            df["pacientes_programados"] = df["pacientes_programados"].fillna(0)
            df["pacientes_atendidos"] = df["pacientes_atendidos"].fillna(0)
            df["no_asistieron"] = df["pacientes_programados"] - df["pacientes_atendidos"]
            df["tasa_atencion"] = np.where(
                df["pacientes_programados"] > 0,
                df["pacientes_atendidos"] / df["pacientes_programados"],
                np.nan,
            )
        return df

    def delete_registro(self, registro_id: int) -> None:
        with self.sqlite:
            self.sqlite.execute("DELETE FROM registros WHERE id=?", (registro_id,))

    def update_registro(self, registro_id: int, updates: Dict[str, Any]) -> None:
        updates["actualizado_en"] = _now_tzless()
        cols = ",".join([f"{k}=?" for k in updates.keys()])
        with self.sqlite:
            self.sqlite.execute(
                f"UPDATE registros SET {cols} WHERE id=?",
                (*updates.values(), registro_id),
            )

    # -------- Viáticos --------
    def insert_viatico(
        self,
        fecha: date,
        programa_id: Optional[int],
        convenio_id: Optional[int],
        institucion_id: Optional[int],
        profesor_id: Optional[int],
        requiere_viatico: bool,
        origen: Optional[str],
        destino: Optional[str],
        valor: Optional[float],
        observaciones: Optional[str],
        creado_por: Optional[str],
    ) -> None:
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "requiere_viatico": 1 if requiere_viatico else 0,
            "origen": origen or None,
            "destino": destino or None,
            "valor": float(valor) if valor is not None else None,
            "observaciones": observaciones or None,
            "creado_por": creado_por,
            "creado_en": _now_tzless(),
            "actualizado_en": _now_tzless(),
        }
        cols = ",".join(row.keys())
        placeholders = ",".join(["?"] * len(row))
        with self.sqlite:
            self.sqlite.execute(
                f"INSERT INTO viaticos ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )

    def list_viaticos(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        base = (
            "SELECT v.*, "
            "p.nombre AS programa, "
            "c.nombre AS convenio, "
            "i.nombre AS institucion, "
            "f.nombre AS profesor "
            "FROM viaticos v "
            "LEFT JOIN programas p ON p.id = v.programa_id "
            "LEFT JOIN convenios c ON c.id = v.convenio_id "
            "LEFT JOIN instituciones i ON i.id = v.institucion_id "
            "LEFT JOIN profesores f ON f.id = v.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            base += " AND date(v.fecha) >= date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            base += " AND date(v.fecha) <= date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                base += f" AND v.{k} = ?"
                params.append(filtros[k])
        base += " ORDER BY v.fecha DESC, v.id DESC"
        df = pd.read_sql_query(base, self.sqlite, params=params)
        return df

    def delete_viatico(self, viatico_id: int) -> None:
        with self.sqlite:
            self.sqlite.execute("DELETE FROM viaticos WHERE id=?", (viatico_id,))

    # -------- Agenda --------
    def insert_agenda_event(
        self,
        fecha: date,
        hora_inicio: Optional[dtime],
        hora_fin: Optional[dtime],
        titulo: str,
        descripcion: Optional[str],
        programa_id: Optional[int],
        convenio_id: Optional[int],
        institucion_id: Optional[int],
        profesor_id: Optional[int],
        creado_por: Optional[str],
    ) -> None:
        hi = hora_inicio.strftime("%H:%M") if hora_inicio else None
        hf = hora_fin.strftime("%H:%M") if hora_fin else None
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "hora_inicio": hi,
            "hora_fin": hf,
            "titulo": titulo.strip(),
            "descripcion": descripcion or None,
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "creado_por": creado_por,
            "creado_en": _now_tzless(),
            "actualizado_en": _now_tzless(),
        }
        cols = ",".join(row.keys())
        placeholders = ",".join(["?"] * len(row))
        with self.sqlite:
            self.sqlite.execute(
                f"INSERT INTO agenda ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )

    def list_agenda(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        base = (
            "SELECT a.*, "
            "p.nombre AS programa, "
            "c.nombre AS convenio, "
            "i.nombre AS institucion, "
            "f.nombre AS profesor "
            "FROM agenda a "
            "LEFT JOIN programas p ON p.id = a.programa_id "
            "LEFT JOIN convenios c ON c.id = a.convenio_id "
            "LEFT JOIN instituciones i ON i.id = a.institucion_id "
            "LEFT JOIN profesores f ON f.id = a.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            base += " AND date(a.fecha) >= date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            base += " AND date(a.fecha) <= date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                base += f" AND a.{k} = ?"
                params.append(filtros[k])
        base += " ORDER BY a.fecha ASC, a.hora_inicio ASC"
        df = pd.read_sql_query(base, self.sqlite, params=params)
        return df

    def delete_agenda_event(self, event_id: int) -> None:
        with self.sqlite:
            self.sqlite.execute("DELETE FROM agenda WHERE id=?", (event_id,))


DATA = DataAccess(SQLITE_CONN)

# -------------------------------------------------------------
# Session state y filtros
# -------------------------------------------------------------
def ensure_session_state():
    if "filters" not in st.session_state:
        st.session_state.filters = {}
    if "user" not in st.session_state:
        st.session_state.user = None
    if "role" not in st.session_state:
        st.session_state.role = None
    for key in [
        "pac_doc",
        "pac_nombre",
        "pac_fecha_nac",
        "pac_sexo",
        "pac_telefono",
        "pac_email",
        "pac_direccion",
        "pac_localidad",
        "pac_municipio",
        "pac_departamento",
        "pac_zona",
        "pac_id_actual",
    ]:
        st.session_state.setdefault(key, None)


def sidebar_filters():
    st.sidebar.header("Filtros")
    hoy = date.today()
    default_from = hoy.replace(day=1)
    default_to = hoy

    f_desde = st.sidebar.date_input(
        "Desde",
        value=st.session_state.filters.get("fecha_desde", default_from),
        key="flt_desde",
    )
    f_hasta = st.sidebar.date_input(
        "Hasta",
        value=st.session_state.filters.get("fecha_hasta", default_to),
        key="flt_hasta",
    )

    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = st.sidebar.selectbox(
        "Programa",
        options=["(Todos)"] + list(prog_map.keys()),
        key="flt_programa",
    )
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = st.sidebar.selectbox(
        "Convenio",
        options=["(Todos)"] + list(conv_map.keys()),
        key="flt_convenio",
    )
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = st.sidebar.selectbox(
        "Profesional",
        options=["(Todos)"] + list(prof_map.keys()),
        key="flt_profesional",
    )
    profesor_id = prof_map.get(prof_sel)

    actividad_sel = st.sidebar.selectbox(
        "Actividad / plantilla",
        options=["(Todas)"] + ACTIVIDADES_PLANTILLAS,
        key="flt_actividad",
    )
    actividad = None if actividad_sel == "(Todas)" else actividad_sel

    st.session_state.filters = {
        "fecha_desde": f_desde,
        "fecha_hasta": f_hasta,
        "programa_id": programa_id,
        "convenio_id": convenio_id,
        "profesor_id": profesor_id,
        "actividad": actividad,
    }


def render_login():
    with st.sidebar:
        if st.session_state.user:
            st.success(f"Sesión: {st.session_state.user} ({st.session_state.role})")
            if st.button("Cerrar sesión", key="btn_logout", use_container_width=True):
                st.session_state.user = None
                st.session_state.role = None
                st.rerun()
        else:
            st.markdown("### Iniciar sesión")
            u = st.text_input("Usuario", key="login_user")
            p = st.text_input("Contraseña", type="password", key="login_pass")
            if st.button("Ingresar", key="btn_login", use_container_width=True):
                user = USERS.get(u)
                if user and p == user["password"]:
                    st.session_state.user = u
                    st.session_state.role = user["role"]
                    success_toast("Ingreso exitoso.")
                    st.rerun()
                else:
                    error_toast("Usuario o contraseña incorrectos.")


# -------------------------------------------------------------
# UI: Registrar atenciones
# -------------------------------------------------------------
def ui_cargar_datos(auth_user: Optional[str]):
    st.subheader("Registrar atención / paciente")

    c1, c2 = st.columns([1.4, 1.4])

    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = c1.selectbox(
        "Programa",
        options=list(prog_map.keys()) if prog_map else [],
        key="form_programa",
        placeholder="Crea programas en Configuración",
    )
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else pd.DataFrame()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = c1.selectbox(
        "Convenio",
        options=list(conv_map.keys()) if conv_map else [],
        key="form_convenio",
    )
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = c2.selectbox(
        "Profesional",
        options=list(prof_map.keys()) if prof_map else [],
        key="form_profesional",
    )
    profesor_id = prof_map.get(prof_sel)

    instituciones = DATA.list_instituciones()
    institucion_id = None
    localidad_val = None
    municipio_val = None
    departamento_val = None

    st.markdown("#### Ubicación e institución")
    if instituciones.empty:
        st.info("No hay instituciones configuradas. Crea instituciones en la pestaña Configuración.")
    else:
        g1, g2, g3, g4 = st.columns([1, 1, 1, 2])
        deps = sorted({str(x) for x in instituciones["departamento"].dropna().unique()})
        dep_sel = g1.selectbox(
            "Departamento",
            options=deps,
            key="form_departamento_sel",
        ) if deps else None

        inst_dep = instituciones
        if dep_sel:
            inst_dep = inst_dep[inst_dep["departamento"] == dep_sel]

        muns = sorted({str(x) for x in inst_dep["municipio"].dropna().unique()})
        mun_sel = g2.selectbox(
            "Municipio",
            options=["(Todos)"] + muns,
            key="form_municipio_sel",
        ) if muns else "(Todos)"

        inst_mun = inst_dep
        if mun_sel and mun_sel != "(Todos)":
            inst_mun = inst_mun[inst_mun["municipio"] == mun_sel]

        locs = sorted({str(x) for x in inst_mun["localidad"].dropna().unique()})
        loc_label = "Localidad (Bogotá)" if dep_sel and "BOGOTA" in dep_sel.upper() else "Localidad"
        loc_sel = g3.selectbox(
            loc_label,
            options=["(Todas)"] + locs,
            key="form_localidad_sel",
        ) if locs else "(Todas)"

        inst_geo = inst_mun
        if loc_sel and loc_sel != "(Todas)":
            inst_geo = inst_geo[inst_geo["localidad"] == loc_sel]

        inst_map = {r["nombre"]: int(r["id"]) for _, r in inst_geo.iterrows()}
        inst_sel = g4.selectbox(
            "Institución",
            options=list(inst_map.keys()) if inst_map else [],
            key="form_institucion",
        )
        institucion_id = inst_map.get(inst_sel)

        if institucion_id:
            row_inst = instituciones[instituciones["id"] == institucion_id].iloc[0]
            localidad_val = row_inst.get("localidad")
            municipio_val = row_inst.get("municipio")
            departamento_val = row_inst.get("departamento")

    c3, c4 = st.columns([1, 1])
    fecha = c3.date_input("Fecha de la atención", value=date.today(), key="form_fecha")
    actividad = c4.selectbox("Actividad / plantilla", ACTIVIDADES_PLANTILLAS, key="form_actividad")

    st.markdown("#### Datos del paciente")
    p1, p2 = st.columns([1, 1])
    pac_doc = p1.text_input("Documento del paciente (cédula)", key="pac_doc")
    if p2.button("Buscar paciente por documento", key="btn_buscar_paciente"):
        try:
            pac = DATA.get_paciente_por_documento(pac_doc)
            if pac:
                st.session_state["pac_id_actual"] = pac.get("id")
                st.session_state["pac_nombre"] = pac.get("nombre")
                st.session_state["pac_fecha_nac"] = pac.get("fecha_nacimiento")
                st.session_state["pac_sexo"] = pac.get("sexo")
                st.session_state["pac_telefono"] = pac.get("telefono")
                st.session_state["pac_email"] = pac.get("email")
                st.session_state["pac_direccion"] = pac.get("direccion")
                st.session_state["pac_localidad"] = pac.get("localidad")
                st.session_state["pac_municipio"] = pac.get("municipio")
                st.session_state["pac_departamento"] = pac.get("departamento")
                st.session_state["pac_zona"] = pac.get("zona")
                success_toast("Paciente encontrado. Datos cargados en el formulario.")
            else:
                st.session_state["pac_id_actual"] = None
                warn_toast("No se encontró paciente. Diligencia los datos y se creará automáticamente.")
        except Exception as e:
            error_toast(f"Error buscando paciente: {e}")

    p3, p4 = st.columns([1.5, 1])
    pac_nombre = p3.text_input(
        "Nombre completo del paciente",
        value=st.session_state.get("pac_nombre") or "",
        key="pac_nombre_input",
    )
    pac_sexo_opciones = ["(No especifica)", "F", "M", "Otro"]
    sexo_pre = st.session_state.get("pac_sexo") or "(No especifica)"
    if sexo_pre not in pac_sexo_opciones:
        sexo_pre = "(No especifica)"
    pac_sexo = p4.selectbox(
        "Sexo (opcional)",
        options=pac_sexo_opciones,
        index=pac_sexo_opciones.index(sexo_pre),
        key="pac_sexo_sel",
    )

    p5, p6 = st.columns([1, 1])
    pac_fecha_nac = p5.text_input(
        "Fecha de nacimiento (AAAA-MM-DD, opcional)",
        value=st.session_state.get("pac_fecha_nac") or "",
        key="pac_fecha_nac_input",
    )
    pac_telefono = p6.text_input(
        "Teléfono (opcional)",
        value=st.session_state.get("pac_telefono") or "",
        key="pac_telefono_input",
    )

    p7, p8 = st.columns([1, 1])
    pac_email = p7.text_input(
        "Email (opcional)",
        value=st.session_state.get("pac_email") or "",
        key="pac_email_input",
    )
    pac_direccion = p8.text_input(
        "Dirección (opcional)",
        value=st.session_state.get("pac_direccion") or "",
        key="pac_direccion_input",
    )

    p9, p10, p11 = st.columns([1, 1, 1])
    pac_loc = p9.text_input(
        "Localidad paciente (opcional)",
        value=st.session_state.get("pac_localidad") or "",
        key="pac_localidad_input",
    )
    pac_mun = p10.text_input(
        "Municipio paciente (opcional)",
        value=st.session_state.get("pac_municipio") or "",
        key="pac_municipio_input",
    )
    pac_dep = p11.text_input(
        "Departamento paciente (opcional)",
        value=st.session_state.get("pac_departamento") or "",
        key="pac_departamento_input",
    )

    zcol, _ = st.columns([1, 3])
    zona_opts = ["(No especifica)", "Urbana", "Rural"]
    zona_pre = st.session_state.get("pac_zona") or "(No especifica)"
    if zona_pre not in zona_opts:
        zona_pre = "(No especifica)"
    pac_zona = zcol.selectbox(
        "Zona (Rural/Urbana)",
        options=zona_opts,
        index=zona_opts.index(zona_pre),
        key="pac_zona_sel",
    )

    c9, c10 = st.columns([1, 1])
    atendido_flag = c9.radio("¿Atendido?", ["No", "Sí"], index=1, horizontal=True, key="form_atendido")
    registrado_panacea = c10.checkbox("Ya registrado en Panacea", key="form_reg_panacea")

    c11, c12 = st.columns([1, 1])
    tipo_contacto = c11.selectbox(
        "Tipo de contacto",
        options=["(No especifica)"] + TIPOS_CONTACTO,
        key="form_tipo_contacto",
    )
    duracion_minutos = c12.number_input(
        "Duración de la atención (minutos, opcional)",
        min_value=0,
        max_value=480,
        step=5,
        key="form_duracion_minutos",
    )
    duracion_val = int(duracion_minutos) if duracion_minutos > 0 else None
    tipo_contacto_val = None if tipo_contacto == "(No especifica)" else tipo_contacto

    observaciones = st.text_area("Observaciones", key="form_observaciones")

    btn_guardar = st.button(
        "Guardar atención",
        type="primary",
        use_container_width=True,
        key="btn_guardar_atencion",
        disabled=not all([programa_id, convenio_id, profesor_id, institucion_id]),
    )

    if btn_guardar:
        if not pac_doc or not pac_nombre:
            warn_toast("Documento y nombre del paciente son obligatorios.")
        else:
            try:
                sexo_val = None if pac_sexo == "(No especifica)" else pac_sexo
                zona_val = None if pac_zona == "(No especifica)" else pac_zona
                pac_id = DATA.upsert_paciente(
                    numero_documento=pac_doc,
                    nombre=pac_nombre,
                    fecha_nacimiento=pac_fecha_nac or None,
                    sexo=sexo_val,
                    telefono=pac_telefono or None,
                    email=pac_email or None,
                    direccion=pac_direccion or None,
                    localidad=pac_loc or None,
                    municipio=pac_mun or None,
                    departamento=pac_dep or None,
                    zona=zona_val,
                )
                DATA.insert_registro(
                    fecha=fecha,
                    programa_id=int(programa_id),
                    convenio_id=int(convenio_id),
                    institucion_id=int(institucion_id),
                    profesor_id=int(profesor_id),
                    paciente_id=pac_id,
                    localidad=localidad_val,
                    municipio=municipio_val,
                    departamento=departamento_val,
                    numero_paciente=pac_doc,
                    nombre_paciente=pac_nombre,
                    actividad=actividad,
                    atendido=True if atendido_flag == "Sí" else False,
                    registrado_panacea=bool(registrado_panacea),
                    duracion_minutos=duracion_val,
                    tipo_contacto=tipo_contacto_val,
                    observaciones=observaciones,
                    creado_por=auth_user,
                )
                success_toast("Atención registrada correctamente.")
                st.rerun()
            except Exception as e:
                error_toast(f"Error al guardar la atención: {e}")


# -------------------------------------------------------------
# UI: Listado de atenciones
# -------------------------------------------------------------
def ui_registros():
    st.subheader("Listado de atenciones")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay registros con los filtros actuales.")
        return

    if "tasa_atencion" in df.columns:
        df["tasa_atencion_%"] = (df["tasa_atencion"] * 100).round(1)

    show_cols = [
        "id",
        "fecha",
        "programa",
        "convenio",
        "institucion",
        "profesor",
        "actividad",
        "numero_paciente",
        "nombre_paciente",
        "tipo_contacto",
        "duracion_minutos",
        "atendido",
        "registrado_panacea",
        "pacientes_programados",
        "pacientes_atendidos",
        "no_asistieron",
        "tasa_atencion_%",
        "observaciones",
        "creado_por",
        "creado_en",
        "actualizado_en",
    ]
    cols_to_show = [c for c in show_cols if c in df.columns]
    st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 3])
    id_sel = c1.number_input("ID de atención", min_value=1, step=1, key="reg_id_sel")
    if c2.button("Eliminar atención", use_container_width=True, key="btn_eliminar_reg"):
        try:
            DATA.delete_registro(int(id_sel))
            success_toast("Atención eliminada.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    with st.expander("Editar atención seleccionada"):
        df_ids = df["id"].tolist()
        row_sel = None
        if int(id_sel) in df_ids:
            row_sel = df.loc[df["id"] == int(id_sel)].iloc[0]
        else:
            st.info("Selecciona un ID existente de la tabla superior.")

        if row_sel is not None:
            c4, c5 = st.columns(2)
            upd_numero = c4.text_input(
                "Número de paciente",
                value=row_sel.get("numero_paciente", "") or "",
                key="upd_numero_paciente",
            )
            upd_nombre = c5.text_input(
                "Nombre de paciente",
                value=row_sel.get("nombre_paciente", "") or "",
                key="upd_nombre_paciente",
            )
            try:
                idx_act = ACTIVIDADES_PLANTILLAS.index(row_sel.get("actividad"))
            except Exception:
                idx_act = 0
            upd_actividad = st.selectbox(
                "Actividad / plantilla",
                ACTIVIDADES_PLANTILLAS,
                index=idx_act,
                key="upd_actividad",
            )

            c6, c7 = st.columns(2)
            upd_atendido_flag = c6.radio(
                "¿Atendido?",
                ["No", "Sí"],
                index=1 if row_sel.get("atendido") in [1, True] else 0,
                horizontal=True,
                key="upd_atendido",
            )
            upd_reg_panacea = c7.checkbox(
                "Ya registrado en Panacea",
                value=bool(row_sel.get("registrado_panacea")),
                key="upd_reg_panacea",
            )

            c8, c9 = st.columns(2)
            tipo_opts = ["(No especifica)"] + TIPOS_CONTACTO
            current_tipo = row_sel.get("tipo_contacto")
            idx_tipo = tipo_opts.index(current_tipo) if current_tipo in tipo_opts else 0
            upd_tipo_contacto = c8.selectbox(
                "Tipo de contacto",
                options=tipo_opts,
                index=idx_tipo,
                key="upd_tipo_contacto",
            )
            upd_duracion = c9.number_input(
                "Duración (minutos)",
                min_value=0,
                max_value=480,
                step=5,
                value=int(row_sel.get("duracion_minutos") or 0),
                key="upd_duracion_minutos",
            )

            upd_obs = st.text_area(
                "Observaciones",
                value=row_sel.get("observaciones", "") or "",
                key="upd_observaciones",
            )

            if st.button("Guardar cambios", type="primary", key="btn_guardar_cambios"):
                atendido_bool = upd_atendido_flag == "Sí"
                tc_val = None if upd_tipo_contacto == "(No especifica)" else upd_tipo_contacto
                dur_val = int(upd_duracion) if upd_duracion > 0 else None
                updates = {
                    "numero_paciente": upd_numero or None,
                    "nombre_paciente": upd_nombre or None,
                    "actividad": upd_actividad,
                    "atendido": 1 if atendido_bool else 0,
                    "registrado_panacea": 1 if upd_reg_panacea else 0,
                    "pacientes_programados": 1,
                    "pacientes_atendidos": 1 if atendido_bool else 0,
                    "tipo_contacto": tc_val,
                    "duracion_minutos": dur_val,
                    "observaciones": upd_obs or None,
                }
                try:
                    DATA.update_registro(int(id_sel), updates)
                    success_toast("Atención actualizada.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")


# -------------------------------------------------------------
# UI: Dashboard
# -------------------------------------------------------------
def ui_dashboard():
    st.subheader("Dashboard de gestión")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay datos para graficar con los filtros actuales.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"])

    total_prog = int(df["pacientes_programados"].sum())
    total_att = int(df["pacientes_atendidos"].sum())
    total_no = int(df["no_asistieron"].sum())
    tasa = (total_att / total_prog * 100) if total_prog else 0.0

    total_minutos = int(df["duracion_minutos"].fillna(0).sum()) if "duracion_minutos" in df.columns else 0
    n_con_duracion = int(df["duracion_minutos"].notna().sum()) if "duracion_minutos" in df.columns else 0
    dur_promedio = (total_minutos / n_con_duracion) if n_con_duracion else 0.0
    horas_totales = total_minutos / 60 if total_minutos > 0 else 0.0
    productividad_ph = (total_att / horas_totales) if horas_totales > 0 else 0.0

    total_reg_panacea = int(df["registrado_panacea"].fillna(0).sum()) if "registrado_panacea" in df.columns else 0
    brecha_panacea = total_att - total_reg_panacea

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Pacientes programados", f"{total_prog:,}".replace(",", "."))
    k2.metric("Pacientes atendidos", f"{total_att:,}".replace(",", "."))
    k3.metric("No asistieron", f"{total_no:,}".replace(",", "."))
    k4.metric("Tasa de atención", f"{tasa:.1f}%")

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Minutos de atención", f"{total_minutos:,}".replace(",", "."))
    k6.metric("Duración promedio (min)", f"{dur_promedio:.1f}")
    k7.metric("Atenciones por hora efectiva", f"{productividad_ph:.2f}")
    k8.metric("Cargadas en Panacea / brecha", f"{total_reg_panacea} / {brecha_panacea}")

    tdf = (
        df.groupby(pd.Grouper(key="fecha", freq="W"))[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    fig1 = px.line(
        tdf,
        x="fecha",
        y=["pacientes_programados", "pacientes_atendidos"],
        markers=True,
        title="Tendencia semanal de pacientes programados vs atendidos",
    )
    st.plotly_chart(fig1, use_container_width=True)

    rank_prof = (
        df.groupby("profesor", dropna=True)["pacientes_atendidos"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
    )
    fig2 = px.bar(
        rank_prof,
        x="profesor",
        y="pacientes_atendidos",
        title="Top profesionales por pacientes atendidos",
    )
    fig2.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig2, use_container_width=True)

    if "registrado_panacea" in df.columns:
        pan_prof = (
            df.groupby("profesor", dropna=True)
            .agg(
                pacientes_atendidos=("pacientes_atendidos", "sum"),
                cargadas_panacea=("registrado_panacea", "sum"),
            )
            .reset_index()
        )
        pan_prof["brecha"] = pan_prof["pacientes_atendidos"] - pan_prof["cargadas_panacea"]
        pan_prof["cumplimiento"] = np.where(
            pan_prof["pacientes_atendidos"] > 0,
            pan_prof["cargadas_panacea"] / pan_prof["pacientes_atendidos"],
            np.nan,
        )
        pan_prof = pan_prof.sort_values("brecha", ascending=False).head(15)
        fig2b = px.bar(
            pan_prof,
            x="profesor",
            y=["pacientes_atendidos", "cargadas_panacea"],
            barmode="group",
            title="Atenciones vs cargadas en Panacea por profesional",
        )
        fig2b.update_layout(xaxis_tickangle=-40)
        st.plotly_chart(fig2b, use_container_width=True)

    act_sum = (
        df.groupby("actividad")[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    fig3 = px.bar(
        act_sum,
        x="actividad",
        y=["pacientes_programados", "pacientes_atendidos"],
        barmode="group",
        title="Distribución por actividad / plantilla",
    )
    fig3.update_layout(xaxis_tickangle=-30)
    st.plotly_chart(fig3, use_container_width=True)

    inst_sum = (
        df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .sort_values(by="pacientes_atendidos", ascending=False)
        .head(15)
        .reset_index()
    )
    fig4 = px.bar(
        inst_sum,
        x="institucion",
        y=["pacientes_programados", "pacientes_atendidos"],
        barmode="group",
        title="Instituciones con mayor actividad",
    )
    fig4.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig4, use_container_width=True)


# -------------------------------------------------------------
# UI: Reportes
# -------------------------------------------------------------
def to_excel_bytes(multi_sheets: Dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in multi_sheets.items():
            safe = df.copy()
            safe.columns = [str(c)[:40] for c in safe.columns]
            safe.to_excel(writer, sheet_name=name[:31], index=False)
    return out.getvalue()


def ui_reportes():
    st.subheader("Reportes y descargas")

    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("No hay registros con los filtros actuales.")
        return

    agg_prof = (
        df.groupby("profesor", dropna=True)
        .agg(
            pacientes_programados=("pacientes_programados", "sum"),
            pacientes_atendidos=("pacientes_atendidos", "sum"),
            cargadas_panacea=("registrado_panacea", "sum"),
            minutos=("duracion_minutos", "sum"),
        )
        .reset_index()
    )
    agg_prof["tasa_atencion"] = np.where(
        agg_prof["pacientes_programados"] > 0,
        agg_prof["pacientes_atendidos"] / agg_prof["pacientes_programados"],
        np.nan,
    )
    agg_prof["brecha_panacea"] = agg_prof["pacientes_atendidos"] - agg_prof["cargadas_panacea"]

    por_inst = (
        df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    por_geo = (
        df.groupby(["departamento", "municipio"], dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    por_act = (
        df.groupby("actividad")[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )

    xls = to_excel_bytes(
        {
            "Detalle": df,
            "Por_profesional": agg_prof,
            "Por_institucion": por_inst,
            "Por_geo": por_geo,
            "Por_actividad": por_act,
        }
    )
    st.download_button(
        "Descargar Excel (.xlsx)",
        data=xls,
        file_name=f"productividad_profesionales_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="btn_descargar_xlsx",
    )

    st.download_button(
        "Descargar detalle (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"productividad_profesionales_detalle_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="btn_descargar_csv",
    )


# -------------------------------------------------------------
# UI: Viáticos
# -------------------------------------------------------------
def ui_viaticos(auth_user: Optional[str]):
    st.subheader("Registro de viáticos")

    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="via_fecha")

    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = c2.selectbox(
        "Programa (opcional)",
        options=["(Sin programa)"] + list(prog_map.keys()),
        key="via_programa",
    )
    programa_id = prog_map.get(prog_sel)

    c3, c4 = st.columns([1, 1])
    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = c3.selectbox(
        "Convenio (opcional)",
        options=["(Sin convenio)"] + list(conv_map.keys()),
        key="via_convenio",
    )
    convenio_id = conv_map.get(conv_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = c4.selectbox(
        "Profesional (opcional)",
        options=["(Sin profesional)"] + list(prof_map.keys()),
        key="via_profesor",
    )
    profesor_id = prof_map.get(prof_sel)

    instituciones = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in instituciones.iterrows()} if not instituciones.empty else {}
    inst_sel = st.selectbox(
        "Institución destino (opcional)",
        options=["(Sin institución)"] + list(inst_map.keys()),
        key="via_institucion",
    )
    institucion_id = inst_map.get(inst_sel)

    c5, c6 = st.columns([1, 1])
    req_flag = c5.radio(
        "¿Requiere viáticos?",
        ["No", "Sí"],
        index=1,
        horizontal=True,
        key="via_req",
    )
    origen = c6.text_input("Sitio de origen", key="via_origen")

    destino = st.text_input("Sitio de destino", key="via_destino")
    valor = st.number_input(
        "Valor de viáticos",
        min_value=0.0,
        step=1000.0,
        key="via_valor",
    )
    obs = st.text_area("Observaciones (opcional)", key="via_obs")

    if st.button("Guardar viático", type="primary", use_container_width=True, key="via_guardar"):
        try:
            requiere = req_flag == "Sí"
            DATA.insert_viatico(
                fecha=fecha,
                programa_id=programa_id,
                convenio_id=convenio_id,
                institucion_id=institucion_id,
                profesor_id=profesor_id,
                requiere_viatico=requiere,
                origen=origen,
                destino=destino,
                valor=valor if valor > 0 else None,
                observaciones=obs,
                creado_por=auth_user,
            )
            success_toast("Viático registrado correctamente.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo guardar viático: {e}")

    st.markdown("### Listado de viáticos")
    df = DATA.list_viaticos(st.session_state.filters)
    if df.empty:
        st.info("No hay viáticos con los filtros actuales.")
    else:
        df["requiere_viatico"] = df["requiere_viatico"].map({1: "Sí", 0: "No"})
        show_cols = [
            "id",
            "fecha",
            "programa",
            "convenio",
            "institucion",
            "profesor",
            "requiere_viatico",
            "origen",
            "destino",
            "valor",
            "observaciones",
            "creado_por",
            "creado_en",
        ]
        cols_to_show = [c for c in show_cols if c in df.columns]
        st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

        total_valor = df["valor"].fillna(0).sum()
        st.metric("Total viáticos (filtro aplicado)", f"${total_valor:,.0f}".replace(",", "."))

        c7, c8, _ = st.columns([1, 1, 3])
        via_id = c7.number_input("ID de viático", min_value=1, step=1, key="via_id_sel")
        if c8.button("Eliminar viático", use_container_width=True, key="btn_eliminar_viatico"):
            try:
                DATA.delete_viatico(int(via_id))
                success_toast("Viático eliminado.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo eliminar viático: {e}")


# -------------------------------------------------------------
# UI: Planificador / Agenda
# -------------------------------------------------------------
def ui_planificador(auth_user: Optional[str]):
    st.subheader("Planificador (agenda)")

    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha del evento", value=date.today(), key="ag_fecha")
    hi = c1.time_input("Hora inicio", value=dtime(8, 0), key="ag_hora_ini")
    hf = c2.time_input("Hora fin", value=dtime(9, 0), key="ag_hora_fin")

    titulo = st.text_input("Título del evento", key="ag_titulo")
    descripcion = st.text_area("Descripción / notas", key="ag_descripcion")

    c3, c4 = st.columns([1, 1])
    programas = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
    prog_sel = c3.selectbox(
        "Programa (opcional)",
        options=["(Sin programa)"] + list(prog_map.keys()),
        key="ag_programa",
    )
    programa_id = prog_map.get(prog_sel)

    convenios = DATA.list_convenios(programa_id=programa_id) if programa_id else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}
    conv_sel = c4.selectbox(
        "Convenio (opcional)",
        options=["(Sin convenio)"] + list(conv_map.keys()),
        key="ag_convenio",
    )
    convenio_id = conv_map.get(conv_sel)

    c5, c6 = st.columns([1, 1])
    instituciones = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in instituciones.iterrows()} if not instituciones.empty else {}
    inst_sel = c5.selectbox(
        "Institución (opcional)",
        options=["(Sin institución)"] + list(inst_map.keys()),
        key="ag_institucion",
    )
    institucion_id = inst_map.get(inst_sel)

    profesores = DATA.list_profesores(programa_id=programa_id, convenio_id=convenio_id)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in profesores.iterrows()} if not profesores.empty else {}
    prof_sel = c6.selectbox(
        "Profesional (opcional)",
        options=["(Sin profesional)"] + list(prof_map.keys()),
        key="ag_profesor",
    )
    profesor_id = prof_map.get(prof_sel)

    if st.button("Guardar evento", type="primary", use_container_width=True, key="ag_guardar"):
        if not titulo.strip():
            warn_toast("El título del evento es obligatorio.")
        else:
            try:
                DATA.insert_agenda_event(
                    fecha=fecha,
                    hora_inicio=hi,
                    hora_fin=hf,
                    titulo=titulo,
                    descripcion=descripcion,
                    programa_id=programa_id,
                    convenio_id=convenio_id,
                    institucion_id=institucion_id,
                    profesor_id=profesor_id,
                    creado_por=auth_user,
                )
                success_toast("Evento de agenda registrado.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo guardar el evento: {e}")

    st.markdown("### Agenda (según filtros de la barra lateral)")
    df = DATA.list_agenda(st.session_state.filters)
    if df.empty:
        st.info("No hay eventos en la agenda con los filtros actuales.")
    else:
        show_cols = [
            "id",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "titulo",
            "descripcion",
            "programa",
            "convenio",
            "institucion",
            "profesor",
            "creado_por",
            "creado_en",
        ]
        cols_to_show = [c for c in show_cols if c in df.columns]
        st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

        c7, c8, _ = st.columns([1, 1, 3])
        ev_id = c7.number_input("ID de evento", min_value=1, step=1, key="ag_id_sel")
        if c8.button("Eliminar evento", use_container_width=True, key="btn_eliminar_evento"):
            try:
                DATA.delete_agenda_event(int(ev_id))
                success_toast("Evento eliminado.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo eliminar evento: {e}")


# -------------------------------------------------------------
# UI: Configuración / catálogos y cargas masivas
# -------------------------------------------------------------
def ui_configuracion():
    st.subheader("Configuración de catálogos")

    tabs = st.tabs(["Programas", "Convenios", "Instituciones", "Profesionales", "Pacientes"])

    # --- Programas ---
    with tabs[0]:
        c1, c2 = st.columns([2, 1])
        p_nombre = c1.text_input("Nombre del programa", key="cfg_prog_nombre")
        if c2.button("Agregar programa", use_container_width=True, key="btn_add_programa"):
            if not p_nombre.strip():
                warn_toast("Escribe un nombre de programa.")
            else:
                DATA.upsert_programa(p_nombre.strip())
                success_toast("Programa agregado/actualizado.")
                st.rerun()
        st.markdown("**Programas activos**")
        st.dataframe(DATA.list_programas(), use_container_width=True, hide_index=True)

    # --- Convenios ---
    with tabs[1]:
        programas = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
        c1, c2, c3 = st.columns([2, 2, 1])
        cv_prog = c1.selectbox(
            "Programa",
            options=list(prog_map.keys()) if prog_map else [],
            key="cfg_conv_prog",
        )
        cv_nombre = c2.text_input("Nombre del convenio", key="cfg_conv_nombre")
        if c3.button("Agregar convenio", use_container_width=True, key="btn_add_convenio"):
            if not (cv_prog and cv_nombre.strip()):
                warn_toast("Selecciona programa y escribe el nombre del convenio.")
            else:
                DATA.upsert_convenio(cv_nombre.strip(), prog_map[cv_prog])
                success_toast("Convenio agregado/actualizado.")
                st.rerun()
        st.markdown("**Convenios activos**")
        st.dataframe(DATA.list_convenios(), use_container_width=True, hide_index=True)

    # --- Instituciones ---
    with tabs[2]:
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.2, 1.2, 1])
        i_nombre = c1.text_input("Nombre institución", key="cfg_inst_nombre")
        i_localidad = c2.text_input("Localidad", key="cfg_inst_localidad")
        i_municipio = c3.text_input("Municipio", key="cfg_inst_municipio")
        i_departamento = c4.text_input("Departamento", key="cfg_inst_departamento")

        if c5.button("Agregar institución", use_container_width=True, key="btn_add_inst"):
            if not i_nombre.strip():
                warn_toast("Escribe el nombre de la institución.")
            else:
                DATA.upsert_institucion(
                    i_nombre.strip(),
                    i_localidad.strip() if i_localidad else None,
                    i_municipio.strip() if i_municipio else None,
                    i_departamento.strip() if i_departamento else None,
                )
                success_toast("Institución agregada/actualizada.")
                st.rerun()

        st.markdown("**Instituciones activas**")
        st.dataframe(
            DATA.list_instituciones(),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        st.markdown("### Carga masiva de instituciones")
        st.markdown(
            """
            **Formato esperado (Excel o CSV):**  

            Columnas mínimas:
            - `nombre`

            Columnas opcionales:
            - `localidad`
            - `municipio`
            - `departamento`

            > La combinación (`nombre`, `municipio`, `departamento`) se usa para evitar duplicados.
            """
        )

        file_inst = st.file_uploader(
            "Archivo de instituciones (Excel o CSV)",
            type=["xlsx", "xls", "csv"],
            key="up_instituciones",
        )

        if file_inst is not None:
            if st.button("Procesar instituciones", key="btn_procesar_instituciones"):
                try:
                    if file_inst.name.lower().endswith(".csv"):
                        df_inst = pd.read_csv(file_inst, sep=None, engine="python")
                    else:
                        df_inst = pd.read_excel(file_inst)

                    if "nombre" not in df_inst.columns:
                        error_toast("El archivo debe contener al menos la columna 'nombre'.")
                    else:
                        ok = 0
                        for _, row in df_inst.iterrows():
                            nombre = str(row["nombre"]).strip()
                            if not nombre:
                                continue

                            loc = (
                                str(row["localidad"]).strip()
                                if "localidad" in df_inst.columns and pd.notna(row["localidad"])
                                else None
                            )
                            mun = (
                                str(row["municipio"]).strip()
                                if "municipio" in df_inst.columns and pd.notna(row["municipio"])
                                else None
                            )
                            dep = (
                                str(row["departamento"]).strip()
                                if "departamento" in df_inst.columns and pd.notna(row["departamento"])
                                else None
                            )

                            DATA.upsert_institucion(nombre, loc, mun, dep)
                            ok += 1

                        success_toast(f"Se procesaron {ok} instituciones.")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando instituciones: {e}")

    # --- Profesionales ---
    with tabs[3]:
        programas = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in programas.iterrows()} if not programas.empty else {}
        convenios = DATA.list_convenios()
        conv_map = {r["nombre"]: int(r["id"]) for _, r in convenios.iterrows()} if not convenios.empty else {}

        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.2, 1.4, 1.4, 1.2, 1.2])
        f_nombre = c1.text_input("Nombre profesional", key="cfg_prof_nombre")
        f_doc = c2.text_input("Documento (opcional)", key="cfg_prof_doc")
        f_email = c3.text_input("Email (opcional)", key="cfg_prof_email")
        f_prog = c4.selectbox(
            "Programa",
            options=list(prog_map.keys()) if prog_map else [],
            key="cfg_prof_prog",
        )
        f_conv = c5.selectbox(
            "Convenio",
            options=list(conv_map.keys()) if conv_map else [],
            key="cfg_prof_conv",
        )
        zona_opts = ["(No especifica)", "Urbana", "Rural"]
        f_zona = c6.selectbox(
            "Zona (Rural/Urbana, opcional)",
            options=zona_opts,
            key="cfg_prof_zona",
        )
        if st.button("Agregar profesional", use_container_width=True, key="btn_add_prof"):
            if not f_nombre.strip():
                warn_toast("Escribe el nombre del profesional.")
            else:
                zona_val = None if f_zona == "(No especifica)" else f_zona
                DATA.upsert_profesor(
                    f_nombre.strip(),
                    f_doc.strip() if f_doc else None,
                    f_email.strip() if f_email else None,
                    prog_map.get(f_prog),
                    conv_map.get(f_conv),
                    zona_val,
                )
                success_toast("Profesional agregado/actualizado.")
                st.rerun()

        st.markdown("**Profesionales activos**")
        st.dataframe(DATA.list_profesores(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de profesionales")
        st.markdown(
            """
            **Formato esperado (Excel o CSV):**  
            Columnas sugeridas:
            - `nombre` (obligatorio)  
            - `documento` (opcional)  
            - `email` (opcional)  
            - `programa` (opcional, nombre EXACTO)  
            - `convenio` (opcional, nombre EXACTO)
            - `zona` (opcional: Rural / Urbana)
            """
        )
        file_prof = st.file_uploader(
            "Archivo de profesionales",
            type=["xlsx", "xls", "csv"],
            key="up_profesionales",
        )
        if file_prof is not None:
            if st.button("Procesar profesionales", key="btn_procesar_profesionales"):
                try:
                    if file_prof.name.lower().endswith(".csv"):
                        df_prof = pd.read_csv(file_prof, sep=None, engine="python")
                    else:
                        df_prof = pd.read_excel(file_prof)
                    if "nombre" not in df_prof.columns:
                        error_toast("El archivo debe contener al menos la columna 'nombre'.")
                    else:
                        progs2 = DATA.list_programas()
                        prog_map2 = {r["nombre"]: int(r["id"]) for _, r in progs2.iterrows()} if not progs2.empty else {}
                        convs2 = DATA.list_convenios()
                        conv_map2 = {r["nombre"]: int(r["id"]) for _, r in convs2.iterrows()} if not convs2.empty else {}

                        ok = 0
                        for _, row in df_prof.iterrows():
                            nombre = str(row["nombre"]).strip()
                            if not nombre:
                                continue
                            documento = (
                                str(row["documento"]).strip()
                                if "documento" in df_prof.columns and pd.notna(row["documento"])
                                else None
                            )
                            email = (
                                str(row["email"]).strip()
                                if "email" in df_prof.columns and pd.notna(row["email"])
                                else None
                            )
                            prog_name = (
                                str(row["programa"]).strip()
                                if "programa" in df_prof.columns and pd.notna(row["programa"])
                                else None
                            )
                            conv_name = (
                                str(row["convenio"]).strip()
                                if "convenio" in df_prof.columns and pd.notna(row["convenio"])
                                else None
                            )
                            zona_val = (
                                str(row["zona"]).strip()
                                if "zona" in df_prof.columns and pd.notna(row["zona"])
                                else None
                            )
                            if zona_val not in ["Rural", "Urbana"]:
                                zona_val = None

                            prog_id = prog_map2.get(prog_name) if prog_name else None
                            conv_id = conv_map2.get(conv_name) if conv_name else None

                            DATA.upsert_profesor(nombre, documento, email, prog_id, conv_id, zona_val)
                            ok += 1
                        success_toast(f"Se procesaron {ok} profesionales.")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando profesionales: {e}")

    # --- Pacientes ---
    with tabs[4]:
        st.markdown("### Gestión de pacientes")
        c1, c2 = st.columns([1.2, 2])
        cfg_doc = c1.text_input("Documento (cédula)", key="cfg_pac_doc")
        cfg_nombre = c2.text_input("Nombre completo", key="cfg_pac_nombre")

        c3, c4, c5 = st.columns([1, 1, 1])
        cfg_fecha_nac = c3.text_input("Fecha de nacimiento (AAAA-MM-DD, opcional)", key="cfg_pac_fecha_nac")
        sexo_opts = ["(No especifica)", "F", "M", "Otro"]
        cfg_sexo = c4.selectbox("Sexo (opcional)", sexo_opts, key="cfg_pac_sexo")
        cfg_tel = c5.text_input("Teléfono (opcional)", key="cfg_pac_tel")

        c6, c7 = st.columns([1, 1])
        cfg_email = c6.text_input("Email (opcional)", key="cfg_pac_email")
        cfg_dir = c7.text_input("Dirección (opcional)", key="cfg_pac_dir")

        c8, c9, c10 = st.columns([1, 1, 1])
        cfg_loc = c8.text_input("Localidad (opcional)", key="cfg_pac_loc")
        cfg_mun = c9.text_input("Municipio (opcional)", key="cfg_pac_mun")
        cfg_dep = c10.text_input("Departamento (opcional)", key="cfg_pac_dep")

        zc1, _ = st.columns([1, 3])
        zona_opts = ["(No especifica)", "Urbana", "Rural"]
        cfg_zona = zc1.selectbox("Zona (Rural/Urbana, opcional)", zona_opts, key="cfg_pac_zona")

        if st.button("Guardar / actualizar paciente", key="btn_guardar_paciente_cfg"):
            if not cfg_doc.strip() or not cfg_nombre.strip():
                warn_toast("Documento y nombre del paciente son obligatorios.")
            else:
                sexo_val = None if cfg_sexo == "(No especifica)" else cfg_sexo
                zona_val = None if cfg_zona == "(No especifica)" else cfg_zona
                try:
                    DATA.upsert_paciente(
                        numero_documento=cfg_doc.strip(),
                        nombre=cfg_nombre.strip(),
                        fecha_nacimiento=cfg_fecha_nac or None,
                        sexo=sexo_val,
                        telefono=cfg_tel or None,
                        email=cfg_email or None,
                        direccion=cfg_dir or None,
                        localidad=cfg_loc or None,
                        municipio=cfg_mun or None,
                        departamento=cfg_dep or None,
                        zona=zona_val,
                    )
                    success_toast("Paciente guardado / actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo guardar paciente: {e}")

        st.markdown("**Pacientes activos**")
        st.dataframe(DATA.list_pacientes(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de pacientes")
        st.markdown(
            """
            **Formato esperado (Excel o CSV):**  
            Columnas mínimas:
            - `documento`
            - `nombre`

            Columnas opcionales:
            - `fecha_nacimiento` (AAAA-MM-DD)
            - `sexo` (F / M / Otro)
            - `telefono`
            - `email`
            - `direccion`
            - `localidad`
            - `municipio`
            - `departamento`
            - `zona` (Rural / Urbana)
            """
        )
        file_pac = st.file_uploader(
            "Archivo de pacientes (Excel o CSV)",
            type=["xlsx", "xls", "csv"],
            key="up_pacientes",
        )
        if file_pac is not None:
            if st.button("Procesar pacientes", key="btn_procesar_pacientes"):
                try:
                    if file_pac.name.lower().endswith(".csv"):
                        df_pac = pd.read_csv(file_pac, sep=None, engine="python")
                    else:
                        df_pac = pd.read_excel(file_pac)
                    if "documento" not in df_pac.columns or "nombre" not in df_pac.columns:
                        error_toast("El archivo debe contener al menos las columnas 'documento' y 'nombre'.")
                    else:
                        ok = 0
                        for _, row in df_pac.iterrows():
                            doc = str(row["documento"]).strip()
                            nom = str(row["nombre"]).strip()
                            if not doc or not nom:
                                continue
                            zona_val = (
                                str(row["zona"]).strip()
                                if "zona" in df_pac.columns and pd.notna(row["zona"])
                                else None
                            )
                            if zona_val not in ["Rural", "Urbana"]:
                                zona_val = None

                            DATA.upsert_paciente(
                                numero_documento=doc,
                                nombre=nom,
                                fecha_nacimiento=str(row["fecha_nacimiento"]) if "fecha_nacimiento" in df_pac.columns and pd.notna(row["fecha_nacimiento"]) else None,
                                sexo=str(row["sexo"]).strip() if "sexo" in df_pac.columns and pd.notna(row["sexo"]) else None,
                                telefono=str(row["telefono"]).strip() if "telefono" in df_pac.columns and pd.notna(row["telefono"]) else None,
                                email=str(row["email"]).strip() if "email" in df_pac.columns and pd.notna(row["email"]) else None,
                                direccion=str(row["direccion"]).strip() if "direccion" in df_pac.columns and pd.notna(row["direccion"]) else None,
                                localidad=str(row["localidad"]).strip() if "localidad" in df_pac.columns and pd.notna(row["localidad"]) else None,
                                municipio=str(row["municipio"]).strip() if "municipio" in df_pac.columns and pd.notna(row["municipio"]) else None,
                                departamento=str(row["departamento"]).strip() if "departamento" in df_pac.columns and pd.notna(row["departamento"]) else None,
                                zona=zona_val,
                            )
                            ok += 1
                        success_toast(f"Se procesaron {ok} pacientes.")
                        st.rerun()
                except Exception as e:
                    error_toast(f"Error procesando pacientes: {e}")


# -------------------------------------------------------------
# main()
# -------------------------------------------------------------
def main():
    ensure_session_state()

    st.markdown(f"# {APP_ICON} {APP_TITLE}")
    st.caption(
        "Base de datos en SQLite local (`productividad_profesores.db`). "
        "Todos los usuarios que ingresen al mismo enlace comparten la misma información."
    )

    sidebar_filters()
    render_login()

    if not st.session_state.user:
        st.info("Por favor inicia sesión para usar el aplicativo.")
        return

    auth_user = st.session_state.user
    role = st.session_state.role

    if role == "admin":
        tab_labels = [
            "Registrar atenciones",
            "Listado",
            "Dashboard",
            "Reportes",
            "Viáticos",
            "Planificador",
            "Configuración",
        ]
    else:
        tab_labels = [
            "Registrar atenciones",
            "Listado",
            "Viáticos",
            "Planificador",
        ]

    tabs = st.tabs(tab_labels)

    if role == "admin":
        with tabs[0]:
            ui_cargar_datos(auth_user)
        with tabs[1]:
            ui_registros()
        with tabs[2]:
            ui_dashboard()
        with tabs[3]:
            ui_reportes()
        with tabs[4]:
            ui_viaticos(auth_user)
        with tabs[5]:
            ui_planificador(auth_user)
        with tabs[6]:
            ui_configuracion()
    else:
        with tabs[0]:
            ui_cargar_datos(auth_user)
        with tabs[1]:
            ui_registros()
        with tabs[2]:
            ui_viaticos(auth_user)
        with tabs[3]:
            ui_planificador(auth_user)


if __name__ == "__main__":
    main()
