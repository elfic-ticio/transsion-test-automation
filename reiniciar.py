"""
Script para reiniciar el servidor de Transsion Test Automation.
Mata cualquier proceso Flask en el puerto 5000 y lo reinicia.
"""
import subprocess
import sys
import os
import time
import signal

PORT = 5000

def kill_process_on_port(port):
    """Mata el proceso que está usando el puerto especificado"""
    try:
        # Windows: buscar PID por puerto
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'TCP'],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                print(f"  Deteniendo proceso PID {pid} en puerto {port}...")
                subprocess.run(['taskkill', '/F', '/PID', pid],
                               capture_output=True, text=True)
                time.sleep(1)
                return True
    except Exception as e:
        print(f"  Error al buscar proceso: {e}")
    return False


def main():
    print("=" * 50)
    print("  Reiniciando Transsion Test Automation")
    print("=" * 50)

    # Paso 1: Matar proceso existente
    print("\n[1] Buscando servidor existente...")
    killed = kill_process_on_port(PORT)
    if killed:
        print("  Servidor anterior detenido.")
    else:
        print("  No habia servidor ejecutandose.")

    # Paso 2: Iniciar nuevo servidor
    print(f"\n[2] Iniciando servidor en puerto {PORT}...")
    print("    URL: http://localhost:5000")
    print("    Presiona Ctrl+C para detener\n")

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.execv(sys.executable, [sys.executable, 'app.py'])


if __name__ == '__main__':
    main()
