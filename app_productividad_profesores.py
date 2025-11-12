import io, re, unicodedata
import pandas as pd

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
    # 1) normalizar
    df.columns = [_slug_col(c) for c in df.columns]

    # 2) mapear sinónimos
    synonyms = {
        "num_documento": "documento",
        "numero_documento": "documento",
        "nro_documento": "documento",
        "identificacion": "documento",
        "identificación": "documento",
        "cedula": "documento",
        "cedula_de_ciudadania": "documento",
        "c_c": "documento",

        "nombre_completo": "nombre",
        "nombres": "nombres",
        "apellidos": "apellidos",

        "correo": "email",
        "correo_electronico": "email",

        "telefono_contacto": "telefono",
        "teléfono": "telefono",

        "dirección": "direccion",
        "fecha_de_nacimiento": "fecha_nacimiento",
        "zona_geografica": "zona",
    }
    df = df.rename(columns={c: synonyms.get(c, c) for c in df.columns})

    # 3) construir 'nombre' si vienen 'nombres' y/o 'apellidos'
    cols = set(df.columns)
    if "nombre" not in cols and ("nombres" in cols or "apellidos" in cols):
        n = df["nombres"].astype(str) if "nombres" in cols else ""
        a = df["apellidos"].astype(str) if "apellidos" in cols else ""
        df["nombre"] = (n.fillna("") + " " + a.fillna("")).str.strip().replace("", pd.NA)

    # 4) limpiar espacios invisibles
    for key_col in ("documento", "nombre"):
        if key_col in df.columns:
            df[key_col] = df[key_col].astype(str).str.replace("\u200b", "", regex=False).str.strip()

    return df

def read_table_upload(uploaded_file) -> pd.DataFrame:
    """
    Lee CSV/Excel con tolerancia de codificación y separador.
    - Excel: .xlsx/.xls
    - CSV: intenta utf-8, utf-8-sig, cp1252, latin1 y separadores auto, ',', ';'
    """
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
                # Si solo trajo 1 columna, probar ';' explícito
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

    # último recurso
    try:
        txt = raw.decode("cp1252", errors="replace")
        df = pd.read_csv(io.StringIO(txt), sep=None, engine="python")
        return normalize_columns(df)
    except Exception:
        pass

    raise last_err
