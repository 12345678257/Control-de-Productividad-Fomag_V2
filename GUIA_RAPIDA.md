# 🚀 GUÍA RÁPIDA - Sistema FOMAG

## ⚠️ RECUPERACIÓN DE DATOS URGENTE (Tu Caso)

Si perdiste datos del 24 de noviembre en adelante, **sigue estos pasos AHORA**:

### Paso 1: Ejecutar script de recuperación automática
```bash
python recuperar_datos_perdidos.py
```

Este script:
1. ✅ Buscará TODOS los respaldos en tu sistema
2. ✅ Identificará el respaldo del 24/11
3. ✅ Identificará el respaldo más reciente
4. ✅ Los fusionará sin duplicar datos
5. ✅ Generará `bd_recuperada.db`

### Paso 2: Verificar la recuperación
```bash
python recovery_tool.py analizar bd_recuperada.db
```

Esto te mostrará:
- 📊 Cantidad de registros total
- 📅 Rango de fechas (debe incluir del 24 en adelante)
- 📋 Datos por tabla

### Paso 3: Restaurar la base recuperada

**Opción A: Desde línea de comandos (Rápido)**
```bash
# Respaldar actual por si acaso
cp productividad_Profesionales.db productividad_Profesionales.db.backup_antes_restaurar

# Restaurar recuperada
cp bd_recuperada.db productividad_Profesionales.db
```

**Opción B: Desde Streamlit (Seguro)**
```bash
streamlit run app_productividad_Profesionales.py
```
Luego:
1. Ir a Tab "Respaldo"
2. Pestaña "Restaurar desde Archivo"
3. Subir `bd_recuperada.db`
4. Confirmar con "RESTAURAR"

---

## 🎯 INSTALACIÓN INICIAL (Primera Vez)

### 1. Instalar dependencias
```bash
pip install streamlit pandas numpy plotly openpyxl python-dotenv schedule
```

O simplemente:
```bash
pip install -r requirements.txt
```

### 2. Ejecutar la aplicación
```bash
streamlit run app_productividad_Profesionales.py
```

### 3. Acceder en el navegador
Se abrirá automáticamente en: `http://localhost:8501`

### 4. Login
- **Usuario**: admin
- **Contraseña**: admin123

---

## 📥 CONFIGURAR RESPALDOS REMOTOS (Opcional pero Recomendado)

### Google Drive (Recomendado)

#### Paso 1: Obtener credenciales
1. Ir a https://console.cloud.google.com/
2. Crear proyecto: "Respaldos-FOMAG"
3. Habilitar Google Drive API
4. Crear credenciales OAuth 2.0
5. Descargar como `credentials.json`
6. Colocar en carpeta del proyecto

#### Paso 2: Configurar
```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar con nano o tu editor favorito
nano .env
```

Agregar:
```bash
GOOGLE_DRIVE_ENABLED=true
```

#### Paso 3: Instalar librerías
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

#### Paso 4: Activar sistema de respaldos
```bash
# En terminal separada
python backup_system.py
```

La primera vez se abrirá un navegador para autorizar. Luego creará automáticamente `token.json`.

### Dropbox

#### Paso 1: Obtener token
1. Ir a https://www.dropbox.com/developers/apps
2. Create app → Scoped access → Full Dropbox
3. Nombrar: "RespaldosFOMAG"
4. En "Permissions": files.content.write, files.content.read
5. En "Settings" → Generate access token

#### Paso 2: Configurar en .env
```bash
DROPBOX_ENABLED=true
DROPBOX_TOKEN=tu_token_muy_largo_aqui
```

#### Paso 3: Instalar librería
```bash
pip install dropbox
```

### Email (Gmail)

#### Paso 1: Contraseña de aplicación
1. Ir a https://myaccount.google.com/security
2. Habilitar verificación en 2 pasos
3. Ir a "Contraseñas de aplicaciones"
4. Crear una para "Respaldos FOMAG"
5. Copiar la contraseña de 16 caracteres

#### Paso 2: Configurar en .env
```bash
EMAIL_ENABLED=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USER=tu_email@gmail.com
EMAIL_PASS=abcd efgh ijkl mnop  # Contraseña de aplicación
EMAIL_DESTINATARIO=respaldo@email.com
```

---

## 🛡️ USO DIARIO DEL SISTEMA DE RESPALDOS

### Desde la UI (Fácil)

1. **Tab "Respaldo"** → Pestaña "Descargar Respaldos"
   - Click "💾 Crear Punto de Restauración Ahora"
   - ✅ Listo, respaldo creado

2. **Ver respaldos disponibles**
   - Tab "Respaldo" → Pestaña "Puntos de Restauración"
   - Verás lista de todos los respaldos
   - Indicadores: 🟢 reciente, 🟡 esta semana, 🔵 antiguo

3. **Restaurar un respaldo**
   - Tab "Respaldo" → Pestaña "Puntos de Restauración"
   - Click "🔄 Restaurar" en el respaldo deseado
   - ✅ Se restaura automáticamente con respaldo de seguridad

### Desde Línea de Comandos (Avanzado)

```bash
# Crear respaldo manual
python -c "from app_productividad_Profesionales import create_automatic_backup; print(create_automatic_backup('manual'))"

# Listar respaldos
python -c "from app_productividad_Profesionales import list_available_backups; import json; print(json.dumps(list_available_backups(), indent=2, default=str))"

# Limpiar respaldos antiguos (mantener últimos 20)
python -c "from app_productividad_Profesionales import cleanup_old_backups; cleanup_old_backups(20)"
```

---

## 🆘 COMANDOS DE EMERGENCIA

### Buscar TODOS los respaldos en el sistema
```bash
python recovery_tool.py buscar
```

### Analizar un respaldo específico
```bash
python recovery_tool.py analizar respaldos_automaticos/backup_20241201_120000.db
```

### Comparar dos respaldos
```bash
python recovery_tool.py comparar backup_viejo.db backup_nuevo.db
```

### Fusionar dos respaldos (sin duplicar)
```bash
python recovery_tool.py fusionar backup_24nov.db backup_reciente.db bd_fusionada.db
```

### Restaurar un respaldo
```bash
python recovery_tool.py restaurar respaldos_automaticos/backup_20241201_120000.db
```

### Modo interactivo (menú)
```bash
python recovery_tool.py
```

---

## 📊 GENERAR SCHEMA PARA GITHUB

### Generar init_db.sql
```bash
python generate_schema.py
```

Esto genera:
- `init_db.sql` - Schema vacío (SUBIR a GitHub)
- `init_db_con_datos.sql` - Con datos de catálogos (NO subir)

### Verificar integridad de BD
```bash
python generate_schema.py verificar
```

### Crear BD desde schema
```bash
python generate_schema.py crear init_db.sql nueva_base.db
```

---

## 🔧 SOLUCIÓN RÁPIDA DE PROBLEMAS

### "No se muestran los datos"
1. Click botón "🔄 Reconectar BD" en sidebar
2. Activar "🔍 Mostrar diagnóstico"
3. Ver cantidad de registros

### "La BD desapareció"
1. Ir a Tab "Respaldo" → "Puntos de Restauración"
2. Restaurar el más reciente
3. O ejecutar: `python recuperar_datos_perdidos.py`

### "Error al iniciar Streamlit"
```bash
# Verificar instalación
pip install -r requirements.txt

# Ejecutar en otro puerto
streamlit run app_productividad_Profesionales.py --server.port 8502
```

### "La base está corrupta"
```bash
# Verificar integridad
sqlite3 productividad_Profesionales.db "PRAGMA integrity_check;"

# Si está corrupta, restaurar respaldo
python recovery_tool.py
# Opción 4: Restaurar un respaldo
```

---

## 📋 CHECKLIST POST-INSTALACIÓN

- [ ] ✅ Instalé dependencias (`pip install -r requirements.txt`)
- [ ] ✅ La app inicia (`streamlit run app_productividad_Profesionales.py`)
- [ ] ✅ Puedo hacer login (admin/admin123)
- [ ] ✅ Creé primer respaldo manual (Tab Respaldo)
- [ ] ✅ Configuré .env para respaldos remotos (opcional)
- [ ] ✅ Probé crear y restaurar un respaldo
- [ ] ✅ Agregué *.db al .gitignore
- [ ] ✅ Generé init_db.sql para GitHub
- [ ] ✅ Cambié contraseñas por defecto
- [ ] ✅ Probé recuperar datos (si aplica)

---

## 📞 AYUDA ADICIONAL

### Ver logs del sistema
```bash
tail -f logs/backup_system.log
```

### Estado de respaldos
```bash
ls -lh respaldos_automaticos/
```

### Tamaño de BD actual
```bash
ls -lh productividad_Profesionales.db
```

### Cantidad de registros actual
```bash
sqlite3 productividad_Profesionales.db "SELECT COUNT(*) FROM registros;"
```

---

## 🎯 FLUJO RECOMENDADO DIARIO

### Al Iniciar el Día
```bash
streamlit run app_productividad_Profesionales.py
```
El sistema creará automáticamente un respaldo si pasó >1 hora.

### Durante el Día
- Trabaja normalmente en la app
- Los respaldos automáticos se gestionan solos

### Al Finalizar el Día
- Tab "Respaldo" → "Crear Punto de Restauración Ahora"
- Descargar ZIP completo una vez por semana

### Una Vez por Semana
- Revisar "Puntos de Restauración"
- Limpiar respaldos antiguos (mantener últimos 30)
- Descargar respaldo completo a ubicación externa

---

**¿Listo para empezar?**

1. Si necesitas recuperar datos: `python recuperar_datos_perdidos.py`
2. Si es primera vez: `streamlit run app_productividad_Profesionales.py`
3. Si tienes dudas: Ver README.md completo

**¡Éxito! 🚀**
