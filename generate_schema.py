"""
Generador de schema SQL desde base de datos SQLite existente
Genera init_db.sql para subir a GitHub
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "productividad_Profesionales.db"
OUTPUT_SCHEMA = "init_db.sql"
OUTPUT_SCHEMA_WITH_DATA = "init_db_con_datos.sql"

def generar_schema_sql(incluir_datos: bool = False) -> str:
    """
    Genera SQL schema desde base de datos existente
    
    Args:
        incluir_datos: Si True, incluye INSERTs de datos (usar solo para catálogos)
    
    Returns:
        String con el SQL completo
    """
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Base de datos no encontrada: {DB_PATH}")
        return ""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    sql_lines = []
    
    # Header
    sql_lines.append("-- ============================================")
    sql_lines.append("-- SCHEMA DE BASE DE DATOS - FOMAG Productividad")
    sql_lines.append(f"-- Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sql_lines.append("-- ============================================\n")
    
    # Obtener todas las tablas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tablas = [row[0] for row in cursor.fetchall()]
    
    print(f"📋 Tablas encontradas: {len(tablas)}")
    
    for tabla in tablas:
        print(f"   - {tabla}")
        sql_lines.append(f"\n-- Tabla: {tabla}")
        sql_lines.append("-- " + "="*50)
        
        # Obtener CREATE TABLE statement
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tabla}'")
        create_statement = cursor.fetchone()[0]
        sql_lines.append(create_statement + ";")
        
        # Si se solicita, incluir datos (solo para tablas de catálogo)
        if incluir_datos:
            tablas_catalogo = ["programas", "convenios", "instituciones", "Profesionales"]
            
            if tabla in tablas_catalogo:
                cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
                count = cursor.fetchone()[0]
                
                if count > 0:
                    sql_lines.append(f"\n-- Datos de {tabla} ({count} registros)")
                    
                    # Obtener nombres de columnas
                    cursor.execute(f"PRAGMA table_info({tabla})")
                    columnas = [row[1] for row in cursor.fetchall()]
                    
                    # Obtener datos
                    cursor.execute(f"SELECT * FROM {tabla}")
                    filas = cursor.fetchall()
                    
                    for fila in filas:
                        valores = []
                        for valor in fila:
                            if valor is None:
                                valores.append("NULL")
                            elif isinstance(valor, str):
                                # Escapar comillas simples
                                valor_escapado = valor.replace("'", "''")
                                valores.append(f"'{valor_escapado}'")
                            else:
                                valores.append(str(valor))
                        
                        insert = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join(valores)});"
                        sql_lines.append(insert)
        
        sql_lines.append("")
    
    # Obtener índices
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    indices = cursor.fetchall()
    
    if indices:
        sql_lines.append("\n-- Índices")
        sql_lines.append("-- " + "="*50)
        for idx in indices:
            sql_lines.append(idx[0] + ";")
    
    conn.close()
    
    return "\n".join(sql_lines)

def guardar_schema_completo():
    """Genera ambos archivos: schema vacío y schema con datos de catálogos"""
    
    print("="*60)
    print("🔧 GENERADOR DE SCHEMA SQL")
    print("="*60)
    
    # 1. Schema vacío (para GitHub)
    print("\n📄 Generando schema vacío (sin datos)...")
    schema_vacio = generar_schema_sql(incluir_datos=False)
    
    if schema_vacio:
        with open(OUTPUT_SCHEMA, "w", encoding="utf-8") as f:
            f.write(schema_vacio)
        
        tamaño = os.path.getsize(OUTPUT_SCHEMA) / 1024
        print(f"✅ Generado: {OUTPUT_SCHEMA} ({tamaño:.1f} KB)")
        print(f"   → Este archivo DEBE subirse a GitHub")
    
    # 2. Schema con datos de catálogos (para restauración rápida)
    print("\n📦 Generando schema con datos de catálogos...")
    schema_con_datos = generar_schema_sql(incluir_datos=True)
    
    if schema_con_datos:
        with open(OUTPUT_SCHEMA_WITH_DATA, "w", encoding="utf-8") as f:
            f.write(schema_con_datos)
        
        tamaño = os.path.getsize(OUTPUT_SCHEMA_WITH_DATA) / 1024
        print(f"✅ Generado: {OUTPUT_SCHEMA_WITH_DATA} ({tamaño:.1f} KB)")
        print(f"   → Este archivo es para restauración local (no subir a GitHub)")
    
    print("\n" + "="*60)
    print("✅ GENERACIÓN COMPLETA")
    print("="*60)
    print("\n📋 Siguientes pasos:")
    print("1. Revisar init_db.sql")
    print("2. Subir init_db.sql a GitHub (git add init_db.sql && git commit && git push)")
    print("3. Mantener init_db_con_datos.sql como respaldo local")
    print("4. Agregar a .gitignore: init_db_con_datos.sql, *.db, respaldos_automaticos/")

def crear_db_desde_schema(schema_file: str = OUTPUT_SCHEMA, nueva_db: str = "nueva_db.db"):
    """
    Crea una base de datos desde un archivo schema SQL
    Útil para restaurar estructura en otro ambiente
    """
    try:
        if os.path.exists(nueva_db):
            respuesta = input(f"⚠️ {nueva_db} ya existe. ¿Sobrescribir? (s/n): ")
            if respuesta.lower() != 's':
                print("❌ Operación cancelada")
                return False
            os.remove(nueva_db)
        
        conn = sqlite3.connect(nueva_db)
        cursor = conn.cursor()
        
        with open(schema_file, 'r', encoding='utf-8') as f:
            sql_schema = f.read()
        
        # Ejecutar todas las sentencias SQL
        cursor.executescript(sql_schema)
        conn.commit()
        conn.close()
        
        print(f"✅ Base de datos creada: {nueva_db}")
        return True
        
    except Exception as e:
        print(f"❌ Error creando base de datos: {e}")
        return False

def verificar_integridad():
    """Verifica integridad de la base de datos y cuenta registros"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verificar integridad
        cursor.execute("PRAGMA integrity_check")
        resultado = cursor.fetchone()[0]
        
        print("\n🔍 VERIFICACIÓN DE INTEGRIDAD")
        print("="*60)
        
        if resultado == "ok":
            print("✅ Base de datos íntegra")
        else:
            print(f"⚠️ Problemas detectados: {resultado}")
        
        # Contar registros por tabla
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tablas = [row[0] for row in cursor.fetchall()]
        
        print("\n📊 REGISTROS POR TABLA")
        print("="*60)
        
        total_registros = 0
        for tabla in tablas:
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            count = cursor.fetchone()[0]
            total_registros += count
            print(f"   {tabla}: {count:,} registros".replace(",", "."))
        
        print("="*60)
        print(f"   TOTAL: {total_registros:,} registros".replace(",", "."))
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verificando integridad: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        comando = sys.argv[1]
        
        if comando == "verificar":
            verificar_integridad()
        elif comando == "crear":
            schema_file = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_SCHEMA
            nueva_db = sys.argv[3] if len(sys.argv) > 3 else "nueva_db.db"
            crear_db_desde_schema(schema_file, nueva_db)
        else:
            print("Comandos disponibles:")
            print("  python generate_schema.py              - Generar schemas")
            print("  python generate_schema.py verificar    - Verificar integridad de BD")
            print("  python generate_schema.py crear [schema.sql] [nueva.db]  - Crear BD desde schema")
    else:
        # Modo por defecto: generar ambos schemas
        guardar_schema_completo()
