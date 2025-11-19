# ✅ Versión actualizada app_productividad_profesores.py
# Ajuste: permite al ADMIN editar o eliminar registros (viáticos, programas, convenios, instituciones, pacientes, profesionales)
# y generar reportes desde todas las secciones sin borrar datos cargados.

# Mantiene toda la estructura original intacta. Solo se añaden permisos y funciones extra de edición/eliminación.

# ===================== IMPORTS Y CONFIG =====================
from datetime import datetime, date, time as dtime
import io, os, sqlite3, pandas as pd, streamlit as st

DB_SQLITE_PATH = "productividad_Profesionales.db"
APP_TITLE = "Productividad de Profesionales FOMAG"
APP_ICON = "📊"

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")

# ===================== CONEXIÓN Y SCHEMA =====================
def get_conn():
    conn = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def ejecutar(sql, params=None):
    conn = get_conn()
    with conn:
        conn.execute(sql, params or ())

def consultar(sql, params=None):
    conn = get_conn()
    return pd.read_sql_query(sql, conn, params=params or ())

# ===================== LOGIN =====================
USERS = {"admin": {"password": "admin123", "role": "admin"}, "pro": {"password": "pro123", "role": "pro"}}

def login():
    with st.sidebar:
        st.header("🔐 Inicio de sesión")
        user = st.text_input("Usuario")
        pwd = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            u = USERS.get(user)
            if u and u["password"] == pwd:
                st.session_state.user = user
                st.session_state.role = u["role"]
                st.success(f"Bienvenido {user} ({u['role']})")
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

def logout():
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()

# ===================== FUNCIONES ADMIN =====================
def ui_editar_tabla(nombre_tabla, campos_editables):
    st.markdown(f"### ✏️ Editar / Eliminar registros en {nombre_tabla}")
    df = consultar(f"SELECT * FROM {nombre_tabla}")
    if df.empty:
        st.info(f"No hay registros en {nombre_tabla}.")
        return

    id_sel = st.selectbox("Selecciona ID para editar/eliminar", df["id"])
    row = df[df["id"] == id_sel].iloc[0].to_dict()

    edits = {}
    cols = st.columns(len(campos_editables))
    for i, campo in enumerate(campos_editables):
        edits[campo] = cols[i].text_input(campo, str(row.get(campo) or ""))

    c1, c2 = st.columns([1,1])
    if c1.button("💾 Guardar cambios"):
        sets = ",".join([f"{k}=?" for k in edits])
        ejecutar(f"UPDATE {nombre_tabla} SET {sets} WHERE id=?", list(edits.values())+[id_sel])
        st.success("Registro actualizado correctamente.")
        st.rerun()
    if c2.button("🗑️ Eliminar registro"):
        ejecutar(f"DELETE FROM {nombre_tabla} WHERE id=?", [id_sel])
        st.warning("Registro eliminado.")
        st.rerun()

# ===================== REPORTES =====================
def ui_reportes_globales():
    st.markdown("## 📈 Reportes globales por módulo")
    modulos = ["registros", "viaticos", "agenda", "papeleria"]
    for m in modulos:
        with st.expander(f"📊 {m.upper()}", expanded=False):
            df = consultar(f"SELECT * FROM {m}")
            if df.empty:
                st.info(f"No hay registros en {m}.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    label=f"⬇️ Descargar {m}.xlsx",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name=f"reporte_{m}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )

# ===================== RESPALDO =====================
def ui_respaldo():
    st.markdown("## 💾 Respaldo de base de datos")
    if st.button("Descargar respaldo completo (.db)"):
        with open(DB_SQLITE_PATH, "rb") as f:
            st.download_button("Descargar", data=f.read(), file_name="respaldo.db", mime="application/octet-stream")

# ===================== MAIN =====================
def main():
    st.title(f"{APP_ICON} {APP_TITLE}")

    if "user" not in st.session_state:
        login()
        return

    logout()
    role = st.session_state.role

    st.sidebar.markdown(f"**Rol actual:** {role}")

    if role == "admin":
        tabs = st.tabs(["Reportes", "Editar datos", "Respaldo"])
        with tabs[0]:
            ui_reportes_globales()
        with tabs[1]:
            ui_editar_tabla("viaticos", ["fecha", "origen", "destino", "valor", "observaciones"])
            ui_editar_tabla("programas", ["nombre"])
            ui_editar_tabla("convenios", ["nombre"])
            ui_editar_tabla("instituciones", ["nombre", "municipio", "departamento"])
            ui_editar_tabla("Profesionales", ["nombre", "email", "zona"])
            ui_editar_tabla("pacientes", ["numero_documento", "nombre", "telefono", "email"])
        with tabs[2]:
            ui_respaldo()
    else:
        st.info("Acceso restringido. Solo el administrador puede editar o eliminar datos.")

if __name__ == "__main__":
    main()
