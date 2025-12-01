#!/usr/bin/env python3
"""
Script de instalación y configuración automática
Sistema de Productividad FOMAG con Respaldos Automáticos
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def print_header(texto):
    """Imprime un encabezado con estilo"""
    print("\n" + "="*80)
    print(f"  {texto}")
    print("="*80 + "\n")

def print_step(numero, texto):
    """Imprime un paso numerado"""
    print(f"\n{'='*5} PASO {numero}: {texto} {'='*5}")

def check_python_version():
    """Verifica la versión de Python"""
    print_step(1, "Verificando versión de Python")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Se requiere Python 3.8 o superior")
        print(f"   Tienes: Python {version.major}.{version.minor}.{version.micro}")
        return False
    
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} detectado")
    return True

def install_dependencies():
    """Instala las dependencias necesarias"""
    print_step(2, "Instalando dependencias")
    
    if not os.path.exists("requirements.txt"):
        print("⚠️ requirements.txt no encontrado, creando...")
        
        requirements = """streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.17.0
openpyxl>=3.1.0
python-dateutil>=2.8.2
pytz>=2023.3
chardet>=5.2.0
python-dotenv>=1.0.0
schedule>=1.2.0"""
        
        with open("requirements.txt", "w") as f:
            f.write(requirements)
    
    try:
        print("📦 Instalando paquetes de Python...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"])
        print("✅ Dependencias instaladas correctamente")
        return True
    except subprocess.CalledProcessError:
        print("❌ Error instalando dependencias")
        print("   Intenta manualmente: pip install -r requirements.txt")
        return False

def create_directories():
    """Crea las carpetas necesarias"""
    print_step(3, "Creando estructura de carpetas")
    
    directories = [
        "respaldos_automaticos",
        "respaldos_remotos",
        "logs"
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✅ Creada carpeta: {directory}/")
        else:
            print(f"ℹ️  Ya existe: {directory}/")
    
    return True

def setup_env_file():
    """Configura el archivo .env"""
    print_step(4, "Configurando archivo de entorno (.env)")
    
    if os.path.exists(".env"):
        print("ℹ️  .env ya existe")
        respuesta = input("   ¿Sobrescribir? (s/n): ")
        if respuesta.lower() != 's':
            print("   Manteniendo .env existente")
            return True
    
    if os.path.exists(".env.example"):
        shutil.copy(".env.example", ".env")
        print("✅ .env creado desde .env.example")
    else:
        print("⚠️ .env.example no encontrado, creando .env básico...")
        
        env_content = """# Configuración básica
GOOGLE_DRIVE_ENABLED=false
DROPBOX_ENABLED=false
EMAIL_ENABLED=false

# Programación de respaldos
BACKUP_DIARIO_HORA=02:00
BACKUP_SEMANAL_DIA=monday
BACKUP_SEMANAL_HORA=03:00
KEEP_LOCAL_BACKUPS=30
"""
        
        with open(".env", "w") as f:
            f.write(env_content)
        
        print("✅ .env creado con configuración básica")
    
    print("\n💡 Para habilitar respaldos remotos, edita .env con tus credenciales")
    return True

def check_database():
    """Verifica si existe la base de datos"""
    print_step(5, "Verificando base de datos")
    
    if os.path.exists("productividad_Profesionales.db"):
        size = os.path.getsize("productividad_Profesionales.db") / 1024
        print(f"✅ Base de datos encontrada ({size:.2f} KB)")
        
        try:
            import sqlite3
            conn = sqlite3.connect("productividad_Profesionales.db")
            cursor = conn.execute("SELECT COUNT(*) FROM registros")
            count = cursor.fetchone()[0]
            conn.close()
            print(f"   📊 Registros actuales: {count:,}".replace(",", "."))
        except:
            print("   ⚠️ No se pudo leer la BD (puede ser normal si es nueva)")
    else:
        print("ℹ️  Base de datos no encontrada (se creará al iniciar la app)")
    
    return True

def create_gitignore():
    """Crea o actualiza .gitignore"""
    print_step(6, "Configurando .gitignore")
    
    gitignore_content = """# Base de datos
*.db
*.db-journal
productividad_Profesionales.db*

# Respaldos
respaldos_automaticos/
respaldos_remotos/
backups/

# Configuración con credenciales
.env
token.json
credentials.json

# Logs
logs/
*.log

# Python
__pycache__/
*.py[cod]
venv/
"""
    
    if os.path.exists(".gitignore"):
        print("ℹ️  .gitignore ya existe")
    else:
        with open(".gitignore", "w") as f:
            f.write(gitignore_content)
        print("✅ .gitignore creado")
    
    return True

def generate_schema():
    """Genera el schema SQL"""
    print_step(7, "Generando schema SQL")
    
    if not os.path.exists("generate_schema.py"):
        print("⚠️ generate_schema.py no encontrado, saltando...")
        return True
    
    if not os.path.exists("productividad_Profesionales.db"):
        print("ℹ️  BD no existe aún, se generará el schema al crearla")
        return True
    
    try:
        subprocess.check_call([sys.executable, "generate_schema.py"])
        print("✅ Schema SQL generado (init_db.sql)")
    except:
        print("⚠️ No se pudo generar schema (no crítico)")
    
    return True

def test_import():
    """Prueba importar los módulos principales"""
    print_step(8, "Verificando módulos")
    
    try:
        import streamlit
        print("✅ Streamlit importado correctamente")
    except ImportError:
        print("❌ Error importando Streamlit")
        return False
    
    try:
        import pandas
        import numpy
        import plotly
        print("✅ Librerías científicas OK")
    except ImportError:
        print("❌ Error importando librerías científicas")
        return False
    
    return True

def show_next_steps():
    """Muestra los siguientes pasos"""
    print_header("✅ INSTALACIÓN COMPLETADA")
    
    print("🎯 SIGUIENTES PASOS:\n")
    
    print("1️⃣  EJECUTAR LA APLICACIÓN:")
    print("   streamlit run app_productividad_Profesionales.py\n")
    
    print("2️⃣  ACCEDER EN EL NAVEGADOR:")
    print("   http://localhost:8501\n")
    
    print("3️⃣  LOGIN:")
    print("   Usuario: admin")
    print("   Contraseña: admin123\n")
    
    print("4️⃣  SI NECESITAS RECUPERAR DATOS:")
    print("   python recuperar_datos_perdidos.py\n")
    
    print("5️⃣  CONFIGURAR RESPALDOS REMOTOS (OPCIONAL):")
    print("   - Editar .env con tus credenciales")
    print("   - Ver GUIA_RAPIDA.md para instrucciones\n")
    
    print("📚 DOCUMENTACIÓN:")
    print("   - GUIA_RAPIDA.md - Inicio rápido")
    print("   - README.md - Documentación completa\n")
    
    print("="*80)
    print("¡Listo para comenzar! 🚀")
    print("="*80 + "\n")

def main():
    """Función principal de setup"""
    print_header("🛡️ INSTALADOR AUTOMÁTICO - SISTEMA FOMAG")
    
    print("Este script configurará todo lo necesario para usar el sistema.")
    print("Presiona Ctrl+C en cualquier momento para cancelar.\n")
    
    respuesta = input("¿Continuar con la instalación? (s/n): ")
    if respuesta.lower() != 's':
        print("\n❌ Instalación cancelada")
        return
    
    # Ejecutar pasos
    pasos = [
        ("Versión de Python", check_python_version),
        ("Dependencias", install_dependencies),
        ("Carpetas", create_directories),
        ("Archivo .env", setup_env_file),
        ("Base de datos", check_database),
        (".gitignore", create_gitignore),
        ("Schema SQL", generate_schema),
        ("Módulos", test_import),
    ]
    
    for nombre, funcion in pasos:
        if not funcion():
            print(f"\n❌ Error en paso: {nombre}")
            print("La instalación no se completó correctamente")
            return
    
    # Mostrar siguiente pasos
    show_next_steps()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Instalación cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ Error durante la instalación: {e}")
        import traceback
        traceback.print_exc()
