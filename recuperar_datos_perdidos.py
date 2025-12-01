"""
Script de recuperación específica para datos perdidos
Recupera y fusiona datos del 24 de noviembre en adelante
"""

import sqlite3
import os
import shutil
from datetime import datetime
import pandas as pd

def buscar_respaldos_con_datos():
    """Busca todos los respaldos disponibles y muestra sus rangos de fechas"""
    print("="*80)
    print("🔍 BUSCANDO RESPALDOS CON DATOS...")
    print("="*80)
    
    carpetas = [
        "respaldos_automaticos",
        ".",
        "backups"
    ]
    
    respaldos_validos = []
    
    for carpeta in carpetas:
        if not os.path.exists(carpeta):
            continue
        
        for archivo in os.listdir(carpeta):
            if archivo.endswith('.db'):
                ruta = os.path.join(carpeta, archivo)
                
                try:
                    conn = sqlite3.connect(ruta)
                    cursor = conn.cursor()
                    
                    # Verificar que tenga la tabla registros
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros'")
                    if not cursor.fetchone():
                        conn.close()
                        continue
                    
                    # Obtener rango de fechas
                    cursor.execute("SELECT MIN(fecha), MAX(fecha), COUNT(*) FROM registros")
                    min_fecha, max_fecha, count = cursor.fetchone()
                    
                    if count > 0:
                        respaldos_validos.append({
                            'archivo': archivo,
                            'ruta': ruta,
                            'fecha_min': min_fecha,
                            'fecha_max': max_fecha,
                            'registros': count,
                            'modificado': datetime.fromtimestamp(os.path.getmtime(ruta))
                        })
                    
                    conn.close()
                except Exception as e:
                    pass
    
    # Ordenar por fecha de modificación
    respaldos_validos.sort(key=lambda x: x['modificado'], reverse=True)
    
    return respaldos_validos

def analizar_respaldos_disponibles():
    """Muestra todos los respaldos encontrados con sus rangos de fechas"""
    respaldos = buscar_respaldos_con_datos()
    
    if not respaldos:
        print("\n❌ No se encontraron respaldos con datos")
        return []
    
    print(f"\n✅ Se encontraron {len(respaldos)} respaldos con datos:\n")
    
    for i, r in enumerate(respaldos, 1):
        print(f"{i}. 📄 {r['archivo']}")
        print(f"   📅 Rango: {r['fecha_min']} → {r['fecha_max']}")
        print(f"   📊 Registros: {r['registros']:,}".replace(",", "."))
        print(f"   🕐 Modificado: {r['modificado'].strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    
    return respaldos

def identificar_respaldo_del_24():
    """Identifica el respaldo del 24 de noviembre"""
    respaldos = buscar_respaldos_con_datos()
    
    print("\n🔍 Buscando respaldo del 24 de noviembre...\n")
    
    respaldos_24 = []
    for r in respaldos:
        if r['fecha_min'] and '2024-11-24' in r['fecha_min']:
            respaldos_24.append(r)
        elif r['fecha_max'] and '2024-11-24' in r['fecha_max']:
            respaldos_24.append(r)
        elif r['fecha_min'] and r['fecha_max']:
            if r['fecha_min'] <= '2024-11-24' <= r['fecha_max']:
                respaldos_24.append(r)
    
    if respaldos_24:
        print(f"✅ Encontrados {len(respaldos_24)} respaldos que contienen datos del 24/11:\n")
        for i, r in enumerate(respaldos_24, 1):
            print(f"{i}. {r['archivo']}")
            print(f"   Rango: {r['fecha_min']} → {r['fecha_max']}")
            print(f"   Registros: {r['registros']:,}".replace(",", "."))
            print()
        return respaldos_24[0]  # Retornar el más reciente
    else:
        print("❌ No se encontró respaldo específico del 24/11")
        return None

def identificar_respaldo_mas_reciente():
    """Identifica el respaldo más reciente con datos"""
    respaldos = buscar_respaldos_con_datos()
    
    if not respaldos:
        return None
    
    print("\n🔍 Respaldo más reciente encontrado:\n")
    reciente = respaldos[0]
    print(f"📄 {reciente['archivo']}")
    print(f"📅 Rango: {reciente['fecha_min']} → {reciente['fecha_max']}")
    print(f"📊 Registros: {reciente['registros']:,}".replace(",", "."))
    print(f"🕐 Modificado: {reciente['modificado'].strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    return reciente

def fusionar_respaldos_inteligente(respaldo_base, respaldo_adicional, salida="bd_recuperada.db"):
    """
    Fusiona dos respaldos de forma inteligente, combinando todos los registros únicos
    """
    print("\n" + "="*80)
    print("🔀 FUSIÓN INTELIGENTE DE RESPALDOS")
    print("="*80)
    
    print(f"\n📂 Base: {respaldo_base['archivo']}")
    print(f"   Rango: {respaldo_base['fecha_min']} → {respaldo_base['fecha_max']}")
    print(f"   Registros: {respaldo_base['registros']:,}".replace(",", "."))
    
    print(f"\n📂 Adicional: {respaldo_adicional['archivo']}")
    print(f"   Rango: {respaldo_adicional['fecha_min']} → {respaldo_adicional['fecha_max']}")
    print(f"   Registros: {respaldo_adicional['registros']:,}".replace(",", "."))
    
    # Crear copia de la base
    shutil.copy2(respaldo_base['ruta'], salida)
    print(f"\n✅ Base copiada a: {salida}")
    
    # Conectar a ambas
    conn_salida = sqlite3.connect(salida)
    conn_adicional = sqlite3.connect(respaldo_adicional['ruta'])
    
    # Adjuntar base adicional
    conn_salida.execute(f"ATTACH DATABASE '{respaldo_adicional['ruta']}' AS adicional")
    
    # Obtener todas las tablas
    cursor = conn_salida.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tablas = [row[0] for row in cursor.fetchall()]
    
    print(f"\n📋 Fusionando {len(tablas)} tablas...")
    
    estadisticas = {}
    
    for tabla in tablas:
        try:
            # Contar antes
            count_antes = conn_salida.execute(f"SELECT COUNT(*) FROM main.{tabla}").fetchone()[0]
            
            # Estrategia de fusión según tipo de tabla
            if tabla == 'registros':
                # Para registros, insertar solo los que no tengan el mismo ID
                conn_salida.execute(f"""
                    INSERT OR IGNORE INTO main.{tabla}
                    SELECT * FROM adicional.{tabla}
                """)
            elif tabla in ['programas', 'convenios', 'instituciones', 'Profesionales', 'pacientes']:
                # Para catálogos, hacer REPLACE para actualizar
                conn_salida.execute(f"""
                    INSERT OR REPLACE INTO main.{tabla}
                    SELECT * FROM adicional.{tabla}
                """)
            else:
                # Para otras tablas (viaticos, agenda, papeleria)
                conn_salida.execute(f"""
                    INSERT OR IGNORE INTO main.{tabla}
                    SELECT * FROM adicional.{tabla}
                """)
            
            # Contar después
            count_despues = conn_salida.execute(f"SELECT COUNT(*) FROM main.{tabla}").fetchone()[0]
            agregados = count_despues - count_antes
            
            estadisticas[tabla] = {
                'antes': count_antes,
                'despues': count_despues,
                'agregados': agregados
            }
            
            if agregados > 0:
                print(f"   ✅ {tabla}: +{agregados} registros (ahora: {count_despues})")
            else:
                print(f"   ℹ️  {tabla}: sin cambios ({count_despues} registros)")
        
        except Exception as e:
            print(f"   ⚠️ Error en {tabla}: {e}")
    
    conn_salida.commit()
    conn_salida.execute("DETACH DATABASE adicional")
    
    # Verificar resultado
    cursor = conn_salida.execute("SELECT MIN(fecha), MAX(fecha), COUNT(*) FROM registros")
    min_fecha, max_fecha, total = cursor.fetchone()
    
    conn_salida.close()
    conn_adicional.close()
    
    print("\n" + "="*80)
    print("✅ FUSIÓN COMPLETADA")
    print("="*80)
    print(f"\n📄 Archivo generado: {salida}")
    print(f"📅 Rango de fechas: {min_fecha} → {max_fecha}")
    print(f"📊 Total de registros: {total:,}".replace(",", "."))
    
    if 'registros' in estadisticas:
        print(f"\n📈 Registros de atenciones:")
        print(f"   Antes: {estadisticas['registros']['antes']:,}".replace(",", "."))
        print(f"   Después: {estadisticas['registros']['despues']:,}".replace(",", "."))
        print(f"   Recuperados: {estadisticas['registros']['agregados']:,}".replace(",", "."))
    
    return salida

def proceso_recuperacion_completo():
    """
    Proceso completo de recuperación paso a paso
    """
    print("\n" + "="*80)
    print("🆘 PROCESO DE RECUPERACIÓN DE DATOS - FOMAG")
    print("="*80)
    print("\nEste script te ayudará a recuperar los datos perdidos del 24/11 en adelante\n")
    
    # Paso 1: Analizar respaldos disponibles
    print("PASO 1: Analizando respaldos disponibles...")
    respaldos = analizar_respaldos_disponibles()
    
    if not respaldos:
        print("\n❌ No hay respaldos disponibles para recuperar")
        return
    
    # Paso 2: Identificar respaldo del 24
    print("\nPASO 2: Identificando respaldo del 24 de noviembre...")
    respaldo_24 = identificar_respaldo_del_24()
    
    if not respaldo_24:
        print("\n⚠️ No se encontró respaldo específico del 24/11")
        print("Mostrando todos los respaldos disponibles para selección manual:\n")
        
        for i, r in enumerate(respaldos, 1):
            print(f"{i}. {r['archivo']} ({r['fecha_min']} → {r['fecha_max']})")
        
        try:
            sel = int(input("\nSelecciona el número del respaldo BASE (del 24 o anterior): "))
            if 1 <= sel <= len(respaldos):
                respaldo_24 = respaldos[sel - 1]
            else:
                print("❌ Selección inválida")
                return
        except:
            print("❌ Entrada inválida")
            return
    
    # Paso 3: Identificar respaldo más reciente
    print("\nPASO 3: Identificando respaldo más reciente...")
    respaldo_reciente = identificar_respaldo_mas_reciente()
    
    if not respaldo_reciente or respaldo_reciente['archivo'] == respaldo_24['archivo']:
        print("\n⚠️ Solo hay un respaldo disponible o ambos son el mismo")
        respuesta = input("¿Deseas restaurar este respaldo sin fusión? (si/no): ")
        
        if respuesta.lower() == 'si':
            print(f"\nCopiando {respaldo_24['archivo']} como productividad_Profesionales.db...")
            shutil.copy2(respaldo_24['ruta'], 'productividad_Profesionales.db')
            print("✅ Restauración completada")
        return
    
    # Paso 4: Confirmar fusión
    print("\n" + "="*80)
    print("RESUMEN DE FUSIÓN")
    print("="*80)
    print(f"\nSe fusionarán:")
    print(f"  BASE: {respaldo_24['archivo']}")
    print(f"        Fechas: {respaldo_24['fecha_min']} → {respaldo_24['fecha_max']}")
    print(f"        Registros: {respaldo_24['registros']:,}".replace(",", "."))
    print(f"\n  ADICIONAL: {respaldo_reciente['archivo']}")
    print(f"             Fechas: {respaldo_reciente['fecha_min']} → {respaldo_reciente['fecha_max']}")
    print(f"             Registros: {respaldo_reciente['registros']:,}".replace(",", "."))
    
    respuesta = input("\n¿Continuar con la fusión? (si/no): ")
    
    if respuesta.lower() != 'si':
        print("\n❌ Operación cancelada")
        return
    
    # Paso 5: Ejecutar fusión
    print("\nPASO 4: Ejecutando fusión...")
    archivo_fusionado = fusionar_respaldos_inteligente(
        respaldo_24,
        respaldo_reciente,
        salida="bd_recuperada.db"
    )
    
    # Paso 6: Instrucciones finales
    print("\n" + "="*80)
    print("✅ RECUPERACIÓN COMPLETADA")
    print("="*80)
    print(f"\nSe ha generado: {archivo_fusionado}")
    print("\nPasos siguientes:")
    print("1. Revisar el archivo generado con:")
    print(f"   python recovery_tool.py analizar {archivo_fusionado}")
    print("\n2. Si todo está correcto, reemplazar la base actual:")
    print(f"   cp {archivo_fusionado} productividad_Profesionales.db")
    print("\n3. O restaurar desde la UI de Streamlit:")
    print("   - Tab 'Respaldo' → 'Restaurar desde Archivo'")
    print(f"   - Subir el archivo: {archivo_fusionado}")
    
    print("\n⚠️ IMPORTANTE: Se recomienda hacer un respaldo de la BD actual antes de reemplazarla")

if __name__ == "__main__":
    try:
        proceso_recuperacion_completo()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
