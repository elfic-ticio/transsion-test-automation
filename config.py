"""
Configuración central del sistema de pruebas
"""

# Operadores colombianos con sus capacidades de servicios
OPERATORS_CONFIG = {
    "CLARO": {
        "mcc": "732",
        "mnc": "101",
        "display_name": "Claro Colombia",
        "services": {
            "2G": True,
            "3G": True,
            "4G": True,
            "5G_NSA": True,
            "5G_SA": False,
            "VoLTE": True,
            "VoNR": False,
            "ViLTE": False,
            "VoWiFi": True,
            "ViWiFi": False,
            "CSFB": True,
            "SRVCC": True
        },
        "vowifi_mode": "Cellular Preferred",
        "vowifi_activation": "airplane_mode_wifi",
        "notes": "VoWiFi SOLO se activa con modo avión + WiFi activo. No se puede probar ViLTE ni ViWiFi.",
        "test_networks": ["2G", "3G", "4G", "5G_NSA"]
    },
    "WOM": {
        "mcc": "732",
        "mnc": ["130", "360"],
        "display_name": "WOM Colombia",
        "services": {
            "2G": True,
            "3G": True,
            "4G": True,
            "5G_NSA": False,
            "5G_SA": False,
            "VoLTE": True,
            "VoNR": False,
            "ViLTE": True,
            "VoWiFi": True,
            "ViWiFi": True,
            "CSFB": True,
            "SRVCC": True
        },
        "vowifi_mode": "WiFi Preferred",
        "vowifi_activation": "normal",
        "notes": "NO tiene 5G. Único operador con ViLTE y ViWiFi completo.",
        "test_networks": ["2G", "3G", "4G"]
    },
    "TIGO": {
        "mcc": "732",
        "mnc": ["111", "103"],
        "display_name": "Tigo Colombia",
        "services": {
            "2G": True,
            "3G": True,
            "4G": True,
            "5G_NSA": True,
            "5G_SA": False,
            "VoLTE": True,
            "VoNR": False,
            "ViLTE": False,
            "VoWiFi": True,
            "ViWiFi": False,
            "CSFB": True,
            "SRVCC": True
        },
        "vowifi_mode": "WiFi Preferred",
        "vowifi_activation": "normal",
        "notes": "",
        "test_networks": ["2G", "3G", "4G", "5G_NSA"]
    },
    "MOVISTAR": {
        "mcc": "732",
        "mnc": "123",
        "display_name": "Movistar Colombia",
        "services": {
            "2G": True,
            "3G": True,
            "4G": True,
            "5G_NSA": True,
            "5G_SA": False,
            "VoLTE": True,
            "VoNR": False,
            "ViLTE": False,
            "VoWiFi": True,
            "ViWiFi": False,
            "CSFB": True,
            "SRVCC": True
        },
        "vowifi_mode": "Cellular Preferred",
        "vowifi_activation": "airplane_mode_wifi",
        "notes": "VoWiFi SOLO se activa con modo avión + WiFi activo. 3G será apagado en 2026.",
        "test_networks": ["2G", "3G", "4G", "5G_NSA"]
    }
}

# Lista ordenada de operadores
OPERATORS = ["CLARO", "WOM", "TIGO", "MOVISTAR"]
