# app_productividad_profesores.py
from datetime import datetime, date, time as dtime
from typing import Optional, Dict, Any, List, Tuple
import io
import os
import re
import zipfile
import unicodedata
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

# Orígenes para priorización (cuando se marca el check)
PRIORI_ORIGEN_OPTS = [
    "SG -SST FOMAG",
    "Directivas del colegio",
    "Psicólogo contigo profe en aula",
]

# Usuarios demo
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "pro": {"password": "pro123", "role": "profesional"},
}

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")

# ---------------- LECTURA ROBUSTA CSV/EXCEL ----------------
def _slug_col(s: str) -> str:
    if s is None:
        return ""
    s = str(s).replace("\ufeff", "")  # BOM
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_slug_col(c) for c in df.columns]
    synonyms = {
        # generales
        "num_documento": "documento",
        "numero_documento": "documento",
        "nro_documento": "documento",
        "identificacion": "documento",
        "identificación": "documento",
        "cedula": "documento",
        "c_c": "documento",
        "nombre_completo": "nombre",
        "correo": "email",
        "correo_electronico": "email",
        "telefono_contacto": "telefono",
        "teléfono": "telefono",
        "dirección": "direccion",
        "fecha_de_nacimiento": "fecha_nacimiento",
        "zona_geografica": "zona",
        "actividad_plantilla": "actividad",
        "duracion": "duracion_minutos",
        "duracion_min": "duracion_minutos",
        "atendio": "atendido",
        "asistio": "atendido",

        # atención registrada en Panacea (NO es el paciente)
        "registrado_en_panacea": "registrado_panacea",
        "en_panacea": "registrado_panacea",
        "atencion_en_panacea": "registrado_panacea",
        "atencion_registrada_panacea": "registrado_panacea",

        # paciente creado en Panacea (nuevo)
        "paciente_en_panacea": "paciente_creado_panacea",
        "paciente_creado_panacea": "paciente_creado_panacea",
        "creado_panacea": "paciente_creado_panacea",
        "paciente_creado": "paciente_creado_panacea",

        # priorización
        "priorizado": "paciente_priorizado",
        "es_priorizado": "paciente_priorizado",
        "origen_priorizado": "priorizado_origen",
    }
    df = df.rename(columns={c: synonyms.get(c, c) for c in df.columns})

    if "nombre" not in df.columns and ("nombres" in df.columns or "apellidos" in df.columns):
        n = df["nombres"].astype(str) if "nombres" in df.columns else ""
        a = df["apellidos"].astype(str) if "apellidos" in df.columns else ""
        df["nombre"] = (n.fillna("") + " " + a.fillna("")).str.strip().replace("", pd.NA)

    for key_col in ("documento", "nombre"):
        if key_col in df.columns:
            df[key_col] = (
                df[key_col].astype(str).str.replace("\u200b", "", regex=False).str.strip()
            )
    return df

def read_table_upload(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(raw))
        return normalize_columns(df)

    last_err = None
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin1")
    seps = (None, ",", ";")
    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=sep, engine="python")
                if df.shape[1] == 1 and sep is None:
                    try:
                        df2 = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=";", engine="python")
                        if df2.shape[1] > 1:
                            df = df2
                    except Exception:
                        pass
                return normalize_columns(df)
            except Exception as e:
                last_err = e

    try:
        txt = raw.decode("cp1252", errors="replace")
        df = pd.read_csv(io.StringIO(txt), sep=None, engine="python")
        return normalize_columns(df)
    except Exception:
        pass

    raise last_err

# ---------------- UTIL ----------------
def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def success_toast(msg: str) -> None:
    st.toast(msg, icon="✅")

def warn_toast(msg: str) -> None:
    st.toast(msg, icon="⚠️")

def error_toast(msg: str) -> None:
    st.toast(msg, icon="❌")

def str2bool(x) -> Optional[bool]:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    s = str(x).strip().lower()
    if s in ("si", "sí", "true", "1", "x", "si.", "sí."):
        return True
    if s in ("no", "false", "0", ""):
        return False
    return None

def safe_int(x) -> Optional[int]:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return None
        return int(str(x).strip())
    except Exception:
        return None

# ---------------- DB ----------------
def get_sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

SQLITE_CONN = get_sqlite_conn()

SQLITE_DDL = {
    "programas": """
    CREATE TABLE IF NOT EXISTS programas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        activo INTEGER DEFAULT 1
    );
    """,
    "convenios": """
    CREATE TABLE IF NOT EXISTS convenios(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        programa_id INTEGER NOT NULL,
        activo INTEGER DEFAULT 1,
        UNIQUE(nombre, programa_id),
        FOREIGN KEY(programa_id) REFERENCES programas(id)
    );
    """,
    "instituciones": """
    CREATE TABLE IF NOT EXISTS instituciones(
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
    CREATE TABLE IF NOT EXISTS profesores(
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
    CREATE TABLE IF NOT EXISTS pacientes(
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
    CREATE TABLE IF NOT EXISTS registros(
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
        registrado_panacea INTEGER,           -- atención registrada (NO el paciente)
        paciente_creado_panacea INTEGER,      -- paciente creado en Panacea
        paciente_priorizado INTEGER,          -- ⬅️ NUEVO
        priorizado_origen TEXT,               -- ⬅️ NUEVO
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
    CREATE TABLE IF NOT EXISTS viaticos(
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
    CREATE TABLE IF NOT EXISTS agenda(
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
    "papeleria": """
    CREATE TABLE IF NOT EXISTS papeleria(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        programa_id INTEGER,
        convenio_id INTEGER,
        institucion_id INTEGER,
        profesor_id INTEGER,
        item TEXT NOT NULL,
        cantidad INTEGER,
        estado TEXT,
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
}

def ensure_sqlite_schema():
    with SQLITE_CONN:
        for ddl in SQLITE_DDL.values():
            SQLITE_CONN.execute(ddl)
        # Migraciones suaves
        cur = SQLITE_CONN.execute("PRAGMA table_info(registros);")
        have = {r["name"] for r in cur.fetchall()}
        add_cols = {
            "numero_paciente": "ALTER TABLE registros ADD COLUMN numero_paciente TEXT;",
            "nombre_paciente": "ALTER TABLE registros ADD COLUMN nombre_paciente TEXT;",
            "actividad": "ALTER TABLE registros ADD COLUMN actividad TEXT;",
            "atendido": "ALTER TABLE registros ADD COLUMN atendido INTEGER;",
            "registrado_panacea": "ALTER TABLE registros ADD COLUMN registrado_panacea INTEGER;",
            "paciente_creado_panacea": "ALTER TABLE registros ADD COLUMN paciente_creado_panacea INTEGER;",
            "paciente_priorizado": "ALTER TABLE registros ADD COLUMN paciente_priorizado INTEGER;",   # NUEVO
            "priorizado_origen": "ALTER TABLE registros ADD COLUMN priorizado_origen TEXT;",         # NUEVO
            "duracion_minutos": "ALTER TABLE registros ADD COLUMN duracion_minutos INTEGER;",
            "tipo_contacto": "ALTER TABLE registros ADD COLUMN tipo_contacto TEXT;",
            "paciente_id": "ALTER TABLE registros ADD COLUMN paciente_id INTEGER;",
        }
        for c, stmt in add_cols.items():
            if c not in have:
                SQLITE_CONN.execute(stmt)

ensure_sqlite_schema()

# ---------------- DAO ----------------
class DataAccess:
    def __init__(self, conn: sqlite3.Connection):
        self.db = conn

    # Helpers name->id
    def programa_id_by_name(self, nombre: str) -> Optional[int]:
        if not nombre:
            return None
        r = self.db.execute("SELECT id FROM programas WHERE nombre=? AND activo=1", (nombre,)).fetchone()
        return int(r["id"]) if r else None

    def convenio_id_by_name(self, nombre: str, programa_id: Optional[int]) -> Optional[int]:
        if not nombre or not programa_id:
            return None
        r = self.db.execute(
            "SELECT id FROM convenios WHERE nombre=? AND programa_id=? AND activo=1",
            (nombre, programa_id),
        ).fetchone()
        return int(r["id"]) if r else None

    def institucion_id_by_name_geo(
        self, nombre: str, municipio: Optional[str], departamento: Optional[str]
    ) -> Optional[int]:
        if not nombre:
            return None
        if municipio and departamento:
            r = self.db.execute(
                "SELECT id FROM instituciones WHERE nombre=? AND municipio=? AND departamento=? AND activo=1",
                (nombre, municipio, departamento),
            ).fetchone()
            if r:
                return int(r["id"])
        r = self.db.execute(
            "SELECT id FROM instituciones WHERE nombre=? AND activo=1 ORDER BY id ASC",
            (nombre,),
        ).fetchone()
        return int(r["id"]) if r else None

    def profesor_id_by_name(
        self, nombre: str, programa_id: Optional[int], convenio_id: Optional[int]
    ) -> Optional[int]:
        if not nombre:
            return None
        r = self.db.execute(
            "SELECT id FROM profesores WHERE nombre=? AND activo=1 ORDER BY id ASC",
            (nombre,),
        ).fetchone()
        return int(r["id"]) if r else None

    # CRUD básicos
    def list_programas(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM programas WHERE activo=1 ORDER BY nombre", self.db)

    def upsert_programa(self, nombre: str) -> int:
        if not nombre:
            return None
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO programas(nombre,activo) VALUES(?,1)", (nombre.strip(),))
        r = self.db.execute("SELECT id FROM programas WHERE nombre=?", (nombre.strip(),)).fetchone()
        return int(r["id"])

    def list_convenios(self, programa_id: Optional[int] = None) -> pd.DataFrame:
        q = "SELECT * FROM convenios WHERE activo=1"
        p: List[Any] = []
        if programa_id:
            q += " AND programa_id=?"
            p.append(programa_id)
        q += " ORDER BY nombre"
        return pd.read_sql_query(q, self.db, params=p)

    def upsert_convenio(self, nombre: str, programa_id: int) -> int:
        if not (nombre and programa_id):
            return None
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO convenios(nombre,programa_id,activo) VALUES(?,?,1)",
                (nombre.strip(), programa_id),
            )
        r = self.db.execute(
            "SELECT id FROM convenios WHERE nombre=? AND programa_id=?", (nombre.strip(), programa_id)
        ).fetchone()
        return int(r["id"])

    def list_instituciones(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM instituciones WHERE activo=1 ORDER BY departamento, municipio, nombre", self.db
        )

    def upsert_institucion(
        self, nombre: str, localidad: Optional[str], municipio: Optional[str], departamento: Optional[str]
    ) -> int:
        if not nombre:
            return None
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO instituciones(nombre,localidad,municipio,departamento,activo) VALUES(?,?,?,?,1)",
                (nombre.strip(), (localidad or None), (municipio or None), (departamento or None)),
            )
        r = self.db.execute(
            "SELECT id FROM instituciones WHERE nombre=? ORDER BY id ASC", (nombre.strip(),)
        ).fetchone()
        return int(r["id"])

    def list_profesores(
        self, programa_id: Optional[int] = None, convenio_id: Optional[int] = None
    ) -> pd.DataFrame:
        q = "SELECT * FROM profesores WHERE activo=1"
        p: List[Any] = []
        if programa_id:
            q += " AND programa_id=?"
            p.append(programa_id)
        if convenio_id:
            q += " AND convenio_id=?"
            p.append(convenio_id)
        q += " ORDER BY nombre"
        return pd.read_sql_query(q, self.db, params=p)

    def upsert_profesor(
        self,
        nombre: str,
        documento: Optional[str],
        email: Optional[str],
        programa_id: Optional[int],
        convenio_id: Optional[int],
        zona: Optional[str],
    ) -> int:
        if not nombre:
            return None
        with self.db:
            self.db.execute(
                "INSERT INTO profesores(nombre,documento,email,programa_id,convenio_id,zona,activo) VALUES(?,?,?,?,?,?,1)",
                (nombre.strip(), (documento or None), (email or None), programa_id, convenio_id, zona),
            )
        r = self.db.execute(
            "SELECT id FROM profesores WHERE nombre=? ORDER BY id DESC", (nombre.strip(),)
        ).fetchone()
        return int(r["id"])

    def list_pacientes(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM pacientes WHERE activo=1 ORDER BY nombre", self.db)

    def get_paciente_por_documento(self, doc: str) -> Optional[Dict[str, Any]]:
        doc = (doc or "").strip()
        if not doc:
            return None
        row = self.db.execute("SELECT * FROM pacientes WHERE numero_documento=? AND activo=1", (doc,)).fetchone()
        return dict(row) if row else None

    def upsert_paciente(
        self,
        numero_documento: str,
        nombre: str,
        fecha_nacimiento=None,
        sexo=None,
        telefono=None,
        email=None,
        direccion=None,
        localidad=None,
        municipio=None,
        departamento=None,
        zona=None,
    ) -> int:
        numero_documento = (numero_documento or "").strip()
        nombre = (nombre or "").strip()
        if not numero_documento or not nombre:
            raise ValueError("Documento y nombre del paciente son obligatorios")
        row = self.db.execute("SELECT id FROM pacientes WHERE numero_documento=?", (numero_documento,)).fetchone()
        if row:
            pid = int(row["id"])
            with self.db:
                self.db.execute(
                    """UPDATE pacientes
                       SET nombre=?, fecha_nacimiento=?, sexo=?, telefono=?, email=?,
                           direccion=?, localidad=?, municipio=?, departamento=?, zona=?
                     WHERE id=?""",
                    (
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
                        pid,
                    ),
                )
            return pid
        with self.db:
            cur = self.db.execute(
                """INSERT INTO pacientes(
                       numero_documento, nombre, fecha_nacimiento, sexo, telefono, email,
                       direccion, localidad, municipio, departamento, zona, activo
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    numero_documento,
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
                ),
            )
        return int(cur.lastrowid)

    def insert_registro(
        self,
        fecha: date,
        programa_id: int,
        convenio_id: int,
        institucion_id: int,
        profesor_id: int,
        paciente_id: Optional[int],
        localidad,
        municipio,
        departamento,
        numero_paciente,
        nombre_paciente,
        actividad,
        atendido,
        registrado_panacea,
        paciente_creado_panacea,
        paciente_priorizado,
        priorizado_origen,
        duracion_minutos,
        tipo_contacto,
        observaciones,
        creado_por,
    ) -> None:
        row = {
            "fecha": fecha.strftime("%Y-%m-%d") if isinstance(fecha, date) else str(fecha),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "paciente_id": paciente_id,
            "localidad": localidad,
            "municipio": municipio,
            "departamento": departamento,
            "numero_paciente": (numero_paciente or "").strip() or None,
            "nombre_paciente": (nombre_paciente or "").strip() or None,
            "actividad": actividad,
            "atendido": 1 if atendido else 0,
            "registrado_panacea": 1 if registrado_panacea else 0,          # atención
            "paciente_creado_panacea": 1 if paciente_creado_panacea else 0, # paciente
            "paciente_priorizado": 1 if paciente_priorizado else 0,         # ⬅️ nuevo
            "priorizado_origen": priorizado_origen,
            "duracion_minutos": int(duracion_minutos) if duracion_minutos is not None else None,
            "tipo_contacto": tipo_contacto,
            "pacientes_programados": 1,
            "pacientes_atendidos": 1 if atendido else 0,
            "observaciones": observaciones,
            "creado_por": creado_por,
            "creado_en": _now(),
            "actualizado_en": _now(),
        }
        cols = ",".join(row.keys())
        ph = ",".join(["?"] * len(row))
        with self.db:
            self.db.execute(f"INSERT INTO registros ({cols}) VALUES ({ph})", tuple(row.values()))

    def list_registros(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        q = (
            "SELECT r.*, p.nombre AS programa, c.nombre AS convenio, "
            "i.nombre AS institucion, f.nombre AS profesor, f.email AS profesor_email "
            "FROM registros r "
            "LEFT JOIN programas p ON p.id=r.programa_id "
            "LEFT JOIN convenios c ON c.id=r.convenio_id "
            "LEFT JOIN instituciones i ON i.id=r.institucion_id "
            "LEFT JOIN profesores f ON f.id=r.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(r.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(r.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                q += f" AND r.{k}=?"
                params.append(filtros[k])
        if filtros.get("actividad"):
            q += " AND r.actividad=?"
            params.append(filtros["actividad"])
        q += " ORDER BY r.fecha DESC, r.id DESC"

        df = pd.read_sql_query(q, self.db, params=params)
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

    def delete_registro(self, rid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM registros WHERE id=?", (rid,))

    def update_registro(self, rid: int, updates: Dict[str, Any]) -> None:
        updates = dict(updates)
        updates["actualizado_en"] = _now()
        sets = ",".join([f"{k}=?" for k in updates.keys()])
        with self.db:
            self.db.execute(f"UPDATE registros SET {sets} WHERE id=?", (*updates.values(), rid))

    # Viáticos
    def insert_viatico(
        self,
        fecha: date,
        programa_id,
        convenio_id,
        institucion_id,
        profesor_id,
        requiere_viatico,
        origen,
        destino,
        valor,
        observaciones,
        creado_por,
    ) -> None:
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "requiere_viatico": 1 if requiere_viatico else 0,
            "origen": origen,
            "destino": destino,
            "valor": float(valor) if valor is not None else None,
            "observaciones": observaciones,
            "creado_por": creado_por,
            "creado_en": _now(),
            "actualizado_en": _now(),
        }
        cols = ",".join(row.keys())
        ph = ",".join(["?"] * len(row))
        with self.db:
            self.db.execute(f"INSERT INTO viaticos ({cols}) VALUES ({ph})", tuple(row.values()))

    def list_viaticos(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        q = (
            "SELECT v.*, p.nombre AS programa, c.nombre AS convenio, "
            "i.nombre AS institucion, f.nombre AS profesor "
            "FROM viaticos v "
            "LEFT JOIN programas p ON p.id=v.programa_id "
            "LEFT JOIN convenios c ON c.id=v.convenio_id "
            "LEFT JOIN instituciones i ON i.id=v.institucion_id "
            "LEFT JOIN profesores f ON f.id=v.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(v.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(v.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                q += f" AND v.{k}=?"
                params.append(filtros[k])
        q += " ORDER BY v.fecha DESC, v.id DESC"
        return pd.read_sql_query(q, self.db, params=params)

    def delete_viatico(self, vid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM viaticos WHERE id=?", (vid,))

    # Agenda
    def insert_agenda_event(
        self,
        fecha: date,
        hi: Optional[dtime],
        hf: Optional[dtime],
        titulo: str,
        descripcion,
        programa_id,
        convenio_id,
        institucion_id,
        profesor_id,
        creado_por,
    ) -> None:
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "hora_inicio": hi.strftime("%H:%M") if hi else None,
            "hora_fin": hf.strftime("%H:%M") if hf else None,
            "titulo": titulo.strip(),
            "descripcion": descripcion,
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "creado_por": creado_por,
            "creado_en": _now(),
            "actualizado_en": _now(),
        }
        cols = ",".join(row.keys())
        ph = ",".join(["?"] * len(row))
        with self.db:
            self.db.execute(f"INSERT INTO agenda ({cols}) VALUES ({ph})", tuple(row.values()))

    def list_agenda(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        q = (
            "SELECT a.*, p.nombre AS programa, c.nombre AS convenio, "
            "i.nombre AS institucion, f.nombre AS profesor "
            "FROM agenda a "
            "LEFT JOIN programas p ON p.id=a.programa_id "
            "LEFT JOIN convenios c ON c.id=a.convenio_id "
            "LEFT JOIN instituciones i ON i.id=a.institucion_id "
            "LEFT JOIN profesores f ON f.id=a.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(a.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(a.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                q += f" AND a.{k}=?"
                params.append(filtros[k])
        q += " ORDER BY a.fecha ASC, a.hora_inicio ASC"
        return pd.read_sql_query(q, self.db, params=params)

    def get_agenda_by_id(self, eid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM agenda WHERE id=?", (eid,)).fetchone()
        return dict(r) if r else None

    def update_agenda_event(self, eid: int, updates: Dict[str, Any]) -> None:
        updates = dict(updates)
        updates["actualizado_en"] = _now()
        sets = ",".join([f"{k}=?" for k in updates.keys()])
        with self.db:
            self.db.execute(f"UPDATE agenda SET {sets} WHERE id=?", (*updates.values(), eid))

    def delete_agenda_event(self, eid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM agenda WHERE id=?", (eid,))

    # Papelería
    def insert_papeleria(
        self,
        fecha: date,
        programa_id,
        convenio_id,
        institucion_id,
        profesor_id,
        item: str,
        cantidad: Optional[int],
        estado: str,
        observaciones: Optional[str],
        creado_por: str,
    ) -> None:
        row = {
            "fecha": fecha.strftime("%Y-%m-%d"),
            "programa_id": programa_id,
            "convenio_id": convenio_id,
            "institucion_id": institucion_id,
            "profesor_id": profesor_id,
            "item": item.strip(),
            "cantidad": cantidad,
            "estado": estado,
            "observaciones": observaciones,
            "creado_por": creado_por,
            "creado_en": _now(),
            "actualizado_en": _now(),
        }
        cols = ",".join(row.keys())
        ph = ",".join(["?"] * len(row))
        with self.db:
            self.db.execute(f"INSERT INTO papeleria ({cols}) VALUES ({ph})", tuple(row.values()))

    def list_papeleria(self, filtros: Dict[str, Any]) -> pd.DataFrame:
        q = (
            "SELECT pa.*, p.nombre AS programa, c.nombre AS convenio, "
            "i.nombre AS institucion, f.nombre AS profesor "
            "FROM papeleria pa "
            "LEFT JOIN programas p ON p.id=pa.programa_id "
            "LEFT JOIN convenios c ON c.id=pa.convenio_id "
            "LEFT JOIN instituciones i ON i.id=pa.institucion_id "
            "LEFT JOIN profesores f ON f.id=pa.profesor_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(pa.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(pa.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "profesor_id"]:
            if filtros.get(k):
                q += f" AND pa.{k}=?"
                params.append(filtros[k])
        q += " ORDER BY pa.fecha DESC, pa.id DESC"
        return pd.read_sql_query(q, self.db, params=params)

    def get_papeleria_by_id(self, pid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM papeleria WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def update_papeleria(self, pid: int, updates: Dict[str, Any]) -> None:
        updates = dict(updates)
        updates["actualizado_en"] = _now()
        sets = ",".join([f"{k}=?" for k in updates.keys()])
        with self.db:
            self.db.execute(f"UPDATE papeleria SET {sets} WHERE id=?", (*updates.values(), pid))

    def delete_papeleria(self, pid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM papeleria WHERE id=?", (pid,))

DATA = DataAccess(SQLITE_CONN)

# ---------------- BACKUP HELPERS ----------------
def backup_sqlite_file() -> bytes:
    try:
        SQLITE_CONN.commit()
    except Exception:
        pass
    with open(DB_SQLITE_PATH, "rb") as f:
        return f.read()

def build_zip_backup() -> bytes:
    try:
        SQLITE_CONN.commit()
    except Exception:
        pass
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # DB
        if os.path.exists(DB_SQLITE_PATH):
            z.writestr(os.path.basename(DB_SQLITE_PATH), backup_sqlite_file())
        # CSV de tablas
        tbls = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
            SQLITE_CONN,
        )
        for t in tbls["name"].tolist():
            try:
                df = pd.read_sql_query(f"SELECT * FROM {t}", SQLITE_CONN)
                z.writestr(f"csv/{t}.csv", df.to_csv(index=False))
            except Exception as e:
                z.writestr(f"csv/{t}_ERROR.txt", f"No se pudo exportar {t}: {e}")
        # schema
        try:
            ddl_joined = "\n\n".join(SQLITE_DDL.values())
            z.writestr("schema.sql", ddl_joined)
        except Exception:
            pass
    buf.seek(0)
    return buf.getvalue()

# ---------------- ESTADO / LOGIN ----------------
def ensure_session_state():
    if "filters" not in st.session_state:
        st.session_state.filters = {}
    if "user" not in st.session_state:
        st.session_state.user = None
    if "role" not in st.session_state:
        st.session_state.role = None

ensure_session_state()

def sidebar_filters():
    st.sidebar.header("Filtros")
    hoy = date.today()
    fdesde = st.sidebar.date_input(
        "Desde", value=st.session_state.filters.get("fecha_desde", hoy.replace(day=1)), key="flt_desde"
    )
    fhasta = st.sidebar.date_input("Hasta", value=st.session_state.filters.get("fecha_hasta", hoy), key="flt_hasta")

    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = st.sidebar.selectbox("Programa", options=["(Todos)"] + list(prog_map.keys()), key="flt_programa")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = st.sidebar.selectbox("Convenio", options=["(Todos)"] + list(conv_map.keys()), key="flt_convenio")
    cid = conv_map.get(csel)

    prof = DATA.list_profesores(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = st.sidebar.selectbox("Profesional", options=["(Todos)"] + list(prof_map.keys()), key="flt_profesional")
    fid = prof_map.get(fsel)

    act = st.sidebar.selectbox("Actividad / plantilla", options=["(Todas)"] + ACTIVIDADES_PLANTILLAS, key="flt_actividad")

    st.session_state.filters = {
        "fecha_desde": fdesde,
        "fecha_hasta": fhasta,
        "programa_id": pid,
        "convenio_id": cid,
        "profesor_id": fid,
        "actividad": (None if act == "(Todas)" else act),
    }

def render_login():
    with st.sidebar:
        if st.session_state.user:
            st.success(f"Sesión: {st.session_state.user} ({st.session_state.role})")
            if st.button("Cerrar sesión", key="login_logout", use_container_width=True):
                st.session_state.user = None
                st.session_state.role = None
                st.rerun()
        else:
            st.markdown("### Iniciar sesión")
            u = st.text_input("Usuario", key="login_user")
            p = st.text_input("Contraseña", type="password", key="login_pass")
            if st.button("Ingresar", key="login_btn", use_container_width=True):
                user = USERS.get(u)
                if user and p == user["password"]:
                    st.session_state.user = u
                    st.session_state.role = user["role"]
                    success_toast("Ingreso exitoso.")
                    st.rerun()
                else:
                    error_toast("Usuario o contraseña incorrectos.")

# ---------------- CARGA MASIVA DE ATENCIONES (helper) ----------------
def plantilla_atenciones_df() -> pd.DataFrame:
    cols = [
        "fecha",
        "programa",
        "convenio",
        "institucion",
        "departamento",
        "municipio",
        "localidad",
        "profesional",
        "documento",
        "nombre",
        "actividad",
        "atendido",
        "registrado_panacea",        # atención registrada
        "paciente_creado_panacea",   # paciente creado en Panacea
        "paciente_priorizado",       # ⬅️ nuevo
        "priorizado_origen",         # ⬅️ nuevo (si está priorizado)
        "tipo_contacto",
        "duracion_minutos",
        "observaciones",
        "sexo",
        "fecha_nacimiento",
        "telefono",
        "email",
        "direccion",
        "zona",
    ]
    return pd.DataFrame(columns=cols)

def parse_fecha(value) -> str:
    if pd.isna(value) or value is None:
        return date.today().strftime("%Y-%m-%d")
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip().replace("/", "-")
    try:
        return pd.to_datetime(s, dayfirst=True, errors="coerce").strftime("%Y-%m-%d")
    except Exception:
        return date.today().strftime("%Y-%m-%d")

def procesar_atenciones_masivo(df: pd.DataFrame, auth_user: str) -> Tuple[int, List[str]]:
    """
    Columnas mínimas: fecha, programa, convenio, institucion, profesional, documento, nombre, actividad
    Opcionales: departamento, municipio, localidad, atendido, registrado_panacea, paciente_creado_panacea,
                paciente_priorizado, priorizado_origen, tipo_contacto, duracion_minutos, observaciones,
                sexo, fecha_nacimiento, telefono, email, direccion, zona
    """
    df = normalize_columns(df.copy())
    req = {"fecha", "programa", "convenio", "institucion", "profesional", "documento", "nombre", "actividad"}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas obligatorias: {sorted(list(missing))}")

    ok = 0
    errores: List[str] = []
    for idx, r in df.iterrows():
        try:
            # Fecha
            f_raw = r.get("fecha")
            fecha = parse_fecha(f_raw)

            # Programa y convenio (auto-upsert)
            p_name = str(r.get("programa") or "").strip()
            c_name = str(r.get("convenio") or "").strip()
            if not p_name or not c_name:
                raise ValueError("Programa y convenio son obligatorios")
            pid = DATA.programa_id_by_name(p_name) or DATA.upsert_programa(p_name)
            cid = DATA.convenio_id_by_name(c_name, pid) or DATA.upsert_convenio(c_name, pid)

            # Institución (auto-upsert con geo si viene)
            i_name = str(r.get("institucion") or "").strip()
            dep = str(r.get("departamento") or "").strip() or None
            mun = str(r.get("municipio") or "").strip() or None
            loc = str(r.get("localidad") or "").strip() or None
            if not i_name:
                raise ValueError("Institución es obligatoria")
            iid = DATA.institucion_id_by_name_geo(i_name, mun, dep) or DATA.upsert_institucion(i_name, loc, mun, dep)
            inst_row = SQLITE_CONN.execute("SELECT * FROM instituciones WHERE id=?", (iid,)).fetchone()
            localidad_val = inst_row["localidad"]
            municipio_val = inst_row["municipio"]
            departamento_val = inst_row["departamento"]

            # Profesional (auto-upsert)
            f_name = str(r.get("profesional") or "").strip()
            if not f_name:
                raise ValueError("Profesional es obligatorio")
            fid = DATA.profesor_id_by_name(f_name, pid, cid) or DATA.upsert_profesor(f_name, None, None, pid, cid, None)

            # Paciente (upsert)
            doc = str(r.get("documento") or "").strip()
            nom = str(r.get("nombre") or "").strip()
            if not doc or not nom:
                raise ValueError("Documento y nombre del paciente son obligatorios")
            pac_id = DATA.upsert_paciente(
                numero_documento=doc,
                nombre=nom,
                fecha_nacimiento=str(r.get("fecha_nacimiento")) if pd.notna(r.get("fecha_nacimiento")) else None,
                sexo=str(r.get("sexo")).strip() if pd.notna(r.get("sexo")) else None,
                telefono=str(r.get("telefono")).strip() if pd.notna(r.get("telefono")) else None,
                email=str(r.get("email")).strip() if pd.notna(r.get("email")) else None,
                direccion=str(r.get("direccion")).strip() if pd.notna(r.get("direccion")) else None,
                localidad=None,
                municipio=None,
                departamento=None,
                zona=str(r.get("zona")).strip() if pd.notna(r.get("zona")) else None,
            )

            # Campos de la atención
            actividad = str(r.get("actividad") or "").strip() or ACTIVIDADES_PLANTILLAS[0]
            atendido = bool(str2bool(r.get("atendido")))

            # atención registrada en Panacea (NO el paciente)
            reg_field_att = next(
                (
                    c
                    for c in [
                        "registrado_panacea",
                        "atencion_en_panacea",
                        "atencion_registrada_panacea",
                        "en_panacea",
                    ]
                    if c in df.columns
                ),
                None,
            )
            registrado_panacea = bool(str2bool(r.get(reg_field_att))) if reg_field_att else False

            # paciente creado en Panacea
            reg_field_pac = next(
                (
                    c
                    for c in [
                        "paciente_creado_panacea",
                        "paciente_en_panacea",
                        "creado_panacea",
                        "paciente_creado",
                    ]
                    if c in df.columns
                ),
                None,
            )
            paciente_creado_panacea = bool(str2bool(r.get(reg_field_pac))) if reg_field_pac else False

            # priorizado
            paciente_priorizado = bool(str2bool(r.get("paciente_priorizado"))) if "paciente_priorizado" in df.columns else False
            priorizado_origen = None
            if paciente_priorizado:
                priorizado_origen = str(r.get("priorizado_origen")).strip() if pd.notna(r.get("priorizado_origen")) else None
                if priorizado_origen == "":
                    priorizado_origen = None

            tipo_contacto = str(r.get("tipo_contacto")).strip() if pd.notna(r.get("tipo_contacto")) else None
            if tipo_contacto in ("", "(no especifica)", "no especifica"):
                tipo_contacto = None
            duracion = safe_int(r.get("duracion_minutos"))

            # Insert
            DATA.insert_registro(
                fecha=fecha,
                programa_id=pid,
                convenio_id=cid,
                institucion_id=iid,
                profesor_id=fid,
                paciente_id=pac_id,
                localidad=localidad_val,
                municipio=municipio_val,
                departamento=departamento_val,
                numero_paciente=doc,
                nombre_paciente=nom,
                actividad=actividad,
                atendido=atendido,
                registrado_panacea=registrado_panacea,
                paciente_creado_panacea=paciente_creado_panacea,
                paciente_priorizado=paciente_priorizado,
                priorizado_origen=priorizado_origen,
                duracion_minutos=duracion,
                tipo_contacto=tipo_contacto,
                observaciones=(str(r.get("observaciones")).strip() if pd.notna(r.get("observaciones")) else None),
                creado_por=auth_user,
            )
            ok += 1
        except Exception as e:
            errores.append(f"Fila {idx+2}: {e}")
    return ok, errores

# ---------------- UI: REGISTRAR ATENCION ----------------
def ui_cargar_datos(auth_user: Optional[str]):
    st.subheader("Registrar atención / paciente")

    def K(x: str) -> str:
        return f"reg_{x}"

    # Estado para autocompletado
    defaults = {
        K("pac_nombre"): "",
        K("pac_fecha_nac"): "",
        K("pac_telefono"): "",
        K("pac_email"): "",
        K("pac_direccion"): "",
        K("pac_localidad"): "",
        K("pac_municipio"): "",
        K("pac_departamento"): "",
        K("pac_sexo"): "(No especifica)",
        K("pac_zona"): "(No especifica)",
        K("pac_id_actual"): None,
        K("pac_doc"): "",
        K("pac_creado_panacea"): False,
        K("pac_priorizado"): False,          # ⬅️ nuevo
        K("priorizado_origen"): "(Seleccione)",  # ⬅️ nuevo
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Selección programa/convenio/profesional
    c1, c2 = st.columns([1.4, 1.4])
    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c1.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key=K("form_programa"))
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else pd.DataFrame()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c1.selectbox("Convenio", options=list(conv_map.keys()) if conv_map else [], key=K("form_convenio"))
    cid = conv_map.get(csel)

    prof = DATA.list_profesores(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c2.selectbox("Profesional", options=list(prof_map.keys()) if prof_map else [], key=K("form_profesional"))
    fid = prof_map.get(fsel)

    # Ubicación e institución
    instituciones = DATA.list_instituciones()
    institucion_id = None
    localidad_val = municipio_val = departamento_val = None

    st.markdown("#### Ubicación e institución")
    if instituciones.empty:
        st.info("No hay instituciones configuradas. Crea instituciones en Configuración.")
    else:
        g1, g2, g3, g4 = st.columns([1, 1, 1, 2])
        deps = sorted({str(x) for x in instituciones["departamento"].dropna().unique()})
        dep_sel = g1.selectbox("Departamento", options=deps, key=K("departamento_sel")) if deps else None

        inst_dep = instituciones if not dep_sel else instituciones[instituciones["departamento"] == dep_sel]
        muns = sorted({str(x) for x in inst_dep["municipio"].dropna().unique()})
        mun_sel = g2.selectbox("Municipio", options=["(Todos)"] + muns, key=K("municipio_sel")) if muns else "(Todos)"

        inst_mun = inst_dep if mun_sel == "(Todos)" else inst_dep[inst_dep["municipio"] == mun_sel]
        locs = sorted({str(x) for x in inst_mun["localidad"].dropna().unique()})
        loc_label = "Localidad (Bogotá)" if dep_sel and "BOGOTA" in dep_sel.upper() else "Localidad"
        loc_sel = g3.selectbox(loc_label, options=["(Todas)"] + locs, key=K("localidad_sel")) if locs else "(Todas)"

        inst_geo = inst_mun if loc_sel == "(Todas)" else inst_mun[inst_mun["localidad"] == loc_sel]
        inst_map = {r["nombre"]: int(r["id"]) for _, r in inst_geo.iterrows()}
        inst_sel = g4.selectbox("Institución", options=list(inst_map.keys()) if inst_map else [], key=K("institucion_sel"))
        institucion_id = inst_map.get(inst_sel)
        if institucion_id:
            row = instituciones[instituciones["id"] == institucion_id].iloc[0]
            localidad_val = row.get("localidad")
            municipio_val = row.get("municipio")
            departamento_val = row.get("departamento")

    # Fecha y actividad
    c3, c4 = st.columns([1, 1])
    fecha = c3.date_input("Fecha de la atención", value=date.today(), key=K("fecha"))
    actividad = c4.selectbox("Actividad / plantilla", ACTIVIDADES_PLANTILLAS, key=K("actividad"))

    # ---------------- AUTORELLENO PACIENTE ----------------
    st.markdown("#### Datos del paciente")
    p1, p2 = st.columns([1, 1])
    p1.text_input("Documento del paciente (cédula)", key=K("pac_doc"))
    if p2.button("Buscar paciente por documento", key=K("btn_buscar_paciente")):
        try:
            doc_trim = (st.session_state[K("pac_doc")] or "").strip()
            pac = DATA.get_paciente_por_documento(doc_trim)
            if pac:
                st.session_state[K("pac_id_actual")] = pac.get("id")
                st.session_state[K("pac_nombre")] = pac.get("nombre", "") or ""
                st.session_state[K("pac_sexo")] = pac.get("sexo") if pac.get("sexo") in ["F", "M", "Otro"] else "(No especifica)"
                st.session_state[K("pac_fecha_nac")] = pac.get("fecha_nacimiento", "") or ""
                st.session_state[K("pac_telefono")] = pac.get("telefono", "") or ""
                st.session_state[K("pac_email")] = pac.get("email", "") or ""
                st.session_state[K("pac_direccion")] = pac.get("direccion", "") or ""
                st.session_state[K("pac_localidad")] = pac.get("localidad", "") or ""
                st.session_state[K("pac_municipio")] = pac.get("municipio", "") or ""
                st.session_state[K("pac_departamento")] = pac.get("departamento", "") or ""
                st.session_state[K("pac_zona")] = pac.get("zona") if pac.get("zona") in ["Urbana", "Rural"] else "(No especifica)"
                success_toast("Paciente encontrado. Campos autocompletados.")
                st.rerun()
            else:
                st.session_state[K("pac_id_actual")] = None
                warn_toast("No se encontró paciente. Diligencia y se creará.")
        except Exception as e:
            error_toast(f"Error buscando paciente: {e}")

    p3, p4 = st.columns([1.5, 1])
    p3.text_input("Nombre completo del paciente", key=K("pac_nombre"))
    sexo_opts = ["(No especifica)", "F", "M", "Otro"]
    st.session_state.setdefault(K("pac_sexo"), "(No especifica)")
    p4.selectbox("Sexo (opcional)", options=sexo_opts, key=K("pac_sexo"))

    p5, p6 = st.columns([1, 1])
    p5.text_input("Fecha de nacimiento (AAAA-MM-DD, opcional)", key=K("pac_fecha_nac"))
    p6.text_input("Teléfono (opcional)", key=K("pac_telefono"))

    p7, p8 = st.columns([1, 1])
    p7.text_input("Email (opcional)", key=K("pac_email"))
    p8.text_input("Dirección (opcional)", key=K("pac_direccion"))

    p9, p10, p11 = st.columns([1, 1, 1])
    p9.text_input("Localidad paciente (opcional)", key=K("pac_localidad"))
    p10.text_input("Municipio paciente (opcional)", key=K("pac_municipio"))
    p11.text_input("Departamento paciente (opcional)", key=K("pac_departamento"))

    zcol, zcol2 = st.columns([1, 1])
    zona_opts = ["(No especifica)", "Urbana", "Rural"]
    st.session_state.setdefault(K("pac_zona"), "(No especifica)")
    zcol.selectbox("Zona (Rural/Urbana)", options=zona_opts, key=K("pac_zona"))

    # ----- NUEVOS CHECKS -----
    zcol2.checkbox("Paciente creado en Panacea", key=K("pac_creado_panacea"))  # paciente
    c9, c10 = st.columns([1, 1])
    c9.radio("¿Atendido?", ["No", "Sí"], index=1, horizontal=True, key=K("atendido"))
    c10.checkbox("Atención registrada en Panacea", key=K("reg_panacea"))       # atención

    # Prioridad condicional
    pr1, pr2 = st.columns([1, 1])
    pr1.checkbox("Paciente priorizado", key=K("pac_priorizado"))
    show_origen = st.session_state.get(K("pac_priorizado"), False)
    if show_origen:
        # Si está priorizado, mostramos el origen
        current = st.session_state.get(K("priorizado_origen")) or "(Seleccione)"
        pr2.selectbox("Origen priorización", options=["(Seleccione)"] + PRIORI_ORIGEN_OPTS, key=K("priorizado_origen"))
    else:
        # Limpiamos origen si se desmarca
        st.session_state[K("priorizado_origen")] = "(Seleccione)"

    c11, c12 = st.columns([1, 1])
    c11.selectbox("Tipo de contacto", options=["(No especifica)"] + TIPOS_CONTACTO, key=K("tipo_contacto"))
    c12.number_input("Duración de la atención (minutos, opcional)", min_value=0, max_value=480, step=5, key=K("duracion_minutos"))

    observaciones = st.text_area("Observaciones", key=K("observaciones"))

    # Guardar atención (manual)
    clicked = st.button("Guardar atención", type="primary", use_container_width=True, key=K("btn_guardar_atencion"))
    if clicked:
        faltantes = []
        if not pid:
            faltantes.append("Programa")
        if not cid:
            faltantes.append("Convenio")
        if not fid:
            faltantes.append("Profesional")
        if not institucion_id:
            faltantes.append("Institución")
        if not (st.session_state.get(K("pac_doc")) or "").strip():
            faltantes.append("Documento del paciente")
        if not (st.session_state.get(K("pac_nombre")) or "").strip():
            faltantes.append("Nombre del paciente")

        if st.session_state.get(K("pac_priorizado")) and st.session_state.get(K("priorizado_origen")) in (None, "", "(Seleccione)"):
            faltantes.append("Origen de priorización")

        if faltantes:
            error_toast("Faltan datos obligatorios: " + ", ".join(faltantes))
        else:
            try:
                dur = st.session_state.get(K("duracion_minutos")) or 0
                dur_val = int(dur) if dur and dur > 0 else None
                tc = st.session_state.get(K("tipo_contacto"))
                tipo_contacto_val = None if tc == "(No especifica)" else tc
                sexo_val = None if st.session_state[K("pac_sexo")] == "(No especifica)" else st.session_state[K("pac_sexo")]
                zona_val = None if st.session_state[K("pac_zona")] == "(No especifica)" else st.session_state[K("pac_zona")]

                pac_id = DATA.upsert_paciente(
                    numero_documento=(st.session_state[K("pac_doc")] or "").strip(),
                    nombre=(st.session_state[K("pac_nombre")] or "").strip(),
                    fecha_nacimiento=(st.session_state[K("pac_fecha_nac")] or None),
                    sexo=sexo_val,
                    telefono=(st.session_state[K("pac_telefono")] or None),
                    email=(st.session_state[K("pac_email")] or None),
                    direccion=(st.session_state[K("pac_direccion")] or None),
                    localidad=(st.session_state[K("pac_localidad")] or None),
                    municipio=(st.session_state[K("pac_municipio")] or None),
                    departamento=(st.session_state[K("pac_departamento")] or None),
                    zona=zona_val,
                )

                priorizado = bool(st.session_state[K("pac_priorizado")])
                priorizado_origen = (
                    None
                    if not priorizado or st.session_state[K("priorizado_origen")] in ("", "(Seleccione)")
                    else st.session_state[K("priorizado_origen")]
                )

                DATA.insert_registro(
                    fecha=st.session_state[K("fecha")],
                    programa_id=int(pid),
                    convenio_id=int(cid),
                    institucion_id=int(institucion_id),
                    profesor_id=int(fid),
                    paciente_id=pac_id,
                    localidad=localidad_val,
                    municipio=municipio_val,
                    departamento=departamento_val,
                    numero_paciente=(st.session_state[K("pac_doc")] or "").strip(),
                    nombre_paciente=(st.session_state[K("pac_nombre")] or "").strip(),
                    actividad=st.session_state[K("actividad")],
                    atendido=True if st.session_state[K("atendido")] == "Sí" else False,
                    registrado_panacea=bool(st.session_state[K("reg_panacea")]),          # atención
                    paciente_creado_panacea=bool(st.session_state[K("pac_creado_panacea")]),  # paciente
                    paciente_priorizado=priorizado,
                    priorizado_origen=priorizado_origen,
                    duracion_minutos=dur_val,
                    tipo_contacto=tipo_contacto_val,
                    observaciones=observaciones,
                    creado_por=auth_user,
                )
                success_toast("Atención registrada.")
                st.rerun()
            except Exception as e:
                error_toast(f"Error al guardar: {e}")

    st.markdown("---")
    with st.expander("📥 Carga masiva de atenciones (Excel/CSV)", expanded=False):
        def KM(x: str) -> str:
            return f"regm_{x}"

        tpl = plantilla_atenciones_df()

        def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as w:
                for name, df in sheets.items():
                    dd = df.copy()
                    dd.columns = [str(c)[:40] for c in dd.columns]
                    dd.to_excel(w, sheet_name=name[:31], index=False)
            return out.getvalue()

        tpl_xlsx = to_excel_bytes({"Atenciones": tpl})
        st.download_button(
            "Descargar plantilla (.xlsx)",
            data=tpl_xlsx,
            file_name="plantilla_atenciones.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=KM("dl_xlsx"),
        )
        st.download_button(
            "Descargar plantilla (.csv)",
            data=tpl.to_csv(index=False).encode("utf-8"),
            file_name="plantilla_atenciones.csv",
            mime="text/csv",
            use_container_width=True,
            key=KM("dl_csv"),
        )

        st.caption(
            "**Obligatorias**: fecha, programa, convenio, institucion, profesional, documento, nombre, actividad. "
            "**Opcionales**: departamento, municipio, localidad, atendido, registrado_panacea (atención), "
            "paciente_creado_panacea (paciente), **paciente_priorizado**, **priorizado_origen**, "
            "tipo_contacto, duracion_minutos, observaciones, sexo, fecha_nacimiento, "
            "telefono, email, direccion, zona."
        )

        up = st.file_uploader("Archivo de atenciones", type=["xlsx", "xls", "csv"], key=KM("file"))
        if up is not None and st.button("Procesar atenciones", type="primary", use_container_width=True, key=KM("btn")):
            try:
                df_up = read_table_upload(up)
                ok, errores = procesar_atenciones_masivo(df_up, auth_user or "desconocido")
                if ok:
                    success_toast(f"Atenciones procesadas: {ok}")
                if errores:
                    st.error("Se encontraron errores:")
                    for e in errores[:500]:
                        st.write(f"- {e}")
                if ok:
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando archivo: {e}")

# ---------------- UI: LISTADO ----------------
def ui_registros():
    st.subheader("Listado de atenciones")
    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("Sin registros.")
        return

    if "tasa_atencion" in df.columns:
        df["tasa_atencion_%"] = (df["tasa_atencion"] * 100).round(1)

    show = [
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
        "paciente_creado_panacea",
        "registrado_panacea",
        "paciente_priorizado",  # ⬅️ nuevo visible
        "priorizado_origen",    # ⬅️ nuevo visible
        "pacientes_programados",
        "pacientes_atendidos",
        "no_asistieron",
        "tasa_atencion_%",
        "observaciones",
        "creado_por",
        "creado_en",
        "actualizado_en",
    ]
    st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 3])
    rid = c1.number_input("ID de atención", min_value=1, step=1, key="lst_reg_id_sel")
    if c2.button("Eliminar atención", use_container_width=True, key="lst_btn_eliminar_reg"):
        try:
            DATA.delete_registro(int(rid))
            success_toast("Eliminado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

# ---------------- UI: DASHBOARD ----------------
def ui_dashboard():
    st.subheader("Dashboard de gestión")
    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("Sin datos para graficar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"])
    total_prog = int(df["pacientes_programados"].sum())
    total_att = int(df["pacientes_atendidos"].sum())
    total_no = int(df["no_asistieron"].sum())
    tasa = (total_att / total_prog * 100) if total_prog else 0.0
    total_min = int(df.get("duracion_minutos", pd.Series()).fillna(0).sum()) if "duracion_minutos" in df.columns else 0
    n_con = int(df.get("duracion_minutos", pd.Series()).notna().sum()) if "duracion_minutos" in df.columns else 0
    prom = (total_min / n_con) if n_con else 0.0
    horas = total_min / 60 if total_min > 0 else 0.0
    prod_ph = (total_att / horas) if horas > 0 else 0.0
    total_pan = int(df.get("registrado_panacea", pd.Series()).fillna(0).sum()) if "registrado_panacea" in df.columns else 0
    total_pac_creados = int(df.get("paciente_creado_panacea", pd.Series()).fillna(0).sum()) if "paciente_creado_panacea" in df.columns else 0
    total_priorizados = int(df.get("paciente_priorizado", pd.Series()).fillna(0).sum()) if "paciente_priorizado" in df.columns else 0
    brecha = total_att - total_pan

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Programados", f"{total_prog:,}".replace(",", "."))
    k2.metric("Atendidos", f"{total_att:,}".replace(",", "."))
    k3.metric("No asistieron", f"{total_no:,}".replace(",", "."))
    k4.metric("Tasa atención", f"{tasa:.1f}%")

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Minutos", f"{total_min:,}".replace(",", "."))
    k6.metric("Duración prom (min)", f"{prom:.1f}")
    k7.metric("Atenciones/hora", f"{prod_ph:.2f}")
    k8.metric("Atención en Panacea / brecha", f"{total_pan} / {brecha}")

    k9, k10 = st.columns([1, 1])
    k9.metric("Pacientes CRE. Panacea (registros)", f"{total_pac_creados:,}".replace(",", "."))
    k10.metric("Pacientes priorizados", f"{total_priorizados:,}".replace(",", "."))

    # Tendencia semanal
    tdf = df.groupby(pd.Grouper(key="fecha", freq="W"))[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()
    st.plotly_chart(
        px.line(tdf, x="fecha", y=["pacientes_programados", "pacientes_atendidos"], markers=True, title="Tendencia semanal"),
        use_container_width=True,
    )

    # Ranking profesional
    rank = (
        df.groupby("profesor", dropna=True)["pacientes_atendidos"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
    )
    fig2 = px.bar(rank, x="profesor", y="pacientes_atendidos", title="Top profesionales")
    fig2.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig2, use_container_width=True)

    # Cargadas a Panacea vs Atendidas
    if "registrado_panacea" in df.columns:
        pan = (
            df.groupby("profesor", dropna=True)
            .agg(
                pacientes_atendidos=("pacientes_atendidos", "sum"),
                cargadas_panacea=("registrado_panacea", "sum"),
            )
            .reset_index()
        )
        pan["brecha"] = pan["pacientes_atendidos"] - pan["cargadas_panacea"]
        fig2b = px.bar(
            pan.sort_values("brecha", ascending=False).head(15),
            x="profesor",
            y=["pacientes_atendidos", "cargadas_panacea"],
            barmode="group",
            title="Atenciones vs Panacea por profesional",
        )
        fig2b.update_layout(xaxis_tickangle=-40)
        st.plotly_chart(fig2b, use_container_width=True)

    # Prioridad: distribución por origen
    if "paciente_priorizado" in df.columns:
        dist = (
            df.assign(
                priorizado=df["paciente_priorizado"].fillna(0).astype(int),
                prior_origen=df["priorizado_origen"].fillna("(Sin origen)"),
            )
            .groupby("prior_origen")["priorizado"]
            .sum()
            .reset_index()
            .sort_values("priorizado", ascending=False)
        )
        figp = px.bar(dist, x="prior_origen", y="priorizado", title="Pacientes priorizados por origen")
        figp.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(figp, use_container_width=True)

    # Por actividad
    act_sum = df.groupby("actividad")[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()
    st.plotly_chart(
        px.bar(
            act_sum,
            x="actividad",
            y=["pacientes_programados", "pacientes_atendidos"],
            barmode="group",
            title="Por actividad",
        ),
        use_container_width=True,
    )

# ---------------- UI: REPORTES ----------------
def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in sheets.items():
            dd = df.copy()
            dd.columns = [str(c)[:40] for c in dd.columns]
            dd.to_excel(w, sheet_name=name[:31], index=False)
    return out.getvalue()

def ui_reportes():
    st.subheader("Reportes y descargas")
    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("Sin registros para descargar.")
        return

    agg_prof = (
        df.groupby("profesor", dropna=True)
        .agg(
            pacientes_programados=("pacientes_programados", "sum"),
            pacientes_atendidos=("pacientes_atendidos", "sum"),
            cargadas_panacea=("registrado_panacea", "sum"),
            pac_creados_panacea=("paciente_creado_panacea", "sum"),
            priorizados=("paciente_priorizado", "sum"),
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

    por_inst = df.groupby("institucion", dropna=True)[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()
    por_geo = (
        df.groupby(["departamento", "municipio"], dropna=True)[["pacientes_programados", "pacientes_atendidos"]]
        .sum()
        .reset_index()
    )
    por_act = df.groupby("actividad")[["pacientes_programados", "pacientes_atendidos"]].sum().reset_index()
    por_prior_origen = (
        df.assign(prior_origen=df["priorizado_origen"].fillna("(Sin origen)"))
        .groupby("prior_origen")[["pacientes_atendidos"]]
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
            "Prior_por_origen": por_prior_origen,
        }
    )
    st.download_button(
        "Descargar Excel (.xlsx)",
        data=xls,
        file_name=f"productividad_profesionales_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="rep_btn_descargar_xlsx",
    )
    st.download_button(
        "Descargar detalle (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"productividad_profesionales_detalle_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="rep_btn_descargar_csv",
    )

# ---------------- UI: VIATICOS ----------------
def ui_viaticos(auth_user: Optional[str]):
    st.subheader("Registro de viáticos")
    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="via_fecha")

    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c2.selectbox("Programa (opcional)", options=["(Sin programa)"] + list(prog_map.keys()), key="via_programa")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c1.selectbox("Convenio (opcional)", options=["(Sin convenio)"] + list(conv_map.keys()), key="via_convenio")
    cid = conv_map.get(csel)

    prof = DATA.list_profesores(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c2.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="via_profesional")
    fid = prof_map.get(fsel)

    inst = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in inst.iterrows()} if not inst.empty else {}
    isel = st.selectbox("Institución destino (opcional)", options=["(Sin institución)"] + list(inst_map.keys()), key="via_institucion")
    iid = inst_map.get(isel)

    c5, c6 = st.columns([1, 1])
    req = c5.radio("¿Requiere viáticos?", ["No", "Sí"], index=1, horizontal=True, key="via_req")
    origen = c6.text_input("Sitio de origen", key="via_origen")
    destino = st.text_input("Sitio de destino", key="via_destino")
    valor = st.number_input("Valor de viáticos", min_value=0.0, step=1000.0, key="via_valor")
    obs = st.text_area("Observaciones (opcional)", key="via_obs")

    if st.button("Guardar viático", type="primary", use_container_width=True, key="via_guardar"):
        try:
            DATA.insert_viatico(
                fecha=fecha,
                programa_id=pid,
                convenio_id=cid,
                institucion_id=iid,
                profesor_id=fid,
                requiere_viatico=(req == "Sí"),
                origen=origen,
                destino=destino,
                valor=valor if valor > 0 else None,
                observaciones=obs,
                creado_por=auth_user,
            )
            success_toast("Viático registrado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo guardar: {e}")

    st.markdown("### Listado de viáticos")
    df = DATA.list_viaticos(st.session_state.filters)
    if df.empty:
        st.info("Sin viáticos.")
    else:
        df["requiere_viatico"] = df["requiere_viatico"].map({1: "Sí", 0: "No"})
        show = [
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
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)
        st.metric("Total viáticos (filtro)", f"${df['valor'].fillna(0).sum():,.0f}".replace(",", "."))

# ---------------- UI: PLANIFICADOR ----------------
def ui_planificador(auth_user: Optional[str]):
    st.subheader("Planificador (agenda)")

    # CREATE
    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="ag_fecha")
    hi = c1.time_input("Hora inicio", value=dtime(8, 0), key="ag_hora_ini")
    hf = c2.time_input("Hora fin", value=dtime(9, 0), key="ag_hora_fin")
    titulo = st.text_input("Título", key="ag_titulo")
    descripcion = st.text_area("Descripción / notas", key="ag_descripcion")

    c3, c4 = st.columns([1, 1])
    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c3.selectbox("Programa (opcional)", options=["(Sin programa)"] + list(prog_map.keys()), key="ag_programa")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c4.selectbox("Convenio (opcional)", options=["(Sin convenio)"] + list(conv_map.keys()), key="ag_convenio")
    cid = conv_map.get(csel)

    c5, c6 = st.columns([1, 1])
    inst = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in inst.iterrows()} if not inst.empty else {}
    isel = c5.selectbox("Institución (opcional)", options=["(Sin institución)"] + list(inst_map.keys()), key="ag_institucion")
    iid = inst_map.get(isel)

    prof = DATA.list_profesores(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c6.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="ag_profesor")
    fid = prof_map.get(fsel)

    if st.button("Guardar evento", type="primary", use_container_width=True, key="ag_guardar"):
        if not titulo.strip():
            warn_toast("Título obligatorio.")
        else:
            try:
                DATA.insert_agenda_event(fecha, hi, hf, titulo, descripcion, pid, cid, iid, fid, auth_user)
                success_toast("Evento registrado.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo guardar: {e}")

    st.markdown("### Agenda (según filtros)")
    df = DATA.list_agenda(st.session_state.filters)
    if df.empty:
        st.info("Sin eventos.")
    else:
        show = [
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
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    # EDIT / DELETE
    st.markdown("---")
    st.markdown("#### Editar / eliminar evento")
    c7, c8, c9 = st.columns([1, 1, 1])
    eid = c7.number_input("ID de evento", min_value=1, step=1, key="ag_edit_id")
    cargar = c8.button("Cargar", key="ag_edit_cargar")
    eliminar = c9.button("Eliminar", key="ag_edit_eliminar")

    if eliminar:
        try:
            DATA.delete_agenda_event(int(eid))
            success_toast("Evento eliminado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    if cargar:
        ev = DATA.get_agenda_by_id(int(eid))
        if not ev:
            warn_toast("No existe evento con ese ID.")
        else:
            e1, e2 = st.columns([1, 1])
            new_fecha = e1.date_input("Fecha", value=pd.to_datetime(ev["fecha"]).date(), key="ag_edit_fecha")
            new_hi = e1.time_input(
                "Hora inicio", value=dtime.fromisoformat(ev["hora_inicio"]) if ev["hora_inicio"] else dtime(8, 0), key="ag_edit_hi"
            )
            new_hf = e2.time_input(
                "Hora fin", value=dtime.fromisoformat(ev["hora_fin"]) if ev["hora_fin"] else dtime(9, 0), key="ag_edit_hf"
            )
            new_tit = st.text_input("Título", value=ev["titulo"], key="ag_edit_titulo")
            new_desc = st.text_area("Descripción / notas", value=ev["descripcion"] or "", key="ag_edit_desc")

            if st.button("Guardar cambios", type="primary", key="ag_edit_guardar"):
                try:
                    DATA.update_agenda_event(
                        int(eid),
                        {
                            "fecha": new_fecha.strftime("%Y-%m-%d"),
                            "hora_inicio": new_hi.strftime("%H:%M") if new_hi else None,
                            "hora_fin": new_hf.strftime("%H:%M") if new_hf else None,
                            "titulo": new_tit.strip(),
                            "descripcion": new_desc.strip() or None,
                        },
                    )
                    success_toast("Evento actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")

# ---------------- UI: PAPELERIA ----------------
def ui_papeleria(auth_user: Optional[str]):
    st.subheader("Solicitud de papelería")

    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="pp_fecha")
    item = c1.text_input("Ítem solicitado (ej. Historias, Carpetas, Esferos, Hojas A4)", key="pp_item")
    cantidad = c2.number_input("Cantidad", min_value=1, step=1, key="pp_cantidad")
    estado = c2.selectbox("Estado", options=["Solicitado", "Aprobado", "Entregado"], index=0, key="pp_estado")
    observ = st.text_area("Observaciones", key="pp_obs")

    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = st.selectbox("Programa (opcional)", options=["(Sin programa)"] + list(prog_map.keys()), key="pp_prog")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = st.selectbox("Convenio (opcional)", options=["(Sin convenio)"] + list(conv_map.keys()), key="pp_conv")
    cid = conv_map.get(csel)

    inst = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in inst.iterrows()} if not inst.empty else {}
    isel = st.selectbox("Institución (opcional)", options=["(Sin institución)"] + list(inst_map.keys()), key="pp_inst")
    iid = inst_map.get(isel)

    prof = DATA.list_profesores(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = st.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="pp_prof")
    fid = prof_map.get(fsel)

    if st.button("Guardar solicitud", type="primary", use_container_width=True, key="pp_guardar"):
        if not item.strip():
            warn_toast("Debes indicar el ítem solicitado.")
        else:
            try:
                DATA.insert_papeleria(fecha, pid, cid, iid, fid, item, int(cantidad), estado, observ or None, auth_user)
                success_toast("Solicitud registrada.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo guardar: {e}")

    st.markdown("### Solicitudes registradas (según filtros)")
    df = DATA.list_papeleria(st.session_state.filters)
    if df.empty:
        st.info("Sin solicitudes.")
    else:
        show = [
            "id",
            "fecha",
            "item",
            "cantidad",
            "estado",
            "programa",
            "convenio",
            "institucion",
            "profesor",
            "observaciones",
            "creado_por",
            "creado_en",
        ]
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Editar / eliminar solicitud")
    c7, c8, c9 = st.columns([1, 1, 1])
    pid_in = c7.number_input("ID de solicitud", min_value=1, step=1, key="pp_edit_id")
    cargar = c8.button("Cargar", key="pp_edit_cargar")
    eliminar = c9.button("Eliminar", key="pp_edit_eliminar")

    if eliminar:
        try:
            DATA.delete_papeleria(int(pid_in))
            success_toast("Solicitud eliminada.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    if cargar:
        rec = DATA.get_papeleria_by_id(int(pid_in))
        if not rec:
            warn_toast("No existe solicitud con ese ID.")
        else:
            e1, e2 = st.columns([1, 1])
            new_fecha = e1.date_input("Fecha", value=pd.to_datetime(rec["fecha"]).date(), key="pp_edit_fecha")
            new_item = e1.text_input("Ítem", value=rec["item"], key="pp_edit_item")
            new_cant = e2.number_input("Cantidad", min_value=1, step=1, value=int(rec["cantidad"] or 1), key="pp_edit_cant")
            new_estado = e2.selectbox(
                "Estado",
                options=["Solicitado", "Aprobado", "Entregado"],
                index=["Solicitado", "Aprobado", "Entregado"].index(rec["estado"] or "Solicitado"),
                key="pp_edit_estado",
            )
            new_obs = st.text_area("Observaciones", value=rec["observaciones"] or "", key="pp_edit_obs")

            if st.button("Guardar cambios", type="primary", key="pp_edit_guardar"):
                try:
                    DATA.update_papeleria(
                        int(pid_in),
                        {
                            "fecha": new_fecha.strftime("%Y-%m-%d"),
                            "item": new_item.strip(),
                            "cantidad": int(new_cant),
                            "estado": new_estado,
                            "observaciones": new_obs.strip() or None,
                        },
                    )
                    success_toast("Solicitud actualizada.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")

# ---------------- UI: CONFIGURACION ----------------
def ui_configuracion():
    st.subheader("Configuración de catálogos")
    tabs = st.tabs(["Programas", "Convenios", "Instituciones", "Profesionales", "Pacientes"])

    # Programas
    with tabs[0]:
        c1, c2 = st.columns([2, 1])
        pnom = c1.text_input("Nombre del programa", key="cfg_prog_nombre")
        if c2.button("Agregar programa", use_container_width=True, key="cfg_btn_add_programa"):
            if not pnom.strip():
                warn_toast("Escribe un nombre.")
            else:
                DATA.upsert_programa(pnom.strip())
                success_toast("Programa agregado.")
                st.rerun()
        st.dataframe(DATA.list_programas(), use_container_width=True, hide_index=True)

    # Convenios
    with tabs[1]:
        progs = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
        c1, c2, c3 = st.columns([2, 2, 1])
        cv_prog = c1.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key="cfg_conv_prog")
        cv_nom = c2.text_input("Nombre del convenio", key="cfg_conv_nombre")
        if c3.button("Agregar convenio", use_container_width=True, key="cfg_btn_add_convenio"):
            if not (cv_prog and cv_nom.strip()):
                warn_toast("Selecciona programa y nombre.")
            else:
                DATA.upsert_convenio(cv_nom.strip(), prog_map[cv_prog])
                success_toast("Convenio agregado.")
                st.rerun()
        st.dataframe(DATA.list_convenios(), use_container_width=True, hide_index=True)

    # Instituciones
    with tabs[2]:
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.2, 1.2, 1])
        i_nom = c1.text_input("Nombre institución", key="cfg_inst_nombre")
        i_loc = c2.text_input("Localidad", key="cfg_inst_localidad")
        i_mun = c3.text_input("Municipio", key="cfg_inst_municipio")
        i_dep = c4.text_input("Departamento", key="cfg_inst_departamento")
        if c5.button("Agregar institución", use_container_width=True, key="cfg_btn_add_inst"):
            if not i_nom.strip():
                warn_toast("Escribe el nombre.")
            else:
                DATA.upsert_institucion(i_nom.strip(), i_loc or None, i_mun or None, i_dep or None)
                success_toast("Institución agregada.")
                st.rerun()
        st.dataframe(DATA.list_instituciones(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de instituciones")
        file_inst = st.file_uploader("Archivo de instituciones (Excel o CSV)", type=["xlsx", "xls", "csv"], key="cfg_up_instituciones")
        if file_inst is not None and st.button("Procesar instituciones", key="cfg_btn_proc_inst"):
            try:
                df_inst = read_table_upload(file_inst)
                if "nombre" not in df_inst.columns:
                    st.error(f"El archivo debe contener 'nombre'. Columnas: {list(df_inst.columns)}")
                else:
                    ok = 0
                    for _, r in df_inst.iterrows():
                        nom = str(r.get("nombre", "")).strip()
                        if not nom:
                            continue
                        DATA.upsert_institucion(
                            nom,
                            str(r.get("localidad", "")).strip() or None if "localidad" in df_inst.columns else None,
                            str(r.get("municipio", "")).strip() or None if "municipio" in df_inst.columns else None,
                            str(r.get("departamento", "")).strip() or None if "departamento" in df_inst.columns else None,
                        )
                        ok += 1
                    success_toast(f"Se procesaron {ok} instituciones.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando instituciones: {e}")

    # Profesionales
    with tabs[3]:
        progs = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
        conv = DATA.list_convenios()
        conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}

        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.2, 1.4, 1.4, 1.2, 1.2])
        f_nom = c1.text_input("Nombre profesional", key="cfg_prof_nombre")
        f_doc = c2.text_input("Documento (opcional)", key="cfg_prof_doc")
        f_email = c3.text_input("Email (opcional)", key="cfg_prof_email")
        f_prog = c4.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key="cfg_prof_prog")
        f_conv = c5.selectbox("Convenio", options=list(conv_map.keys()) if conv_map else [], key="cfg_prof_conv")
        zona_opts = ["(No especifica)", "Urbana", "Rural"]
        f_zona = c6.selectbox("Zona (opcional)", options=zona_opts, key="cfg_prof_zona")

        if st.button("Agregar profesional", use_container_width=True, key="cfg_btn_add_prof"):
            if not f_nom.strip():
                warn_toast("Escribe el nombre.")
            else:
                zona = None if f_zona == "(No especifica)" else f_zona
                DATA.upsert_profesor(f_nom.strip(), f_doc or None, f_email or None, prog_map.get(f_prog), conv_map.get(f_conv), zona)
                success_toast("Profesional agregado.")
                st.rerun()

        st.dataframe(DATA.list_profesores(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de profesionales")
        st.caption("Columnas: **nombre** (obligatoria), opcionales: documento, email, programa, convenio, zona (Rural/Urbana).")
        file_prof = st.file_uploader("Archivo de profesionales", type=["xlsx", "xls", "csv"], key="cfg_up_profesionales")
        if file_prof is not None and st.button("Procesar profesionales", key="cfg_btn_proc_prof"):
            try:
                df_prof = read_table_upload(file_prof)
                if "nombre" not in df_prof.columns:
                    st.error(f"El archivo debe contener 'nombre'. Columnas: {list(df_prof.columns)}")
                else:
                    progs2 = DATA.list_programas()
                    prog_map2 = {r["nombre"]: int(r["id"]) for _, r in progs2.iterrows()} if not progs2.empty else {}
                    conv2 = DATA.list_convenios()
                    conv_map2 = {r["nombre"]: int(r["id"]) for _, r in conv2.iterrows()} if not conv2.empty else {}

                    ok = 0
                    for _, r in df_prof.iterrows():
                        nom = str(r.get("nombre", "")).strip()
                        if not nom:
                            continue
                        doc = str(r.get("documento", "")).strip() if pd.notna(r.get("documento")) else None
                        email = str(r.get("email", "")).strip() if pd.notna(r.get("email")) else None
                        p_name = str(r.get("programa", "")).strip() if pd.notna(r.get("programa")) else None
                        c_name = str(r.get("convenio", "")).strip() if pd.notna(r.get("convenio")) else None
                        zona = str(r.get("zona", "")).strip() if pd.notna(r.get("zona")) else None
                        if zona not in ("Rural", "Urbana"):
                            zona = None
                        pid = prog_map2.get(p_name) if p_name else None
                        cid = conv_map2.get(c_name) if c_name else None
                        if p_name and not pid:
                            pid = DATA.upsert_programa(p_name)
                        if c_name and not cid and pid:
                            cid = DATA.upsert_convenio(c_name, pid)
                        DATA.upsert_profesor(nom, doc, email, pid, cid, zona)
                        ok += 1
                    success_toast(f"Se procesaron {ok} profesionales.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando profesionales: {e}")

    # Pacientes
    with tabs[4]:
        st.markdown("### Gestión de pacientes")
        c1, c2 = st.columns([1.2, 2])
        cfg_doc = c1.text_input("Documento (cédula)", key="cfg_pac_doc")
        cfg_nom = c2.text_input("Nombre completo", key="cfg_pac_nombre")

        c3, c4, c5 = st.columns([1, 1, 1])
        cfg_nac = c3.text_input("Fecha de nacimiento (AAAA-MM-DD, opcional)", key="cfg_pac_fecha_nac")
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
        cfg_zona = zc1.selectbox("Zona (opcional)", zona_opts, key="cfg_pac_zona")

        if st.button("Guardar / actualizar paciente", key="cfg_btn_guardar_paciente"):
            if not cfg_doc.strip() or not cfg_nom.strip():
                warn_toast("Documento y nombre son obligatorios.")
            else:
                try:
                    DATA.upsert_paciente(
                        cfg_doc.strip(),
                        cfg_nom.strip(),
                        cfg_nac or None,
                        None if cfg_sexo == "(No especifica)" else cfg_sexo,
                        cfg_tel or None,
                        cfg_email or None,
                        cfg_dir or None,
                        cfg_loc or None,
                        cfg_mun or None,
                        cfg_dep or None,
                        None if cfg_zona == "(No especifica)" else cfg_zona,
                    )
                    success_toast("Paciente guardado/actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo guardar: {e}")

        st.dataframe(DATA.list_pacientes(), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Carga masiva de pacientes")
        st.caption(
            "Obligatorias: **documento**, **nombre**. Opcionales: fecha_nacimiento, sexo, telefono, email, "
            "direccion, localidad, municipio, departamento, zona (Rural/Urbana)."
        )
        file_pac = st.file_uploader("Archivo de pacientes (Excel o CSV)", type=["xlsx", "xls", "csv"], key="cfg_up_pacientes")
        if file_pac is not None and st.button("Procesar pacientes", key="cfg_btn_proc_pac"):
            try:
                df_pac = read_table_upload(file_pac)
                if not {"documento", "nombre"}.issubset(df_pac.columns):
                    st.error(f"El archivo debe contener 'documento' y 'nombre'. Columnas detectadas: {list(df_pac.columns)}")
                else:
                    ok = 0
                    for _, r in df_pac.iterrows():
                        doc = str(r.get("documento", "")).strip()
                        nom = str(r.get("nombre", "")).strip()
                        if not doc or not nom:
                            continue
                        zona = (
                            str(r.get("zona", "")).strip()
                            if "zona" in df_pac.columns and pd.notna(r.get("zona"))
                            else None
                        )
                        if zona not in ("Rural", "Urbana"):
                            zona = None
                        DATA.upsert_paciente(
                            numero_documento=doc,
                            nombre=nom,
                            fecha_nacimiento=str(r.get("fecha_nacimiento"))
                            if "fecha_nacimiento" in df_pac.columns and pd.notna(r.get("fecha_nacimiento"))
                            else None,
                            sexo=str(r.get("sexo")).strip() if "sexo" in df_pac.columns and pd.notna(r.get("sexo")) else None,
                            telefono=str(r.get("telefono")).strip()
                            if "telefono" in df_pac.columns and pd.notna(r.get("telefono"))
                            else None,
                            email=str(r.get("email")).strip() if "email" in df_pac.columns and pd.notna(r.get("email")) else None,
                            direccion=str(r.get("direccion")).strip()
                            if "direccion" in df_pac.columns and pd.notna(r.get("direccion"))
                            else None,
                            localidad=str(r.get("localidad")).strip()
                            if "localidad" in df_pac.columns and pd.notna(r.get("localidad"))
                            else None,
                            municipio=str(r.get("municipio")).strip()
                            if "municipio" in df_pac.columns and pd.notna(r.get("municipio"))
                            else None,
                            departamento=str(r.get("departamento")).strip()
                            if "departamento" in df_pac.columns and pd.notna(r.get("departamento"))
                            else None,
                            zona=zona,
                        )
                        ok += 1
                    success_toast(f"Se procesaron {ok} pacientes.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando pacientes: {e}")

# ---------------- UI: RESPALDO ----------------
def ui_respaldo():
    st.subheader("Respaldo de la base de datos")
    st.caption(
        "Descarga la base SQLite actual y/o un paquete ZIP con copias en CSV de todas las tablas y el schema.sql."
    )

    col1, col2 = st.columns(2)

    # Botón: descargar .db
    if os.path.exists(DB_SQLITE_PATH):
        col1.download_button(
            "⬇️ Descargar base (.db)",
            data=backup_sqlite_file(),
            file_name=f"respaldo_sqlite_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
            mime="application/octet-stream",
            use_container_width=True,
            key="bk_btn_db",
        )
    else:
        col1.warning("No se encontró el archivo de base de datos actual.")

    # Botón: descargar ZIP
    col2.download_button(
        "⬇️ Descargar ZIP (.db + CSV + schema)",
        data=build_zip_backup(),
        file_name=f"respaldo_productividad_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
        mime="application/zip",
        use_container_width=True,
        key="bk_btn_zip",
    )

# ---------------- MAIN ----------------
def main():
    st.markdown(f"# {APP_ICON} {APP_TITLE}")
    st.caption("Base SQLite local (`productividad_profesores.db`). Usuarios del mismo enlace comparten la misma información.")
    sidebar_filters()
    render_login()

    if not st.session_state.user:
        st.info("Inicia sesión para usar el aplicativo.")
        return

    user = st.session_state.user
    role = st.session_state.role

    tabs_admin = [
        "Registrar atenciones",
        "Listado",
        "Dashboard",
        "Reportes",
        "Viáticos",
        "Planificador",
        "Papelería",
        "Configuración",
        "Respaldo",
    ]
    tabs_pro = ["Registrar atenciones", "Listado", "Viáticos", "Planificador", "Papelería"]
    tabs = st.tabs(tabs_admin if role == "admin" else tabs_pro)

    if role == "admin":
        with tabs[0]:
            ui_cargar_datos(user)
        with tabs[1]:
            ui_registros()
        with tabs[2]:
            ui_dashboard()
        with tabs[3]:
            ui_reportes()
        with tabs[4]:
            ui_viaticos(user)
        with tabs[5]:
            ui_planificador(user)
        with tabs[6]:
            ui_papeleria(user)
        with tabs[7]:
            ui_configuracion()
        with tabs[8]:
            ui_respaldo()
    else:
        with tabs[0]:
            ui_cargar_datos(user)
        with tabs[1]:
            ui_registros()
        with tabs[2]:
            ui_viaticos(user)
        with tabs[3]:
            ui_planificador(user)
        with tabs[4]:
            ui_papeleria(user)

if __name__ == "__main__":
    main()
