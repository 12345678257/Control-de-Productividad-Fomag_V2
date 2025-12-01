# 📊 Sistema de Gestión de Productividad - FOMAG

Sistema completo para gestión de atenciones profesionales con respaldos automáticos multi-nivel.

## 🚀 Características

### Gestión de Atenciones
- ✅ Registro individual y masivo de atenciones
- ✅ Gestión de profesionales, instituciones, pacientes
- ✅ Dashboard con métricas y gráficos
- ✅ Reportes en Excel multi-hoja
- ✅ Control de viáticos, agenda y papelería

### Sistema de Respaldos
- ✅ **Respaldos locales automáticos** (cada hora)
- ✅ **Respaldos programados** (diarios/semanales)
- ✅ **Google Drive** (automático)
- ✅ **Dropbox** (automático)
- ✅ **Email** (automático)
- ✅ **Puntos de restauración** con interfaz gráfica
- ✅ **Fusión de respaldos** para recuperación

---

## 📦 Instalación

### 1. Clonar o descargar el proyecto

```bash
git clone <tu-repositorio>
cd <nombre-carpeta>
```

### 2. Crear entorno virtual (recomendado)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar respaldos (opcional pero recomendado)

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env con tus credenciales
# (ver sección Configuración más abajo)
```

---

## 🎯 Uso Rápido

### Iniciar la aplicación

```bash
streamlit run app_productividad_Profesionales.py
```

### Acceder

- **URL:** http://localhost:8501
- **Usuario admin:** `admin` / `admin123`
- **Usuario profesional:** `pro` / `pro123`

---

## 🔧 Configuración de Respaldos

### Respaldos Locales (Activados por defecto)

Se crean automáticamente en `./respaldos_automaticos/`:
- Al iniciar la aplicación (cada hora)
- Antes de restaurar
- Antes de reiniciar BD
- Manualmente desde la app

### Google Drive (Opcional)

1. **Crear proyecto en Google Cloud:**
   - https://console.cloud.google.com/
   - Habilitar Google Drive API
   - Crear credenciales OAuth 2.0
   - Descargar como `credentials.json`

2. **Colocar `credentials.json` en raíz del proyecto**

3. **Configurar `.env`:**
   ```bash
   GOOGLE_DRIVE_ENABLED=true
   ```

4. **Primera ejecución:** Se abrirá navegador para autorizar

### Dropbox (Opcional)

1. **Crear app en Dropbox:**
   - https://www.dropbox.com/developers/apps
   - Generar Access Token

2. **Configurar `.env`:**
   ```bash
   DROPBOX_ENABLED=true
   DROPBOX_TOKEN=tu_token_aqui
   ```

### Email (Opcional)

1. **Para Gmail, crear contraseña de aplicación:**
   - https://myaccount.google.com/security
   - Habilitar verificación en 2 pasos
   - Generar contraseña de aplicación

2. **Configurar `.env`:**
   ```bash
   EMAIL_ENABLED=true
   EMAIL_USER=tu_email@gmail.com
   EMAIL_PASS=tu_contraseña_de_aplicacion
   EMAIL_DESTINATARIO=destino@email.com
   ```

### Respaldos Programados

Ejecutar en terminal separada:

```bash
python backup_system.py
```

Esto iniciará el scheduler que creará respaldos automáticos según configuración en `.env`:

```bash
BACKUP_DIARIO_HORA=02:00          # Todos los días a las 2am
BACKUP_SEMANAL_DIA=monday         # Cada lunes
BACKUP_SEMANAL_HORA=03:00         # A las 3am
```

---

## 🛠️ Herramientas Incluidas

### 1. `recovery_tool.py` - Recuperación de Emergencia

```bash
python recovery_tool.py
```

Funciones:
- 🔍 Buscar respaldos en todo el sistema
- 📊 Analizar contenido de respaldos
- 🔄 Comparar dos respaldos
- 💾 Restaurar desde respaldo
- 🔀 Fusionar múltiples respaldos

### 2. `generate_schema.py` - Gestión de Schema

```bash
# Generar archivos SQL
python generate_schema.py

# Verificar integridad de BD
python generate_schema.py verificar

# Crear BD desde schema
python generate_schema.py crear init_db.sql nueva_base.db
```

### 3. `backup_system.py` - Sistema de Respaldos

```bash
# Ejecutar respaldos programados
python backup_system.py
```

---

## 📁 Estructura del Proyecto

```
proyecto/
├── app_productividad_Profesionales.py   # Aplicación principal
├── backup_system.py                     # Sistema de respaldos automáticos
├── recovery_tool.py                     # Herramienta de recuperación
├── generate_schema.py                   # Generador de schema SQL
├── requirements.txt                     # Dependencias
├── .env.example                         # Plantilla de configuración
├── .env                                 # Configuración (NO subir a Git)
├── .gitignore                           # Archivos ignorados por Git
├── README.md                            # Esta documentación
├── RECUPERACION_EMERGENCIA.md           # Guía de recuperación
├── productividad_Profesionales.db       # Base de datos (NO subir)
├── init_db.sql                          # Schema vacío (subir a Git)
├── respaldos_automaticos/               # Respaldos locales (NO subir)
│   └── backup_*.db
└── logs/                                # Logs del sistema (NO subir)
    └── backup_system.log
```

---

## 🚨 Recuperación de Emergencia

### Si perdiste datos:

1. **Lee la guía completa:**
   ```bash
   cat RECUPERACION_EMERGENCIA.md
   ```

2. **Busca respaldos:**
   ```bash
   python recovery_tool.py
   # Opción 1: Buscar todos los respaldos
   ```

3. **Restaura el mejor respaldo:**
   ```bash
   python recovery_tool.py
   # Opción 4: Restaurar desde respaldo
   ```

4. **Si tienes múltiples respaldos parciales:**
   ```bash
   python recovery_tool.py
   # Opción 5: Fusionar respaldos
   ```

---

## 📚 Guías de Usuario

### Registrar Atención Individual

1. Login en la app
2. Tab "Registrar atenciones"
3. Seleccionar Programa, Convenio, Profesional, Institución
4. Buscar paciente por documento (si existe) o crear nuevo
5. Completar datos de la atención
6. Click "Guardar atención"

### Carga Masiva de Atenciones

1. Tab "Registrar atenciones"
2. Expander "Carga masiva"
3. Descargar plantilla Excel/CSV
4. Llenar plantilla con datos
5. Subir archivo
6. Click "Procesar atenciones"

### Crear Respaldo Manual

1. Tab "Respaldo"
2. Click "⬇️ Descargar base (.db)"
3. Guardar en lugar seguro

### Restaurar desde Respaldo

1. Tab "Respaldo"
2. Sección "Restaurar desde respaldo"
3. Cargar archivo .db
4. Click "Restaurar base de datos"

---

## 🔒 Seguridad

### Archivos que NUNCA debes subir a GitHub:

- ❌ `*.db` (base de datos con datos reales)
- ❌ `.env` (credenciales)
- ❌ `credentials.json` (OAuth Google)
- ❌ `token.json` (Token de acceso Google)
- ❌ `respaldos_automaticos/` (respaldos locales)

### Archivos que SÍ debes subir:

- ✅ `app_productividad_Profesionales.py`
- ✅ `backup_system.py`
- ✅ `recovery_tool.py`
- ✅ `generate_schema.py`
- ✅ `requirements.txt`
- ✅ `.env.example`
- ✅ `.gitignore`
- ✅ `README.md`
- ✅ `init_db.sql` (schema vacío, sin datos)

---

## 🐛 Solución de Problemas

### La app no muestra datos / "Sin registros"

```bash
# 1. Verificar que el archivo .db existe
ls -lh productividad_Profesionales.db

# 2. Verificar integridad
python generate_schema.py verificar

# 3. Reconectar desde la app
# Sidebar → Botón "🔄 Reconectar BD"

# 4. Si sigue sin funcionar, restaurar respaldo
python recovery_tool.py
```

### Error "database is locked"

```bash
# Cerrar todas las instancias de la app
# Reiniciar Streamlit
streamlit run app_productividad_Profesionales.py
```

### Respaldos no se crean automáticamente

```bash
# Verificar que backup_system.py está corriendo
# Debe ejecutarse en terminal separada
python backup_system.py

# Verificar logs
cat logs/backup_system.log
```

### Google Drive no funciona

```bash
# Verificar que credentials.json existe
ls -lh credentials.json

# Eliminar token antiguo y reautorizar
rm token.json
python backup_system.py
# Se abrirá navegador para autorizar
```

---

## 📊 Tablas de la Base de Datos

- **programas**: Programas de la organización
- **convenios**: Convenios por programa
- **instituciones**: Instituciones atendidas
- **Profesionales**: Profesionales del sistema
- **pacientes**: Pacientes atendidos
- **registros**: Atenciones registradas
- **viaticos**: Control de viáticos
- **agenda**: Planificación de eventos
- **papeleria**: Solicitudes de papelería

---

## 🤝 Contribuir

1. Fork del repositorio
2. Crear rama: `git checkout -b feature/nueva-funcionalidad`
3. Commit: `git commit -m 'Agregar nueva funcionalidad'`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Pull Request

---

## 📝 Licencia

Este proyecto es de uso interno para FOMAG.

---

## 📞 Soporte

Para problemas o preguntas:
- Crear issue en GitHub
- Contactar al administrador del sistema

---

## 🎯 Roadmap

### Implementado ✅
- [x] Sistema de registro de atenciones
- [x] Dashboard y reportes
- [x] Respaldos automáticos locales
- [x] Respaldos a Google Drive/Dropbox
- [x] Herramienta de recuperación
- [x] Fusión de respaldos
- [x] Puntos de restauración

### Próximamente 🚀
- [ ] API REST
- [ ] App móvil
- [ ] Sincronización multi-dispositivo
- [ ] Notificaciones automáticas
- [ ] Dashboard en tiempo real

---

**Desarrollado con ❤️ para FOMAG**
