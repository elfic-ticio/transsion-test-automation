"""
Aplicación Flask - API REST para automatización de pruebas Transsion (Tecno / Infinix)
"""
import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

from config import OPERATORS, OPERATORS_CONFIG
from adb_manager import ADBManager
from custom_tests import CustomTestManager, CustomTest
from dut_executor import DUTExecutor, DUTConfig
from speedtest_executor import SpeedtestExecutor
from fota_executor import FOTAExecutor
from sanity_wom_executor import SanityWOMExecutor

# Crear directorios necesarios antes de configurar logging
for folder in ['data', 'screenshots', 'logs']:
    os.makedirs(folder, exist_ok=True)

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Crear aplicación Flask
app = Flask(__name__)

# Instancias globales
adb_manager = ADBManager()
custom_test_manager = CustomTestManager()
dut_executor = DUTExecutor(adb_manager)
speedtest_executor = SpeedtestExecutor(adb_manager)
fota_executor = FOTAExecutor(adb_manager)
sanity_wom_executor = SanityWOMExecutor(adb_manager)

# ==================== RUTAS DE PÁGINA ====================

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

# ==================== API: DISPOSITIVOS ====================

@app.route('/api/devices', methods=['GET'])
def api_get_devices():
    """Obtiene lista de dispositivos conectados"""
    try:
        devices = adb_manager.get_connected_devices()
        return jsonify({
            'success': True,
            'devices': [d.to_dict() for d in devices]
        })
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/<serial>/phone-debug', methods=['GET'])
def api_phone_debug(serial):
    """Diagnostico: muestra el output raw de cada metodo de deteccion de numero."""
    cmds = {
        'siminfo_all_cols':           'shell content query --uri content://telephony/siminfo',
        'siminfo_projection':         'shell content query --uri content://telephony/siminfo --projection sim_slot_index:number:display_name',
        'dumpsys_iphonesubinfo':      'shell dumpsys iphonesubinfo',
        'ril_msisdn1':                'shell getprop ril.msisdn1',
        'ril_msisdn':                 'shell getprop ril.msisdn',
        'ril_number':                 'shell getprop ril.number',
        'gsm_sim_msisdn':             'shell getprop gsm.sim.msisdn',
        'service_16_i32_1':           'shell service call iphonesubinfo 16 i32 1',
        'service_16_i32_2':           'shell service call iphonesubinfo 16 i32 2',
        'service_6':                  'shell service call iphonesubinfo 6',
        'service_11':                 'shell service call iphonesubinfo 11',
        'service_3':                  'shell service call iphonesubinfo 3',
        'service_16':                 'shell service call iphonesubinfo 16',
        'settings_mobile_data_number':'shell settings get global mobile_data_number',
        'settings_mobile_number':     'shell settings get global mobile_number',
        'settings_phone_number':      'shell settings get global phone_number',
        'telephony_registry':         'shell dumpsys telephony.registry',
    }
    results = {}
    for key, cmd in cmds.items():
        ok, out = adb_manager.run_command(cmd, serial)
        results[key] = {'ok': ok, 'output': out[:500] if out else ''}

    # Incluir también el resultado final de la cascada completa
    detected = adb_manager._get_phone_numbers(serial)
    results['_detected_numbers'] = detected

    return jsonify({'serial': serial, 'results': results})

@app.route('/api/devices/<serial>/refresh', methods=['POST'])
def api_refresh_device(serial):
    """Refresca información de un dispositivo"""
    try:
        device = adb_manager.refresh_device(serial)
        if device:
            return jsonify({'success': True, 'device': device.to_dict()})
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    except Exception as e:
        logger.error(f"Error refreshing device: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API: CONFIGURACIÓN ====================

@app.route('/api/config/operators', methods=['GET'])
def api_get_operators():
    """Obtiene configuración de operadores"""
    return jsonify({
        'success': True,
        'operators': OPERATORS,
        'config': OPERATORS_CONFIG
    })

# ==================== API: CONTROL MANUAL ====================

@app.route('/api/call/make', methods=['POST'])
def api_make_call():
    """Realiza una llamada manual"""
    try:
        data = request.json
        serial = data.get('device_serial')
        number = data.get('phone_number')

        if not serial or not number:
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400

        success, message = adb_manager.make_call(serial, number)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"Error making call: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/call/end', methods=['POST'])
def api_end_call():
    """Finaliza llamada"""
    try:
        data = request.json
        serial = data.get('device_serial')

        success, message = adb_manager.end_call(serial)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"Error ending call: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/call/answer', methods=['POST'])
def api_answer_call():
    """Contesta llamada"""
    try:
        data = request.json
        serial = data.get('device_serial')

        success, message = adb_manager.answer_call(serial)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"Error answering call: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/call/state', methods=['GET'])
def api_call_state():
    """Obtiene estado de llamada"""
    try:
        serial = request.args.get('device_serial')
        state = adb_manager.get_call_state(serial)
        return jsonify({'success': True, 'state': state})
    except Exception as e:
        logger.error(f"Error getting call state: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/device/airplane', methods=['POST'])
def api_airplane_mode():
    """Activa/desactiva modo avión"""
    try:
        data = request.json
        serial = data.get('device_serial')
        enable = data.get('enable', False)

        success, message = adb_manager.set_airplane_mode(serial, enable)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"Error toggling airplane mode: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/device/screenshot', methods=['POST'])
def api_screenshot():
    """Captura screenshot"""
    try:
        data = request.json
        serial = data.get('device_serial')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshots/manual_{timestamp}.png"

        success, path = adb_manager.capture_screenshot(serial, filename)
        return jsonify({'success': success, 'path': path if success else None})
    except Exception as e:
        logger.error(f"Error capturing screenshot: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API: PRUEBAS PERSONALIZADAS (DUT-to-DUT) ====================

@app.route('/api/custom-tests', methods=['GET'])
def api_get_custom_tests():
    """Obtiene todas las pruebas personalizadas"""
    try:
        tests = custom_test_manager.get_all_tests()
        categories = custom_test_manager.get_categories()
        return jsonify({
            'success': True,
            'tests': tests,
            'categories': categories,
            'count': len(tests)
        })
    except Exception as e:
        logger.error(f"Error getting custom tests: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/custom-tests/<test_id>', methods=['GET'])
def api_get_custom_test(test_id):
    """Obtiene una prueba personalizada por ID"""
    try:
        test = custom_test_manager.get_test(test_id)
        if test:
            return jsonify({'success': True, 'test': test})
        return jsonify({'success': False, 'error': 'Test not found'}), 404
    except Exception as e:
        logger.error(f"Error getting custom test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/custom-tests', methods=['POST'])
def api_create_custom_test():
    """Crea una nueva prueba personalizada"""
    try:
        data = request.json
        test = custom_test_manager.create_test(data)
        return jsonify({'success': True, 'test': test})
    except Exception as e:
        logger.error(f"Error creating custom test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/custom-tests/<test_id>', methods=['PUT'])
def api_update_custom_test(test_id):
    """Actualiza una prueba personalizada"""
    try:
        data = request.json
        test = custom_test_manager.update_test(test_id, data)
        if test:
            return jsonify({'success': True, 'test': test})
        return jsonify({'success': False, 'error': 'Test not found'}), 404
    except Exception as e:
        logger.error(f"Error updating custom test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/custom-tests/<test_id>', methods=['DELETE'])
def api_delete_custom_test(test_id):
    """Elimina una prueba personalizada"""
    try:
        success = custom_test_manager.delete_test(test_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Test not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting custom test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/custom-tests/<test_id>/duplicate', methods=['POST'])
def api_duplicate_custom_test(test_id):
    """Duplica una prueba personalizada"""
    try:
        test = custom_test_manager.duplicate_test(test_id)
        if test:
            return jsonify({'success': True, 'test': test})
        return jsonify({'success': False, 'error': 'Test not found'}), 404
    except Exception as e:
        logger.error(f"Error duplicating custom test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API: EJECUCIÓN DUT-to-DUT ====================

@app.route('/api/dut/execute', methods=['POST'])
def api_dut_execute():
    """Inicia ejecución de prueba DUT-to-DUT"""
    try:
        data = request.json

        required = ['test_id', 'dut1_serial', 'dut1_phone', 'dut2_serial', 'dut2_phone']
        for field in required:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'}), 400

        test_data = custom_test_manager.get_test(data['test_id'])
        if not test_data:
            return jsonify({'success': False, 'error': 'Test not found'}), 404

        test = CustomTest.from_dict(test_data)

        dut1 = DUTConfig(
            serial=data['dut1_serial'],
            phone_number=data['dut1_phone'],
            operator=data.get('dut1_operator', ''),
            name=data.get('dut1_name', 'DUT1')
        )

        dut2 = DUTConfig(
            serial=data['dut2_serial'],
            phone_number=data['dut2_phone'],
            operator=data.get('dut2_operator', ''),
            name=data.get('dut2_name', 'DUT2')
        )

        success = dut_executor.start_execution(test, dut1, dut2)

        if success:
            return jsonify({
                'success': True,
                'message': f'Ejecución iniciada: {test.name}'
            })
        return jsonify({
            'success': False,
            'error': 'No se pudo iniciar la ejecución (puede haber una ejecución en curso)'
        }), 500

    except Exception as e:
        logger.error(f"Error starting DUT execution: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dut/stop', methods=['POST'])
def api_dut_stop():
    """Detiene la ejecución DUT-to-DUT"""
    try:
        dut_executor.stop_execution()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error stopping DUT execution: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dut/pause', methods=['POST'])
def api_dut_pause():
    """Pausa la ejecución DUT-to-DUT"""
    try:
        dut_executor.pause_execution()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error pausing DUT execution: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dut/resume', methods=['POST'])
def api_dut_resume():
    """Reanuda la ejecución DUT-to-DUT"""
    try:
        dut_executor.resume_execution()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error resuming DUT execution: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dut/status', methods=['GET'])
def api_dut_status():
    """Obtiene el estado de la ejecución DUT-to-DUT"""
    try:
        state = dut_executor.get_state()
        return jsonify({
            'success': True,
            'state': state
        })
    except Exception as e:
        logger.error(f"Error getting DUT status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API: DEBUGLOGGER ====================

@app.route('/api/debuglogger/start', methods=['POST'])
def api_debuglogger_start():
    """Inicia captura de DebugLogger"""
    try:
        data = request.json
        serial = data.get('serial')
        if not serial:
            return jsonify({'success': False, 'error': 'Serial requerido'}), 400

        ok, msg = adb_manager.start_debuglogger(serial)
        return jsonify({'success': ok, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debuglogger/stop', methods=['POST'])
def api_debuglogger_stop():
    """Detiene captura de DebugLogger"""
    try:
        data = request.json
        serial = data.get('serial')
        if not serial:
            return jsonify({'success': False, 'error': 'Serial requerido'}), 400

        ok, msg = adb_manager.stop_debuglogger(serial)
        return jsonify({'success': ok, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debuglogger/status', methods=['GET'])
def api_debuglogger_status():
    """Obtiene estado del DebugLogger"""
    try:
        serial = request.args.get('serial')
        if not serial:
            return jsonify({'success': False, 'error': 'Serial requerido'}), 400

        status = adb_manager.get_debuglogger_status(serial)
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debuglogger/extract', methods=['POST'])
def api_debuglogger_extract():
    """Extrae logs del DebugLogger a carpeta local"""
    try:
        data = request.json
        serial = data.get('serial')
        folder = data.get('folder', '')
        subfolder = data.get('subfolder', '')

        if not serial or not folder:
            return jsonify({'success': False, 'error': 'Serial y carpeta requeridos'}), 400

        base_dir = os.path.join('data', 'debuglogs', folder)
        if subfolder:
            base_dir = os.path.join(base_dir, subfolder)

        ok, msg = adb_manager.pull_debuglogger_logs(serial, base_dir)
        if ok:
            adb_manager.clear_debuglogger_logs(serial)
        return jsonify({'success': ok, 'message': msg, 'path': base_dir})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debuglogger/clear', methods=['POST'])
def api_debuglogger_clear():
    """Limpia logs del DebugLogger en el dispositivo"""
    try:
        data = request.json
        serial = data.get('serial')
        if not serial:
            return jsonify({'success': False, 'error': 'Serial requerido'}), 400

        ok, msg = adb_manager.clear_debuglogger_logs(serial)
        return jsonify({'success': ok, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API: SPEEDTEST ====================

@app.route('/api/speedtest/start', methods=['POST'])
def api_speedtest_start():
    """Inicia ejecución de speedtest automatizado"""
    try:
        data = request.json
        config = {
            'serial': data.get('serial'),
            'role': data.get('role', 'dut'),
            'operator': data.get('operator', ''),
            'networks': data.get('networks', ['5g', '4g']),
            'iterations': data.get('iterations', 5),
        }

        if not config['serial']:
            return jsonify({'success': False, 'error': 'Serial requerido'}), 400

        if not config['operator']:
            device = adb_manager.refresh_device(config['serial'])
            if device:
                config['operator'] = device.sim_operator

        ok = speedtest_executor.start(config)
        if ok:
            return jsonify({'success': True, 'message': 'Speedtest iniciado'})
        return jsonify({'success': False, 'error': 'Ya hay un speedtest en ejecución'}), 409
    except Exception as e:
        logger.error(f"Error starting speedtest: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/speedtest/stop', methods=['POST'])
def api_speedtest_stop():
    """Detiene ejecución de speedtest"""
    speedtest_executor.stop()
    return jsonify({'success': True})

@app.route('/api/speedtest/status', methods=['GET'])
def api_speedtest_status():
    """Obtiene estado actual del speedtest"""
    try:
        state = speedtest_executor.get_state()
        return jsonify({'success': True, **state})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/speedtest/results', methods=['POST'])
def api_speedtest_save_results():
    """Guarda los resultados ingresados manualmente por el usuario"""
    try:
        data = request.json
        results = data.get('results', [])
        config = data.get('config', {})

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        operator = config.get('operator', 'unknown')
        role = config.get('role', 'dut')
        save_dir = os.path.join('data', 'speedtest', f'{operator}_{role}_{timestamp}')
        os.makedirs(save_dir, exist_ok=True)

        filepath = os.path.join(save_dir, 'manual_results.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({'config': config, 'results': results, 'timestamp': timestamp},
                      f, indent=2, ensure_ascii=False)

        return jsonify({'success': True, 'path': filepath})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/speedtest/screenshot/<path:filename>')
def api_speedtest_screenshot(filename):
    """Sirve un screenshot de speedtest"""
    filepath = os.path.join('data', 'speedtest', filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='image/png')
    return jsonify({'error': 'Not found'}), 404

# ==================== API: FOTA TEST CASES ====================

@app.route('/api/fota/tests', methods=['GET'])
def api_fota_tests():
    """Retorna todos los test cases FOTA con resultados"""
    try:
        tests = fota_executor.get_test_cases()
        return jsonify({'success': True, 'tests': tests})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fota/status', methods=['GET'])
def api_fota_status():
    """Estado actual de ejecución FOTA"""
    try:
        state = fota_executor.get_state()
        return jsonify({'success': True, **state})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fota/run-single', methods=['POST'])
def api_fota_run_single():
    """Ejecuta un test FOTA individual"""
    try:
        data = request.json
        serial = data.get('serial')
        test_id = data.get('test_id')
        dut2_serial = data.get('dut2_serial')
        dut2_phone = data.get('dut2_phone')

        if not serial or not test_id:
            return jsonify({'success': False, 'error': 'Serial y test_id requeridos'}), 400

        result = fota_executor.run_single(serial, int(test_id), dut2_serial, dut2_phone)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        logger.error(f"Error running FOTA test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fota/run-all-auto', methods=['POST'])
def api_fota_run_all_auto():
    """Ejecuta todos los tests FOTA automáticos"""
    try:
        data = request.json
        serial = data.get('serial')
        dut2_serial = data.get('dut2_serial')
        dut2_phone = data.get('dut2_phone')

        if not serial:
            return jsonify({'success': False, 'error': 'Serial requerido'}), 400

        ok = fota_executor.run_all_auto(serial, dut2_serial, dut2_phone)
        if ok:
            return jsonify({'success': True, 'message': 'Ejecución automática iniciada'})
        return jsonify({'success': False, 'error': 'Ya hay una ejecución en curso'}), 409
    except Exception as e:
        logger.error(f"Error running all FOTA tests: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fota/stop', methods=['POST'])
def api_fota_stop():
    """Detiene ejecución FOTA"""
    fota_executor.stop()
    return jsonify({'success': True})

@app.route('/api/fota/set-result', methods=['POST'])
def api_fota_set_result():
    """Marca resultado manual de un test"""
    try:
        data = request.json
        test_id = data.get('test_id')
        result = data.get('result')
        remark = data.get('remark', '')

        if not test_id or not result:
            return jsonify({'success': False, 'error': 'test_id y result requeridos'}), 400

        ok = fota_executor.set_manual_result(int(test_id), result, remark)
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fota/report', methods=['POST'])
def api_fota_report():
    """Genera informe de resultados"""
    try:
        data = request.json
        model = data.get('model', '')
        sw_version = data.get('sw_version', '')
        tester = data.get('tester', '')
        sp_date = data.get('sp_date', '')
        format_type = data.get('format', 'excel')

        if format_type == 'excel':
            filepath = fota_executor.generate_excel_report(model, sw_version, tester, sp_date)
        else:
            filepath = fota_executor.generate_report(model, sw_version, tester, sp_date)

        return jsonify({'success': True, 'path': filepath})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fota/report/download/<path:filename>')
def api_fota_report_download(filename):
    """Descarga un informe FOTA"""
    filepath = os.path.join('data', 'fota_reports', filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'Not found'}), 404

# ==================== API: SANITY CHECK WOM ====================

@app.route('/api/sanity-wom/tests', methods=['GET'])
def api_sanity_wom_tests():
    """Retorna todos los casos del Sanity Check WOM con resultados actuales."""
    try:
        tests = sanity_wom_executor.get_test_cases()
        return jsonify({'success': True, 'tests': tests})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sanity-wom/set-result', methods=['POST'])
def api_sanity_wom_set_result():
    """Guarda el resultado (pass/fail/na) y observacion de un caso."""
    try:
        data = request.json
        test_id = data.get('test_id')
        result = data.get('result')
        remark = data.get('remark', '')

        if not test_id or not result:
            return jsonify({'success': False, 'error': 'test_id y result son requeridos'}), 400

        ok = sanity_wom_executor.set_result(test_id, result, remark)
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sanity-wom/run', methods=['POST'])
def api_sanity_wom_run():
    """Ejecuta la automatizacion ADB de un caso (AUTO o SEMI)."""
    try:
        data = request.json
        test_id = data.get('test_id')
        serial = data.get('serial')

        if not test_id or not serial:
            return jsonify({'success': False, 'error': 'test_id y serial son requeridos'}), 400

        result = sanity_wom_executor.run_auto_test(test_id, serial)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error running WOM sanity test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sanity-wom/report', methods=['POST'])
def api_sanity_wom_report():
    """Genera el informe Excel del Sanity Check WOM."""
    try:
        data = request.json
        model = data.get('model', '')
        tester = data.get('tester', '')
        sw_version = data.get('sw_version', '')

        filepath = sanity_wom_executor.generate_excel_report(model, tester, sw_version)
        return jsonify({'success': True, 'path': filepath})
    except Exception as e:
        logger.error(f"Error generating WOM report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sanity-wom/report/download/<path:filename>')
def api_sanity_wom_report_download(filename):
    """Descarga un informe del Sanity Check WOM."""
    filepath = os.path.join('data', 'sanity_wom_reports', filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/sanity-wom/reset', methods=['POST'])
def api_sanity_wom_reset():
    """Resetea todos los resultados a 'pending'."""
    try:
        sanity_wom_executor.reset_results()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    print("=" * 70)
    print("  Transsion Test Automation - Homologacion Colombia")
    print("  Marcas: Tecno | Infinix")
    print("  Modulos: FOTA Claro | Speed Test | DUT-to-DUT")
    print("  Operadores: CLARO | WOM | TIGO | MOVISTAR")
    print("=" * 70)
    print(f"  Servidor: http://localhost:5000")
    print("=" * 70)

    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
