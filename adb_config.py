"""
Configuración de ruta de ADB
"""
import os

# Ruta de ADB incluida dentro del proyecto
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADB_PATH = os.path.join(_BASE_DIR, "platform-tools-36.0.2", "adb.exe")

# Si por alguna razón no se encuentra, intentar con adb del sistema
if not os.path.exists(ADB_PATH):
    print(f"ADVERTENCIA: ADB no encontrado en: {ADB_PATH}")
    ADB_PATH = "adb"
