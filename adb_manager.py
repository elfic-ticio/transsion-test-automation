"""
Gestor de comandos ADB para control de dispositivos Android
"""
import subprocess
import time
import re
import logging
import os
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass, asdict

# Importar configuración de ADB
try:
    from adb_config import ADB_PATH
except ImportError:
    ADB_PATH = "adb"

logger = logging.getLogger(__name__)

@dataclass
class Device:
    serial: str
    model: str
    android_version: str
    manufacturer: str = ""
    sw_version: str = ""
    network_type: str = ""
    signal_strength: int = 0
    sim_operator: str = ""
    sim_state: str = ""
    phone_number: str = ""   # Texto display (puede incluir "SIM1: X / SIM2: Y")
    phone_sim1: str = ""     # Numero limpio SIM1 (para auto-fill en DUT)
    phone_sim2: str = ""     # Numero limpio SIM2 (para auto-fill en DUT)
    is_connected: bool = False
    volte_enabled: bool = False
    vowifi_enabled: bool = False
    airplane_mode: bool = False

    def to_dict(self):
        return asdict(self)


class ADBManager:
    """Gestor de comandos ADB"""

    # Mapeo MCC/MNC → nombre canónico del operador (Colombia MCC=732)
    MCCMNC_TO_OPERATOR = {
        '732101': 'Claro',
        '732103': 'Tigo',
        '732123': 'Movistar',
        '732187': 'WOM',
    }

    def __init__(self):
        self.devices: Dict[str, Device] = {}
        self.command_timeout = 30

    def run_command(self, command: str, device_serial: str = None, timeout: int = None) -> Tuple[bool, str]:
        """
        Ejecuta un comando ADB.

        Args:
            command: Comando ADB (sin 'adb' al inicio)
            device_serial: Serial del dispositivo (opcional)
            timeout: Timeout en segundos

        Returns:
            tuple: (success: bool, output: str)
        """
        timeout = timeout or self.command_timeout

        try:
            if device_serial:
                full_cmd = f'"{ADB_PATH}" -s {device_serial} {command}'
            else:
                full_cmd = f'"{ADB_PATH}" {command}'

            logger.debug(f"Ejecutando: {full_cmd}")

            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            success = result.returncode == 0
            output = result.stdout.strip() if success else result.stderr.strip()

            if not success:
                logger.warning(f"Comando falló: {output}")

            return success, output

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout ejecutando: {command}")
            return False, "Command timeout"
        except FileNotFoundError:
            logger.error("ADB no encontrado. Verificar instalación.")
            return False, "ADB not found"
        except Exception as e:
            logger.error(f"Error ejecutando comando: {e}")
            return False, str(e)

    # ==================== GESTIÓN DE DISPOSITIVOS ====================

    def get_connected_devices(self) -> List[Device]:
        """Obtiene lista de dispositivos conectados"""
        success, output = self.run_command("devices -l")
        devices = []

        if not success:
            return devices

        lines = output.split('\n')[1:]  # Skip header "List of devices attached"

        for line in lines:
            line = line.strip()
            if not line or 'offline' in line or 'unauthorized' in line:
                continue

            if '\tdevice' in line or ' device ' in line:
                parts = line.split()
                serial = parts[0]

                device = Device(
                    serial=serial,
                    model=self._get_prop(serial, "ro.product.model"),
                    android_version=self._get_prop(serial, "ro.build.version.release"),
                    manufacturer=self._get_prop(serial, "ro.product.manufacturer"),
                    sw_version=self._get_prop(serial, "ro.build.display.id"),
                    is_connected=True
                )

                # Actualizar información de red
                self._update_network_info(device)
                self._update_sim_info(device)
                self._update_call_features(device)

                devices.append(device)
                self.devices[serial] = device

        return devices

    def _get_prop(self, serial: str, prop: str) -> str:
        """Obtiene una propiedad del sistema"""
        success, output = self.run_command(f"shell getprop {prop}", serial)
        return output if success else "Unknown"

    def _update_network_info(self, device: Device):
        """Actualiza información de red del dispositivo"""
        success, output = self.run_command(
            "shell dumpsys telephony.registry | grep -E \"mServiceState|mDataNetworkType\"",
            device.serial
        )

        if success:
            output_upper = output.upper()
            if 'NR_SA' in output_upper or '5G_SA' in output_upper:
                device.network_type = "5G SA"
            elif 'NR' in output_upper or 'LTE_NR' in output_upper:
                device.network_type = "5G NSA"
            elif 'LTE' in output_upper:
                device.network_type = "LTE"
            elif 'UMTS' in output_upper or 'HSPA' in output_upper or 'HSDPA' in output_upper:
                device.network_type = "3G"
            elif 'GSM' in output_upper or 'EDGE' in output_upper or 'GPRS' in output_upper:
                device.network_type = "2G"
            else:
                device.network_type = "Unknown"

        # Obtener fuerza de señal
        success, output = self.run_command(
            "shell dumpsys telephony.registry | grep mSignalStrength",
            device.serial
        )
        if success:
            # Extraer valor de señal (simplificado)
            match = re.search(r'signalStrength=(\d+)', output)
            if match:
                device.signal_strength = int(match.group(1))

    def _update_sim_info(self, device: Device):
        """Actualiza información de SIM"""
        # Estado SIM - usar gsm.sim.state para detectar slot activo
        active_slot = self._get_active_sim_slot(device.serial)

        success, output = self.run_command(
            "shell getprop gsm.sim.state",
            device.serial
        )
        if success and output:
            parts = [p.strip().upper() for p in output.split(',')]
            idx = active_slot - 1
            if idx < len(parts):
                state = parts[idx]
                if state == 'LOADED':
                    device.sim_state = f"Ready (SIM {active_slot})"
                elif state == 'ABSENT':
                    device.sim_state = "No SIM"
                else:
                    device.sim_state = f"Unknown ({state})"
            else:
                device.sim_state = "Unknown"
        else:
            device.sim_state = "Unknown"

        # Operador SIM - obtener solo del slot activo
        operator = self._get_sim_operator_name(device.serial, active_slot)
        if operator:
            device.sim_operator = operator
        else:
            device.sim_operator = "Sin operador"

        # Numeros de telefono por SIM
        nums = self._get_phone_numbers(device.serial)
        device.phone_sim1 = nums.get(1, "")
        device.phone_sim2 = nums.get(2, "")
        if nums:
            if len(nums) == 1:
                device.phone_number = next(iter(nums.values()))
            else:
                device.phone_number = " / ".join(f"SIM{s}: {n}" for s, n in sorted(nums.items()))
        else:
            device.phone_number = ""

    def _update_call_features(self, device: Device):
        """Actualiza estado de VoLTE/VoWiFi"""
        # VoLTE
        success, output = self.run_command(
            "shell dumpsys telephony.registry | grep -i volte",
            device.serial
        )
        if success:
            device.volte_enabled = 'true' in output.lower() or 'enabled' in output.lower()

        # VoWiFi
        success, output = self.run_command(
            "shell dumpsys telephony.registry | grep -i vowifi",
            device.serial
        )
        if success:
            device.vowifi_enabled = 'true' in output.lower() or 'enabled' in output.lower()

        # Airplane mode
        success, output = self.run_command(
            "shell settings get global airplane_mode_on",
            device.serial
        )
        if success:
            device.airplane_mode = output.strip() == '1'

    def refresh_device(self, serial: str) -> Optional[Device]:
        """Refresca información de un dispositivo específico"""
        if serial not in self.devices:
            return None

        device = self.devices[serial]
        self._update_network_info(device)
        self._update_sim_info(device)
        self._update_call_features(device)

        return device

    # ==================== CONTROL DE LLAMADAS ====================

    def make_call(self, serial: str, phone_number: str) -> Tuple[bool, str]:
        """
        Realiza una llamada telefónica.

        Args:
            serial: Serial del dispositivo
            phone_number: Número a marcar

        Returns:
            tuple: (success, message)
        """
        # Limpiar número (solo dígitos y +)
        clean_number = re.sub(r'[^\d+]', '', phone_number)

        command = f'shell am start -a android.intent.action.CALL -d tel:{clean_number}'
        success, output = self.run_command(command, serial)

        if success:
            return True, f"Llamando a {clean_number}"
        return False, f"Error al llamar: {output}"

    def end_call(self, serial: str) -> Tuple[bool, str]:
        """Finaliza la llamada actual"""
        # Método 1: KeyEvent ENDCALL
        success, output = self.run_command('shell input keyevent KEYCODE_ENDCALL', serial)

        if not success:
            # Método 2: Service call
            success, output = self.run_command(
                'shell service call phone 5',  # Puede variar según versión Android
                serial
            )

        return success, "Llamada finalizada" if success else f"Error: {output}"

    def answer_call(self, serial: str) -> Tuple[bool, str]:
        """
        Contesta una llamada entrante.
        Usa múltiples métodos en secuencia hasta que uno funcione.
        """
        logger.info(f"Intentando contestar llamada en {serial}")

        # Verificar estado inicial
        initial_state = self.get_call_state(serial)
        logger.info(f"Estado inicial: {initial_state}")

        if initial_state == 'offhook':
            return True, "Llamada ya activa"

        # Método 1: KeyEvent 5 (CALL) - el más universal
        self.run_command('shell input keyevent 5', serial)
        time.sleep(1)
        if self.get_call_state(serial) == 'offhook':
            logger.info("Contestada con keyevent 5")
            return True, "Llamada contestada"

        # Método 2: KeyEvent 79 (HEADSETHOOK)
        self.run_command('shell input keyevent 79', serial)
        time.sleep(1)
        if self.get_call_state(serial) == 'offhook':
            logger.info("Contestada con keyevent 79")
            return True, "Llamada contestada"

        # Método 3: Swipe en pantalla (gesto de contestar)
        success, output = self.run_command('shell wm size', serial)
        if success and 'x' in output:
            try:
                size_part = output.split(':')[-1].strip()
                width, height = map(int, size_part.split('x'))

                # Swipe hacia arriba (contestar)
                cx = width // 2
                self.run_command(f'shell input swipe {cx} {int(height*0.85)} {cx} {int(height*0.4)} 400', serial)
                time.sleep(1)
                if self.get_call_state(serial) == 'offhook':
                    return True, "Llamada contestada (swipe)"

                # Swipe hacia derecha
                self.run_command(f'shell input swipe {int(width*0.2)} {int(height*0.75)} {int(width*0.8)} {int(height*0.75)} 400', serial)
                time.sleep(1)
                if self.get_call_state(serial) == 'offhook':
                    return True, "Llamada contestada (swipe)"

            except Exception as e:
                logger.warning(f"Error swipe: {e}")

        # Verificar una última vez
        if self.get_call_state(serial) == 'offhook':
            return True, "Llamada contestada"

        return False, "No se pudo contestar - habilitar permisos USB de seguridad"

    def reject_call(self, serial: str) -> Tuple[bool, str]:
        """Rechaza una llamada entrante"""
        return self.end_call(serial)

    def get_call_state(self, serial: str) -> str:
        """
        Obtiene el estado actual de llamada.
        Maneja dual SIM: si cualquier SIM tiene llamada, retorna ese estado.

        Returns:
            str: 'idle', 'ringing', 'offhook' (activa), 'unknown'
        """
        success, output = self.run_command(
            'shell dumpsys telephony.registry | grep mCallState',
            serial
        )

        if success and output:
            # Buscar en todas las líneas (dual SIM)
            # Prioridad: offhook > ringing > idle
            has_offhook = False
            has_ringing = False
            has_idle = False

            for line in output.split('\n'):
                line_upper = line.upper()

                # Formato numérico: mCallState=0/1/2
                if '=2' in line or 'OFFHOOK' in line_upper:
                    has_offhook = True
                elif '=1' in line or 'RINGING' in line_upper:
                    has_ringing = True
                elif '=0' in line or 'IDLE' in line_upper:
                    has_idle = True

            # Retornar en orden de prioridad
            if has_offhook:
                return 'offhook'
            elif has_ringing:
                return 'ringing'
            elif has_idle:
                return 'idle'

        return 'unknown'

    # ==================== CONTROL DE RED ====================

    def set_airplane_mode(self, serial: str, enable: bool) -> Tuple[bool, str]:
        """Activa/desactiva modo avión"""
        state = '1' if enable else '0'

        # Establecer configuración
        success1, _ = self.run_command(
            f'shell settings put global airplane_mode_on {state}',
            serial
        )

        # Enviar broadcast para que el sistema actualice
        success2, _ = self.run_command(
            'shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state ' + str(enable).lower(),
            serial
        )

        if serial in self.devices:
            self.devices[serial].airplane_mode = enable

        action = "activado" if enable else "desactivado"
        return success1, f"Modo avión {action}"

    def set_wifi(self, serial: str, enable: bool) -> Tuple[bool, str]:
        """Activa/desactiva WiFi"""
        action = 'enable' if enable else 'disable'
        return self.run_command(f'shell svc wifi {action}', serial)

    def set_mobile_data(self, serial: str, enable: bool) -> Tuple[bool, str]:
        """Activa/desactiva datos móviles"""
        action = 'enable' if enable else 'disable'
        return self.run_command(f'shell svc data {action}', serial)

    # ==================== TIPO DE RED ====================

    # Índice posicional en el selector "Tipo de red preferida".
    # El orden siempre es el mismo sin importar las etiquetas del operador:
    #   Posición 0 (arriba): 5G/4G/3G/2G
    #   Posición 1: 4G/3G/2G
    #   Posición 2 (abajo): 3G/2G
    NETWORK_MODE_INDEX = {
        '5g':   0,   # 5G/4G/3G/2G (Automático) — opción más alta
        'auto': 0,   # igual que 5g
        '4g':   1,   # 4G/3G/2G (Automático)
        '3g':   2,   # 3G/2G (Automático)
    }

    # Fabricantes de la familia Transsion (Infinix, Tecno, itel)
    TRANSSION_MANUFACTURERS = {'transsion', 'infinix', 'tecno', 'itel'}

    def _is_transsion_device(self, serial: str) -> bool:
        """Detecta si el dispositivo es de la familia Transsion (Infinix, Tecno, itel)."""
        mfr = self._get_prop(serial, 'ro.product.manufacturer').lower().strip()
        return any(m in mfr for m in self.TRANSSION_MANUFACTURERS)

    def _open_operator_settings(self, serial: str, sim_slot: int = 0) -> Tuple[bool, str]:
        """
        Abre la pantalla de configuración del operador SIM.
        - Transsion (Infinix/Tecno/itel): usa NETWORK_OPERATOR_SETTINGS que llega directo.
        - Xiaomi y otros: abre MobileNetworkSettings y navega al operador por nombre.
        Retorna (ok, operator_name). Deja la pantalla en la configuración del operador.
        """
        if sim_slot == 0:
            sim_slot = self._get_active_sim_slot(serial)

        self.run_command('shell input keyevent WAKEUP', serial)
        time.sleep(0.5)
        self.run_command('shell input keyevent 82', serial)
        time.sleep(0.5)

        canonical_name = self._get_sim_operator_name(serial, sim_slot)
        sim_label      = self._get_sim_label(serial, sim_slot)
        operator_name  = canonical_name or sim_label or f'SIM{sim_slot}'

        if self._is_transsion_device(serial):
            # ── Infinix / Tecno / itel ──────────────────────────────────────────
            # NETWORK_OPERATOR_SETTINGS abre directamente la pantalla del operador
            # activo (SIM 1 por defecto) sin necesidad de navegar por nombre.
            self.run_command(
                'shell am start -a android.settings.NETWORK_OPERATOR_SETTINGS',
                serial
            )
            time.sleep(2)
            logger.info(f"Transsion: pantalla de operador abierta directamente ({operator_name})")
            return True, operator_name

        # ── Xiaomi y otros ──────────────────────────────────────────────────────
        # Abre MobileNetworkSettings y busca el operador por nombre para navegar.
        self.run_command(
            'shell am start -S -n com.android.phone/.settings.MobileNetworkSettings',
            serial
        )
        time.sleep(2)

        if not canonical_name and not sim_label:
            return False, f"No se pudo obtener el nombre del operador para SIM {sim_slot}"

        # Dump UI
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        success, ui_xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)
        if not success or not ui_xml:
            return False, "No se pudo leer la UI de ajustes"

        # Intentar buscar: 1) nombre canónico, 2) etiqueta SIM, 3) búsqueda parcial
        names_to_try = []
        if canonical_name:
            names_to_try.append(canonical_name)
        if sim_label and sim_label != canonical_name:
            names_to_try.append(sim_label)

        match = None
        matched_name = ''
        for name in names_to_try:
            pattern = rf'text="({re.escape(name)})".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            match = re.search(pattern, ui_xml, re.IGNORECASE)
            if match:
                matched_name = name
                break
            # Buscar como texto parcial
            pattern = rf'text="[^"]*{re.escape(name)}[^"]*".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            m2 = re.search(pattern, ui_xml, re.IGNORECASE)
            if m2:
                match = m2
                matched_name = name
                break

        if not match:
            tried = ' / '.join(names_to_try)
            return False, f"Operador '{tried}' no encontrado en Redes móviles"

        # Extraer bounds (match puede tener 4 o 5 groups dependiendo de la regex)
        groups = match.groups()
        if len(groups) == 5:
            x1, y1, x2, y2 = int(groups[1]), int(groups[2]), int(groups[3]), int(groups[4])
        else:
            x1, y1, x2, y2 = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        logger.info(f"Tap operador '{matched_name}' en ({cx}, {cy})")
        self.run_command(f'shell input tap {cx} {cy}', serial)
        time.sleep(2)

        return True, canonical_name or sim_label

    def _close_settings(self, serial: str, n: int = 4):
        """Cierra las pantallas de ajustes abiertas."""
        for _ in range(n):
            self.run_command('shell input keyevent BACK', serial)
            time.sleep(0.3)

    def set_volte(self, serial: str, enabled: bool, sim_slot: int = 0) -> Tuple[bool, str]:
        """
        Activa o desactiva VoLTE via UI automation.
        Navegación: MobileNetworkSettings → operador → buscar switch VoLTE → toggle si necesario.
        """
        action = "activar" if enabled else "desactivar"
        logger.info(f"VoLTE: {action} en {serial}")

        ok, result = self._open_operator_settings(serial, sim_slot)
        if not ok:
            self._close_settings(serial)
            return False, result

        # Leer UI para buscar el toggle de VoLTE
        ok, xml = self._dump_and_read_ui(serial)
        if not ok or not xml:
            self._close_settings(serial)
            return False, "No se pudo leer la pantalla del operador"

        # Buscar texto "VoLTE" o "Llamadas VoLTE" o "Llamadas HD" o "VoLTE calls"
        volte_patterns = [
            r'text="[^"]*[Vv]o[Ll][Tt][Ee][^"]*"',
            r'text="[^"]*[Ll]lamadas HD[^"]*"',
        ]
        volte_found = False
        for vp in volte_patterns:
            if re.search(vp, xml):
                volte_found = True
                break

        if not volte_found:
            # Scroll hacia abajo por si el toggle está fuera de pantalla
            self.run_command('shell input swipe 540 1800 540 800 500', serial)
            time.sleep(1)
            ok, xml = self._dump_and_read_ui(serial)
            if not ok or not xml:
                self._close_settings(serial)
                return False, "No se pudo leer UI después de scroll"

        # Buscar el switch de VoLTE: un android.widget.Switch cerca de texto VoLTE
        # Estrategia: buscar todos los switches y el texto VoLTE, encontrar el más cercano
        volte_text_match = re.search(
            r'text="([^"]*[Vv]o[Ll][Tt][Ee][^"]*)".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml
        )
        if not volte_text_match:
            volte_text_match = re.search(
                r'text="([^"]*[Ll]lamadas HD[^"]*)".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml
            )

        if not volte_text_match:
            self._close_settings(serial)
            return False, "No se encontró toggle VoLTE en la pantalla del operador"

        volte_y = (int(volte_text_match.group(3)) + int(volte_text_match.group(5))) // 2

        # Buscar el Switch en la misma fila (similar Y)
        switch_pattern = r'class="android\.widget\.Switch"[^>]*checked="(true|false)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        switches = list(re.finditer(switch_pattern, xml))

        best_switch = None
        best_distance = 9999
        for sw in switches:
            sw_y = (int(sw.group(3)) + int(sw.group(5))) // 2
            distance = abs(sw_y - volte_y)
            if distance < best_distance:
                best_distance = distance
                best_switch = sw

        if not best_switch or best_distance > 150:
            # Fallback: buscar switch por checked cerca del texto VoLTE
            # Intentar encontrar nodo clickable en la misma área
            switch_pattern2 = r'class="android\.widget\.Switch"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*checked="(true|false)"'
            switches2 = list(re.finditer(switch_pattern2, xml))
            for sw in switches2:
                sw_y = (int(sw.group(2)) + int(sw.group(4))) // 2
                distance = abs(sw_y - volte_y)
                if distance < best_distance:
                    best_distance = distance
                    best_switch = sw

        if not best_switch or best_distance > 150:
            self._close_settings(serial)
            return False, "No se encontró switch VoLTE cerca del texto"

        # Leer estado actual del switch
        is_checked = 'checked="true"' in best_switch.group(0)
        logger.info(f"VoLTE switch actual: {'ON' if is_checked else 'OFF'}, deseado: {'ON' if enabled else 'OFF'}")

        if is_checked == enabled:
            self._close_settings(serial)
            return True, f"VoLTE ya {'activado' if enabled else 'desactivado'}"

        # Tap en el switch para cambiar estado
        # Extraer bounds del switch
        bounds_match = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', best_switch.group(0))
        if bounds_match:
            x1, y1, x2, y2 = int(bounds_match.group(1)), int(bounds_match.group(2)), int(bounds_match.group(3)), int(bounds_match.group(4))
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            self.run_command(f'shell input tap {cx} {cy}', serial)
            time.sleep(2)

        self._close_settings(serial)
        return True, f"VoLTE {'activado' if enabled else 'desactivado'}"

    def _ui_dump_and_find(self, serial: str, text: str) -> Tuple[bool, Optional[Tuple[int, int]], str]:
        """
        Hace dump de la UI y busca un elemento por texto.
        Returns: (encontrado, (cx, cy) o None, ui_xml)
        """
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        success, ui_xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)

        if not success or not ui_xml:
            return False, None, ""

        # Buscar texto exacto (usar .*? en vez de [^/]* porque resource-id contiene /)
        pattern = rf'text="{re.escape(text)}".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        match = re.search(pattern, ui_xml)

        # Si no encuentra exacto, buscar texto parcial
        if not match:
            pattern = rf'text="[^"]*{re.escape(text)}[^"]*".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            match = re.search(pattern, ui_xml)

        if match:
            x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            return True, (cx, cy), ui_xml

        return False, None, ui_xml

    def _ui_find_and_tap(self, serial: str, text: str, wait_after: float = 1.5) -> Tuple[bool, str]:
        """
        Busca un elemento por texto en la UI y hace tap.
        Returns: (success, message)
        """
        found, coords, ui_xml = self._ui_dump_and_find(serial, text)

        if not found:
            logger.warning(f"No se encontró '{text}' en la UI")
            return False, f"No se encontró '{text}' en la pantalla"

        cx, cy = coords
        logger.info(f"Tap en '{text}' en ({cx}, {cy})")
        self.run_command(f'shell input tap {cx} {cy}', serial)
        time.sleep(wait_after)

        return True, f"Tap en '{text}' ({cx}, {cy})"

    def _get_active_sim_slot(self, serial: str) -> int:
        """
        Detecta automáticamente qué slot SIM está activo (tiene tarjeta/eSIM).
        Revisa gsm.sim.state que devuelve 'LOADED,ABSENT' o 'ABSENT,LOADED' etc.
        Retorna 1 o 2. Por defecto retorna 1.
        """
        success, output = self.run_command('shell getprop gsm.sim.state', serial)
        if success and output:
            parts = [p.strip().upper() for p in output.split(',')]
            # Si slot 1 está cargado, retornar 1
            if len(parts) >= 1 and parts[0] == 'LOADED':
                return 1
            # Si slot 2 está cargado (y slot 1 no), retornar 2
            if len(parts) >= 2 and parts[1] == 'LOADED':
                return 2
        return 1

    def _parse_iphonesubinfo_parcel(self, output: str) -> str:
        """
        Parsea la respuesta Parcel Unicode de iphonesubinfo.
        Formato: Result: Parcel(... "'+.5.7.3.1.2.3.4.5.6.7'" ...)
        """
        # Extraer contenido entre comillas simples
        chars = re.findall(r"'([^']+)'", output)
        if chars:
            raw = ''.join(chars)
            number = ''.join(c for c in raw if c.isdigit() or c == '+')
            if len(number) >= 7:
                return number
        return ""

    def _get_phone_numbers(self, serial: str) -> Dict[int, str]:
        """
        Obtiene los numeros de telefono de cada SIM.
        Devuelve dict {1: "+573XXX", 2: "+573YYY"} con solo las SIMs con numero detectado.

        Cascada de metodos (Android 11+ restringió READ_PHONE_NUMBERS para service call):
          1. content://telephony/siminfo         — content provider, sin permisos extra
          2. dumpsys iphonesubinfo               — texto legible, Android 8-13
          3. getprop ril.msisdn*                 — algunos fabricantes (Qualcomm/MIUI)
          4. settings get global mobile_data_number — ajustes del sistema
          5. dumpsys telephony.registry          — mPhoneNumber, Android 12+
          6. service call iphonesubinfo          — fallback legacy
        """
        results: Dict[int, str] = {}

        def clean_num(raw: str) -> str:
            n = re.sub(r'[\s\-\(\)]', '', (raw or '').strip())
            if len(n) >= 7 and n.lower() not in ('null', 'unknown', '') and re.search(r'\d{5}', n):
                return n
            return ''

        # ── Metodo 1: content provider telephony/siminfo (sin filtro de columnas) ──────
        # La columna puede llamarse "number", "phone_number" o "icc_id" segun el fabricante.
        # Se trae todo y se busca cualquier campo que contenga un numero de telefono valido.
        ok, out = self.run_command(
            'shell content query --uri content://telephony/siminfo',
            serial
        )
        if ok and out:
            # Cada fila: "Row: N col1=val1, col2=val2, ..."
            # Buscamos slot y cualquier campo con numero de telefono (+57...)
            for row in out.splitlines():
                if 'Row:' not in row:
                    continue
                # Slot: sim_slot_index o slot_index
                slot_m = re.search(r'sim_slot_index=(\d+)', row)
                if not slot_m:
                    slot_m = re.search(r'slot(?:_index)?=(\d+)', row)
                slot = int(slot_m.group(1)) + 1 if slot_m else None

                # Numero: buscar campo "number=", "phone_number=", "msisdn=" con valor valido
                num = ''
                for field in re.findall(r'(?:number|phone_number|msisdn)=([^,\n]+)', row, re.IGNORECASE):
                    n = clean_num(field)
                    if n:
                        num = n
                        break

                if num:
                    results[slot if slot else len(results) + 1] = num

        if results:
            return results

        # ── Metodo 2: dumpsys iphonesubinfo ──────────────────────────────────────────
        ok, out = self.run_command('shell dumpsys iphonesubinfo', serial)
        if ok and out:
            phone_blocks = re.split(r'Phone\s*#\s*=\s*(\d+)', out)
            if len(phone_blocks) > 2:
                for i in range(1, len(phone_blocks) - 1, 2):
                    slot_num = int(phone_blocks[i]) + 1
                    block    = phone_blocks[i + 1]
                    m = re.search(r'Line 1 (?:Phone )?Number\s*=\s*([\+\d\s\-]+)', block)
                    if m:
                        n = clean_num(m.group(1))
                        if n:
                            results[slot_num] = n
            else:
                m = re.search(r'Line 1 (?:Phone )?Number\s*=\s*([\+\d\s\-]+)', out)
                if m:
                    n = clean_num(m.group(1))
                    if n:
                        results[1] = n

        if results:
            return results

        # ── Metodo 3: getprop ril.msisdn / ril.number ────────────────────────────────
        for prop in ['ril.msisdn1', 'ril.msisdn', 'ril.number', 'gsm.sim.msisdn']:
            ok, out = self.run_command(f'shell getprop {prop}', serial)
            if ok and out:
                for idx, part in enumerate(out.split(','), 1):
                    n = clean_num(part)
                    if n:
                        results[idx] = n
            if results:
                return results

        # ── Metodo 4: settings get global mobile_data_number ────────────────────────────
        for key in ['mobile_data_number', 'mobile_number', 'phone_number']:
            ok, out = self.run_command(f'shell settings get global {key}', serial)
            if ok and out:
                n = clean_num(out.strip())
                if n:
                    results[1] = n
                    return results

        # ── Metodo 5: dumpsys telephony.registry (mPhoneNumber, Android 12+) ──────────
        ok, out = self.run_command('shell dumpsys telephony.registry', serial)
        if ok and out:
            # Buscar mPhoneNumber o phoneNumber por slot
            slot_blocks = re.split(r'(?:slot|phone)\s*(?:id|index)?\s*=?\s*(\d+)', out, flags=re.IGNORECASE)
            if len(slot_blocks) > 2:
                for i in range(1, len(slot_blocks) - 1, 2):
                    slot_num = int(slot_blocks[i]) + 1
                    block = slot_blocks[i + 1]
                    for field in re.findall(r'm?[Pp]hone[Nn]umber\s*=\s*([^\s,\n]+)', block):
                        n = clean_num(field)
                        if n:
                            results[slot_num] = n
                            break
            else:
                for field in re.findall(r'm?[Pp]hone[Nn]umber\s*=\s*([^\s,\n]+)', out):
                    n = clean_num(field)
                    if n:
                        results[1] = n
                        break
            for field in re.findall(r'mNumber\s*=\s*([^\s,\n]+)', out):
                n = clean_num(field)
                if n and 1 not in results:
                    results[1] = n
                    break

        if results:
            return results

        # ── Metodo 6: service call iphonesubinfo (legacy, puede fallar en Android 11+) ─
        for slot in [1, 2]:
            for code in [16, 6, 11]:
                ok, out = self.run_command(
                    f'shell service call iphonesubinfo {code} i32 {slot}', serial
                )
                if ok and out:
                    n = self._parse_iphonesubinfo_parcel(out)
                    if n:
                        results[slot] = n
                        break
        if results:
            return results

        for code in [16, 6, 11, 3]:
            ok, out = self.run_command(f'shell service call iphonesubinfo {code}', serial)
            if ok and out:
                n = self._parse_iphonesubinfo_parcel(out)
                if n:
                    return {1: n}

        return {}

    def _get_phone_number(self, serial: str) -> str:
        """Compatibilidad: devuelve string de display con todos los numeros detectados."""
        nums = self._get_phone_numbers(serial)
        if not nums:
            return ""
        if len(nums) == 1:
            return next(iter(nums.values()))
        return " / ".join(f"SIM{s}: {n}" for s, n in sorted(nums.items()))

    def _get_sim_operator_name(self, serial: str, sim_slot: int = 0) -> str:
        """
        Obtiene el nombre canónico del operador para un slot SIM.
        Usa MCC/MNC (gsm.sim.operator.numeric) para identificar el operador real,
        independiente de etiquetas personalizadas del SIM.
        Fallback a gsm.sim.operator.alpha si MCC/MNC no está mapeado.
        """
        if sim_slot == 0:
            sim_slot = self._get_active_sim_slot(serial)
        idx = sim_slot - 1

        # Método 1: MCC/MNC → nombre canónico (más confiable)
        success, output = self.run_command('shell getprop gsm.sim.operator.numeric', serial)
        if success and output:
            parts = [p.strip() for p in output.split(',')]
            if idx < len(parts) and parts[idx]:
                canonical = self.MCCMNC_TO_OPERATOR.get(parts[idx])
                if canonical:
                    return canonical

        # Método 2: gsm.sim.operator.alpha (puede tener etiqueta personalizada)
        success, output = self.run_command('shell getprop gsm.sim.operator.alpha', serial)
        if success and output:
            parts = [p.strip() for p in output.split(',')]
            if idx < len(parts) and parts[idx]:
                return parts[idx]
        return ""

    def _get_sim_label(self, serial: str, sim_slot: int = 0) -> str:
        """
        Obtiene la etiqueta tal cual la reporta gsm.sim.operator.alpha.
        Puede ser diferente del nombre canónico (ej: '#UnaMejorRed' en vez de 'Movistar').
        """
        if sim_slot == 0:
            sim_slot = self._get_active_sim_slot(serial)
        success, output = self.run_command('shell getprop gsm.sim.operator.alpha', serial)
        if success and output:
            parts = [p.strip() for p in output.split(',')]
            idx = sim_slot - 1
            if idx < len(parts) and parts[idx]:
                return parts[idx]
        return ""

    def set_preferred_network(self, serial: str, mode: str, sim_slot: int = 0) -> Tuple[bool, str]:
        """
        Cambia el tipo de red usando la UI de ajustes del dispositivo.
        Navegación: MobileNetworkSettings → operador → Tipo de red preferida → seleccionar por posición.
        Las etiquetas varían por operador pero el orden siempre es: 5G, 4G, 3G (de arriba a abajo).
        """
        mode_lower = mode.lower().strip()
        target_index = self.NETWORK_MODE_INDEX.get(mode_lower)

        if target_index is None:
            return False, f"Modo no válido: {mode}. Usar: {list(self.NETWORK_MODE_INDEX.keys())}"

        logger.info(f"Cambiando red de {serial} a {mode} (posición {target_index} en selector)")

        ok, result = self._open_operator_settings(serial, sim_slot)
        if not ok:
            self._close_settings(serial)
            return False, result

        # 3. Tap en "Tipo de red preferida"
        found, msg = self._ui_find_and_tap(serial, "Tipo de red preferida", wait_after=1.5)
        if not found:
            # Scroll por si está fuera de pantalla
            self.run_command('shell input swipe 540 1800 540 800 500', serial)
            time.sleep(1)
            found, msg = self._ui_find_and_tap(serial, "Tipo de red preferida", wait_after=1.5)
        if not found:
            self._close_settings(serial)
            return False, "No se encontró 'Tipo de red preferida' en la configuración de SIM"

        # 4. Seleccionar opción por posición (las etiquetas varían por operador)
        # Dump UI del diálogo selector
        ok, xml = self._dump_and_read_ui(serial)
        if not ok or not xml:
            self._close_settings(serial)
            return False, "No se pudo leer el selector de red"

        # Buscar todos los CheckedTextView (opciones del radio dialog) ordenados por Y
        # Los atributos XML pueden venir en cualquier orden, así que buscamos cada nodo completo
        # y extraemos text y bounds por separado
        options = []
        for node_match in re.finditer(r'<node[^>]*class="android\.widget\.CheckedTextView"[^>]*/>', xml):
            node = node_match.group(0)
            text_m = re.search(r'text="([^"]*)"', node)
            bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
            if text_m and bounds_m:
                text = text_m.group(1)
                x_center = (int(bounds_m.group(1)) + int(bounds_m.group(3))) // 2
                y_center = (int(bounds_m.group(2)) + int(bounds_m.group(4))) // 2
                options.append({'text': text, 'cx': x_center, 'cy': y_center})

        # Ordenar por posición vertical (de arriba a abajo)
        options.sort(key=lambda o: o['cy'])

        if not options:
            self._close_settings(serial)
            return False, "No se encontraron opciones en el selector de red"

        if target_index >= len(options):
            available = [o['text'] for o in options]
            self._close_settings(serial)
            return False, f"Posición {target_index} no disponible. Opciones: {available}"

        selected = options[target_index]
        logger.info(f"Seleccionando posición {target_index}: '{selected['text']}' en ({selected['cx']}, {selected['cy']})")
        self.run_command(f"shell input tap {selected['cx']} {selected['cy']}", serial)
        time.sleep(1)

        # 5. Confirmar selección si hay botón "Aceptar" (Infinix/Tecno muestran diálogo con botón)
        #    En Xiaomi y otros la selección se aplica directamente sin confirmación.
        confirmed = self._ui_find_and_tap(serial, 'Aceptar', wait_after=1.0)
        if not confirmed[0]:
            # Intentar "OK" como fallback (algunos idiomas/ROMs)
            self._ui_find_and_tap(serial, 'OK', wait_after=1.0)

        # 6. Cerrar pantallas de ajustes
        self._close_settings(serial)

        # 7. Esperar a que la red se estabilice
        time.sleep(5)

        current = self.get_current_network_type(serial)
        logger.info(f"Red cambiada a {mode} ('{selected['text']}'). Red actual: {current}")

        return True, f"Red cambiada a '{selected['text']}' (actual: {current})"

    def get_preferred_network(self, serial: str) -> Tuple[str, int]:
        """Obtiene el tipo de red preferido actual."""
        success, output = self.run_command(
            'shell settings get global preferred_network_mode',
            serial
        )

        if success:
            first_value = output.split(',')[0].strip()
            try:
                value = int(first_value)
                mode_map = {33: 'auto', 9: '4g', 3: '3g', 1: '2g', 11: '4g', 25: '5g', 2: '3g'}
                name = mode_map.get(value, f"modo_{value}")
                return name, value
            except ValueError:
                pass

        return "unknown", -1

    def get_current_network_type(self, serial: str) -> str:
        """Obtiene el tipo de red actual en uso"""
        success, output = self.run_command(
            'shell dumpsys telephony.registry',
            serial
        )

        if success and output:
            # Buscar getRilVoiceRadioTechnology en la primera línea de mServiceState
            for line in output.split('\n'):
                if 'getRilVoiceRadioTechnology' in line:
                    upper = line.upper()
                    if 'NR)' in upper:
                        return '5G'
                    elif 'LTE)' in upper:
                        return '4G'
                    elif any(x + ')' in upper for x in ['UMTS', 'HSDPA', 'HSPA', 'HSUPA']):
                        return '3G'
                    elif any(x + ')' in upper for x in ['EDGE', 'GPRS', 'GSM']):
                        return '2G'
                    break

        return 'unknown'

    # ==================== SMS ====================

    def _run_service_call_sms(self, serial: str, tx_code: int, number: str, message: str) -> Tuple[bool, str]:
        """
        Ejecuta service call isms usando subprocess con lista de args.
        El comando shell se pasa como string único para preservar las comillas.
        """
        escaped_msg = message.replace('"', '\\"')
        shell_cmd = (
            f'service call isms {tx_code} '
            f'i32 0 '
            f's16 "com.android.mms" '
            f's16 "null" '
            f's16 "{number}" '
            f's16 "null" '
            f's16 "{escaped_msg}" '
            f's16 "null" '
            f's16 "null" '
            f'i32 0 '
            f'i64 0'
        )
        cmd = [ADB_PATH, '-s', serial, 'shell', shell_cmd]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            output = result.stdout.strip()
            if result.returncode == 0 and 'error' not in output.lower() and 'not fully consumed' not in output.lower():
                return True, output
            return False, output or result.stderr.strip()
        except Exception as e:
            return False, str(e)

    def send_sms(self, serial: str, phone_number: str, message: str) -> Tuple[bool, str]:
        """
        Envía un SMS usando service call isms (funciona en background, durante llamadas).
        Usa subprocess con lista de args para evitar problemas de quoting en Windows.
        """
        clean_number = re.sub(r'[^\d+]', '', phone_number)
        logger.info(f"Enviando SMS de {serial} a {clean_number}: '{message}'")

        # Método 1: service call isms - funciona en background sin interrumpir llamadas
        # tx=5 funciona en Android 16
        for tx_code in [5, 7]:
            success, output = self._run_service_call_sms(serial, tx_code, clean_number, message)
            if success:
                logger.info(f"SMS enviado con service call isms tx={tx_code}: {output}")
                return True, f"SMS enviado a {clean_number}"
            logger.debug(f"service call isms tx={tx_code} falló: {output}")

        # Método 2: am start + UI automation (fallback, no funciona durante llamadas)
        logger.info("service call falló, intentando con am start + UI tap")
        self.run_command(
            f'shell am start -a android.intent.action.SENDTO '
            f'-d sms:{clean_number} '
            f'--es sms_body "{message}"',
            serial
        )
        time.sleep(2)

        # Buscar y tap en botón de enviar (por texto o content-desc)
        found = False
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        _, ui_xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)
        if ui_xml:
            for send_text in ['Enviar', 'Send', 'enviar', 'send']:
                # Buscar por text
                pattern = rf'text="[^"]*{send_text}[^"]*".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
                match = re.search(pattern, ui_xml, re.IGNORECASE)
                if not match:
                    # Buscar por content-desc
                    pattern = rf'content-desc="[^"]*{send_text}[^"]*".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
                    match = re.search(pattern, ui_xml, re.IGNORECASE)
                if match:
                    x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    self.run_command(f'shell input tap {cx} {cy}', serial)
                    time.sleep(1)
                    found = True
                    break

        # Cerrar la app de mensajes
        self.run_command('shell input keyevent BACK', serial)
        time.sleep(0.5)
        self.run_command('shell input keyevent BACK', serial)
        time.sleep(0.5)
        self.run_command('shell input keyevent HOME', serial)

        if found:
            return True, f"SMS enviado a {clean_number} (UI)"
        return False, "No se pudo enviar el SMS"

    def check_sms_received(self, serial: str, from_number: str, expected_text: str,
                           timeout: int = 30) -> Tuple[bool, str]:
        """
        Verifica si se recibió un SMS de un número específico con el texto esperado.
        Consulta la bandeja de entrada SMS vía content provider.
        """
        clean_number = re.sub(r'[^\d+]', '', from_number)
        # Usar los últimos 10 dígitos para comparar (evitar problemas con +57, etc.)
        number_suffix = clean_number[-10:] if len(clean_number) >= 10 else clean_number

        logger.info(f"Verificando SMS de {clean_number} en {serial} (timeout {timeout}s)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            success, output = self.run_command(
                'shell content query --uri content://sms/inbox '
                '--projection "address,body,date" '
                '--sort "date DESC LIMIT 5"',
                serial
            )

            if success and output:
                for line in output.split('\n'):
                    if number_suffix in line and expected_text in line:
                        logger.info(f"SMS recibido: {line.strip()}")
                        return True, f"SMS recibido de {clean_number}: '{expected_text}'"

            time.sleep(3)

        return False, f"SMS de {clean_number} no recibido después de {timeout}s"

    # ==================== UTILIDADES ====================

    def capture_screenshot(self, serial: str, local_path: str) -> Tuple[bool, str]:
        """Captura screenshot del dispositivo"""
        remote_path = '/sdcard/screenshot_temp.png'

        # Capturar
        success, _ = self.run_command(f'shell screencap -p {remote_path}', serial)
        if not success:
            return False, "Error capturando screenshot"

        # Descargar
        success, _ = self.run_command(f'pull {remote_path} "{local_path}"', serial)
        if not success:
            return False, "Error descargando screenshot"

        # Limpiar
        self.run_command(f'shell rm {remote_path}', serial)

        return True, local_path

    # ==================== SPEEDTEST ====================

    SPEEDTEST_PKG = 'org.zwanoo.android.speedtest'

    def launch_speedtest(self, serial: str) -> Tuple[bool, str]:
        """Lanza la app Speedtest (force-stop + relaunch para estado limpio)."""
        self.run_command(f'shell am force-stop {self.SPEEDTEST_PKG}', serial)
        time.sleep(1)
        self.run_command('shell input keyevent WAKEUP', serial)
        time.sleep(0.5)
        self.run_command('shell input keyevent 82', serial)
        time.sleep(0.5)
        self.run_command(
            f'shell monkey -p {self.SPEEDTEST_PKG} -c android.intent.category.LAUNCHER 1',
            serial
        )
        time.sleep(4)

        # Verificar que go_button está visible
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        ok, xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)
        if ok and 'go_button' in xml:
            return True, "Speedtest app lista"
        return False, "No se encontró el botón INICIO en Speedtest"

    def start_speedtest_run(self, serial: str) -> Tuple[bool, str]:
        """Presiona el botón INICIO/GO en la app Speedtest."""
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        ok, xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)

        if not ok or not xml:
            return False, "No se pudo leer UI de Speedtest"

        match = re.search(
            r'resource-id="org.zwanoo.android.speedtest:id/go_button".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml
        )
        if not match:
            return False, "No se encontró el botón GO/INICIO"

        x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        logger.info(f"Tap GO button en ({cx}, {cy})")
        self.run_command(f'shell input tap {cx} {cy}', serial)
        return True, f"Speedtest iniciado (tap en {cx},{cy})"

    def wait_speedtest_complete(self, serial: str, timeout: int = 120) -> Tuple[bool, str]:
        """
        Espera a que el speedtest termine.
        Detecta finalización buscando textos de resultado o resource-ids de la pantalla final.
        """
        logger.info(f"Esperando speedtest en {serial} (max {timeout}s)...")
        start = time.time()
        # Esperar mínimo 45 segundos antes de empezar a verificar
        time.sleep(45)

        while time.time() - start < timeout:
            # Intentar dump (puede fallar por animaciones)
            self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
            time.sleep(1)
            ok, xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)

            if ok and xml:
                # Buscar indicadores de que terminó (español e inglés)
                finish_indicators = [
                    'Prueba de nuevo', 'Resultado detallado',
                    'Test Again', 'Detailed result',
                    'suite_completed_feedback',
                    'txt_test_result_value',
                ]
                for indicator in finish_indicators:
                    if indicator in xml:
                        logger.info(f"Speedtest completado (indicador: {indicator})")
                        return True, "Speedtest completado"

            time.sleep(5)

        return False, f"Timeout ({timeout}s) esperando speedtest"

    def capture_speedtest_screenshot(self, serial: str, save_path: str) -> Tuple[bool, str]:
        """Captura screenshot del resultado del speedtest."""
        remote = '/data/local/tmp/speedtest_screenshot.png'
        self.run_command(f'shell screencap -p {remote}', serial)
        time.sleep(0.5)
        success, _ = self.run_command(f'pull {remote} "{save_path}"', serial)
        self.run_command(f'shell rm {remote}', serial)
        if success:
            return True, save_path
        return False, "Error guardando screenshot"

    def read_speedtest_results(self, serial: str) -> Dict[str, Optional[str]]:
        """
        Lee los resultados del speedtest desde la pantalla de resultados via UI dump.
        Extrae download, upload y ping emparejando títulos y valores por orden.
        Retorna dict con 'download', 'upload', 'ping' (valores como string o None).
        """
        ok, xml = self._dump_and_read_ui(serial)
        if not ok or not xml:
            return {'download': None, 'upload': None, 'ping': None}

        # Extraer títulos y valores en orden de aparición en el XML
        titles = []
        values = []
        for m in re.finditer(
            r'<node[^>]*resource-id="org\.zwanoo\.android\.speedtest:id/'
            r'(txt_test_result_title|txt_test_result_value)"[^>]*/>',
            xml
        ):
            node = m.group(0)
            rid = m.group(1)
            text_m = re.search(r'text="([^"]*)"', node)
            if text_m:
                if rid == 'txt_test_result_title':
                    titles.append(text_m.group(1))
                else:
                    values.append(text_m.group(1))

        # Emparejar por orden: título[i] → value[i]
        result = {'download': None, 'upload': None, 'ping': None}
        for i, title in enumerate(titles):
            if i >= len(values):
                break
            key = title.lower()
            if key in ('bajada', 'download'):
                result['download'] = values[i]
            elif key in ('subida', 'upload'):
                result['upload'] = values[i]
            elif key == 'ping':
                result['ping'] = values[i]

        logger.info(f"Speedtest results: download={result['download']} upload={result['upload']} ping={result['ping']}")
        return result

    def get_logcat(self, serial: str, tag: str = None, lines: int = 100) -> str:
        """Obtiene logs del dispositivo"""
        cmd = f'shell logcat -d -t {lines}'
        if tag:
            cmd += f' | grep -i {tag}'

        success, output = self.run_command(cmd, serial, timeout=60)
        return output if success else ""

    def clear_logcat(self, serial: str) -> Tuple[bool, str]:
        """Limpia el buffer de logcat"""
        return self.run_command('shell logcat -c', serial)

    # ==================== DEBUGLOGGER (MediaTek) ====================

    DEBUGLOGGER_PKG = 'com.debug.loggerui'
    DEBUGLOGGER_LOG_PATH = '/data/debuglogger/'

    def _open_debuglogger(self, serial: str):
        """Abre la app DebugLoggerUI en la pantalla principal (MainActivity)."""
        self.run_command('shell input keyevent WAKEUP', serial)
        time.sleep(0.5)
        self.run_command('shell input keyevent 82', serial)
        time.sleep(0.5)
        self.run_command(
            f'shell am start -n {self.DEBUGLOGGER_PKG}/.MainActivity', serial
        )
        time.sleep(3)
        # Verificar si estamos en la pantalla principal (tiene startStopToggleButton)
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        ok, xml = self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)
        if ok and xml and 'startStopToggleButton' not in xml:
            # No estamos en la pantalla principal, force-stop y reabrir
            logger.info("DebugLogger no en pantalla principal, reiniciando app")
            self.run_command(f'shell am force-stop {self.DEBUGLOGGER_PKG}', serial)
            time.sleep(1)
            self.run_command(
                f'shell am start -n {self.DEBUGLOGGER_PKG}/.MainActivity', serial
            )
            time.sleep(3)

    def _dump_and_read_ui(self, serial: str) -> Tuple[bool, str]:
        """Hace dump del UI y lo lee. Retorna (ok, xml)."""
        self.run_command('shell uiautomator dump /data/local/tmp/ui.xml', serial)
        time.sleep(1)
        return self.run_command('exec-out cat /data/local/tmp/ui.xml', serial)

    def _find_and_tap(self, xml: str, pattern: str, serial: str) -> Tuple[bool, str]:
        """Busca un elemento por regex en el XML y lo toca. Retorna (ok, msg)."""
        match = re.search(pattern, xml)
        if not match:
            return False, "Elemento no encontrado"
        x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        self.run_command(f'shell input tap {cx} {cy}', serial)
        return True, f"Tap en ({cx},{cy})"

    def get_debuglogger_status(self, serial: str) -> str:
        """Obtiene el estado actual del DebugLogger: 'recording', 'stopped' o 'unknown'."""
        ok, xml = self._dump_and_read_ui(serial)
        if ok and xml and 'debug.loggerui' in xml:
            if 'MobileLog recording' in xml:
                return 'recording'
            elif 'MobileLog stopped' in xml:
                return 'stopped'
        return 'unknown'

    def start_debuglogger(self, serial: str) -> Tuple[bool, str]:
        """Inicia la captura de DebugLogger."""
        self._open_debuglogger(serial)
        status = self.get_debuglogger_status(serial)
        if status == 'recording':
            return True, "DebugLogger ya estaba grabando"

        # Tocar el botón start/stop para iniciar
        ok, xml = self._dump_and_read_ui(serial)
        if not ok or not xml:
            return False, "No se pudo leer UI de DebugLogger"

        ok, msg = self._find_and_tap(
            xml,
            r'resource-id="com.debug.loggerui:id/startStopToggleButton".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            serial
        )
        if not ok:
            return False, "No se encontró botón start/stop"

        # Verificar con reintentos (el UI tarda en actualizar)
        for attempt in range(3):
            time.sleep(3)
            status = self.get_debuglogger_status(serial)
            if status == 'recording':
                logger.info(f"DebugLogger iniciado en {serial}")
                return True, "DebugLogger iniciado"
        return False, f"No se pudo iniciar DebugLogger (estado: {status})"

    def stop_debuglogger(self, serial: str) -> Tuple[bool, str]:
        """Detiene la captura de DebugLogger."""
        self._open_debuglogger(serial)
        status = self.get_debuglogger_status(serial)
        if status == 'stopped':
            return True, "DebugLogger ya estaba detenido"

        ok, xml = self._dump_and_read_ui(serial)
        if not ok or not xml:
            return False, "No se pudo leer UI de DebugLogger"

        ok, msg = self._find_and_tap(
            xml,
            r'resource-id="com.debug.loggerui:id/startStopToggleButton".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            serial
        )
        if not ok:
            return False, "No se encontró botón start/stop"

        time.sleep(5)
        status = self.get_debuglogger_status(serial)
        if status == 'stopped':
            logger.info(f"DebugLogger detenido en {serial}")
            return True, "DebugLogger detenido"
        return False, f"No se pudo detener DebugLogger (estado: {status})"

    def pull_debuglogger_logs(self, serial: str, local_dir: str) -> Tuple[bool, str]:
        """Extrae los logs del DebugLogger a una carpeta local."""
        os.makedirs(local_dir, exist_ok=True)

        # Verificar que hay logs y listar subcarpetas
        ok, output = self.run_command(f'shell ls {self.DEBUGLOGGER_LOG_PATH}', serial)
        if not ok or not output.strip():
            return False, "No hay logs en el dispositivo"

        # Pull cada subcarpeta/archivo individualmente para evitar nesting extra
        items = [item.strip() for item in output.strip().split('\n') if item.strip()]
        pulled = 0
        for item in items:
            remote_path = f'{self.DEBUGLOGGER_LOG_PATH}{item}'
            cmd = [ADB_PATH, '-s', serial, 'pull', remote_path, local_dir]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    pulled += 1
            except Exception as e:
                logger.warning(f"Error pulling {item}: {e}")

        if pulled > 0:
            logger.info(f"Logs extraídos a {local_dir} ({pulled} items)")
            return True, f"Logs extraídos a {local_dir}"
        return False, "No se pudo extraer ningún log"

    def clear_debuglogger_logs(self, serial: str) -> Tuple[bool, str]:
        """Limpia los logs del DebugLogger via UI.
        Flujo: clearLogImageButton → pantalla folders → 'Más opciones' → Clear All → Aceptar
        """
        self._open_debuglogger(serial)
        status = self.get_debuglogger_status(serial)
        if status == 'recording':
            return False, "Detén el DebugLogger antes de limpiar"

        # Paso 1: Tocar botón clearLogImageButton (papelera, esquina inferior derecha)
        ok, xml = self._dump_and_read_ui(serial)
        if not ok or not xml:
            return False, "No se pudo leer UI"
        ok, msg = self._find_and_tap(
            xml,
            r'resource-id="com.debug.loggerui:id/clearLogImageButton".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            serial
        )
        if not ok:
            return False, "No se encontró botón clear (puede que no haya logs)"
        time.sleep(3)

        # Paso 2: Pantalla "Clear DebugLogger Files" con folders.
        # Tocar "Más opciones" (3 puntos, esquina superior derecha)
        ok, xml2 = self._dump_and_read_ui(serial)
        if not ok or not xml2:
            return False, "No se pudo leer pantalla de clear"

        # Buscar por content-desc (puede ser "Más opciones" o "More options")
        ok, msg = self._find_and_tap(
            xml2,
            r'content-desc="M.s opciones".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            serial
        )
        if not ok:
            ok, msg = self._find_and_tap(
                xml2,
                r'content-desc="More options".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                serial
            )
        if not ok:
            self.run_command('shell input keyevent BACK', serial)
            return False, "No se encontró menú de 3 puntos"
        time.sleep(2)

        # Paso 3: Menú desplegable con "Clear All" y "Cancel"
        # Este menú es un diálogo (no se cierra al hacer dump)
        ok, xml3 = self._dump_and_read_ui(serial)
        if not ok or not xml3:
            self.run_command('shell input keyevent BACK', serial)
            return False, "No se pudo leer menú desplegable"

        ok, msg = self._find_and_tap(
            xml3,
            r'text="Clear All".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            serial
        )
        if not ok:
            self.run_command('shell input keyevent BACK', serial)
            return False, "No se encontró opción 'Clear All'"
        time.sleep(2)

        # Paso 4: Diálogo de confirmación con "Cancelar" / "Aceptar"
        ok, xml4 = self._dump_and_read_ui(serial)
        if not ok or not xml4:
            return False, "No se pudo leer diálogo de confirmación"

        # Buscar botón "Aceptar" (android:id/button1)
        ok, msg = self._find_and_tap(
            xml4,
            r'resource-id="android:id/button1".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            serial
        )
        if not ok:
            ok, msg = self._find_and_tap(
                xml4,
                r'text="Aceptar".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                serial
            )
        if not ok:
            self.run_command('shell input keyevent BACK', serial)
            return False, "No se encontró botón Aceptar"

        # Paso 5: Esperar a que se borren (la app vuelve a MainActivity automáticamente)
        logger.info(f"Esperando limpieza de logs en {serial}...")
        time.sleep(15)

        # Verificar que volvimos a la pantalla principal
        ok, xml5 = self._dump_and_read_ui(serial)
        if ok and xml5 and 'startStopToggleButton' in xml5:
            logger.info(f"Logs limpiados correctamente en {serial}")
            return True, "Logs limpiados correctamente"

        return True, "Clear All ejecutado (verificar manualmente)"

    # ==================== MÉTODOS AUXILIARES FOTA ====================

    def reboot_and_wait(self, serial: str, timeout: int = 120) -> Tuple[bool, str]:
        """Reinicia el dispositivo y espera a que vuelva a conectarse"""
        logger.info(f"Reiniciando dispositivo {serial}...")
        success, _ = self.run_command("reboot", serial)
        if not success:
            return False, "No se pudo enviar comando de reinicio"

        time.sleep(10)  # Esperar a que se desconecte

        start = time.time()
        while time.time() - start < timeout:
            ok, output = self.run_command("devices")
            if ok and serial in output and 'device' in output:
                # Verificar que el dispositivo está completamente arrancado
                time.sleep(5)
                boot_ok, boot_val = self.run_command("shell getprop sys.boot_completed", serial)
                if boot_ok and boot_val.strip() == '1':
                    logger.info(f"Dispositivo {serial} reiniciado correctamente")
                    return True, "Dispositivo reiniciado correctamente"
            time.sleep(5)

        return False, f"Timeout ({timeout}s) esperando reconexión del dispositivo"

    def get_sw_version(self, serial: str) -> Dict[str, str]:
        """Obtiene información de versión de software del dispositivo"""
        props = {
            'display_id': 'ro.build.display.id',
            'incremental': 'ro.build.version.incremental',
            'security_patch': 'ro.build.version.security_patch',
            'release': 'ro.build.version.release',
            'sdk': 'ro.build.version.sdk',
            'model': 'ro.product.model',
            'manufacturer': 'ro.product.manufacturer',
            'build_date': 'ro.build.date',
        }
        result = {}
        for key, prop in props.items():
            result[key] = self._get_prop(serial, prop)
        return result

    def get_installed_app_version(self, serial: str, package: str) -> str:
        """Obtiene la versión instalada de una app por su package name"""
        success, output = self.run_command(
            f"shell dumpsys package {package} | grep versionName", serial
        )
        if success and output:
            match = re.search(r'versionName=(.+)', output)
            if match:
                return match.group(1).strip()
        return ""

    def check_bluetooth_enabled(self, serial: str) -> bool:
        """Verifica si Bluetooth está habilitado"""
        success, output = self.run_command(
            "shell settings get global bluetooth_on", serial
        )
        return success and output.strip() == '1'

    def set_bluetooth(self, serial: str, enable: bool) -> Tuple[bool, str]:
        """Habilita o deshabilita Bluetooth"""
        action = "enable" if enable else "disable"
        # Método 1: svc bluetooth
        success, output = self.run_command(f"shell svc bluetooth {action}", serial)
        if success:
            time.sleep(2)
            current = self.check_bluetooth_enabled(serial)
            if current == enable:
                return True, f"Bluetooth {'habilitado' if enable else 'deshabilitado'}"

        # Método 2: am broadcast
        value = "true" if enable else "false"
        self.run_command(
            f"shell am broadcast -a android.bluetooth.adapter.action.REQUEST_ENABLE --ez enable {value}",
            serial
        )
        time.sleep(3)
        current = self.check_bluetooth_enabled(serial)
        if current == enable:
            return True, f"Bluetooth {'habilitado' if enable else 'deshabilitado'}"

        return False, f"No se pudo {'habilitar' if enable else 'deshabilitar'} Bluetooth"

    def launch_app(self, serial: str, package: str, activity: str = None) -> Tuple[bool, str]:
        """Lanza una aplicación genérica"""
        if activity:
            cmd = f"shell am start -n {package}/{activity}"
        else:
            cmd = f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
        success, output = self.run_command(cmd, serial)
        time.sleep(2)
        return success, output

    def insert_contact(self, serial: str, name: str, phone: str) -> Tuple[bool, str]:
        """Inserta un contacto via ADB"""
        cmd = (
            f'shell am start -a android.intent.action.INSERT '
            f'-t vnd.android.cursor.dir/contact '
            f'-e name "{name}" -e phone "{phone}"'
        )
        success, output = self.run_command(cmd, serial)
        if not success:
            return False, "No se pudo abrir el editor de contactos"

        time.sleep(3)
        # Buscar y tap en botón guardar
        ok, coords, xml = self._ui_dump_and_find(serial, "Guardar")
        if not ok:
            ok, coords, xml = self._ui_dump_and_find(serial, "GUARDAR")
        if not ok:
            ok, coords, xml = self._ui_dump_and_find(serial, "Save")

        if ok and coords:
            self.run_command(f"shell input tap {coords[0]} {coords[1]}", serial)
            time.sleep(2)
            return True, f"Contacto '{name}' creado"

        # Intentar guardar via back key
        self.run_command("shell input keyevent 4", serial)
        time.sleep(1)
        return True, f"Contacto '{name}' creado (verificar manualmente)"

    def check_wifi_connected(self, serial: str) -> Tuple[bool, str]:
        """Verifica si WiFi está conectado y retorna el SSID"""
        success, output = self.run_command(
            "shell dumpsys wifi | grep \"mNetworkInfo\"", serial
        )
        if success and 'CONNECTED' in output.upper():
            # Extraer SSID
            ssid_ok, ssid_out = self.run_command(
                "shell dumpsys wifi | grep \"mWifiInfo\"", serial
            )
            ssid = ""
            if ssid_ok:
                match = re.search(r'SSID: "?([^",]+)"?', ssid_out)
                if match:
                    ssid = match.group(1)
            return True, ssid or "Conectado"
        return False, "No conectado"

    def scan_bluetooth_devices(self, serial: str) -> Tuple[bool, List[str]]:
        """Escanea dispositivos Bluetooth cercanos"""
        # Habilitar BT si no está
        if not self.check_bluetooth_enabled(serial):
            self.set_bluetooth(serial, True)
            time.sleep(3)

        # Abrir settings BT para forzar scan
        self.run_command(
            "shell am start -a android.settings.BLUETOOTH_SETTINGS", serial
        )
        time.sleep(5)

        # Leer dispositivos encontrados del dump
        success, output = self.run_command(
            "shell dumpsys bluetooth_manager | grep \"name:\"", serial
        )

        devices = []
        if success and output:
            for line in output.splitlines():
                match = re.search(r'name:\s*(.+)', line)
                if match:
                    name = match.group(1).strip()
                    if name and name not in devices:
                        devices.append(name)

        # Cerrar settings
        self.run_command("shell input keyevent 4", serial)
        return len(devices) > 0, devices
