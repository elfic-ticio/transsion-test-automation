"""
Executor para pruebas de Speedtest automatizadas.
Coordina: lanzar app, ejecutar N iteraciones, capturar screenshots, cambiar red.
"""
import os
import time
import json
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'speedtest')


class SpeedtestExecutor:
    """Ejecuta pruebas de speedtest automatizadas en un dispositivo."""

    def __init__(self, adb_manager):
        self.adb = adb_manager
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        # Estado actual
        self.is_running = False
        self.current_config = {}
        self.logs = []
        self.results = []  # Lista de resultados por iteración
        self.screenshots = []  # Paths de screenshots
        self.progress = {
            'current_network': '',
            'current_iteration': 0,
            'total_iterations': 0,
            'phase': '',  # 'preparing', 'testing', 'switching', 'done'
            'status': 'idle'
        }

        os.makedirs(DATA_DIR, exist_ok=True)

    def _log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(entry)
        logger.info(message)

    def get_state(self) -> dict:
        return {
            'is_running': self.is_running,
            'config': self.current_config,
            'progress': self.progress,
            'results': self.results,
            'screenshots': self.screenshots,
            'logs': self.logs[-50:]
        }

    def stop(self):
        self._stop_flag.set()
        self._log("Deteniendo ejecución...")

    def start(self, config: dict) -> bool:
        """
        Inicia la ejecución de speedtest.
        config = {
            'serial': str,
            'role': 'dut' | 'ref',
            'operator': str,
            'networks': ['5g', '4g'],  # redes a probar
            'iterations': 5,
        }
        """
        with self._lock:
            if self.is_running:
                return False

            self.is_running = True
            self._stop_flag.clear()
            self.logs = []
            self.results = []
            self.screenshots = []
            self.current_config = config
            self.progress = {
                'current_network': '',
                'current_iteration': 0,
                'total_iterations': config.get('iterations', 5) * len(config.get('networks', [])),
                'phase': 'preparing',
                'status': 'running'
            }

        thread = threading.Thread(target=self._run, args=(config,), daemon=True)
        thread.start()
        return True

    def _run(self, config: dict):
        serial = config['serial']
        role = config['role']
        operator = config['operator']
        networks = config.get('networks', ['5g', '4g'])
        iterations = config.get('iterations', 5)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(DATA_DIR, f"{operator}_{role}_{timestamp}")
        os.makedirs(session_dir, exist_ok=True)

        self._log(f"Iniciando speedtest: {operator} | Rol: {role.upper()} | Redes: {networks}")
        self._log(f"Dispositivo: {serial} | {iterations} iteraciones por red")

        global_iter = 0

        try:
            for net_idx, network in enumerate(networks):
                if self._stop_flag.is_set():
                    break

                self.progress['current_network'] = network.upper()
                self.progress['phase'] = 'switching'
                self._log(f"--- Configurando red: {network.upper()} ---")

                # Cambiar red
                ok, msg = self.adb.set_preferred_network(serial, network)
                if not ok:
                    self._log(f"Error cambiando red a {network}: {msg}", "ERROR")
                    continue
                self._log(f"Red cambiada a {network.upper()}: {msg}")

                # Verificar red actual
                actual = self.adb.get_current_network_type(serial)
                self._log(f"Red actual detectada: {actual}")
                time.sleep(3)

                # Ejecutar iteraciones
                for i in range(1, iterations + 1):
                    if self._stop_flag.is_set():
                        break

                    global_iter += 1
                    self.progress['current_iteration'] = global_iter
                    self.progress['phase'] = 'testing'
                    self._log(f"[{network.upper()}] Iteración {i}/{iterations}")

                    # 1. Lanzar app (force-stop + relaunch)
                    ok, msg = self.adb.launch_speedtest(serial)
                    if not ok:
                        self._log(f"  Error lanzando app: {msg}", "ERROR")
                        self.results.append({
                            'network': network.upper(),
                            'iteration': i,
                            'download': None,
                            'upload': None,
                            'error': msg
                        })
                        continue

                    # 2. Iniciar test
                    ok, msg = self.adb.start_speedtest_run(serial)
                    if not ok:
                        self._log(f"  Error iniciando test: {msg}", "ERROR")
                        self.results.append({
                            'network': network.upper(),
                            'iteration': i,
                            'download': None,
                            'upload': None,
                            'error': msg
                        })
                        continue

                    self._log(f"  Test iniciado, esperando resultado...")

                    # 3. Esperar a que termine
                    ok, msg = self.adb.wait_speedtest_complete(serial, timeout=90)
                    if not ok:
                        self._log(f"  Timeout esperando resultado: {msg}", "WARNING")

                    # 4. Capturar screenshot (siempre intentar, incluso si timeout)
                    screenshot_name = f"{network}_{role}_iter{i}.png"
                    screenshot_path = os.path.join(session_dir, screenshot_name)
                    ok_ss, ss_path = self.adb.capture_speedtest_screenshot(serial, screenshot_path)

                    if ok_ss:
                        # Path relativo a data/speedtest/ para que el endpoint lo sirva correctamente
                        relative_path = os.path.relpath(ss_path, DATA_DIR)
                        self.screenshots.append({
                            'network': network.upper(),
                            'iteration': i,
                            'path': relative_path.replace('\\', '/')
                        })
                        self._log(f"  Screenshot guardado: {screenshot_name}")
                    else:
                        self._log(f"  Error guardando screenshot", "WARNING")

                    # 5. Leer resultados de la pantalla (download, upload, ping)
                    speed_data = self.adb.read_speedtest_results(serial)
                    dl = speed_data.get('download')
                    ul = speed_data.get('upload')
                    ping = speed_data.get('ping')

                    self.results.append({
                        'network': network.upper(),
                        'iteration': i,
                        'download': dl,
                        'upload': ul,
                        'ping': ping,
                        'screenshot': screenshot_name if ok_ss else None
                    })

                    if dl and ul:
                        self._log(f"  Resultado: ↓{dl} Mbps  ↑{ul} Mbps  ping {ping}ms")
                    else:
                        self._log(f"  No se pudieron leer los resultados de la pantalla", "WARNING")
                    time.sleep(2)

                # Screenshot final de la pantalla de historial (último resultado visible)
                self._log(f"--- {network.upper()}: {iterations} iteraciones completadas ---")

        except Exception as e:
            self._log(f"Error inesperado: {e}", "ERROR")
        finally:
            # Cerrar app
            self.adb.run_command(f'shell am force-stop {self.adb.SPEEDTEST_PKG}', serial)

            # Restaurar red a auto
            self.adb.set_preferred_network(serial, 'auto')
            self._log("Red restaurada a automático")

            self.progress['phase'] = 'done'
            self.progress['status'] = 'stopped' if self._stop_flag.is_set() else 'completed'
            self.is_running = False

            # Guardar resultados en JSON
            results_file = os.path.join(session_dir, 'results.json')
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'config': config,
                    'results': self.results,
                    'screenshots': self.screenshots,
                    'timestamp': timestamp
                }, f, indent=2, ensure_ascii=False)

            self._log(f"Resultados guardados en {session_dir}")
            self._log("Ejecución finalizada")
