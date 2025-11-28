# app_productividad_Profesionales.py
from datetime import datetime, date, time as dtime
from typing import Optional, Dict, Any, List, Tuple
import io
import os
import re
import zipfile
import unicodedata
import sqlite3
import traceback
import time
import shutil

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_TITLE = "Productividad de Profesionales - FOMAG"
APP_ICON = "📊"
DB_SQLITE_PATH = "productividad_Profesionales.db"

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
def get_db_connection() -> sqlite3.Connection:
    """Obtiene una conexión fresca a la base de datos"""
    if os.path.exists(DB_SQLITE_PATH):
        conn = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False, timeout=10)
    else:
        conn = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

SQLITE_CONN = get_db_connection()

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
    "Profesionales": """
    CREATE TABLE IF NOT EXISTS Profesionales(
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
        Profesional_id INTEGER NOT NULL,
        paciente_id INTEGER,
        localidad TEXT,
        municipio TEXT,
        departamento TEXT,
        numero_paciente TEXT,
        nombre_paciente TEXT,
        actividad TEXT,
        atendido INTEGER,
        registrado_panacea INTEGER,
        paciente_creado_panacea INTEGER,
        paciente_priorizado INTEGER,
        priorizado_origen TEXT,
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
        FOREIGN KEY(Profesional_id) REFERENCES Profesionales(id),
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
        Profesional_id INTEGER,
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
        FOREIGN KEY(Profesional_id) REFERENCES Profesionales(id)
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
        Profesional_id INTEGER,
        creado_por TEXT,
        creado_en TEXT,
        actualizado_en TEXT,
        FOREIGN KEY(programa_id) REFERENCES programas(id),
        FOREIGN KEY(convenio_id) REFERENCES convenios(id),
        FOREIGN KEY(institucion_id) REFERENCES instituciones(id),
        FOREIGN KEY(Profesional_id) REFERENCES Profesionales(id)
    );
    """,
    "papeleria": """
    CREATE TABLE IF NOT EXISTS papeleria(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        programa_id INTEGER,
        convenio_id INTEGER,
        institucion_id INTEGER,
        Profesional_id INTEGER,
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
        FOREIGN KEY(Profesional_id) REFERENCES Profesionales(id)
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
            "paciente_priorizado": "ALTER TABLE registros ADD COLUMN paciente_priorizado INTEGER;",
            "priorizado_origen": "ALTER TABLE registros ADD COLUMN priorizado_origen TEXT;",
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

    def Profesional_id_by_name(
        self, nombre: str, programa_id: Optional[int], convenio_id: Optional[int]
    ) -> Optional[int]:
        if not nombre:
            return None
        r = self.db.execute(
            "SELECT id FROM Profesionales WHERE nombre=? AND activo=1 ORDER BY id ASC",
            (nombre,),
        ).fetchone()
        return int(r["id"]) if r else None

    # CRUD PROGRAMAS
    def list_programas(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM programas WHERE activo=1 ORDER BY nombre", self.db)

    def upsert_programa(self, nombre: str) -> int:
        if not nombre:
            return None
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO programas(nombre,activo) VALUES(?,1)", (nombre.strip(),))
        r = self.db.execute("SELECT id FROM programas WHERE nombre=?", (nombre.strip(),)).fetchone()
        return int(r["id"])

    def get_programa_by_id(self, pid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM programas WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def update_programa(self, pid: int, nombre: str) -> None:
        with self.db:
            self.db.execute("UPDATE programas SET nombre=? WHERE id=?", (nombre.strip(), pid))

    def delete_programa(self, pid: int) -> None:
        with self.db:
            self.db.execute("UPDATE programas SET activo=0 WHERE id=?", (pid,))

    # CRUD CONVENIOS
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

    def get_convenio_by_id(self, cid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM convenios WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None

    def update_convenio(self, cid: int, nombre: str, programa_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE convenios SET nombre=?, programa_id=? WHERE id=?", (nombre.strip(), programa_id, cid))

    def delete_convenio(self, cid: int) -> None:
        with self.db:
            self.db.execute("UPDATE convenios SET activo=0 WHERE id=?", (cid,))

    # CRUD INSTITUCIONES
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

    def get_institucion_by_id(self, iid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM instituciones WHERE id=?", (iid,)).fetchone()
        return dict(r) if r else None

    def update_institucion(self, iid: int, nombre: str, localidad: Optional[str], municipio: Optional[str], departamento: Optional[str]) -> None:
        with self.db:
            self.db.execute(
                "UPDATE instituciones SET nombre=?, localidad=?, municipio=?, departamento=? WHERE id=?",
                (nombre.strip(), localidad, municipio, departamento, iid)
            )

    def delete_institucion(self, iid: int) -> None:
        with self.db:
            self.db.execute("UPDATE instituciones SET activo=0 WHERE id=?", (iid,))

    # CRUD PROFESIONALES
    def list_Profesionales(
        self, programa_id: Optional[int] = None, convenio_id: Optional[int] = None
    ) -> pd.DataFrame:
        q = "SELECT * FROM Profesionales WHERE activo=1"
        p: List[Any] = []
        if programa_id:
            q += " AND programa_id=?"
            p.append(programa_id)
        if convenio_id:
            q += " AND convenio_id=?"
            p.append(convenio_id)
        q += " ORDER BY nombre"
        return pd.read_sql_query(q, self.db, params=p)

    def upsert_Profesional(
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
                "INSERT INTO Profesionales(nombre,documento,email,programa_id,convenio_id,zona,activo) VALUES(?,?,?,?,?,?,1)",
                (nombre.strip(), (documento or None), (email or None), programa_id, convenio_id, zona),
            )
        r = self.db.execute(
            "SELECT id FROM Profesionales WHERE nombre=? ORDER BY id DESC", (nombre.strip(),)
        ).fetchone()
        return int(r["id"])

    def get_profesional_by_id(self, fid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM Profesionales WHERE id=?", (fid,)).fetchone()
        return dict(r) if r else None

    def update_profesional(self, fid: int, nombre: str, documento: Optional[str], email: Optional[str], 
                          programa_id: Optional[int], convenio_id: Optional[int], zona: Optional[str]) -> None:
        with self.db:
            self.db.execute(
                "UPDATE Profesionales SET nombre=?, documento=?, email=?, programa_id=?, convenio_id=?, zona=? WHERE id=?",
                (nombre.strip(), documento, email, programa_id, convenio_id, zona, fid)
            )

    def delete_profesional(self, fid: int) -> None:
        with self.db:
            self.db.execute("UPDATE Profesionales SET activo=0 WHERE id=?", (fid,))

    # CRUD PACIENTES
    def list_pacientes(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM pacientes WHERE activo=1 ORDER BY nombre", self.db)

    def get_paciente_por_documento(self, doc: str) -> Optional[Dict[str, Any]]:
        doc = (doc or "").strip()
        if not doc:
            return None
        row = self.db.execute("SELECT * FROM pacientes WHERE numero_documento=? AND activo=1", (doc,)).fetchone()
        return dict(row) if row else None

    def get_paciente_by_id(self, pid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM pacientes WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

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

    def delete_paciente(self, pid: int) -> None:
        with self.db:
            self.db.execute("UPDATE pacientes SET activo=0 WHERE id=?", (pid,))

    # CRUD REGISTROS
    def insert_registro(
        self,
        fecha: date,
        programa_id: int,
        convenio_id: int,
        institucion_id: int,
        Profesional_id: int,
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
            "Profesional_id": Profesional_id,
            "paciente_id": paciente_id,
            "localidad": localidad,
            "municipio": municipio,
            "departamento": departamento,
            "numero_paciente": (numero_paciente or "").strip() or None,
            "nombre_paciente": (nombre_paciente or "").strip() or None,
            "actividad": actividad,
            "atendido": 1 if atendido else 0,
            "registrado_panacea": 1 if registrado_panacea else 0,
            "paciente_creado_panacea": 1 if paciente_creado_panacea else 0,
            "paciente_priorizado": 1 if paciente_priorizado else 0,
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
            "i.nombre AS institucion, f.nombre AS Profesional, f.email AS Profesional_email "
            "FROM registros r "
            "LEFT JOIN programas p ON p.id=r.programa_id "
            "LEFT JOIN convenios c ON c.id=r.convenio_id "
            "LEFT JOIN instituciones i ON i.id=r.institucion_id "
            "LEFT JOIN Profesionales f ON f.id=r.Profesional_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(r.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(r.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "Profesional_id"]:
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

    # CRUD VIATICOS
    def insert_viatico(
        self,
        fecha: date,
        programa_id,
        convenio_id,
        institucion_id,
        Profesional_id,
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
            "Profesional_id": Profesional_id,
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
            "i.nombre AS institucion, f.nombre AS Profesional "
            "FROM viaticos v "
            "LEFT JOIN programas p ON p.id=v.programa_id "
            "LEFT JOIN convenios c ON c.id=v.convenio_id "
            "LEFT JOIN instituciones i ON i.id=v.institucion_id "
            "LEFT JOIN Profesionales f ON f.id=v.Profesional_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(v.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(v.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "Profesional_id"]:
            if filtros.get(k):
                q += f" AND v.{k}=?"
                params.append(filtros[k])
        q += " ORDER BY v.fecha DESC, v.id DESC"
        return pd.read_sql_query(q, self.db, params=params)

    def get_viatico_by_id(self, vid: int) -> Optional[Dict[str, Any]]:
        r = self.db.execute("SELECT * FROM viaticos WHERE id=?", (vid,)).fetchone()
        return dict(r) if r else None

    def update_viatico(self, vid: int, updates: Dict[str, Any]) -> None:
        updates = dict(updates)
        updates["actualizado_en"] = _now()
        sets = ",".join([f"{k}=?" for k in updates.keys()])
        with self.db:
            self.db.execute(f"UPDATE viaticos SET {sets} WHERE id=?", (*updates.values(), vid))

    def delete_viatico(self, vid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM viaticos WHERE id=?", (vid,))

    # CRUD AGENDA
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
        Profesional_id,
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
            "Profesional_id": Profesional_id,
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
            "i.nombre AS institucion, f.nombre AS Profesional "
            "FROM agenda a "
            "LEFT JOIN programas p ON p.id=a.programa_id "
            "LEFT JOIN convenios c ON c.id=a.convenio_id "
            "LEFT JOIN instituciones i ON i.id=a.institucion_id "
            "LEFT JOIN Profesionales f ON f.id=a.Profesional_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(a.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(a.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "Profesional_id"]:
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

    # CRUD PAPELERIA
    def insert_papeleria(
        self,
        fecha: date,
        programa_id,
        convenio_id,
        institucion_id,
        Profesional_id,
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
            "Profesional_id": Profesional_id,
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
            "i.nombre AS institucion, f.nombre AS Profesional "
            "FROM papeleria pa "
            "LEFT JOIN programas p ON p.id=pa.programa_id "
            "LEFT JOIN convenios c ON c.id=pa.convenio_id "
            "LEFT JOIN instituciones i ON i.id=pa.institucion_id "
            "LEFT JOIN Profesionales f ON f.id=pa.Profesional_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if filtros.get("fecha_desde"):
            q += " AND date(pa.fecha)>=date(?)"
            params.append(filtros["fecha_desde"].strftime("%Y-%m-%d"))
        if filtros.get("fecha_hasta"):
            q += " AND date(pa.fecha)<=date(?)"
            params.append(filtros["fecha_hasta"].strftime("%Y-%m-%d"))
        for k in ["programa_id", "convenio_id", "Profesional_id"]:
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

# ---------------- SISTEMA DE RESPALDOS AUTOMÁTICOS ----------------
BACKUP_DIR = "respaldos_automaticos"

def ensure_backup_directory():
    """Crea el directorio de respaldos si no existe"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        st.sidebar.info(f"📁 Directorio de respaldos creado: {BACKUP_DIR}")

def create_automatic_backup(trigger: str = "manual") -> str:
    """
    Crea un respaldo automático con timestamp
    trigger: 'manual', 'auto_daily', 'auto_hourly', 'before_operation'
    """
    ensure_backup_directory()
    
    if not os.path.exists(DB_SQLITE_PATH):
        return None
    
    try:
        SQLITE_CONN.commit()
    except:
        pass
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{trigger}_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    try:
        shutil.copy2(DB_SQLITE_PATH, backup_path)
        return backup_path
    except Exception as e:
        st.error(f"Error creando respaldo: {e}")
        return None

def list_available_backups() -> List[Dict[str, Any]]:
    """Lista todos los respaldos disponibles con información"""
    ensure_backup_directory()
    
    backups = []
    if os.path.exists(BACKUP_DIR):
        for filename in os.listdir(BACKUP_DIR):
            if filename.endswith('.db'):
                filepath = os.path.join(BACKUP_DIR, filename)
                file_stat = os.stat(filepath)
                
                # Extraer información del nombre del archivo
                # Formato: backup_trigger_YYYYMMDD_HHMMSS.db
                parts = filename.replace('.db', '').split('_')
                
                backups.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_stat.st_size,
                    'created': datetime.fromtimestamp(file_stat.st_mtime),
                    'trigger': parts[1] if len(parts) > 1 else 'unknown',
                })
    
    # Ordenar por fecha de creación (más reciente primero)
    backups.sort(key=lambda x: x['created'], reverse=True)
    return backups

def restore_from_backup(backup_path: str) -> bool:
    """Restaura la base de datos desde un respaldo específico"""
    global SQLITE_CONN, DATA
    
    if not os.path.exists(backup_path):
        st.error(f"El respaldo no existe: {backup_path}")
        return False
    
    try:
        # Crear respaldo de seguridad de la BD actual
        if os.path.exists(DB_SQLITE_PATH):
            safety_backup = f"{DB_SQLITE_PATH}.before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(DB_SQLITE_PATH, safety_backup)
            st.info(f"✅ Respaldo de seguridad creado: {safety_backup}")
        
        # Cerrar conexión actual
        try:
            SQLITE_CONN.close()
        except:
            pass
        
        # Restaurar desde el respaldo seleccionado
        shutil.copy2(backup_path, DB_SQLITE_PATH)
        
        # Reconectar
        time.sleep(0.3)
        SQLITE_CONN = get_db_connection()
        DATA = DataAccess(SQLITE_CONN)
        
        # Verificar
        count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        st.success(f"✅ Base restaurada correctamente desde: {os.path.basename(backup_path)}")
        st.info(f"📊 {count} registros encontrados en la base restaurada")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error restaurando: {e}")
        st.code(traceback.format_exc())
        return False

def delete_backup(backup_path: str) -> bool:
    """Elimina un respaldo específico"""
    try:
        if os.path.exists(backup_path):
            os.remove(backup_path)
            return True
        return False
    except Exception as e:
        st.error(f"Error eliminando respaldo: {e}")
        return False

def auto_backup_on_startup():
    """Crea un respaldo automático al iniciar la aplicación"""
    if os.path.exists(DB_SQLITE_PATH):
        # Solo crear respaldo si han pasado más de 1 hora desde el último
        ensure_backup_directory()
        backups = list_available_backups()
        
        should_backup = True
        if backups:
            last_backup_time = backups[0]['created']
            hours_since_last = (datetime.now() - last_backup_time).total_seconds() / 3600
            should_backup = hours_since_last >= 1
        
        if should_backup:
            backup_path = create_automatic_backup(trigger="auto_startup")
            if backup_path:
                st.sidebar.success(f"✅ Respaldo automático creado")

def cleanup_old_backups(keep_last_n: int = 20):
    """Limpia respaldos antiguos manteniendo solo los últimos N"""
    backups = list_available_backups()
    
    if len(backups) > keep_last_n:
        to_delete = backups[keep_last_n:]
        deleted = 0
        for backup in to_delete:
            if delete_backup(backup['filepath']):
                deleted += 1
        
        if deleted > 0:
            st.info(f"🧹 Se eliminaron {deleted} respaldos antiguos (manteniendo los últimos {keep_last_n})")

def export_data_to_json() -> bytes:
    """Exporta todos los datos a formato JSON para respaldo portable"""
    export_data = {}
    
    tables = ["programas", "convenios", "instituciones", "Profesionales", 
              "pacientes", "registros", "viaticos", "agenda", "papeleria"]
    
    for table in tables:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", SQLITE_CONN)
            export_data[table] = df.to_dict(orient='records')
        except Exception as e:
            export_data[table] = {"error": str(e)}
    
    export_data['metadata'] = {
        'export_date': datetime.now().isoformat(),
        'db_path': DB_SQLITE_PATH,
        'app_version': '2.0'
    }
    
    import json
    return json.dumps(export_data, indent=2, default=str).encode('utf-8')

# ---------------- UI MEJORADA DE RESPALDO CON PUNTOS DE RESTAURACIÓN ----------------
def ui_respaldo():
    st.subheader("🔄 Sistema de Respaldos y Restauración")
    
    # Verificar si existe la base de datos
    if not os.path.exists(DB_SQLITE_PATH):
        st.error(f"⚠️ **ALERTA: No se encuentra el archivo de base de datos: `{DB_SQLITE_PATH}`**")
        st.warning("La base de datos no existe. Se creará una nueva al guardar datos.")
        
        if st.button("Crear base de datos vacía ahora", type="primary"):
            global SQLITE_CONN, DATA
            SQLITE_CONN = get_db_connection()
            ensure_sqlite_schema()
            DATA = DataAccess(SQLITE_CONN)
            st.success("✅ Base de datos creada correctamente")
            st.rerun()
        return
    
    # Información de la base de datos actual
    db_size = os.path.getsize(DB_SQLITE_PATH)
    db_modified = datetime.fromtimestamp(os.path.getmtime(DB_SQLITE_PATH))
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Tamaño BD actual", f"{db_size / 1024:.1f} KB")
    col2.metric("Última modificación", db_modified.strftime("%Y-%m-%d %H:%M"))
    
    try:
        count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        col3.metric("Registros totales", f"{count:,}".replace(",", "."))
    except:
        col3.metric("Registros totales", "Error")
    
    st.markdown("---")
    
    # TABS PARA ORGANIZAR FUNCIONES
    tab1, tab2, tab3, tab4 = st.tabs([
        "📥 Descargar Respaldos", 
        "📤 Restaurar desde Respaldo",
        "🕐 Puntos de Restauración",
        "⚙️ Configuración"
    ])
    
    # ============ TAB 1: DESCARGAR RESPALDOS ============
    with tab1:
        st.markdown("### Descargar respaldo de la base de datos actual")
        
        col1, col2, col3 = st.columns(3)
        
        # Respaldo .db
        col1.download_button(
            "💾 Descargar .DB",
            data=backup_sqlite_file(),
            file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            mime="application/octet-stream",
            use_container_width=True,
            help="Archivo SQLite completo"
        )
        
        # Respaldo ZIP
        col2.download_button(
            "📦 Descargar ZIP",
            data=build_zip_backup(),
            file_name=f"backup_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True,
            help="ZIP con .db + CSV + schema"
        )
        
        # Respaldo JSON
        col3.download_button(
            "📄 Descargar JSON",
            data=export_data_to_json(),
            file_name=f"backup_datos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
            help="Datos en formato JSON portable"
        )
        
        st.markdown("---")
        st.markdown("### Crear punto de restauración manual")
        st.info("💡 Los puntos de restauración se guardan automáticamente en la carpeta `respaldos_automaticos/`")
        
        if st.button("📸 Crear Punto de Restauración Ahora", type="primary", use_container_width=True):
            backup_path = create_automatic_backup(trigger="manual")
            if backup_path:
                st.success(f"✅ Punto de restauración creado: `{backup_path}`")
                st.rerun()
    
    # ============ TAB 2: RESTAURAR DESDE ARCHIVO ============
    with tab2:
        st.markdown("### Restaurar base de datos desde archivo")
        
        uploaded_db = st.file_uploader(
            "Selecciona un archivo .db para restaurar", 
            type=["db"],
            key="restore_upload"
        )
        
        if uploaded_db is not None:
            st.warning("⚠️ **ADVERTENCIA:** Esto sobrescribirá la base de datos actual")
            st.info(f"📁 Archivo seleccionado: `{uploaded_db.name}` ({uploaded_db.size / 1024:.1f} KB)")
            
            col1, col2 = st.columns([1, 3])
            
            if col1.button("🔄 Restaurar Ahora", type="primary", use_container_width=True):
                try:
                    global SQLITE_CONN, DATA
                    
                    # Cerrar conexión
                    try:
                        SQLITE_CONN.close()
                    except:
                        pass
                    
                    # Crear respaldo de seguridad
                    safety_backup = create_automatic_backup(trigger="before_restore")
                    if safety_backup:
                        st.info(f"✅ Respaldo de seguridad creado: `{os.path.basename(safety_backup)}`")
                    
                    # Escribir archivo subido
                    with open(DB_SQLITE_PATH, "wb") as f:
                        f.write(uploaded_db.getvalue())
                    
                    # Reconectar
                    time.sleep(0.3)
                    SQLITE_CONN = get_db_connection()
                    DATA = DataAccess(SQLITE_CONN)
                    
                    # Verificar
                    count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
                    st.success(f"✅ Base restaurada correctamente. {count} registros encontrados.")
                    
                    time.sleep(2)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error restaurando: {e}")
                    st.code(traceback.format_exc())
    
    # ============ TAB 3: PUNTOS DE RESTAURACIÓN AUTOMÁTICOS ============
    with tab3:
        st.markdown("### 🕐 Puntos de Restauración Disponibles")
        st.caption(f"Los respaldos se guardan en: `{os.path.abspath(BACKUP_DIR)}/`")
        
        # Botón para crear respaldo manual en esta sección también
        col1, col2, col3 = st.columns([2, 1, 1])
        if col1.button("📸 Crear Punto de Restauración", use_container_width=True):
            backup_path = create_automatic_backup(trigger="manual")
            if backup_path:
                st.success(f"✅ Creado: `{os.path.basename(backup_path)}`")
                st.rerun()
        
        if col2.button("🔄 Actualizar", use_container_width=True):
            st.rerun()
        
        # Listar respaldos disponibles
        backups = list_available_backups()
        
        if not backups:
            st.info("📭 No hay puntos de restauración guardados todavía.")
            st.markdown("Los respaldos automáticos se crean:")
            st.markdown("- Al iniciar la aplicación (cada hora)")
            st.markdown("- Manualmente con el botón 'Crear Punto de Restauración'")
            st.markdown("- Antes de operaciones críticas (restauraciones, reinicios)")
        else:
            st.success(f"📦 Se encontraron **{len(backups)}** puntos de restauración")
            
            # Mostrar tabla de respaldos
            for idx, backup in enumerate(backups):
                with st.expander(
                    f"{'🟢' if idx == 0 else '🔵'} {backup['created'].strftime('%Y-%m-%d %H:%M:%S')} - "
                    f"{backup['trigger'].upper()} - {backup['size'] / 1024:.1f} KB",
                    expanded=(idx == 0)
                ):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    col1.write(f"**Archivo:** `{backup['filename']}`")
                    col1.write(f"**Tamaño:** {backup['size'] / 1024:.1f} KB")
                    col1.write(f"**Creado:** {backup['created'].strftime('%Y-%m-%d %H:%M:%S')}")
                    col1.write(f"**Tipo:** {backup['trigger']}")
                    
                    # Botones de acción
                    restore_key = f"restore_{idx}"
                    download_key = f"download_{idx}"
                    delete_key = f"delete_{idx}"
                    
                    if col2.button("🔄 Restaurar", key=restore_key, use_container_width=True):
                        if restore_from_backup(backup['filepath']):
                            time.sleep(2)
                            st.rerun()
                    
                    # Botón de descarga
                    with open(backup['filepath'], 'rb') as f:
                        col2.download_button(
                            "💾 Descargar",
                            data=f.read(),
                            file_name=backup['filename'],
                            mime="application/octet-stream",
                            key=download_key,
                            use_container_width=True
                        )
                    
                    if col3.button("🗑️ Eliminar", key=delete_key, use_container_width=True):
                        if delete_backup(backup['filepath']):
                            st.success(f"✅ Eliminado: {backup['filename']}")
                            st.rerun()
    
    # ============ TAB 4: CONFIGURACIÓN ============
    with tab4:
        st.markdown("### ⚙️ Configuración de Respaldos")
        
        # Limpieza de respaldos antiguos
        st.markdown("#### 🧹 Limpieza de Respaldos Antiguos")
        keep_count = st.number_input(
            "Mantener últimos N respaldos",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            help="Los respaldos más antiguos serán eliminados"
        )
        
        if st.button("🧹 Limpiar Respaldos Antiguos", use_container_width=True):
            cleanup_old_backups(keep_last_n=keep_count)
            st.rerun()
        
        st.markdown("---")
        
        # Reiniciar base de datos
        st.markdown("#### ⚠️ Reiniciar Base de Datos (Destructivo)")
        
        with st.expander("🔴 Zona de Peligro - Reiniciar Base", expanded=False):
            st.error("⚠️ **ADVERTENCIA:** Esta acción es irreversible si no tienes respaldos")
            
            # Crear respaldo antes de reiniciar
            if st.button("📸 Crear Respaldo de Seguridad Antes de Continuar"):
                backup_path = create_automatic_backup(trigger="before_reset")
                if backup_path:
                    st.success(f"✅ Respaldo creado: `{os.path.basename(backup_path)}`")
            
            metodo = st.radio(
                "Método de reinicio",
                ["Vaciar tablas (conservar archivo .db)", "Borrar archivo .db (recrear esquema en blanco)"],
                index=0,
            )
            
            confirma = st.text_input("Escribe exactamente: BORRAR TODO")
            
            if st.button("💥 REINICIAR BASE DE DATOS", type="primary"):
                if confirma.strip() != "BORRAR TODO":
                    st.error("❌ Debes escribir 'BORRAR TODO' exactamente para confirmar")
                else:
                    # Crear respaldo automático antes de reiniciar
                    backup_path = create_automatic_backup(trigger="before_reset")
                    if backup_path:
                        st.info(f"✅ Respaldo automático creado: `{os.path.basename(backup_path)}`")
                    
                    m = "vaciar" if metodo.startswith("Vaciar") else "borrar_archivo"
                    if _reset_database(m):
                        st.success("✅ Base reiniciada correctamente")
                        time.sleep(2)
                        st.rerun()

# Modificar ensure_session_state para incluir respaldo automático
def ensure_session_state():
    if "filters" not in st.session_state:
        st.session_state.filters = {}
    if "user" not in st.session_state:
        st.session_state.user = None
    if "role" not in st.session_state:
        st.session_state.role = None
    if "backup_done_this_session" not in st.session_state:
        st.session_state.backup_done_this_session = False
        # Crear respaldo automático al iniciar (solo una vez por sesión)
        if not st.session_state.backup_done_this_session:
            auto_backup_on_startup()
            st.session_state.backup_done_this_session = True

## 📝 Instrucciones de Uso:

### 1. **Reemplaza la función `ui_respaldo()` completa** con la nueva versión que incluye los 4 tabs

### 2. **Añade las funciones nuevas** después de `build_zip_backup()`:
- `ensure_backup_directory()`
- `create_automatic_backup()`
- `list_available_backups()`
- `restore_from_backup()`
- `delete_backup()`
- `auto_backup_on_startup()`
- `cleanup_old_backups()`
- `export_data_to_json()`

### 3. **Modifica `ensure_session_state()`** para incluir el respaldo automático

## 🎯 Características del Sistema:



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

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = st.sidebar.selectbox("Profesional", options=["(Todos)"] + list(prof_map.keys()), key="flt_profesional")
    fid = prof_map.get(fsel)

    act = st.sidebar.selectbox("Actividad / plantilla", options=["(Todas)"] + ACTIVIDADES_PLANTILLAS, key="flt_actividad")

    st.session_state.filters = {
        "fecha_desde": fdesde,
        "fecha_hasta": fhasta,
        "programa_id": pid,
        "convenio_id": cid,
        "Profesional_id": fid,
        "actividad": (None if act == "(Todas)" else act),
    }

def render_login():
    with st.sidebar:
        # Botón de reconexión de emergencia
        if st.button("🔄 Reconectar BD", help="Usar si los datos no aparecen", use_container_width=True):
            global SQLITE_CONN, DATA
            try:
                SQLITE_CONN.close()
            except:
                pass
            SQLITE_CONN = get_db_connection()
            DATA = DataAccess(SQLITE_CONN)
            success_toast("Base de datos reconectada")
            st.rerun()
        
        st.markdown("---")
        
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
        "registrado_panacea",
        "paciente_creado_panacea",
        "paciente_priorizado",
        "priorizado_origen",
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
    df = normalize_columns(df.copy())
    req = {"fecha", "programa", "convenio", "institucion", "profesional", "documento", "nombre", "actividad"}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas obligatorias: {sorted(list(missing))}")

    ok = 0
    errores: List[str] = []
    for idx, r in df.iterrows():
        try:
            fecha = parse_fecha(r.get("fecha"))
            p_name = str(r.get("programa") or "").strip()
            c_name = str(r.get("convenio") or "").strip()
            if not p_name or not c_name:
                raise ValueError("Programa y convenio son obligatorios")
            pid = DATA.programa_id_by_name(p_name) or DATA.upsert_programa(p_name)
            cid = DATA.convenio_id_by_name(c_name, pid) or DATA.upsert_convenio(c_name, pid)

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

            f_name = str(r.get("profesional") or "").strip()
            if not f_name:
                raise ValueError("Profesional es obligatorio")
            fid = DATA.Profesional_id_by_name(f_name, pid, cid) or DATA.upsert_Profesional(f_name, None, None, pid, cid, None)

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

            actividad = str(r.get("actividad") or "").strip() or ACTIVIDADES_PLANTILLAS[0]
            atendido = bool(str2bool(r.get("atendido")))

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

            DATA.insert_registro(
                fecha=fecha,
                programa_id=pid,
                convenio_id=cid,
                institucion_id=iid,
                Profesional_id=fid,
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
        K("pac_priorizado"): False,
        K("priorizado_origen"): "(Seleccione)",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    c1, c2 = st.columns([1.4, 1.4])
    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c1.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key=K("form_programa"))
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else pd.DataFrame()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c1.selectbox("Convenio", options=list(conv_map.keys()) if conv_map else [], key=K("form_convenio"))
    cid = conv_map.get(csel)

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c2.selectbox("Profesional", options=list(prof_map.keys()) if prof_map else [], key=K("form_profesional"))
    fid = prof_map.get(fsel)

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

    c3, c4 = st.columns([1, 1])
    fecha = c3.date_input("Fecha de la atención", value=date.today(), key=K("fecha"))
    actividad = c4.selectbox("Actividad / plantilla", ACTIVIDADES_PLANTILLAS, key=K("actividad"))

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

    zcol2.checkbox("Paciente creado en Panacea", key=K("pac_creado_panacea"))
    c9, c10 = st.columns([1, 1])
    c9.radio("¿Atendido?", ["No", "Sí"], index=1, horizontal=True, key=K("atendido"))
    c10.checkbox("Atención registrada en Panacea", key=K("reg_panacea"))

    pr1, pr2 = st.columns([1, 1])
    pr1.checkbox("Paciente priorizado", key=K("pac_priorizado"))
    show_origen = st.session_state.get(K("pac_priorizado"), False)
    if show_origen:
        current = st.session_state.get(K("priorizado_origen")) or "(Seleccione)"
        pr2.selectbox("Origen priorización", options=["(Seleccione)"] + PRIORI_ORIGEN_OPTS, key=K("priorizado_origen"))
    else:
        st.session_state[K("priorizado_origen")] = "(Seleccione)"

    c11, c12 = st.columns([1, 1])
    c11.selectbox("Tipo de contacto", options=["(No especifica)"] + TIPOS_CONTACTO, key=K("tipo_contacto"))
    c12.number_input("Duración de la atención (minutos, opcional)", min_value=0, max_value=480, step=5, key=K("duracion_minutos"))

    observaciones = st.text_area("Observaciones", key=K("observaciones"))

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
                    Profesional_id=int(fid),
                    paciente_id=pac_id,
                    localidad=localidad_val,
                    municipio=municipio_val,
                    departamento=departamento_val,
                    numero_paciente=(st.session_state[K("pac_doc")] or "").strip(),
                    nombre_paciente=(st.session_state[K("pac_nombre")] or "").strip(),
                    actividad=st.session_state[K("actividad")],
                    atendido=True if st.session_state[K("atendido")] == "Sí" else False,
                    registrado_panacea=bool(st.session_state[K("reg_panacea")]),
                    paciente_creado_panacea=bool(st.session_state[K("pac_creado_panacea")]),
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
        "Profesional",
        "actividad",
        "numero_paciente",
        "nombre_paciente",
        "tipo_contacto",
        "duracion_minutos",
        "atendido",
        "paciente_creado_panacea",
        "registrado_panacea",
        "paciente_priorizado",
        "priorizado_origen",
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
    
    # CORREGIDO: Contamos registros únicos donde atendido=1
    total_prog = int(df.shape[0])  # Total de registros
    total_att = int(df[df["atendido"] == 1].shape[0])  # Registros con atendido=1
    total_no = total_prog - total_att
    tasa = (total_att / total_prog * 100) if total_prog else 0.0
    
    total_min = int(df.get("duracion_minutos", pd.Series()).fillna(0).sum()) if "duracion_minutos" in df.columns else 0
    n_con = int(df.get("duracion_minutos", pd.Series()).notna().sum()) if "duracion_minutos" in df.columns else 0
    prom = (total_min / n_con) if n_con else 0.0
    horas = total_min / 60 if total_min > 0 else 0.0
    prod_ph = (total_att / horas) if horas > 0 else 0.0
    
    total_pan = int(df[df.get("registrado_panacea", 0) == 1].shape[0]) if "registrado_panacea" in df.columns else 0
    total_pac_creados = int(df[df.get("paciente_creado_panacea", 0) == 1].shape[0]) if "paciente_creado_panacea" in df.columns else 0
    total_priorizados = int(df[df.get("paciente_priorizado", 0) == 1].shape[0]) if "paciente_priorizado" in df.columns else 0
    brecha = total_att - total_pan

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total registros", f"{total_prog:,}".replace(",", "."))
    k2.metric("Atendidos", f"{total_att:,}".replace(",", "."))
    k3.metric("No asistieron", f"{total_no:,}".replace(",", "."))
    k4.metric("Tasa atención", f"{tasa:.1f}%")

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Minutos totales", f"{total_min:,}".replace(",", "."))
    k6.metric("Duración prom (min)", f"{prom:.1f}")
    k7.metric("Atenciones/hora", f"{prod_ph:.2f}")
    k8.metric("Atención en Panacea / brecha", f"{total_pan} / {brecha}")

    k9, k10 = st.columns([1, 1])
    k9.metric("Pacientes creados Panacea", f"{total_pac_creados:,}".replace(",", "."))
    k10.metric("Pacientes priorizados", f"{total_priorizados:,}".replace(",", "."))

    # Tendencia semanal - CORREGIDA
    tdf = df.copy()
    tdf["atendido_num"] = df["atendido"].apply(lambda x: 1 if x == 1 else 0)
    tdf_agg = tdf.groupby(pd.Grouper(key="fecha", freq="W")).agg({
        "id": "count",  # Total programados
        "atendido_num": "sum"  # Total atendidos
    }).reset_index()
    tdf_agg.columns = ["fecha", "pacientes_programados", "pacientes_atendidos"]
    
    st.plotly_chart(
        px.line(tdf_agg, x="fecha", y=["pacientes_programados", "pacientes_atendidos"], 
                markers=True, title="Tendencia semanal"),
        use_container_width=True,
    )

    # Ranking profesional - CORREGIDO
    rank = (
        df[df["atendido"] == 1]
        .groupby("Profesional", dropna=True)
        .size()
        .sort_values(ascending=False)
        .head(15)
        .reset_index(name="pacientes_atendidos")
    )
    fig2 = px.bar(rank, x="Profesional", y="pacientes_atendidos", title="Top profesionales (atendidos)")
    fig2.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig2, use_container_width=True)

    # Cargadas a Panacea vs Atendidas
    if "registrado_panacea" in df.columns:
        pan = (
            df.groupby("Profesional", dropna=True)
            .agg(
                pacientes_atendidos=("atendido", lambda x: (x == 1).sum()),
                cargadas_panacea=("registrado_panacea", lambda x: (x == 1).sum()),
            )
            .reset_index()
        )
        pan["brecha"] = pan["pacientes_atendidos"] - pan["cargadas_panacea"]
        fig2b = px.bar(
            pan.sort_values("brecha", ascending=False).head(15),
            x="Profesional",
            y=["pacientes_atendidos", "cargadas_panacea"],
            barmode="group",
            title="Atenciones vs Panacea por profesional",
        )
        fig2b.update_layout(xaxis_tickangle=-40)
        st.plotly_chart(fig2b, use_container_width=True)

    # Prioridad: distribución por origen
    if "paciente_priorizado" in df.columns:
        dist = (
            df[df["paciente_priorizado"] == 1]
            .assign(prior_origen=df["priorizado_origen"].fillna("(Sin origen)"))
            .groupby("prior_origen")
            .size()
            .reset_index(name="priorizado")
            .sort_values("priorizado", ascending=False)
        )
        if not dist.empty:
            figp = px.bar(dist, x="prior_origen", y="priorizado", title="Pacientes priorizados por origen")
            figp.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(figp, use_container_width=True)

    # Por actividad - CORREGIDO
    act_sum = df.groupby("actividad").agg({
        "id": "count",
        "atendido": lambda x: (x == 1).sum()
    }).reset_index()
    act_sum.columns = ["actividad", "pacientes_programados", "pacientes_atendidos"]
    
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

# ---------------- UI: REPORTES (MEJORADO) ----------------
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
    
    # ATENCIONES
    df = DATA.list_registros(st.session_state.filters)
    
    # VIÁTICOS  
    df_viaticos = DATA.list_viaticos(st.session_state.filters)
    
    # AGENDA
    df_agenda = DATA.list_agenda(st.session_state.filters)
    
    # PAPELERÍA
    df_papeleria = DATA.list_papeleria(st.session_state.filters)
    
    if df.empty and df_viaticos.empty and df_agenda.empty and df_papeleria.empty:
        st.info("Sin registros para descargar en el período seleccionado.")
        return

    # Agregados de atenciones
    sheets = {}
    
    if not df.empty:
        agg_prof = (
            df.groupby("Profesional", dropna=True)
            .agg(
                registros_totales=("id", "count"),
                pacientes_atendidos=("atendido", lambda x: (x == 1).sum()),
                cargadas_panacea=("registrado_panacea", lambda x: (x == 1).sum()),
                pac_creados_panacea=("paciente_creado_panacea", lambda x: (x == 1).sum()),
                priorizados=("paciente_priorizado", lambda x: (x == 1).sum()),
                minutos=("duracion_minutos", "sum"),
            )
            .reset_index()
        )
        agg_prof["tasa_atencion_%"] = np.where(
            agg_prof["registros_totales"] > 0,
            (agg_prof["pacientes_atendidos"] / agg_prof["registros_totales"] * 100).round(1),
            0,
        )
        agg_prof["brecha_panacea"] = agg_prof["pacientes_atendidos"] - agg_prof["cargadas_panacea"]

        por_inst = df.groupby("institucion", dropna=True).agg({
            "id": "count",
            "atendido": lambda x: (x == 1).sum()
        }).reset_index()
        por_inst.columns = ["institucion", "pacientes_programados", "pacientes_atendidos"]
        
        por_geo = (
            df.groupby(["departamento", "municipio"], dropna=True).agg({
                "id": "count",
                "atendido": lambda x: (x == 1).sum()
            })
            .reset_index()
        )
        por_geo.columns = ["departamento", "municipio", "pacientes_programados", "pacientes_atendidos"]
        
        por_act = df.groupby("actividad").agg({
            "id": "count",
            "atendido": lambda x: (x == 1).sum()
        }).reset_index()
        por_act.columns = ["actividad", "pacientes_programados", "pacientes_atendidos"]
        
        por_prior_origen = (
            df[df.get("paciente_priorizado", 0) == 1]
            .assign(prior_origen=df["priorizado_origen"].fillna("(Sin origen)"))
            .groupby("prior_origen")
            .size()
            .reset_index(name="pacientes_priorizados")
        )

        sheets["Detalle_Atenciones"] = df
        sheets["Por_Profesional"] = agg_prof
        sheets["Por_Institucion"] = por_inst
        sheets["Por_Geo"] = por_geo
        sheets["Por_Actividad"] = por_act
        if not por_prior_origen.empty:
            sheets["Prior_por_Origen"] = por_prior_origen

    # Agregar viáticos
    if not df_viaticos.empty:
        sheets["Viaticos"] = df_viaticos
        viaticos_resumen = df_viaticos.groupby("Profesional", dropna=True).agg({
            "valor": ["count", "sum"]
        }).reset_index()
        viaticos_resumen.columns = ["Profesional", "cantidad_viaticos", "total_valor"]
        sheets["Viaticos_Resumen"] = viaticos_resumen

    # Agregar agenda
    if not df_agenda.empty:
        sheets["Agenda"] = df_agenda

    # Agregar papelería
    if not df_papeleria.empty:
        sheets["Papeleria"] = df_papeleria
        papel_resumen = df_papeleria.groupby(["item", "estado"], dropna=True).agg({
            "cantidad": "sum"
        }).reset_index()
        sheets["Papeleria_Resumen"] = papel_resumen

    xls = to_excel_bytes(sheets)
    
    st.download_button(
        "📥 Descargar reporte completo Excel (.xlsx)",
        data=xls,
        file_name=f"reporte_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="rep_btn_descargar_xlsx",
    )
    
    # Botones individuales
    col1, col2, col3 = st.columns(3)
    
    if not df.empty:
        col1.download_button(
            "Atenciones (.csv)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"atenciones_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="rep_csv_atenciones",
        )
    
    if not df_viaticos.empty:
        col2.download_button(
            "Viáticos (.csv)",
            data=df_viaticos.to_csv(index=False).encode("utf-8"),
            file_name=f"viaticos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="rep_csv_viaticos",
        )
    
    if not df_papeleria.empty:
        col3.download_button(
            "Papelería (.csv)",
            data=df_papeleria.to_csv(index=False).encode("utf-8"),
            file_name=f"papeleria_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="rep_csv_papeleria",
        )

    # Mostrar resúmenes
    st.markdown("### Resumen de datos en el período")
    
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Atenciones", len(df))
    r2.metric("Viáticos", len(df_viaticos))
    r3.metric("Eventos agenda", len(df_agenda))
    r4.metric("Solicitudes papel.", len(df_papeleria))

# ---------------- UI: VIATICOS (MEJORADO) ----------------
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

    prof = DATA.list_Profesionales(pid, cid)
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
                Profesional_id=fid,
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
            "Profesional",
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

    # EDICIÓN/ELIMINACIÓN
    st.markdown("---")
    st.markdown("#### Editar / eliminar viático")
    e1, e2, e3 = st.columns([1, 1, 1])
    vid_in = e1.number_input("ID de viático", min_value=1, step=1, key="via_edit_id")
    cargar = e2.button("Cargar", key="via_edit_cargar")
    eliminar = e3.button("Eliminar", key="via_edit_eliminar")

    if eliminar:
        try:
            DATA.delete_viatico(int(vid_in))
            success_toast("Viático eliminado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    if cargar:
        rec = DATA.get_viatico_by_id(int(vid_in))
        if not rec:
            warn_toast("No existe viático con ese ID.")
        else:
            st.markdown("##### Editar viático")
            ed1, ed2 = st.columns([1, 1])
            new_fecha = ed1.date_input("Fecha", value=pd.to_datetime(rec["fecha"]).date(), key="via_edit_fecha")
            new_req = ed2.radio("¿Requiere?", ["No", "Sí"], 
                              index=1 if rec["requiere_viatico"] == 1 else 0, 
                              horizontal=True, key="via_edit_req")
            
            ed3, ed4 = st.columns([1, 1])
            new_origen = ed3.text_input("Origen", value=rec["origen"] or "", key="via_edit_origen")
            new_destino = ed4.text_input("Destino", value=rec["destino"] or "", key="via_edit_destino")
            
            new_valor = st.number_input("Valor", min_value=0.0, step=1000.0, 
                                      value=float(rec["valor"] or 0), key="via_edit_valor")
            new_obs = st.text_area("Observaciones", value=rec["observaciones"] or "", key="via_edit_obs")

            if st.button("Guardar cambios", type="primary", key="via_edit_guardar"):
                try:
                    DATA.update_viatico(
                        int(vid_in),
                        {
                            "fecha": new_fecha.strftime("%Y-%m-%d"),
                            "requiere_viatico": 1 if new_req == "Sí" else 0,
                            "origen": new_origen.strip() or None,
                            "destino": new_destino.strip() or None,
                            "valor": float(new_valor) if new_valor > 0 else None,
                            "observaciones": new_obs.strip() or None,
                        },
                    )
                    success_toast("Viático actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")

# ---------------- UI: PLANIFICADOR (MEJORADO) ----------------
def ui_planificador(auth_user: Optional[str]):
    st.subheader("Planificador (agenda)")

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

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c6.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="ag_Profesional")
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
            "Profesional",
            "creado_por",
            "creado_en",
        ]
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    # EDITAR / ELIMINAR
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
            st.markdown("##### Editar evento")
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

# ---------------- UI: PAPELERIA (CORREGIDO) ----------------
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

    prof = DATA.list_Profesionales(pid, cid)
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
            "Profesional",
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
            st.markdown("##### Editar solicitud")
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

# ---------------- UI: CONFIGURACION (CON EDICIÓN EN PROGRAMAS Y CONVENIOS) ----------------
def ui_configuracion():
    st.subheader("Configuración de catálogos")
    tabs = st.tabs(["Programas", "Convenios", "Instituciones", "Profesionales", "Pacientes"])

    # ==================== PROGRAMAS ====================
    with tabs[0]:
        st.markdown("#### Agregar programa")
        c1, c2 = st.columns([2, 1])
        pnom = c1.text_input("Nombre del programa", key="cfg_prog_nombre")
        if c2.button("Agregar programa", use_container_width=True, key="cfg_btn_add_programa"):
            if not pnom.strip():
                warn_toast("Escribe un nombre.")
            else:
                DATA.upsert_programa(pnom.strip())
                success_toast("Programa agregado.")
                st.rerun()
        
        st.markdown("#### Programas existentes")
        df_prog = DATA.list_programas()
        st.dataframe(df_prog, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar programa")
        
        # Inicializar estado de edición
        if "editing_prog_id" not in st.session_state:
            st.session_state.editing_prog_id = None
        if "editing_prog_data" not in st.session_state:
            st.session_state.editing_prog_data = {}
        
        # Controles para cargar y eliminar
        p1, p2, p3 = st.columns([1, 1, 1])
        pid_edit = p1.number_input("ID programa", min_value=1, step=1, key="cfg_prog_edit_id")
        cargar_prog = p2.button("📋 Cargar", use_container_width=True, key="cfg_prog_cargar")
        eliminar_prog = p3.button("🗑️ Eliminar", use_container_width=True, key="cfg_prog_eliminar")
        
        # Eliminar
        if eliminar_prog:
            try:
                DATA.delete_programa(int(pid_edit))
                success_toast("Programa desactivado.")
                st.session_state.editing_prog_id = None
                st.session_state.editing_prog_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_prog:
            prog_rec = DATA.get_programa_by_id(int(pid_edit))
            if not prog_rec:
                warn_toast("No existe programa con ese ID.")
                st.session_state.editing_prog_id = None
                st.session_state.editing_prog_data = {}
            else:
                st.session_state.editing_prog_id = prog_rec["id"]
                st.session_state.editing_prog_data = {
                    "nombre": prog_rec["nombre"]
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_prog_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando programa ID: {st.session_state.editing_prog_id}**")
            
            with st.form(key="form_edit_prog", clear_on_submit=False):
                new_nom = st.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_prog_data["nombre"],
                    key="form_edit_prog_nom"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip():
                    error_toast("El nombre es obligatorio")
                else:
                    try:
                        DATA.update_programa(st.session_state.editing_prog_id, new_nom.strip())
                        success_toast("✅ Programa actualizado correctamente")
                        st.session_state.editing_prog_id = None
                        st.session_state.editing_prog_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_prog_id = None
                st.session_state.editing_prog_data = {}
                st.rerun()

    # ==================== CONVENIOS ====================
    with tabs[1]:
        st.markdown("#### Agregar convenio")
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
        
        st.markdown("#### Convenios existentes")
        df_conv = DATA.list_convenios()
        st.dataframe(df_conv, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar convenio")
        
        # Inicializar estado de edición
        if "editing_conv_id" not in st.session_state:
            st.session_state.editing_conv_id = None
        if "editing_conv_data" not in st.session_state:
            st.session_state.editing_conv_data = {}
        
        # Controles para cargar y eliminar
        cv1, cv2, cv3 = st.columns([1, 1, 1])
        cid_edit = cv1.number_input("ID convenio", min_value=1, step=1, key="cfg_conv_edit_id")
        cargar_conv = cv2.button("📋 Cargar", use_container_width=True, key="cfg_conv_cargar")
        eliminar_conv = cv3.button("🗑️ Eliminar", use_container_width=True, key="cfg_conv_eliminar")
        
        # Eliminar
        if eliminar_conv:
            try:
                DATA.delete_convenio(int(cid_edit))
                success_toast("Convenio desactivado.")
                st.session_state.editing_conv_id = None
                st.session_state.editing_conv_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_conv:
            conv_rec = DATA.get_convenio_by_id(int(cid_edit))
            if not conv_rec:
                warn_toast("No existe convenio con ese ID.")
                st.session_state.editing_conv_id = None
                st.session_state.editing_conv_data = {}
            else:
                st.session_state.editing_conv_id = conv_rec["id"]
                st.session_state.editing_conv_data = {
                    "nombre": conv_rec["nombre"],
                    "programa_id": conv_rec["programa_id"]
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_conv_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando convenio ID: {st.session_state.editing_conv_id}**")
            
            with st.form(key="form_edit_conv", clear_on_submit=False):
                # Obtener lista de programas actualizada
                progs_edit = DATA.list_programas()
                prog_map_edit = {r["nombre"]: int(r["id"]) for _, r in progs_edit.iterrows()} if not progs_edit.empty else {}
                prog_reverse_map = {v: k for k, v in prog_map_edit.items()}
                
                current_prog_name = prog_reverse_map.get(st.session_state.editing_conv_data["programa_id"], "")
                
                cve1, cve2 = st.columns([1, 1])
                new_prog = cve1.selectbox(
                    "Programa *",
                    options=list(prog_map_edit.keys()),
                    index=list(prog_map_edit.keys()).index(current_prog_name) if current_prog_name in prog_map_edit.keys() else 0,
                    key="form_edit_conv_prog"
                )
                
                new_nom = cve2.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_conv_data["nombre"],
                    key="form_edit_conv_nom"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip() or not new_prog:
                    error_toast("El nombre y programa son obligatorios")
                else:
                    try:
                        DATA.update_convenio(
                            st.session_state.editing_conv_id, 
                            new_nom.strip(),
                            prog_map_edit[new_prog]
                        )
                        success_toast("✅ Convenio actualizado correctamente")
                        st.session_state.editing_conv_id = None
                        st.session_state.editing_conv_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_conv_id = None
                st.session_state.editing_conv_data = {}
                st.rerun()

    # ==================== INSTITUCIONES ====================
    with tabs[2]:
        st.markdown("#### Agregar institución")
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
        
        st.markdown("#### Instituciones existentes")
        df_inst = DATA.list_instituciones()
        st.dataframe(df_inst, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar institución")
        
        # Inicializar estado de edición
        if "editing_inst_id" not in st.session_state:
            st.session_state.editing_inst_id = None
        if "editing_inst_data" not in st.session_state:
            st.session_state.editing_inst_data = {}
        
        # Controles para cargar y eliminar
        e1, e2, e3 = st.columns([1, 1, 1])
        iid_edit = e1.number_input("ID institución", min_value=1, step=1, key="cfg_inst_edit_id")
        cargar_inst = e2.button("📋 Cargar", use_container_width=True, key="cfg_inst_cargar")
        eliminar_inst = e3.button("🗑️ Eliminar", use_container_width=True, key="cfg_inst_eliminar")
        
        # Eliminar
        if eliminar_inst:
            try:
                DATA.delete_institucion(int(iid_edit))
                success_toast("Institución desactivada.")
                st.session_state.editing_inst_id = None
                st.session_state.editing_inst_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_inst:
            inst_rec = DATA.get_institucion_by_id(int(iid_edit))
            if not inst_rec:
                warn_toast("No existe institución con ese ID.")
                st.session_state.editing_inst_id = None
                st.session_state.editing_inst_data = {}
            else:
                st.session_state.editing_inst_id = inst_rec["id"]
                st.session_state.editing_inst_data = {
                    "nombre": inst_rec["nombre"],
                    "localidad": inst_rec["localidad"] or "",
                    "municipio": inst_rec["municipio"] or "",
                    "departamento": inst_rec["departamento"] or ""
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_inst_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando institución ID: {st.session_state.editing_inst_id}**")
            
            with st.form(key="form_edit_inst", clear_on_submit=False):
                ed1, ed2, ed3, ed4 = st.columns([2, 1, 1, 1])
                
                new_nom = ed1.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_inst_data["nombre"],
                    key="form_edit_inst_nom"
                )
                new_loc = ed2.text_input(
                    "Localidad", 
                    value=st.session_state.editing_inst_data["localidad"],
                    key="form_edit_inst_loc"
                )
                new_mun = ed3.text_input(
                    "Municipio", 
                    value=st.session_state.editing_inst_data["municipio"],
                    key="form_edit_inst_mun"
                )
                new_dep = ed4.text_input(
                    "Departamento", 
                    value=st.session_state.editing_inst_data["departamento"],
                    key="form_edit_inst_dep"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip():
                    error_toast("El nombre es obligatorio")
                else:
                    try:
                        DATA.update_institucion(
                            st.session_state.editing_inst_id, 
                            new_nom.strip(), 
                            new_loc.strip() or None, 
                            new_mun.strip() or None, 
                            new_dep.strip() or None
                        )
                        success_toast("✅ Institución actualizada correctamente")
                        st.session_state.editing_inst_id = None
                        st.session_state.editing_inst_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_inst_id = None
                st.session_state.editing_inst_data = {}
                st.rerun()

        st.markdown("---")
        st.markdown("### Carga masiva de instituciones")
        file_inst = st.file_uploader("Archivo de instituciones (Excel o CSV)", type=["xlsx", "xls", "csv"], key="cfg_up_instituciones")
        if file_inst is not None and st.button("Procesar instituciones", key="cfg_btn_proc_inst"):
            try:
                df_inst_up = read_table_upload(file_inst)
                if "nombre" not in df_inst_up.columns:
                    st.error(f"El archivo debe contener 'nombre'. Columnas: {list(df_inst_up.columns)}")
                else:
                    ok = 0
                    for _, r in df_inst_up.iterrows():
                        nom = str(r.get("nombre", "")).strip()
                        if not nom:
                            continue
                        DATA.upsert_institucion(
                            nom,
                            str(r.get("localidad", "")).strip() or None if "localidad" in df_inst_up.columns else None,
                            str(r.get("municipio", "")).strip() or None if "municipio" in df_inst_up.columns else None,
                            str(r.get("departamento", "")).strip() or None if "departamento" in df_inst_up.columns else None,
                        )
                        ok += 1
                    success_toast(f"Se procesaron {ok} instituciones.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando instituciones: {e}")

    # ==================== PROFESIONALES ====================
    with tabs[3]:
        st.markdown("#### Agregar profesional")
        progs = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}

        # Necesitamos un programa y convenio fijos para profesionales
        # Por simplicidad, tomamos el primero disponible
        PROGRAMA_FIJO_ID = list(prog_map.values())[0] if prog_map else None
        conv_fijos = DATA.list_convenios(PROGRAMA_FIJO_ID) if PROGRAMA_FIJO_ID else pd.DataFrame()
        CONVENIO_FIJO_ID = int(conv_fijos.iloc[0]["id"]) if not conv_fijos.empty else None

        c1, c2, c3 = st.columns([2, 1.2, 1.4])
        f_nom = c1.text_input("Nombre profesional", key="cfg_prof_nombre")
        f_doc = c2.text_input("Documento (opcional)", key="cfg_prof_doc")
        f_email = c3.text_input("Email (opcional)", key="cfg_prof_email")
        
        zona_opts = ["(No especifica)", "Urbana", "Rural"]
        f_zona = st.selectbox("Zona (opcional)", options=zona_opts, key="cfg_prof_zona")

        if st.button("Agregar profesional", use_container_width=True, key="cfg_btn_add_prof"):
            if not f_nom.strip():
                warn_toast("Escribe el nombre.")
            else:
                zona = None if f_zona == "(No especifica)" else f_zona
                DATA.upsert_Profesional(f_nom.strip(), f_doc or None, f_email or None, PROGRAMA_FIJO_ID, CONVENIO_FIJO_ID, zona)
                success_toast("Profesional agregado.")
                st.rerun()

        st.markdown("#### Profesionales existentes")
        df_prof = DATA.list_Profesionales()
        st.dataframe(df_prof, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar profesional")
        
        # Inicializar estado de edición
        if "editing_prof_id" not in st.session_state:
            st.session_state.editing_prof_id = None
        if "editing_prof_data" not in st.session_state:
            st.session_state.editing_prof_data = {}
        
        # Controles para cargar y eliminar
        p1, p2, p3 = st.columns([1, 1, 1])
        fid_edit = p1.number_input("ID profesional", min_value=1, step=1, key="cfg_prof_edit_id")
        cargar_prof = p2.button("📋 Cargar", use_container_width=True, key="cfg_prof_cargar")
        eliminar_prof = p3.button("🗑️ Eliminar", use_container_width=True, key="cfg_prof_eliminar")
        
        # Eliminar
        if eliminar_prof:
            try:
                DATA.delete_profesional(int(fid_edit))
                success_toast("Profesional desactivado.")
                st.session_state.editing_prof_id = None
                st.session_state.editing_prof_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_prof:
            prof_rec = DATA.get_profesional_by_id(int(fid_edit))
            if not prof_rec:
                warn_toast("No existe profesional con ese ID.")
                st.session_state.editing_prof_id = None
                st.session_state.editing_prof_data = {}
            else:
                st.session_state.editing_prof_id = prof_rec["id"]
                st.session_state.editing_prof_data = {
                    "nombre": prof_rec["nombre"],
                    "documento": prof_rec["documento"] or "",
                    "email": prof_rec["email"] or "",
                    "zona": prof_rec["zona"] or "(No especifica)"
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_prof_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando profesional ID: {st.session_state.editing_prof_id}**")
            
            with st.form(key="form_edit_prof", clear_on_submit=False):
                pe1, pe2, pe3 = st.columns([2, 1, 1])
                
                new_nom = pe1.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_prof_data["nombre"],
                    key="form_edit_prof_nom"
                )
                new_doc = pe2.text_input(
                    "Documento", 
                    value=st.session_state.editing_prof_data["documento"],
                    key="form_edit_prof_doc"
                )
                new_email = pe3.text_input(
                    "Email", 
                    value=st.session_state.editing_prof_data["email"],
                    key="form_edit_prof_email"
                )
                
                zona_opts = ["(No especifica)", "Urbana", "Rural"]
                current_zona = st.session_state.editing_prof_data["zona"]
                if current_zona not in zona_opts:
                    current_zona = "(No especifica)"
                
                new_zona = st.selectbox(
                    "Zona",
                    options=zona_opts,
                    index=zona_opts.index(current_zona),
                    key="form_edit_prof_zona"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip():
                    error_toast("El nombre es obligatorio")
                else:
                    try:
                        DATA.update_profesional(
                            st.session_state.editing_prof_id, 
                            new_nom.strip(), 
                            new_doc.strip() or None,
                            new_email.strip() or None,
                            PROGRAMA_FIJO_ID,
                            CONVENIO_FIJO_ID,
                            None if new_zona == "(No especifica)" else new_zona
                        )
                        success_toast("✅ Profesional actualizado correctamente")
                        st.session_state.editing_prof_id = None
                        st.session_state.editing_prof_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_prof_id = None
                st.session_state.editing_prof_data = {}
                st.rerun()

        st.markdown("---")
        st.markdown("### Carga masiva de profesionales")
        st.caption("Columnas: **nombre** (obligatoria), opcionales: documento, email, zona (Rural/Urbana).")
        file_prof = st.file_uploader("Archivo de profesionales", type=["xlsx", "xls", "csv"], key="cfg_up_profesionales")
        if file_prof is not None and st.button("Procesar profesionales", key="cfg_btn_proc_prof"):
            try:
                df_prof_up = read_table_upload(file_prof)
                if "nombre" not in df_prof_up.columns:
                    st.error(f"El archivo debe contener 'nombre'. Columnas: {list(df_prof_up.columns)}")
                else:
                    ok = 0
                    for _, r in df_prof_up.iterrows():
                        nom = str(r.get("nombre", "")).strip()
                        if not nom:
                            continue
                        doc = str(r.get("documento", "")).strip() if pd.notna(r.get("documento")) else None
                        email = str(r.get("email", "")).strip() if pd.notna(r.get("email")) else None
                        zona = str(r.get("zona", "")).strip() if pd.notna(r.get("zona")) else None
                        if zona not in ("Rural", "Urbana"):
                            zona = None
                        DATA.upsert_Profesional(nom, doc, email, PROGRAMA_FIJO_ID, CONVENIO_FIJO_ID, zona)
                        ok += 1
                    success_toast(f"Se procesaron {ok} profesionales.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando profesionales: {e}")

    # ==================== PACIENTES ====================
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

        st.markdown("#### Pacientes existentes")
        df_pac = DATA.list_pacientes()
        st.dataframe(df_pac, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar paciente")
        
        # Inicializar estado de edición
        if "editing_pac_id" not in st.session_state:
            st.session_state.editing_pac_id = None
        if "editing_pac_data" not in st.session_state:
            st.session_state.editing_pac_data = {}
        
        # Controles para cargar y eliminar
        pa1, pa2, pa3 = st.columns([1, 1, 1])
        pac_id_edit = pa1.number_input("ID paciente", min_value=1, step=1, key="cfg_pac_edit_id")
        cargar_pac = pa2.button("📋 Cargar", use_container_width=True, key="cfg_pac_cargar")
        eliminar_pac = pa3.button("🗑️ Eliminar", use_container_width=True, key="cfg_pac_eliminar")
        
        # Eliminar
        if eliminar_pac:
            try:
                DATA.delete_paciente(int(pac_id_edit))
                success_toast("Paciente desactivado.")
                st.session_state.editing_pac_id = None
                st.session_state.editing_pac_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_pac:
            pac_rec = DATA.get_paciente_by_id(int(pac_id_edit))
            if not pac_rec:
                warn_toast("No existe paciente con ese ID.")
                st.session_state.editing_pac_id = None
                st.session_state.editing_pac_data = {}
            else:
                st.session_state.editing_pac_id = pac_rec["id"]
                st.session_state.editing_pac_data = {
                    "numero_documento": pac_rec["numero_documento"],
                    "nombre": pac_rec["nombre"],
                    "fecha_nacimiento": pac_rec["fecha_nacimiento"] or "",
                    "sexo": pac_rec["sexo"] if pac_rec["sexo"] in ["F", "M", "Otro"] else "(No especifica)",
                    "telefono": pac_rec["telefono"] or "",
                    "email": pac_rec["email"] or "",
                    "direccion": pac_rec["direccion"] or "",
                    "localidad": pac_rec["localidad"] or "",
                    "municipio": pac_rec["municipio"] or "",
                    "departamento": pac_rec["departamento"] or "",
                    "zona": pac_rec["zona"] if pac_rec["zona"] in ["Urbana", "Rural"] else "(No especifica)"
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_pac_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando paciente ID: {st.session_state.editing_pac_id}**")
            
            with st.form(key="form_edit_pac", clear_on_submit=False):
                pae1, pae2 = st.columns([1, 2])
                new_doc = pae1.text_input(
                    "Documento *", 
                    value=st.session_state.editing_pac_data["numero_documento"],
                    key="form_edit_pac_doc"
                )
                new_nom = pae2.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_pac_data["nombre"],
                    key="form_edit_pac_nom"
                )
                
                pae3, pae4, pae5 = st.columns([1, 1, 1])
                new_fnac = pae3.text_input(
                    "Fecha nacimiento", 
                    value=st.session_state.editing_pac_data["fecha_nacimiento"],
                    key="form_edit_pac_fnac"
                )
                
                sexo_opts = ["(No especifica)", "F", "M", "Otro"]
                current_sexo = st.session_state.editing_pac_data["sexo"]
                new_sexo = pae4.selectbox(
                    "Sexo",
                    options=sexo_opts,
                    index=sexo_opts.index(current_sexo),
                    key="form_edit_pac_sexo"
                )
                
                new_tel = pae5.text_input(
                    "Teléfono", 
                    value=st.session_state.editing_pac_data["telefono"],
                    key="form_edit_pac_tel"
                )
                
                pae6, pae7 = st.columns([1, 1])
                new_email = pae6.text_input(
                    "Email", 
                    value=st.session_state.editing_pac_data["email"],
                    key="form_edit_pac_email"
                )
                new_dir = pae7.text_input(
                    "Dirección", 
                    value=st.session_state.editing_pac_data["direccion"],
                    key="form_edit_pac_dir"
                )
                
                pae8, pae9, pae10 = st.columns([1, 1, 1])
                new_loc = pae8.text_input(
                    "Localidad", 
                    value=st.session_state.editing_pac_data["localidad"],
                    key="form_edit_pac_loc"
                )
                new_mun = pae9.text_input(
                    "Municipio", 
                    value=st.session_state.editing_pac_data["municipio"],
                    key="form_edit_pac_mun"
                )
                new_dep = pae10.text_input(
                    "Departamento", 
                    value=st.session_state.editing_pac_data["departamento"],
                    key="form_edit_pac_dep"
                )
                
                zona_opts = ["(No especifica)", "Urbana", "Rural"]
                current_zona = st.session_state.editing_pac_data["zona"]
                new_zona = st.selectbox(
                    "Zona",
                    options=zona_opts,
                    index=zona_opts.index(current_zona),
                    key="form_edit_pac_zona"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_doc.strip() or not new_nom.strip():
                    error_toast("Documento y nombre son obligatorios")
                else:
                    try:
                        DATA.upsert_paciente(
                            numero_documento=new_doc.strip(),
                            nombre=new_nom.strip(),
                            fecha_nacimiento=new_fnac.strip() or None,
                            sexo=None if new_sexo == "(No especifica)" else new_sexo,
                            telefono=new_tel.strip() or None,
                            email=new_email.strip() or None,
                            direccion=new_dir.strip() or None,
                            localidad=new_loc.strip() or None,
                            municipio=new_mun.strip() or None,
                            departamento=new_dep.strip() or None,
                            zona=None if new_zona == "(No especifica)" else new_zona
                        )
                        success_toast("✅ Paciente actualizado correctamente")
                        st.session_state.editing_pac_id = None
                        st.session_state.editing_pac_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_pac_id = None
                st.session_state.editing_pac_data = {}
                st.rerun()

        st.markdown("---")
        st.markdown("### Carga masiva de pacientes")
        st.caption(
            "Obligatorias: **documento**, **nombre**. Opcionales: fecha_nacimiento, sexo, telefono, email, "
            "direccion, localidad, municipio, departamento, zona (Rural/Urbana)."
        )
        file_pac = st.file_uploader("Archivo de pacientes (Excel o CSV)", type=["xlsx", "xls", "csv"], key="cfg_up_pacientes")
        if file_pac is not None and st.button("Procesar pacientes", key="cfg_btn_proc_pac"):
            try:
                df_pac_up = read_table_upload(file_pac)
                if not {"documento", "nombre"}.issubset(df_pac_up.columns):
                    st.error(f"El archivo debe contener 'documento' y 'nombre'. Columnas: {list(df_pac_up.columns)}")
                else:
                    ok = 0
                    for _, r in df_pac_up.iterrows():
                        doc = str(r.get("documento", "")).strip()
                        nom = str(r.get("nombre", "")).strip()
                        if not doc or not nom:
                            continue
                        zona = (
                            str(r.get("zona", "")).strip()
                            if "zona" in df_pac_up.columns and pd.notna(r.get("zona"))
                            else None
                        )
                        if zona not in ("Rural", "Urbana"):
                            zona = None
                        DATA.upsert_paciente(
                            numero_documento=doc,
                            nombre=nom,
                            fecha_nacimiento=str(r.get("fecha_nacimiento"))
                            if "fecha_nacimiento" in df_pac_up.columns and pd.notna(r.get("fecha_nacimiento"))
                            else None,
                            sexo=str(r.get("sexo")).strip() if "sexo" in df_pac_up.columns and pd.notna(r.get("sexo")) else None,
                            telefono=str(r.get("telefono")).strip()
                            if "telefono" in df_pac_up.columns and pd.notna(r.get("telefono"))
                            else None,
                            email=str(r.get("email")).strip() if "email" in df_pac_up.columns and pd.notna(r.get("email")) else None,
                            direccion=str(r.get("direccion")).strip()
                            if "direccion" in df_pac_up.columns and pd.notna(r.get("direccion"))
                            else None,
                            localidad=str(r.get("localidad")).strip()
                            if "localidad" in df_pac_up.columns and pd.notna(r.get("localidad"))
                            else None,
                            municipio=str(r.get("municipio")).strip()
                            if "municipio" in df_pac_up.columns and pd.notna(r.get("municipio"))
                            else None,
                            departamento=str(r.get("departamento")).strip()
                            if "departamento" in df_pac_up.columns and pd.notna(r.get("departamento"))
                            else None,
                            zona=zona,
                        )
                        ok += 1
                    success_toast(f"Se procesaron {ok} pacientes.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando pacientes: {e}")

# ---------------- UI: RESPALDO (MEJORADO CON RESTAURACIÓN) ----------------
def ui_respaldo():
    st.subheader("Respaldo de la base de datos")
    st.caption("Descarga la base SQLite actual y/o un ZIP con CSV y schema.sql.")

    col1, col2 = st.columns(2)
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

    col2.download_button(
        "⬇️ Descargar ZIP (.db + CSV + schema)",
        data=build_zip_backup(),
        file_name=f"respaldo_productividad_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
        mime="application/zip",
        use_container_width=True,
        key="bk_btn_zip",
    )

    st.markdown("---")
    st.markdown("### 📤 Restaurar desde respaldo")
    
    uploaded_db = st.file_uploader(
        "Cargar archivo .db de respaldo", 
        type=["db"], 
        key="restore_db_file"
    )
    
    if uploaded_db is not None:
        st.warning("⚠️ Esto sobrescribirá la base de datos actual")
        
        if st.button("Restaurar base de datos", type="primary", key="restore_btn"):
            try:
                global SQLITE_CONN, DATA
                
                # Cerrar conexión
                try:
                    SQLITE_CONN.close()
                except:
                    pass
                
                # Guardar respaldo actual por si acaso
                if os.path.exists(DB_SQLITE_PATH):
                    backup_name = f"{DB_SQLITE_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(DB_SQLITE_PATH, backup_name)
                    st.info(f"Respaldo automático creado: {backup_name}")
                
                # Escribir archivo subido
                with open(DB_SQLITE_PATH, "wb") as f:
                    f.write(uploaded_db.getvalue())
                
                # Reconectar
                SQLITE_CONN = get_db_connection()
                DATA = DataAccess(SQLITE_CONN)
                
                # Verificar
                count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
                success_toast(f"✅ Base restaurada correctamente. {count} registros encontrados.")
                st.rerun()
                
            except Exception as e:
                error_toast(f"Error restaurando: {e}")
                st.code(traceback.format_exc())

    st.markdown("---")
    with st.expander("⚠️ Reiniciar base (acción destructiva)", expanded=False):
        st.warning("Esto borrará información. Haz un respaldo antes.")
        metodo = st.radio(
            "Método de reinicio",
            ["Vaciar tablas (conservar archivo .db)", "Borrar archivo .db (recrear esquema en blanco)"],
            index=0,
            horizontal=False,
            key="reset_metodo",
        )
        confirma = st.text_input("Escribe exactamente: BORRAR TODO", key="reset_confirm")
        colA, colB = st.columns([1, 3])
        ejecutar = colA.button("Reiniciar ahora", type="primary", use_container_width=True, key="reset_go")

        if ejecutar:
            if confirma.strip() != "BORRAR TODO":
                st.error("Confirma escribiendo 'BORRAR TODO' exactamente.")
            else:
                m = "vaciar" if metodo.startswith("Vaciar") else "borrar_archivo"
                ok = _reset_database(m)
                if ok:
                    st.success("Base reiniciada correctamente. Recarga la página.")
                    st.rerun()

def _reset_database(method: str):
    global SQLITE_CONN, DATA
    try:
        if method == "vaciar":
            # Cerrar conexión actual
            try:
                SQLITE_CONN.close()
            except:
                pass
            
            # Reconectar y vaciar
            SQLITE_CONN = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
            SQLITE_CONN.execute("PRAGMA foreign_keys=OFF;")
            
            tablas = ["registros", "viaticos", "agenda", "papeleria",
                     "Profesionales", "pacientes", "instituciones", "convenios", "programas"]
            
            for t in tablas:
                try:
                    SQLITE_CONN.execute(f"DELETE FROM {t};")
                    st.write(f"✓ Tabla {t} vaciada")
                except Exception as e:
                    st.warning(f"⚠ Error en {t}: {e}")
            
            try:
                SQLITE_CONN.execute("DELETE FROM sqlite_sequence;")
            except:
                pass
            
            SQLITE_CONN.execute("PRAGMA foreign_keys=ON;")
            SQLITE_CONN.commit()
            
            # Recrear esquema
            ensure_sqlite_schema()
            
        elif method == "borrar_archivo":
            try:
                SQLITE_CONN.close()
            except:
                pass
            
            if os.path.exists(DB_SQLITE_PATH):
                os.remove(DB_SQLITE_PATH)
                st.write(f"✓ Archivo {DB_SQLITE_PATH} eliminado")
            
            # Esperar un momento
            time.sleep(0.5)
        
        # Reconectar
        SQLITE_CONN = get_db_connection()
        ensure_sqlite_schema()
        DATA = DataAccess(SQLITE_CONN)
        
        return True
        
    except Exception as e:
        st.error(f"Error al reiniciar: {e}")
        st.code(traceback.format_exc())
        return False

# ---------------- MAIN ----------------
def main():
    st.markdown(f"# {APP_ICON} {APP_TITLE}")
    st.caption("Base SQLite local (`productividad_Profesionales.db`). Usuarios del mismo enlace comparten la misma información.")
    
    # DIAGNÓSTICO
    if st.sidebar.checkbox("🔍 Mostrar diagnóstico", value=False):
        st.sidebar.markdown("### Diagnóstico de BD")
        db_exists = os.path.exists(DB_SQLITE_PATH)
        st.sidebar.write(f"Archivo existe: {db_exists}")
        if db_exists:
            db_size = os.path.getsize(DB_SQLITE_PATH)
            st.sidebar.write(f"Tamaño: {db_size:,} bytes")
            try:
                count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
                st.sidebar.write(f"Registros en BD: {count}")
            except Exception as e:
                st.sidebar.error(f"Error leyendo BD: {e}")
    
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



