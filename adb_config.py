"""
Configuración de ruta de ADB
"""
import os

# CONFIGURA AQUÍ LA RUTA DE TU ADB
# Usando ADB versión 36.0.2 (compatible con Android 16)
ADB_PATH = r"C:\android-sdk-platform-tools-adb-36-02\platform-tools\adb.exe"

# Verificar si el archivo existe
if not os.path.exists(ADB_PATH):
    print(f"⚠️ ADVERTENCIA: ADB no encontrado en: {ADB_PATH}")
    print("Por favor, edita el archivo adb_config.py y configura la ruta correcta")
    # Intentar usar ADB del sistema
    ADB_PATH = "adb"
