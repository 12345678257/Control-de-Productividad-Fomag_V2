"""
Sistema completo de respaldos automáticos
- Respaldos locales con rotación
- Respaldo a Google Drive
- Respaldo a Dropbox
- Respaldo por Email
- Programación automática (diaria/semanal)
"""

import os
import shutil
import sqlite3
import json
import zipfile
import schedule
import threading
import time
import smtplib
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict
import pandas as pd

# ============================================
# CONFIGURACIÓN
# ============================================

DB_PATH = "productividad_Profesionales.db"
BACKUP_DIR = "respaldos_automaticos"
BACKUP_REMOTE_DIR = "respaldos_remotos"

# Configuración para servicios externos (cargar desde variables de entorno o archivo .env)
GOOGLE_DRIVE_ENABLED = os.getenv("GOOGLE_DRIVE_ENABLED", "false").lower() == "true"
DROPBOX_ENABLED = os.getenv("DROPBOX_ENABLED", "false").lower() == "true"
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"

DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN", "")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "")

# Configuración de programación
BACKUP_DIARIO_HORA = os.getenv("BACKUP_DIARIO_HORA", "02:00")
BACKUP_SEMANAL_DIA = os.getenv("BACKUP_SEMANAL_DIA", "monday")  # monday, tuesday, etc.
BACKUP_SEMANAL_HORA = os.getenv("BACKUP_SEMANAL_HORA", "03:00")

# ============================================
# FUNCIONES LOCALES (Base)
# ============================================

def ensure_directories():
    """Crea directorios necesarios"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(BACKUP_REMOTE_DIR, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

def log_message(mensaje: str, tipo: str = "INFO"):
    """Registra mensajes en log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{tipo}] {mensaje}\n"
    
    print(log_entry.strip())
    
    # Guardar en archivo de log
    with open("logs/backup_system.log", "a", encoding="utf-8") as f:
        f.write(log_entry)

def create_local_backup(trigger: str = "manual") -> Optional[str]:
    """
    Crea respaldo local de la base de datos
    
    Args:
        trigger: Tipo de respaldo (manual, auto_startup, scheduled_daily, scheduled_weekly, before_restore, before_reset)
    
    Returns:
        Ruta del archivo de respaldo creado, o None si falla
    """
    try:
        ensure_directories()
        
        if not os.path.exists(DB_PATH):
            log_message(f"Base de datos no encontrada: {DB_PATH}", "ERROR")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{trigger}_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Copiar archivo
        shutil.copy2(DB_PATH, backup_path)
        
        tamaño_kb = os.path.getsize(backup_path) / 1024
        log_message(f"✅ Respaldo local creado: {backup_filename} ({tamaño_kb:.1f} KB)", "SUCCESS")
        
        return backup_path
        
    except Exception as e:
        log_message(f"Error creando respaldo local: {e}", "ERROR")
        return None

def cleanup_old_backups(keep_last_n: int = 30):
    """Elimina respaldos antiguos, manteniendo los últimos N"""
    try:
        if not os.path.exists(BACKUP_DIR):
            return
        
        archivos = [
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if f.endswith(".db")
        ]
        
        # Ordenar por fecha de modificación (más reciente primero)
        archivos.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Eliminar los que excedan el límite
        eliminados = 0
        for archivo in archivos[keep_last_n:]:
            os.remove(archivo)
            eliminados += 1
        
        if eliminados > 0:
            log_message(f"🗑️ Limpieza: eliminados {eliminados} respaldos antiguos", "INFO")
            
    except Exception as e:
        log_message(f"Error en limpieza: {e}", "ERROR")

def export_to_json(backup_path: str) -> Optional[str]:
    """Exporta datos de un respaldo a JSON"""
    try:
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        # Obtener lista de tablas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tablas = [row[0] for row in cursor.fetchall()]
        
        datos = {}
        for tabla in tablas:
            df = pd.read_sql_query(f"SELECT * FROM {tabla}", conn)
            datos[tabla] = df.to_dict(orient="records")
        
        conn.close()
        
        # Guardar JSON
        json_path = backup_path.replace(".db", ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2, default=str)
        
        log_message(f"📄 JSON exportado: {os.path.basename(json_path)}", "INFO")
        return json_path
        
    except Exception as e:
        log_message(f"Error exportando JSON: {e}", "ERROR")
        return None

# ============================================
# RESPALDO A GOOGLE DRIVE
# ============================================

def backup_to_google_drive(backup_path: str) -> bool:
    """
    Sube respaldo a Google Drive
    
    Requiere configuración previa:
    1. pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
    2. Crear credenciales en Google Cloud Console
    3. Generar token.json
    """
    if not GOOGLE_DRIVE_ENABLED:
        return False
    
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    log_message("❌ No se encontró credentials.json para Google Drive", "ERROR")
                    return False
                    
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        service = build('drive', 'v3', credentials=creds)
        
        # Buscar o crear carpeta "RespaldosFOMAG"
        folder_name = "RespaldosFOMAG"
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        folders = results.get('files', [])
        
        if folders:
            folder_id = folders[0]['id']
        else:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
        
        # Subir archivo
        file_metadata = {
            'name': os.path.basename(backup_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(backup_path, mimetype='application/x-sqlite3')
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        log_message(f"☁️ Respaldo subido a Google Drive: {file.get('id')}", "SUCCESS")
        return True
        
    except ImportError:
        log_message("❌ Librerías de Google Drive no instaladas. Ejecuta: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client", "ERROR")
        return False
    except Exception as e:
        log_message(f"❌ Error subiendo a Google Drive: {e}", "ERROR")
        return False

# ============================================
# RESPALDO A DROPBOX
# ============================================

def backup_to_dropbox(backup_path: str) -> bool:
    """
    Sube respaldo a Dropbox
    
    Requiere:
    1. pip install dropbox
    2. Token de acceso en variable DROPBOX_TOKEN
    """
    if not DROPBOX_ENABLED or not DROPBOX_TOKEN:
        return False
    
    try:
        import dropbox
        
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        
        # Verificar conexión
        dbx.users_get_current_account()
        
        # Subir archivo
        with open(backup_path, 'rb') as f:
            dropbox_path = f'/RespaldosFOMAG/{os.path.basename(backup_path)}'
            dbx.files_upload(
                f.read(),
                dropbox_path,
                mode=dropbox.files.WriteMode.overwrite
            )
        
        log_message(f"📦 Respaldo subido a Dropbox: {dropbox_path}", "SUCCESS")
        return True
        
    except ImportError:
        log_message("❌ Librería dropbox no instalada. Ejecuta: pip install dropbox", "ERROR")
        return False
    except Exception as e:
        log_message(f"❌ Error subiendo a Dropbox: {e}", "ERROR")
        return False

# ============================================
# RESPALDO POR EMAIL
# ============================================

def backup_by_email(backup_path: str) -> bool:
    """Envía respaldo por email"""
    if not EMAIL_ENABLED or not EMAIL_USER or not EMAIL_PASS or not EMAIL_DESTINATARIO:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_DESTINATARIO
        msg['Subject'] = f'Respaldo automático BD FOMAG - {datetime.now().strftime("%Y-%m-%d %H:%M")}'
        
        # Adjuntar archivo
        with open(backup_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(backup_path)}')
            msg.attach(part)
        
        # Enviar
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        
        log_message(f"📧 Respaldo enviado por email a {EMAIL_DESTINATARIO}", "SUCCESS")
        return True
        
    except Exception as e:
        log_message(f"❌ Error enviando email: {e}", "ERROR")
        return False

# ============================================
# PROCESO COMPLETO DE RESPALDO
# ============================================

def realizar_respaldo_completo(trigger: str = "manual") -> Dict[str, bool]:
    """
    Realiza respaldo completo en todos los servicios configurados
    
    Returns:
        Diccionario con resultados {servicio: éxito}
    """
    log_message(f"🚀 Iniciando respaldo completo [{trigger}]...", "INFO")
    
    resultados = {
        "local": False,
        "google_drive": False,
        "dropbox": False,
        "email": False,
    }
    
    # 1. Respaldo local
    backup_path = create_local_backup(trigger)
    if not backup_path:
        log_message("❌ Fallo respaldo local. Proceso abortado.", "ERROR")
        return resultados
    
    resultados["local"] = True
    
    # 2. Exportar a JSON (opcional pero útil)
    export_to_json(backup_path)
    
    # 3. Respaldos remotos
    if GOOGLE_DRIVE_ENABLED:
        resultados["google_drive"] = backup_to_google_drive(backup_path)
    
    if DROPBOX_ENABLED:
        resultados["dropbox"] = backup_to_dropbox(backup_path)
    
    if EMAIL_ENABLED:
        resultados["email"] = backup_by_email(backup_path)
    
    # 4. Limpieza de respaldos antiguos
    cleanup_old_backups(keep_last_n=30)
    
    # Resumen
    exitosos = sum(1 for v in resultados.values() if v)
    log_message(f"✅ Respaldo completo finalizado. Exitosos: {exitosos}/{len(resultados)}", "SUCCESS")
    
    return resultados

# ============================================
# PROGRAMACIÓN DE RESPALDOS
# ============================================

def job_respaldo_diario():
    """Tarea de respaldo diario"""
    log_message("⏰ Ejecutando respaldo diario programado", "INFO")
    realizar_respaldo_completo(trigger="scheduled_daily")

def job_respaldo_semanal():
    """Tarea de respaldo semanal"""
    log_message("📅 Ejecutando respaldo semanal programado", "INFO")
    realizar_respaldo_completo(trigger="scheduled_weekly")

def iniciar_scheduler():
    """Inicia el scheduler de respaldos programados"""
    log_message(f"🕐 Configurando respaldos programados:", "INFO")
    log_message(f"   - Diario: {BACKUP_DIARIO_HORA}", "INFO")
    log_message(f"   - Semanal: {BACKUP_SEMANAL_DIA.capitalize()} a las {BACKUP_SEMANAL_HORA}", "INFO")
    
    # Programar respaldo diario
    schedule.every().day.at(BACKUP_DIARIO_HORA).do(job_respaldo_diario)
    
    # Programar respaldo semanal
    dia_func = getattr(schedule.every(), BACKUP_SEMANAL_DIA.lower())
    dia_func.at(BACKUP_SEMANAL_HORA).do(job_respaldo_semanal)
    
    def run_pending():
        while True:
            schedule.run_pending()
            time.sleep(60)  # Revisar cada minuto
    
    # Ejecutar en thread separado
    thread = threading.Thread(target=run_pending, daemon=True)
    thread.start()
    
    log_message("✅ Scheduler de respaldos iniciado", "SUCCESS")

# ============================================
# FUNCIONES DE UTILIDAD
# ============================================

def listar_respaldos_locales() -> pd.DataFrame:
    """Lista todos los respaldos locales disponibles"""
    try:
        if not os.path.exists(BACKUP_DIR):
            return pd.DataFrame()
        
        archivos = []
        for f in os.listdir(BACKUP_DIR):
            if f.endswith(".db"):
                ruta = os.path.join(BACKUP_DIR, f)
                stat = os.stat(ruta)
                archivos.append({
                    "archivo": f,
                    "ruta_completa": ruta,
                    "tamaño_kb": round(stat.st_size / 1024, 2),
                    "fecha_modificacion": datetime.fromtimestamp(stat.st_mtime),
                })
        
        if not archivos:
            return pd.DataFrame()
        
        df = pd.DataFrame(archivos)
        df = df.sort_values("fecha_modificacion", ascending=False)
        return df
        
    except Exception as e:
        log_message(f"Error listando respaldos: {e}", "ERROR")
        return pd.DataFrame()

def restaurar_desde_respaldo(backup_path: str) -> bool:
    """Restaura la base de datos desde un respaldo"""
    try:
        if not os.path.exists(backup_path):
            log_message(f"Respaldo no encontrado: {backup_path}", "ERROR")
            return False
        
        # Crear respaldo de seguridad antes de restaurar
        if os.path.exists(DB_PATH):
            create_local_backup(trigger="before_restore")
        
        # Restaurar
        shutil.copy2(backup_path, DB_PATH)
        
        log_message(f"✅ Base de datos restaurada desde: {os.path.basename(backup_path)}", "SUCCESS")
        return True
        
    except Exception as e:
        log_message(f"Error restaurando: {e}", "ERROR")
        return False

# ============================================
# INICIALIZACIÓN
# ============================================

def inicializar_sistema_respaldos():
    """Inicializa el sistema completo de respaldos"""
    ensure_directories()
    log_message("="*60, "INFO")
    log_message("🛡️ SISTEMA DE RESPALDOS AUTOMÁTICOS INICIADO", "INFO")
    log_message("="*60, "INFO")
    
    # Respaldo inicial al arrancar
    log_message("Creando respaldo inicial...", "INFO")
    realizar_respaldo_completo(trigger="auto_startup")
    
    # Iniciar scheduler
    iniciar_scheduler()
    
    log_message("✅ Sistema de respaldos completamente operativo", "SUCCESS")
    log_message("="*60, "INFO")

# ============================================
# MAIN (para pruebas)
# ============================================

if __name__ == "__main__":
    inicializar_sistema_respaldos()
    
    # Mantener el script corriendo
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_message("Sistema de respaldos detenido por usuario", "INFO")
