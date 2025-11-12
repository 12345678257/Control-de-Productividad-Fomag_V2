# Productividad de Profesionales

Aplicación en Streamlit para medir la productividad de los profesionales (profesores / psicólogos) en programas y convenios.

## Funcionalidades

- Registro de atenciones por paciente (con zona Rural/Urbana).
- Registro y carga masiva de:
  - Profesionales (con zona Rural/Urbana).
  - Pacientes.
  - Instituciones.
- Registro de viáticos (sí/no, origen, destino, valor).
- Planificador / agenda.
- Dashboard con KPIs:
  - Programados vs atendidos.
  - Brecha Panacea (atendidos vs registrados en Panacea).
  - Top profesionales, instituciones, actividades.
- Roles:
  - `admin` / `admin123` → ve todo (incluye Dashboard, Reportes, Configuración).
  - `pro` / `pro123` → sólo ve registrar, listado, viáticos y planificador.
- Base en SQLite (`productividad_profesores.db`) compartida para todos los usuarios que usan el mismo enlace.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app_productividad_profesores.py
