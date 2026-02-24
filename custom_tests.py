"""
Sistema de pruebas personalizadas DUT-to-DUT
Permite crear, modificar y ejecutar pruebas entre dos dispositivos
"""
import json
import os
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# Archivo de almacenamiento
CUSTOM_TESTS_FILE = 'data/custom_tests.json'


class CallDirection(Enum):
    """Dirección de la llamada"""
    DUT1_TO_DUT2 = "dut1_to_dut2"  # DUT1 llama a DUT2
    DUT2_TO_DUT1 = "dut2_to_dut1"  # DUT2 llama a DUT1


class ActionType(Enum):
    """Tipos de acciones en una prueba"""
    MAKE_CALL = "make_call"        # Realizar llamada
    ANSWER_CALL = "answer_call"    # Contestar llamada
    HOLD_CALL = "hold_call"        # Mantener llamada X segundos
    END_CALL = "end_call"          # Colgar llamada
    WAIT = "wait"                  # Esperar X segundos
    VERIFY_CALL_STATE = "verify"   # Verificar estado de llamada
    SET_NETWORK = "set_network"    # Cambiar tipo de red (2g, 3g, 4g, 5g)
    SEND_SMS = "send_sms"          # Enviar SMS al otro DUT
    VERIFY_SMS = "verify_sms"      # Verificar que se recibió el SMS


@dataclass
class TestAction:
    """Acción individual dentro de una prueba"""
    action_type: str  # ActionType value
    target_device: str  # "dut1", "dut2" o "both" (para SET_NETWORK)
    duration_seconds: int = 0  # Para HOLD_CALL y WAIT
    description: str = ""
    network_mode: str = ""  # Para SET_NETWORK: '2g', '3g', '4g', '5g', 'auto'
    sms_message: str = ""  # Para SEND_SMS / VERIFY_SMS

    def to_dict(self) -> dict:
        d = {
            'action_type': self.action_type,
            'target_device': self.target_device,
            'duration_seconds': self.duration_seconds,
            'description': self.description,
        }
        if self.network_mode:
            d['network_mode'] = self.network_mode
        if self.sms_message:
            d['sms_message'] = self.sms_message
        return d

    @staticmethod
    def from_dict(data: dict) -> 'TestAction':
        return TestAction(
            action_type=data.get('action_type', ''),
            target_device=data.get('target_device', ''),
            duration_seconds=data.get('duration_seconds', 0),
            description=data.get('description', ''),
            network_mode=data.get('network_mode', ''),
            sms_message=data.get('sms_message', '')
        )


@dataclass
class CustomTest:
    """Prueba personalizada DUT-to-DUT"""
    id: str
    name: str
    description: str
    actions: List[TestAction]
    created_at: str = ""
    modified_at: str = ""
    is_enabled: bool = True
    category: str = "general"  # general, volte, vowifi, etc.
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.modified_at:
            self.modified_at = self.created_at

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'actions': [a.to_dict() for a in self.actions],
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'is_enabled': self.is_enabled,
            'category': self.category,
            'tags': self.tags
        }

    @staticmethod
    def from_dict(data: dict) -> 'CustomTest':
        actions = [TestAction.from_dict(a) for a in data.get('actions', [])]
        return CustomTest(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            description=data.get('description', ''),
            actions=actions,
            created_at=data.get('created_at', ''),
            modified_at=data.get('modified_at', ''),
            is_enabled=data.get('is_enabled', True),
            category=data.get('category', 'general'),
            tags=data.get('tags', [])
        )


class CustomTestManager:
    """Gestor de pruebas personalizadas"""

    def __init__(self):
        self.tests: Dict[str, CustomTest] = {}
        self._ensure_data_dir()
        self._load_tests()
        self._create_default_tests()

    def _ensure_data_dir(self):
        """Asegura que el directorio de datos existe"""
        os.makedirs(os.path.dirname(CUSTOM_TESTS_FILE), exist_ok=True)

    def _load_tests(self):
        """Carga pruebas desde archivo JSON"""
        if os.path.exists(CUSTOM_TESTS_FILE):
            try:
                with open(CUSTOM_TESTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for test_data in data.get('tests', []):
                        test = CustomTest.from_dict(test_data)
                        self.tests[test.id] = test
                logger.info(f"Cargadas {len(self.tests)} pruebas personalizadas")
            except Exception as e:
                logger.error(f"Error al cargar pruebas: {e}")

    def _save_tests(self):
        """Guarda pruebas a archivo JSON"""
        try:
            data = {
                'version': '1.0',
                'last_modified': datetime.now().isoformat(),
                'tests': [test.to_dict() for test in self.tests.values()]
            }
            with open(CUSTOM_TESTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Guardadas {len(self.tests)} pruebas personalizadas")
        except Exception as e:
            logger.error(f"Error al guardar pruebas: {e}")

    def _create_default_tests(self):
        """Crea pruebas predeterminadas si no existen"""
        if len(self.tests) > 0:
            return

        # Prueba 1: Llamada bidireccional básica (30 segundos)
        test1 = CustomTest(
            id="default-bidirectional-30s",
            name="Llamada Bidireccional 30s",
            description="DUT1 llama a DUT2 por 30s, luego DUT2 llama a DUT1 por 30s",
            category="basic",
            tags=["bidireccional", "30s"],
            actions=[
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 30, "Mantener llamada 30 segundos"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa entre llamadas"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 30, "Mantener llamada 30 segundos"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
            ]
        )

        # Prueba 2: Llamada bidireccional larga (1 minuto)
        test2 = CustomTest(
            id="default-bidirectional-1min",
            name="Llamada Bidireccional 1 minuto",
            description="DUT1 llama a DUT2 por 1min, luego DUT2 llama a DUT1 por 1min",
            category="basic",
            tags=["bidireccional", "1min"],
            actions=[
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 60, "Mantener llamada 1 minuto"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa entre llamadas"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 60, "Mantener llamada 1 minuto"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
            ]
        )

        # Prueba 3: Llamada bidireccional larga (10 minutos)
        test3 = CustomTest(
            id="default-bidirectional-10min",
            name="Llamada Bidireccional 10 minutos",
            description="DUT1 llama a DUT2 por 10min, luego DUT2 llama a DUT1 por 10min",
            category="long_duration",
            tags=["bidireccional", "10min", "larga"],
            actions=[
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 600, "Mantener llamada 10 minutos"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa entre llamadas"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 600, "Mantener llamada 10 minutos"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
            ]
        )

        # Prueba 4: Solo DUT1 llama a DUT2
        test4 = CustomTest(
            id="default-dut1-to-dut2-30s",
            name="DUT1 llama a DUT2 (30s)",
            description="Solo DUT1 llama a DUT2, DUT2 contesta, 30 segundos",
            category="basic",
            tags=["unidireccional", "30s"],
            actions=[
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 30, "Mantener llamada 30 segundos"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
            ]
        )

        # Prueba 5: Solo DUT2 llama a DUT1
        test5 = CustomTest(
            id="default-dut2-to-dut1-30s",
            name="DUT2 llama a DUT1 (30s)",
            description="Solo DUT2 llama a DUT1, DUT1 contesta, 30 segundos",
            category="basic",
            tags=["unidireccional", "30s"],
            actions=[
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 30, "Mantener llamada 30 segundos"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
            ]
        )

        # Prueba 6: Llamada bidireccional 1 hora (para pruebas largas)
        test6 = CustomTest(
            id="default-bidirectional-1hour",
            name="Llamada Bidireccional 1 hora",
            description="DUT1 llama a DUT2 por 1 hora, luego DUT2 llama a DUT1 por 1 hora",
            category="long_duration",
            tags=["bidireccional", "1hora", "muy_larga"],
            actions=[
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 3600, "Mantener llamada 1 hora"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 10, "Pausa entre llamadas"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono de llamada"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 3600, "Mantener llamada 1 hora"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
            ]
        )

        # Prueba 7: Llamada con cambio de red (4G → 3G)
        test7 = CustomTest(
            id="default-network-switch-4g-3g",
            name="Llamada 4G y 3G (40s cada una)",
            description="Cambia a 4G/3G/2G, llamada bidireccional 40s, luego cambia a 3G/2G y repite",
            category="network_switch",
            tags=["4g", "3g", "cambio_red", "bidireccional"],
            actions=[
                # === FASE 1: LLAMADA EN 4G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Cambiar ambos DUT a 4G/3G/2G", "4g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2 (4G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 40, "Mantener llamada 40s en 4G"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1 (4G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 40, "Mantener llamada 40s en 4G"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa entre fases"),

                # === FASE 2: LLAMADA EN 3G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Cambiar ambos DUT a 3G/2G", "3g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 marca a DUT2 (3G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 40, "Mantener llamada 40s en 3G"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 marca a DUT1 (3G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 40, "Mantener llamada 40s en 3G"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),

                # === RESTAURAR RED ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Restaurar red a automático", "auto"),
            ]
        )

        # Prueba 8: Llamada con cambio de red completo (5G → 4G → 3G)
        test8 = CustomTest(
            id="default-network-switch-all",
            name="Llamada todas las redes (5G→4G→3G)",
            description="Llamada bidireccional en cada tipo de red: 5G/4G/3G/2G, 4G/3G/2G, 3G/2G (40s cada una)",
            category="network_switch",
            tags=["5g", "4g", "3g", "cambio_red", "completo"],
            actions=[
                # === 5G/4G/3G/2G (auto con 5G) ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Cambiar a 5G/4G/3G/2G", "5g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1→DUT2 (5G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 40, "Mantener 40s en 5G"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "Colgar"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2→DUT1 (5G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 40, "Mantener 40s en 5G"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "Colgar"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === 4G/3G/2G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Cambiar a 4G/3G/2G", "4g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1→DUT2 (4G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 40, "Mantener 40s en 4G"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "Colgar"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2→DUT1 (4G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 40, "Mantener 40s en 4G"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "Colgar"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === 3G/2G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Cambiar a 3G/2G", "3g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1→DUT2 (3G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 40, "Mantener 40s en 3G"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "Colgar"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2→DUT1 (3G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 40, "Mantener 40s en 3G"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "Colgar"),

                # === RESTAURAR ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Restaurar red a automático", "auto"),
            ]
        )

        # Prueba 9: Llamada multi-red escalonada (5G→4G→3G mixto→3G ambos)
        test9 = CustomTest(
            id="default-network-staggered",
            name="Llamada multi-red escalonada (1min c/u)",
            description="DUT1(5G)→DUT2(5G) 1min, DUT2 baja a 4G y llama DUT1 1min, DUT1 baja a 3G y llama DUT2(4G) 1min, ambos 3G 1min",
            category="network_switch",
            tags=["5g", "4g", "3g", "escalonado", "mixto"],
            actions=[
                # === FASE 1: Ambos en 5G, DUT1 llama DUT2, 1 min ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 5G/4G/3G/2G", "5g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 llama a DUT2 (ambos 5G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 60, "Mantener llamada 1 min"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === FASE 2: DUT2 baja a 4G, DUT2 llama DUT1, 1 min ===
                TestAction(ActionType.SET_NETWORK.value, "dut2", 0, "DUT2 baja a 4G/3G/2G", "4g"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 llama a DUT1 (DUT2 en 4G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 60, "Mantener llamada 1 min"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === FASE 3: DUT1 baja a 3G, DUT1 llama DUT2 (en 4G), 1 min ===
                TestAction(ActionType.SET_NETWORK.value, "dut1", 0, "DUT1 baja a 3G/2G", "3g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 llama a DUT2 (DUT1 3G, DUT2 4G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 60, "Mantener llamada 1 min"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === FASE 4: Ambos en 3G, llamada 1 min ===
                TestAction(ActionType.SET_NETWORK.value, "dut2", 0, "DUT2 baja a 3G/2G", "3g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 llama a DUT2 (ambos 3G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 60, "Mantener llamada 1 min"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),

                # === RESTAURAR ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Restaurar ambos a automático", "auto"),
            ]
        )

        # Prueba 10: SMS bidireccional en cada red (5G, 4G, 3G)
        test10 = CustomTest(
            id="default-sms-multi-network",
            name="SMS bidireccional multi-red (5G→4G→3G)",
            description="Envía SMS de DUT1→DUT2 y DUT2→DUT1 en cada tipo de red: 5G, 4G, 3G",
            category="sms",
            tags=["sms", "bidireccional", "5g", "4g", "3g", "multi-red"],
            actions=[
                # === SMS EN 5G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 5G/4G/3G/2G", "5g"),
                TestAction(ActionType.SEND_SMS.value, "dut1", 0, "DUT1 envía SMS a DUT2 (5G)", sms_message="Test SMS 5G DUT1"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.VERIFY_SMS.value, "dut2", 0, "Verificar SMS en DUT2", sms_message="Test SMS 5G DUT1"),
                TestAction(ActionType.SEND_SMS.value, "dut2", 0, "DUT2 envía SMS a DUT1 (5G)", sms_message="Test SMS 5G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.VERIFY_SMS.value, "dut1", 0, "Verificar SMS en DUT1", sms_message="Test SMS 5G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Pausa"),

                # === SMS EN 4G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 4G/3G/2G", "4g"),
                TestAction(ActionType.SEND_SMS.value, "dut1", 0, "DUT1 envía SMS a DUT2 (4G)", sms_message="Test SMS 4G DUT1"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.VERIFY_SMS.value, "dut2", 0, "Verificar SMS en DUT2", sms_message="Test SMS 4G DUT1"),
                TestAction(ActionType.SEND_SMS.value, "dut2", 0, "DUT2 envía SMS a DUT1 (4G)", sms_message="Test SMS 4G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.VERIFY_SMS.value, "dut1", 0, "Verificar SMS en DUT1", sms_message="Test SMS 4G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Pausa"),

                # === SMS EN 3G ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 3G/2G", "3g"),
                TestAction(ActionType.SEND_SMS.value, "dut1", 0, "DUT1 envía SMS a DUT2 (3G)", sms_message="Test SMS 3G DUT1"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.VERIFY_SMS.value, "dut2", 0, "Verificar SMS en DUT2", sms_message="Test SMS 3G DUT1"),
                TestAction(ActionType.SEND_SMS.value, "dut2", 0, "DUT2 envía SMS a DUT1 (3G)", sms_message="Test SMS 3G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.VERIFY_SMS.value, "dut1", 0, "Verificar SMS en DUT1", sms_message="Test SMS 3G DUT2"),

                # === RESTAURAR ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Restaurar red a automático", "auto"),
            ]
        )

        # Prueba 11: SMS durante llamada activa en cada red
        test11 = CustomTest(
            id="default-sms-during-call",
            name="SMS durante llamada (5G→4G→3G)",
            description="Llamada activa + envío de SMS bidireccional en cada red: 5G, 4G, 3G",
            category="sms",
            tags=["sms", "durante_llamada", "5g", "4g", "3g"],
            actions=[
                # === 5G: Llamada + SMS ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 5G/4G/3G/2G", "5g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 llama a DUT2 (5G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar estabilización de llamada"),
                TestAction(ActionType.SEND_SMS.value, "dut1", 0, "DUT1 envía SMS durante llamada (5G)", sms_message="SMS durante llamada 5G DUT1"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.SEND_SMS.value, "dut2", 0, "DUT2 envía SMS durante llamada (5G)", sms_message="SMS durante llamada 5G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 30, "Mantener llamada 30s"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === 4G: Llamada + SMS ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 4G/3G/2G", "4g"),
                TestAction(ActionType.MAKE_CALL.value, "dut2", 0, "DUT2 llama a DUT1 (4G)"),
                TestAction(ActionType.WAIT.value, "dut2", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut1", 0, "DUT1 contesta"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar estabilización de llamada"),
                TestAction(ActionType.SEND_SMS.value, "dut1", 0, "DUT1 envía SMS durante llamada (4G)", sms_message="SMS durante llamada 4G DUT1"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.SEND_SMS.value, "dut2", 0, "DUT2 envía SMS durante llamada (4G)", sms_message="SMS durante llamada 4G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.HOLD_CALL.value, "dut2", 30, "Mantener llamada 30s"),
                TestAction(ActionType.END_CALL.value, "dut2", 0, "DUT2 cuelga"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Pausa"),

                # === 3G: Llamada + SMS ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Ambos DUT a 3G/2G", "3g"),
                TestAction(ActionType.MAKE_CALL.value, "dut1", 0, "DUT1 llama a DUT2 (3G)"),
                TestAction(ActionType.WAIT.value, "dut1", 3, "Esperar tono"),
                TestAction(ActionType.ANSWER_CALL.value, "dut2", 0, "DUT2 contesta"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar estabilización de llamada"),
                TestAction(ActionType.SEND_SMS.value, "dut1", 0, "DUT1 envía SMS durante llamada (3G)", sms_message="SMS durante llamada 3G DUT1"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.SEND_SMS.value, "dut2", 0, "DUT2 envía SMS durante llamada (3G)", sms_message="SMS durante llamada 3G DUT2"),
                TestAction(ActionType.WAIT.value, "dut1", 5, "Esperar entrega"),
                TestAction(ActionType.HOLD_CALL.value, "dut1", 30, "Mantener llamada 30s"),
                TestAction(ActionType.END_CALL.value, "dut1", 0, "DUT1 cuelga"),

                # === RESTAURAR ===
                TestAction(ActionType.SET_NETWORK.value, "both", 0, "Restaurar red a automático", "auto"),
            ]
        )

        # Agregar pruebas predeterminadas
        for test in [test1, test2, test3, test4, test5, test6, test7, test8, test9, test10, test11]:
            self.tests[test.id] = test

        self._save_tests()
        logger.info("Creadas pruebas predeterminadas")

    # ==================== CRUD ====================

    def get_all_tests(self) -> List[dict]:
        """Obtiene todas las pruebas"""
        return [test.to_dict() for test in self.tests.values()]

    def get_test(self, test_id: str) -> Optional[dict]:
        """Obtiene una prueba por ID"""
        test = self.tests.get(test_id)
        return test.to_dict() if test else None

    def create_test(self, data: dict) -> dict:
        """Crea una nueva prueba"""
        test_id = str(uuid.uuid4())

        # Convertir acciones
        actions = []
        for action_data in data.get('actions', []):
            actions.append(TestAction.from_dict(action_data))

        test = CustomTest(
            id=test_id,
            name=data.get('name', 'Nueva Prueba'),
            description=data.get('description', ''),
            actions=actions,
            category=data.get('category', 'general'),
            tags=data.get('tags', []),
            is_enabled=data.get('is_enabled', True)
        )

        self.tests[test_id] = test
        self._save_tests()

        logger.info(f"Prueba creada: {test.name} (ID: {test_id})")
        return test.to_dict()

    def update_test(self, test_id: str, data: dict) -> Optional[dict]:
        """Actualiza una prueba existente"""
        if test_id not in self.tests:
            return None

        test = self.tests[test_id]

        # Actualizar campos
        if 'name' in data:
            test.name = data['name']
        if 'description' in data:
            test.description = data['description']
        if 'category' in data:
            test.category = data['category']
        if 'tags' in data:
            test.tags = data['tags']
        if 'is_enabled' in data:
            test.is_enabled = data['is_enabled']
        if 'actions' in data:
            test.actions = [TestAction.from_dict(a) for a in data['actions']]

        test.modified_at = datetime.now().isoformat()

        self._save_tests()
        logger.info(f"Prueba actualizada: {test.name} (ID: {test_id})")
        return test.to_dict()

    def delete_test(self, test_id: str) -> bool:
        """Elimina una prueba"""
        if test_id not in self.tests:
            return False

        test_name = self.tests[test_id].name
        del self.tests[test_id]
        self._save_tests()

        logger.info(f"Prueba eliminada: {test_name} (ID: {test_id})")
        return True

    def duplicate_test(self, test_id: str) -> Optional[dict]:
        """Duplica una prueba existente"""
        if test_id not in self.tests:
            return None

        original = self.tests[test_id]
        new_id = str(uuid.uuid4())

        # Crear copia con nuevo ID
        new_test = CustomTest(
            id=new_id,
            name=f"{original.name} (copia)",
            description=original.description,
            actions=[TestAction.from_dict(a.to_dict()) for a in original.actions],
            category=original.category,
            tags=original.tags.copy(),
            is_enabled=True
        )

        self.tests[new_id] = new_test
        self._save_tests()

        logger.info(f"Prueba duplicada: {original.name} -> {new_test.name}")
        return new_test.to_dict()

    def get_tests_by_category(self, category: str) -> List[dict]:
        """Obtiene pruebas por categoría"""
        return [
            test.to_dict()
            for test in self.tests.values()
            if test.category == category
        ]

    def get_categories(self) -> List[str]:
        """Obtiene todas las categorías disponibles"""
        categories = set()
        for test in self.tests.values():
            categories.add(test.category)
        return sorted(list(categories))
