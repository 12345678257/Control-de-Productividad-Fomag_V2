"""
Herramienta de recuperación de emergencia
Busca todos los respaldos disponibles y ayuda a recuperar datos
"""

import os
import glob
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
import pandas as pd

DB_PATH = "productividad_Profesionales.db"
BACKUP_DIR = "respaldos_automaticos"

def buscar_todos_los_respaldos():
    """Busca TODOS los posibles respaldos en el sistema"""
    print("="*70)
    print("🔍 BUSCANDO RESPALDOS EN TODO EL SISTEMA...")
    print("="*70)
    
    # Ubicaciones donde buscar
    ubicaciones = [
        ".",  # Directorio actual
        "./respaldos_automaticos",
        "./backups",
        "./respaldos",
        os.path.expanduser("~"),  # Home del usuario
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Desktop"),
    ]
    
    # Si está en Windows, agregar temp
    if os.name == 'nt':
        ubicaciones.extend([
            os.path.expanduser("~/AppData/Local/Temp"),
            "C:/Temp",
        ])
    else:
        ubicaciones.append("/tmp")
    
    # Patrones de archivo a buscar
    patrones = [
        "*.db",
        "backup*.db",
        "*productividad*.db",
        "*Profesionales*.db",
        "*FOMAG*.db",
    ]
    
    encontrados = []
    
    for ubicacion in ubicaciones:
        if not os.path.exists(ubicacion):
            continue
        
        print(f"\n📂 Buscando en: {ubicacion}")
        
        for patron in patrones:
            try:
                # Buscar recursivamente
                ruta_patron = os.path.join(ubicacion, "**", patron)
                archivos = glob.glob(ruta_patron, recursive=True)
                
                for archivo in archivos:
                    if archivo in [e["ruta"] for e in encontrados]:
                        continue  # Evitar duplicados
                    
                    try:
                        stat = os.stat(archivo)
                        tamaño_kb = stat.st_size / 1024
                        
                        # Intentar verificar que es SQLite válido
                        es_valido = False
                        num_registros = 0
                        try:
                            conn = sqlite3.connect(archivo)
                            cursor = conn.cursor()
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                            tablas = cursor.fetchall()
                            
                            if tablas:
                                es_valido = True
                                # Contar registros en tabla 'registros' si existe
                                if any('registros' in t[0].lower() for t in tablas):
                                    cursor.execute("SELECT COUNT(*) FROM registros")
                                    num_registros = cursor.fetchone()[0]
                            
                            conn.close()
                        except:
                            pass
                        
                        if es_valido:
                            encontrados.append({
                                "ruta": archivo,
                                "tamaño_kb": round(tamaño_kb, 2),
                                "modificado": datetime.fromtimestamp(stat.st_mtime),
                                "creado": datetime.fromtimestamp(stat.st_ctime),
                                "registros": num_registros,
                            })
                            print(f"   ✅ Encontrado: {os.path.basename(archivo)} ({tamaño_kb:.1f} KB, {num_registros} registros)")
                    
                    except Exception as e:
                        pass
            
            except Exception as e:
                pass
    
    return encontrados

def analizar_respaldo(ruta_respaldo: str):
    """Analiza el contenido de un respaldo"""
    try:
        print("\n" + "="*70)
        print(f"📊 ANÁLISIS DE RESPALDO: {os.path.basename(ruta_respaldo)}")
        print("="*70)
        
        conn = sqlite3.connect(ruta_respaldo)
        cursor = conn.cursor()
        
        # Información del archivo
        stat = os.stat(ruta_respaldo)
        print(f"\n📁 Información del archivo:")
        print(f"   Ruta: {ruta_respaldo}")
        print(f"   Tamaño: {stat.st_size / 1024:.2f} KB")
        print(f"   Modificado: {datetime.fromtimestamp(stat.st_mtime)}")
        print(f"   Creado: {datetime.fromtimestamp(stat.st_ctime)}")
        
        # Listar tablas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tablas = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📋 Tablas encontradas: {len(tablas)}")
        
        total_registros = 0
        for tabla in sorted(tablas):
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            count = cursor.fetchone()[0]
            total_registros += count
            print(f"   - {tabla}: {count:,} registros".replace(",", "."))
        
        print(f"\n📊 Total de registros: {total_registros:,}".replace(",", "."))
        
        # Si hay tabla de registros, mostrar rango de fechas
        if "registros" in tablas:
            cursor.execute("SELECT MIN(fecha), MAX(fecha), COUNT(*) FROM registros")
            min_fecha, max_fecha, count = cursor.fetchone()
            
            if min_fecha and max_fecha:
                print(f"\n📅 Rango de fechas en 'registros':")
                print(f"   Desde: {min_fecha}")
                print(f"   Hasta: {max_fecha}")
                print(f"   Total atenciones: {count:,}".replace(",", "."))
        
        # Verificar integridad
        cursor.execute("PRAGMA integrity_check")
        integridad = cursor.fetchone()[0]
        
        print(f"\n🔒 Integridad:")
        if integridad == "ok":
            print("   ✅ Base de datos íntegra")
        else:
            print(f"   ⚠️ Problemas: {integridad}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error analizando respaldo: {e}")

def comparar_respaldos(ruta1: str, ruta2: str):
    """Compara dos respaldos para ver diferencias"""
    try:
        print("\n" + "="*70)
        print("🔄 COMPARACIÓN DE RESPALDOS")
        print("="*70)
        
        conn1 = sqlite3.connect(ruta1)
        conn2 = sqlite3.connect(ruta2)
        
        print(f"\nRespaldo 1: {os.path.basename(ruta1)}")
        print(f"Respaldo 2: {os.path.basename(ruta2)}")
        
        # Comparar tabla registros
        df1 = pd.read_sql_query("SELECT * FROM registros", conn1)
        df2 = pd.read_sql_query("SELECT * FROM registros", conn2)
        
        print(f"\n📊 Comparación de 'registros':")
        print(f"   Respaldo 1: {len(df1):,} registros".replace(",", "."))
        print(f"   Respaldo 2: {len(df2):,} registros".replace(",", "."))
        print(f"   Diferencia: {abs(len(df1) - len(df2)):,} registros".replace(",", "."))
        
        if len(df1) > 0 and len(df2) > 0:
            # Comparar fechas
            min1, max1 = df1['fecha'].min(), df1['fecha'].max()
            min2, max2 = df2['fecha'].min(), df2['fecha'].max()
            
            print(f"\n📅 Rango de fechas:")
            print(f"   Respaldo 1: {min1} a {max1}")
            print(f"   Respaldo 2: {min2} a {max2}")
        
        conn1.close()
        conn2.close()
        
    except Exception as e:
        print(f"❌ Error comparando: {e}")

def restaurar_respaldo(ruta_origen: str, crear_backup: bool = True):
    """Restaura un respaldo específico"""
    try:
        print("\n" + "="*70)
        print("🔄 RESTAURACIÓN DE RESPALDO")
        print("="*70)
        
        if not os.path.exists(ruta_origen):
            print(f"❌ Respaldo no encontrado: {ruta_origen}")
            return False
        
        # Analizar el respaldo primero
        analizar_respaldo(ruta_origen)
        
        # Confirmar
        print("\n⚠️  ADVERTENCIA: Esta operación sobrescribirá la base de datos actual")
        respuesta = input("¿Deseas continuar? (escribe 'SI' para confirmar): ")
        
        if respuesta != "SI":
            print("❌ Operación cancelada")
            return False
        
        # Crear respaldo de seguridad
        if crear_backup and os.path.exists(DB_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs(BACKUP_DIR, exist_ok=True)
            backup_path = os.path.join(BACKUP_DIR, f"backup_before_recovery_{timestamp}.db")
            shutil.copy2(DB_PATH, backup_path)
            print(f"\n💾 Respaldo de seguridad creado: {backup_path}")
        
        # Restaurar
        shutil.copy2(ruta_origen, DB_PATH)
        
        print(f"\n✅ Base de datos restaurada desde: {os.path.basename(ruta_origen)}")
        
        # Verificar resultado
        analizar_respaldo(DB_PATH)
        
        return True
        
    except Exception as e:
        print(f"❌ Error en restauración: {e}")
        return False

def fusionar_respaldos(ruta_base: str, ruta_adicional: str, ruta_salida: str = "bd_fusionada.db"):
    """
    Fusiona dos respaldos, combinando los registros
    Útil para recuperar datos perdidos entre dos respaldos
    """
    try:
        print("\n" + "="*70)
        print("🔀 FUSIÓN DE RESPALDOS")
        print("="*70)
        
        if not os.path.exists(ruta_base):
            print(f"❌ Respaldo base no encontrado: {ruta_base}")
            return False
        
        if not os.path.exists(ruta_adicional):
            print(f"❌ Respaldo adicional no encontrado: {ruta_adicional}")
            return False
        
        print(f"\n📂 Respaldo base: {os.path.basename(ruta_base)}")
        print(f"📂 Respaldo adicional: {os.path.basename(ruta_adicional)}")
        print(f"📂 Salida: {ruta_salida}")
        
        # Copiar base como punto de partida
        shutil.copy2(ruta_base, ruta_salida)
        print(f"\n✅ Copia base creada")
        
        # Conectar a ambos
        conn_salida = sqlite3.connect(ruta_salida)
        conn_adicional = sqlite3.connect(ruta_adicional)
        
        # Tablas a fusionar
        tablas_fusionar = ["registros", "viaticos", "agenda", "papeleria"]
        
        for tabla in tablas_fusionar:
            try:
                print(f"\n🔄 Fusionando tabla: {tabla}")
                
                # Obtener máximo ID en salida
                cursor = conn_salida.execute(f"SELECT MAX(id) FROM {tabla}")
                max_id = cursor.fetchone()[0] or 0
                print(f"   ID máximo actual: {max_id}")
                
                # Leer datos adicionales
                df_adicional = pd.read_sql_query(f"SELECT * FROM {tabla}", conn_adicional)
                print(f"   Registros en adicional: {len(df_adicional)}")
                
                if len(df_adicional) == 0:
                    print(f"   ⚠️ No hay datos para fusionar")
                    continue
                
                # Filtrar registros que no existen en base
                # (simplificado: asumimos que registros con ID mayor son nuevos)
                df_nuevos = df_adicional[df_adicional['id'] > max_id]
                
                if len(df_nuevos) == 0:
                    print(f"   ℹ️ No hay registros nuevos para agregar")
                    continue
                
                print(f"   ➕ Agregando {len(df_nuevos)} registros nuevos")
                
                # Insertar en base de salida
                df_nuevos.to_sql(tabla, conn_salida, if_exists='append', index=False)
                
                print(f"   ✅ Fusión completada para {tabla}")
                
            except Exception as e:
                print(f"   ⚠️ Error en {tabla}: {e}")
        
        conn_salida.commit()
        conn_salida.close()
        conn_adicional.close()
        
        print(f"\n✅ FUSIÓN COMPLETADA")
        print(f"📊 Analizando resultado final...")
        analizar_respaldo(ruta_salida)
        
        return True
        
    except Exception as e:
        print(f"❌ Error fusionando respaldos: {e}")
        return False

def menu_principal():
    """Menú interactivo de recuperación"""
    while True:
        print("\n" + "="*70)
        print("🛠️  HERRAMIENTA DE RECUPERACIÓN - FOMAG")
        print("="*70)
        print("\n1. 🔍 Buscar todos los respaldos disponibles")
        print("2. 📊 Analizar un respaldo específico")
        print("3. 🔄 Comparar dos respaldos")
        print("4. 💾 Restaurar desde un respaldo")
        print("5. 🔀 Fusionar dos respaldos")
        print("6. 🚪 Salir")
        
        opcion = input("\n👉 Selecciona una opción (1-6): ").strip()
        
        if opcion == "1":
            respaldos = buscar_todos_los_respaldos()
            
            if not respaldos:
                print("\n❌ No se encontraron respaldos")
            else:
                print(f"\n✅ Se encontraron {len(respaldos)} respaldos")
                print("\nRespaldos ordenados por fecha (más reciente primero):")
                for i, r in enumerate(respaldos, 1):
                    print(f"\n{i}. {os.path.basename(r['ruta'])}")
                    print(f"   Ruta: {r['ruta']}")
                    print(f"   Tamaño: {r['tamaño_kb']:.1f} KB")
                    print(f"   Modificado: {r['modificado']}")
                    print(f"   Registros: {r['registros']:,}".replace(",", "."))
        
        elif opcion == "2":
            ruta = input("\n👉 Ruta del respaldo a analizar: ").strip()
            if os.path.exists(ruta):
                analizar_respaldo(ruta)
            else:
                print(f"❌ No se encontró el archivo: {ruta}")
        
        elif opcion == "3":
            ruta1 = input("\n👉 Ruta del primer respaldo: ").strip()
            ruta2 = input("👉 Ruta del segundo respaldo: ").strip()
            
            if os.path.exists(ruta1) and os.path.exists(ruta2):
                comparar_respaldos(ruta1, ruta2)
            else:
                print("❌ Una o ambas rutas no son válidas")
        
        elif opcion == "4":
            ruta = input("\n👉 Ruta del respaldo a restaurar: ").strip()
            if os.path.exists(ruta):
                restaurar_respaldo(ruta)
            else:
                print(f"❌ No se encontró el archivo: {ruta}")
        
        elif opcion == "5":
            print("\n🔀 FUSIÓN DE RESPALDOS")
            print("Esto combina registros de dos respaldos diferentes")
            print("Útil para recuperar datos perdidos entre dos puntos en el tiempo\n")
            
            ruta_base = input("👉 Respaldo BASE (más antiguo): ").strip()
            ruta_adicional = input("👉 Respaldo ADICIONAL (más reciente): ").strip()
            ruta_salida = input("👉 Nombre archivo salida [bd_fusionada.db]: ").strip() or "bd_fusionada.db"
            
            if os.path.exists(ruta_base) and os.path.exists(ruta_adicional):
                fusionar_respaldos(ruta_base, ruta_adicional, ruta_salida)
            else:
                print("❌ Una o ambas rutas no son válidas")
        
        elif opcion == "6":
            print("\n👋 ¡Hasta pronto!")
            break
        
        else:
            print("\n❌ Opción inválida")
        
        input("\n[Presiona ENTER para continuar]")

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║        HERRAMIENTA DE RECUPERACIÓN - SISTEMA FOMAG          ║
    ║                                                              ║
    ║  Esta herramienta te ayudará a:                            ║
    ║  • Buscar respaldos perdidos en tu sistema                 ║
    ║  • Analizar el contenido de respaldos                      ║
    ║  • Comparar diferentes versiones                            ║
    ║  • Restaurar bases de datos                                 ║
    ║  • Fusionar datos de múltiples respaldos                    ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    menu_principal()
