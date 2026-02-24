"""
Ejecutor de pruebas DUT-to-DUT
Coordina la ejecución de pruebas entre dos dispositivos
"""
import time
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from adb_manager import ADBManager
from custom_tests import CustomTest, TestAction, ActionType

logger = logging.getLogger(__name__)


@dataclass
class DUTConfig:
    """Configuración de un DUT (Device Under Test)"""
    serial: str
    phone_number: str
    operator: str = ""
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"DUT ({self.serial[:8]}...)"


@dataclass
class DUTExecutionState:
    """Estado de ejecución DUT-to-DUT"""
    is_running: bool = False
    is_paused: bool = False
    current_action_index: int = 0
    total_actions: int = 0
    current_action: str = ""
    progress: int = 0
    start_time: str = ""
    dut1_serial: str = ""
    dut2_serial: str = ""
    test_name: str = ""
    test_id: str = ""
    logs: List[str] = field(default_factory=list)
    result: str = ""  # "running", "pass", "fail", "stopped"
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'current_action_index': self.current_action_index,
            'total_actions': self.total_actions,
            'current_action': self.current_action,
            'progress': self.progress,
            'start_time': self.start_time,
            'dut1_serial': self.dut1_serial,
            'dut2_serial': self.dut2_serial,
            'test_name': self.test_name,
            'test_id': self.test_id,
            'logs': self.logs[-100:] if self.logs else [],  # Últimos 100 logs
            'result': self.result,
            'error_message': self.error_message
        }


class DUTExecutor:
    """Ejecutor de pruebas DUT-to-DUT"""

    def __init__(self, adb_manager: ADBManager):
        self.adb = adb_manager
        self.state = DUTExecutionState()
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        self._execution_thread: Optional[threading.Thread] = None

        # Configuración de DUTs
        self.dut1: Optional[DUTConfig] = None
        self.dut2: Optional[DUTConfig] = None

        # Callbacks
        self.on_log: Optional[Callable] = None
        self.on_action_complete: Optional[Callable] = None
        self.on_execution_complete: Optional[Callable] = None

    def _log(self, message: str, level: str = "INFO"):
        """Registra mensaje en log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.state.logs.append(log_entry)
        logger.info(message)

        if self.on_log:
            self.on_log(log_entry)

    def _update_action(self, action_desc: str):
        """Actualiza la acción actual"""
        self.state.current_action = action_desc
        self._log(action_desc)

    def _calculate_progress(self):
        """Calcula el progreso actual"""
        if self.state.total_actions > 0:
            self.state.progress = int(
                (self.state.current_action_index / self.state.total_actions) * 100
            )

    # ==================== CONTROL ====================

    def start_execution(self, test: CustomTest, dut1: DUTConfig, dut2: DUTConfig) -> bool:
        """
        Inicia la ejecución de una prueba DUT-to-DUT.

        Args:
            test: Prueba a ejecutar
            dut1: Configuración del DUT1
            dut2: Configuración del DUT2

        Returns:
            bool: True si se inició correctamente
        """
        if self.state.is_running:
            self._log("Ya hay una ejecución en curso", "WARNING")
            return False

        self.dut1 = dut1
        self.dut2 = dut2

        # Inicializar estado
        self.state = DUTExecutionState(
            is_running=True,
            is_paused=False,
            current_action_index=0,
            total_actions=len(test.actions),
            current_action="Iniciando...",
            progress=0,
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            dut1_serial=dut1.serial,
            dut2_serial=dut2.serial,
            test_name=test.name,
            test_id=test.id,
            logs=[],
            result="running"
        )

        self._stop_flag.clear()
        self._pause_flag.clear()

        # Iniciar thread de ejecución
        self._execution_thread = threading.Thread(
            target=self._execute_test,
            args=(test,),
            daemon=True
        )
        self._execution_thread.start()

        self._log(f"Ejecución iniciada: {test.name}")
        self._log(f"DUT1: {dut1.serial} -> {dut1.phone_number}")
        self._log(f"DUT2: {dut2.serial} -> {dut2.phone_number}")

        return True

    def stop_execution(self):
        """Detiene la ejecución"""
        self._stop_flag.set()
        self._pause_flag.clear()
        self._log("Deteniendo ejecución...", "WARNING")

    def pause_execution(self):
        """Pausa la ejecución"""
        self._pause_flag.set()
        self.state.is_paused = True
        self._log("Ejecución pausada", "WARNING")

    def resume_execution(self):
        """Reanuda la ejecución"""
        self._pause_flag.clear()
        self.state.is_paused = False
        self._log("Ejecución reanudada", "INFO")

    def get_state(self) -> dict:
        """Obtiene el estado actual"""
        return self.state.to_dict()

    # ==================== EJECUCIÓN ====================

    def _execute_test(self, test: CustomTest):
        """Ejecuta la prueba completa"""
        try:
            # Verificar dispositivos conectados
            self._update_action("Verificando dispositivos...")

            if not self._verify_devices():
                self.state.result = "fail"
                self.state.error_message = "Uno o más dispositivos no están conectados"
                self._log(self.state.error_message, "ERROR")
                return

            # Ejecutar cada acción
            for i, action in enumerate(test.actions):
                # Verificar stop/pause
                if self._stop_flag.is_set():
                    self.state.result = "stopped"
                    self._log("Ejecución detenida por usuario", "WARNING")
                    break

                while self._pause_flag.is_set():
                    time.sleep(0.5)
                    if self._stop_flag.is_set():
                        break

                self.state.current_action_index = i
                self._calculate_progress()

                # Ejecutar acción
                success = self._execute_action(action)

                if not success:
                    self.state.result = "fail"
                    self._log(f"Acción falló: {action.description}", "ERROR")
                    break

                # Callback de acción completada
                if self.on_action_complete:
                    self.on_action_complete(i, action)

            # Completar
            if self.state.result == "running":
                self.state.result = "pass"
                self.state.progress = 100
                self._log("Prueba completada exitosamente", "INFO")

        except Exception as e:
            self.state.result = "fail"
            self.state.error_message = str(e)
            self._log(f"Error en ejecución: {e}", "ERROR")

        finally:
            self.state.is_running = False

            # Asegurar que las llamadas estén colgadas
            self._cleanup()

            if self.on_execution_complete:
                self.on_execution_complete(self.state.result)

    def _verify_devices(self) -> bool:
        """Verifica que ambos dispositivos estén conectados"""
        devices = self.adb.get_connected_devices()
        serials = [d.serial for d in devices]

        dut1_ok = self.dut1.serial in serials
        dut2_ok = self.dut2.serial in serials

        if not dut1_ok:
            self._log(f"DUT1 no encontrado: {self.dut1.serial}", "ERROR")
        if not dut2_ok:
            self._log(f"DUT2 no encontrado: {self.dut2.serial}", "ERROR")

        return dut1_ok and dut2_ok

    def _execute_action(self, action: TestAction) -> bool:
        """Ejecuta una acción individual"""
        action_type = action.action_type
        target = action.target_device
        duration = action.duration_seconds
        description = action.description

        # SET_NETWORK puede aplicar a "both"
        if action_type == ActionType.SET_NETWORK.value:
            return self._action_set_network(action)

        # Determinar dispositivo objetivo
        if target == "dut1":
            device_serial = self.dut1.serial
            other_serial = self.dut2.serial
            device_number = self.dut1.phone_number
            other_number = self.dut2.phone_number
        else:
            device_serial = self.dut2.serial
            other_serial = self.dut1.serial
            device_number = self.dut2.phone_number
            other_number = self.dut1.phone_number

        self._update_action(f"{description}")

        try:
            if action_type == ActionType.MAKE_CALL.value:
                return self._action_make_call(device_serial, other_number, description)

            elif action_type == ActionType.ANSWER_CALL.value:
                return self._action_answer_call(device_serial, description)

            elif action_type == ActionType.HOLD_CALL.value:
                return self._action_hold_call(device_serial, duration, description)

            elif action_type == ActionType.END_CALL.value:
                return self._action_end_call(device_serial, description)

            elif action_type == ActionType.WAIT.value:
                return self._action_wait(duration, description)

            elif action_type == ActionType.VERIFY_CALL_STATE.value:
                return self._action_verify_call_state(device_serial, description)

            elif action_type == ActionType.SEND_SMS.value:
                return self._action_send_sms(device_serial, other_number, action.sms_message, description)

            elif action_type == ActionType.VERIFY_SMS.value:
                return self._action_verify_sms(device_serial, other_number, action.sms_message, description)

            else:
                self._log(f"Tipo de acción desconocido: {action_type}", "WARNING")
                return True

        except Exception as e:
            self._log(f"Error ejecutando acción: {e}", "ERROR")
            return False

    def _action_make_call(self, device_serial: str, number: str, desc: str) -> bool:
        """Realiza una llamada"""
        self._log(f"Marcando {number} desde {device_serial[:8]}...")

        success, msg = self.adb.make_call(device_serial, number)

        if success:
            self._log(f"Llamada iniciada: {msg}")
        else:
            self._log(f"Error al marcar: {msg}", "ERROR")

        return success

    def _action_answer_call(self, device_serial: str, desc: str) -> bool:
        """Contesta una llamada entrante"""
        self._log(f"Esperando llamada en {device_serial[:8]}...")

        # Esperar hasta 20 segundos a que entre la llamada
        for i in range(20):
            if self._stop_flag.is_set():
                return False

            call_state = self.adb.get_call_state(device_serial)
            self._log(f"  Estado: {call_state}")

            if call_state == 'offhook':
                self._log("Llamada ya conectada")
                return True

            if call_state == 'ringing':
                self._log("Llamada entrante detectada, contestando...")

                # Usar keyevent 5 directamente (el que funciona)
                self.adb.run_command('shell input keyevent 5', device_serial)
                time.sleep(1)

                # Verificar si contestó
                new_state = self.adb.get_call_state(device_serial)
                if new_state == 'offhook':
                    self._log("Llamada contestada con keyevent 5")
                    return True

                # Intentar keyevent 79 como backup
                self.adb.run_command('shell input keyevent 79', device_serial)
                time.sleep(1)

                new_state = self.adb.get_call_state(device_serial)
                if new_state == 'offhook':
                    self._log("Llamada contestada con keyevent 79")
                    return True

                self._log("No se pudo contestar", "ERROR")
                return False

            time.sleep(1)

        self._log("Timeout esperando llamada entrante (20s)", "ERROR")
        return False

    def _action_hold_call(self, device_serial: str, duration: int, desc: str) -> bool:
        """Mantiene la llamada activa durante X segundos"""
        self._log(f"Manteniendo llamada por {duration} segundos...")

        start_time = time.time()

        while time.time() - start_time < duration:
            if self._stop_flag.is_set():
                return False

            while self._pause_flag.is_set():
                time.sleep(0.5)
                if self._stop_flag.is_set():
                    return False

            # Verificar que la llamada sigue activa
            call_state = self.adb.get_call_state(device_serial)

            if call_state != 'offhook':
                self._log(f"Llamada terminó inesperadamente (estado: {call_state})", "ERROR")
                return False

            # Log de progreso cada 30 segundos
            elapsed = int(time.time() - start_time)
            if elapsed > 0 and elapsed % 30 == 0:
                remaining = duration - elapsed
                self._log(f"Llamada activa: {elapsed}s transcurridos, {remaining}s restantes")

            time.sleep(1)

        self._log(f"Llamada mantenida por {duration}s exitosamente")
        return True

    def _action_end_call(self, device_serial: str, desc: str) -> bool:
        """Finaliza la llamada"""
        self._log(f"Colgando llamada en {device_serial[:8]}...")

        success, msg = self.adb.end_call(device_serial)

        if success:
            self._log("Llamada finalizada")
        else:
            self._log(f"Error al colgar: {msg}", "WARNING")

        time.sleep(1)  # Esperar estabilización
        return True  # Siempre retornar True ya que colgar no es crítico

    def _action_wait(self, duration: int, desc: str) -> bool:
        """Espera X segundos"""
        self._log(f"Esperando {duration} segundos...")

        for i in range(duration):
            if self._stop_flag.is_set():
                return False

            while self._pause_flag.is_set():
                time.sleep(0.5)
                if self._stop_flag.is_set():
                    return False

            time.sleep(1)

        return True

    def _action_verify_call_state(self, device_serial: str, desc: str) -> bool:
        """Verifica el estado de la llamada"""
        call_state = self.adb.get_call_state(device_serial)
        self._log(f"Estado de llamada en {device_serial[:8]}: {call_state}")
        return True

    def _action_send_sms(self, device_serial: str, other_number: str, message: str, desc: str) -> bool:
        """Envía un SMS al otro DUT"""
        if not message:
            message = "Test SMS automatizado"
        self._log(f"Enviando SMS desde {device_serial[:8]} a {other_number}: '{message}'")

        success, msg = self.adb.send_sms(device_serial, other_number, message)

        if success:
            self._log(f"SMS enviado: {msg}")
        else:
            self._log(f"Error enviando SMS: {msg}", "ERROR")

        return success

    def _action_verify_sms(self, device_serial: str, other_number: str, message: str, desc: str) -> bool:
        """Verifica que se recibió un SMS del otro DUT"""
        if not message:
            message = "Test SMS automatizado"
        self._log(f"Verificando recepción de SMS en {device_serial[:8]} de {other_number}...")

        success, msg = self.adb.check_sms_received(device_serial, other_number, message, timeout=30)

        if success:
            self._log(f"SMS verificado: {msg}")
        else:
            self._log(f"SMS no recibido: {msg}", "WARNING")

        # No fallar el test por verificación de SMS (es informativo)
        return True

    def _action_set_network(self, action: TestAction) -> bool:
        """Cambia el tipo de red en uno o ambos dispositivos"""
        network_mode = action.network_mode
        target = action.target_device

        if not network_mode:
            self._log("No se especificó modo de red", "ERROR")
            return False

        # Determinar a qué dispositivos aplicar
        devices = []
        if target == "both":
            devices = [(self.dut1.serial, "DUT1"), (self.dut2.serial, "DUT2")]
        elif target == "dut1":
            devices = [(self.dut1.serial, "DUT1")]
        else:
            devices = [(self.dut2.serial, "DUT2")]

        all_ok = True
        for serial, name in devices:
            self._log(f"Cambiando {name} ({serial[:8]}) a {network_mode.upper()}...")

            success, msg = self.adb.set_preferred_network(serial, network_mode)

            if success:
                self._log(f"  {name} cambiado a {network_mode.upper()}")
            else:
                self._log(f"  Error en {name}: {msg}", "ERROR")
                all_ok = False

        # Esperar un poco adicional a que la red se estabilice
        if all_ok:
            self._log(f"Esperando 3s adicionales para estabilización...")
            for i in range(3):
                if self._stop_flag.is_set():
                    return False
                time.sleep(1)

            # Verificar red actual
            for serial, name in devices:
                current = self.adb.get_current_network_type(serial)
                self._log(f"  {name} red actual: {current}")

        return all_ok

    def _cleanup(self):
        """Limpieza al finalizar"""
        try:
            # Intentar colgar en ambos dispositivos
            if self.dut1:
                self.adb.end_call(self.dut1.serial)
            if self.dut2:
                self.adb.end_call(self.dut2.serial)

            # Restaurar red a automático en ambos dispositivos
            if self.dut1:
                self.adb.set_preferred_network(self.dut1.serial, 'auto')
            if self.dut2:
                self.adb.set_preferred_network(self.dut2.serial, 'auto')
            self._log("Red restaurada a automático en ambos DUTs")
        except Exception as e:
            self._log(f"Error en limpieza: {e}", "WARNING")
