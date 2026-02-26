/**
 * Módulo para gestionar pruebas personalizadas DUT-to-DUT
 */

// Estado del módulo DUT
const dutState = {
    tests: [],
    categories: [],
    selectedTest: null,
    dut1: null,
    dut2: null,
    isExecuting: false,
    pollingInterval: null
};

// Tipos de acciones disponibles
const ACTION_TYPES = {
    'make_call': { name: 'Realizar llamada', icon: 'fa-phone', color: 'success' },
    'answer_call': { name: 'Contestar llamada', icon: 'fa-phone-volume', color: 'primary' },
    'hold_call': { name: 'Mantener llamada', icon: 'fa-clock', color: 'info' },
    'end_call': { name: 'Colgar llamada', icon: 'fa-phone-slash', color: 'danger' },
    'wait': { name: 'Esperar', icon: 'fa-hourglass-half', color: 'warning' },
    'verify': { name: 'Verificar estado', icon: 'fa-check-circle', color: 'secondary' },
    'set_network': { name: 'Cambiar red', icon: 'fa-signal', color: 'dark' },
    'send_sms': { name: 'Enviar SMS', icon: 'fa-envelope', color: 'info' },
    'verify_sms': { name: 'Verificar SMS', icon: 'fa-envelope-open-text', color: 'secondary' }
};

const NETWORK_MODES = ['5g', '4g', '3g', 'auto'];

// ==================== CARGAR PRUEBAS ====================

async function loadCustomTests() {
    try {
        const response = await fetch('/api/custom-tests');
        const data = await response.json();

        if (data.success) {
            dutState.tests = data.tests;
            dutState.categories = data.categories;
            renderCustomTestsList();
        }
    } catch (error) {
        console.error('Error cargando pruebas:', error);
    }
}

function renderCustomTestsList() {
    const container = document.getElementById('customTestsList');
    if (!container) return;

    if (dutState.tests.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No hay pruebas personalizadas</div>';
        return;
    }

    // Agrupar por categoría
    const byCategory = {};
    dutState.tests.forEach(test => {
        const cat = test.category || 'general';
        if (!byCategory[cat]) byCategory[cat] = [];
        byCategory[cat].push(test);
    });

    let html = '';
    for (const [category, tests] of Object.entries(byCategory)) {
        html += `
            <div class="mb-3">
                <h6 class="text-muted text-uppercase small">
                    <i class="fas fa-folder"></i> ${category}
                </h6>
                <div class="list-group">
        `;

        tests.forEach(test => {
            const isSelected = dutState.selectedTest && dutState.selectedTest.id === test.id;
            html += `
                <button class="list-group-item list-group-item-action ${isSelected ? 'active' : ''}"
                        onclick="selectCustomTest('${test.id}')">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${test.name}</strong>
                            <br>
                            <small class="text-muted">${test.actions.length} acciones</small>
                        </div>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary" onclick="event.stopPropagation(); editCustomTest('${test.id}')" title="Editar">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-outline-secondary" onclick="event.stopPropagation(); duplicateCustomTest('${test.id}')" title="Duplicar">
                                <i class="fas fa-copy"></i>
                            </button>
                            <button class="btn btn-outline-danger" onclick="event.stopPropagation(); deleteCustomTest('${test.id}')" title="Eliminar">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </button>
            `;
        });

        html += '</div></div>';
    }

    container.innerHTML = html;
}

// ==================== SELECCIONAR PRUEBA ====================

function selectCustomTest(testId) {
    const test = dutState.tests.find(t => t.id === testId);
    if (!test) return;

    dutState.selectedTest = test;
    renderCustomTestsList();
    renderTestDetails(test);
}

function renderTestDetails(test) {
    const container = document.getElementById('testDetails');
    if (!container) return;

    let actionsHtml = test.actions.map((action, index) => {
        const actionInfo = ACTION_TYPES[action.action_type] || { name: action.action_type, icon: 'fa-question', color: 'secondary' };
        const targetLabels = { 'dut1': 'DUT1', 'dut2': 'DUT2', 'both': 'AMBOS' };
        const targetLabel = targetLabels[action.target_device] || action.target_device;
        const targetColor = action.target_device === 'both' ? 'info' : 'dark';
        const durationText = action.duration_seconds > 0 ? ` (${action.duration_seconds}s)` : '';
        const networkBadge = action.network_mode ? `<span class="badge bg-warning text-dark me-2"><i class="fas fa-signal"></i> ${action.network_mode.toUpperCase()}</span>` : '';
        const smsBadge = action.sms_message ? `<span class="badge bg-info me-2"><i class="fas fa-envelope"></i> "${action.sms_message}"</span>` : '';

        return `
            <div class="d-flex align-items-center mb-2 p-2 border rounded">
                <span class="badge bg-${actionInfo.color} me-2">${index + 1}</span>
                <i class="fas ${actionInfo.icon} me-2 text-${actionInfo.color}"></i>
                <span class="badge bg-${targetColor} me-2">${targetLabel}</span>
                ${networkBadge}${smsBadge}
                <span>${action.description}${durationText}</span>
            </div>
        `;
    }).join('');

    container.innerHTML = `
        <div class="card">
            <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                <span><i class="fas fa-clipboard-list"></i> ${test.name}</span>
                <button class="btn btn-sm btn-light" onclick="editCustomTest('${test.id}')">
                    <i class="fas fa-edit"></i> Editar
                </button>
            </div>
            <div class="card-body">
                <p class="text-muted">${test.description || 'Sin descripción'}</p>

                <h6>Acciones (${test.actions.length}):</h6>
                <div class="actions-list" style="max-height: 300px; overflow-y: auto;">
                    ${actionsHtml}
                </div>

                <hr>

                <div class="alert alert-info">
                    <strong>Tags:</strong> ${test.tags.length > 0 ? test.tags.join(', ') : 'Sin tags'}
                </div>
            </div>
        </div>
    `;
}

// ==================== CREAR/EDITAR PRUEBA ====================

function showCreateTestModal() {
    document.getElementById('testModalTitle').textContent = 'Nueva Prueba';
    document.getElementById('testForm').reset();
    document.getElementById('testId').value = '';
    document.getElementById('testActions').innerHTML = '';

    addActionRow(); // Agregar primera acción vacía

    const modal = new bootstrap.Modal(document.getElementById('testModal'));
    modal.show();
}

async function editCustomTest(testId) {
    const test = dutState.tests.find(t => t.id === testId);
    if (!test) return;

    document.getElementById('testModalTitle').textContent = 'Editar Prueba';
    document.getElementById('testId').value = test.id;
    document.getElementById('testName').value = test.name;
    document.getElementById('testDescription').value = test.description || '';
    document.getElementById('testCategory').value = test.category || 'general';
    document.getElementById('testTags').value = test.tags.join(', ');

    // Cargar acciones
    const actionsContainer = document.getElementById('testActions');
    actionsContainer.innerHTML = '';

    test.actions.forEach(action => {
        addActionRow(action);
    });

    const modal = new bootstrap.Modal(document.getElementById('testModal'));
    modal.show();
}

function addActionRow(action = null) {
    const container = document.getElementById('testActions');
    const index = container.children.length;

    const actionOptions = Object.entries(ACTION_TYPES).map(([value, info]) =>
        `<option value="${value}" ${action && action.action_type === value ? 'selected' : ''}>${info.name}</option>`
    ).join('');

    const isNetworkAction = action && action.action_type === 'set_network';
    const isSmsAction = action && (action.action_type === 'send_sms' || action.action_type === 'verify_sms');
    const networkModeOptions = NETWORK_MODES.map(mode =>
        `<option value="${mode}" ${action && action.network_mode === mode ? 'selected' : ''}>${mode.toUpperCase()}</option>`
    ).join('');

    const html = `
        <div class="action-row card mb-2" data-index="${index}">
            <div class="card-body p-2">
                <div class="row g-2 align-items-center">
                    <div class="col-auto">
                        <span class="badge bg-secondary">${index + 1}</span>
                    </div>
                    <div class="col-md-2">
                        <select class="form-select form-select-sm action-type" onchange="onActionTypeChange(this)">
                            ${actionOptions}
                        </select>
                    </div>
                    <div class="col-md-2">
                        <select class="form-select form-select-sm action-target">
                            <option value="dut1" ${!action || action.target_device === 'dut1' ? 'selected' : ''}>DUT1</option>
                            <option value="dut2" ${action && action.target_device === 'dut2' ? 'selected' : ''}>DUT2</option>
                            <option value="both" ${action && action.target_device === 'both' ? 'selected' : ''}>Ambos</option>
                        </select>
                    </div>
                    <div class="col-md-2 network-mode-col" style="display: ${isNetworkAction ? 'block' : 'none'}">
                        <select class="form-select form-select-sm action-network-mode">
                            <option value="">Red...</option>
                            ${networkModeOptions}
                        </select>
                    </div>
                    <div class="col-md-2 sms-message-col" style="display: ${isSmsAction ? 'block' : 'none'}">
                        <input type="text" class="form-control form-control-sm action-sms-message"
                               placeholder="Mensaje SMS" value="${action && action.sms_message ? action.sms_message : ''}">
                    </div>
                    <div class="col-md-1">
                        <input type="number" class="form-control form-control-sm action-duration"
                               placeholder="Seg" min="0" value="${action ? action.duration_seconds : 0}">
                    </div>
                    <div class="col">
                        <input type="text" class="form-control form-control-sm action-description"
                               placeholder="Descripción" value="${action ? action.description : ''}">
                    </div>
                    <div class="col-auto">
                        <button type="button" class="btn btn-sm btn-danger" onclick="removeActionRow(this)">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', html);
    updateActionIndices();
}

function onActionTypeChange(select) {
    const row = select.closest('.action-row');
    const networkCol = row.querySelector('.network-mode-col');
    const smsCol = row.querySelector('.sms-message-col');
    const targetSelect = row.querySelector('.action-target');

    if (select.value === 'set_network') {
        networkCol.style.display = 'block';
        smsCol.style.display = 'none';
        targetSelect.value = 'both';
    } else if (select.value === 'send_sms' || select.value === 'verify_sms') {
        networkCol.style.display = 'none';
        smsCol.style.display = 'block';
    } else {
        networkCol.style.display = 'none';
        smsCol.style.display = 'none';
    }
}

function removeActionRow(btn) {
    const row = btn.closest('.action-row');
    row.remove();
    updateActionIndices();
}

function updateActionIndices() {
    const rows = document.querySelectorAll('#testActions .action-row');
    rows.forEach((row, index) => {
        row.dataset.index = index;
        row.querySelector('.badge').textContent = index + 1;
    });
}

async function saveCustomTest() {
    const testId = document.getElementById('testId').value;
    const name = document.getElementById('testName').value.trim();
    const description = document.getElementById('testDescription').value.trim();
    const category = document.getElementById('testCategory').value;
    const tags = document.getElementById('testTags').value.split(',').map(t => t.trim()).filter(t => t);

    if (!name) {
        showNotification('El nombre es requerido', 'warning');
        return;
    }

    // Recoger acciones
    const actions = [];
    document.querySelectorAll('#testActions .action-row').forEach(row => {
        const actionData = {
            action_type: row.querySelector('.action-type').value,
            target_device: row.querySelector('.action-target').value,
            duration_seconds: parseInt(row.querySelector('.action-duration').value) || 0,
            description: row.querySelector('.action-description').value
        };
        // Incluir network_mode si es acción de cambio de red
        if (actionData.action_type === 'set_network') {
            const networkMode = row.querySelector('.action-network-mode');
            if (networkMode) {
                actionData.network_mode = networkMode.value;
            }
        }
        // Incluir sms_message si es acción de SMS
        if (actionData.action_type === 'send_sms' || actionData.action_type === 'verify_sms') {
            const smsMsg = row.querySelector('.action-sms-message');
            if (smsMsg) {
                actionData.sms_message = smsMsg.value;
            }
        }
        actions.push(actionData);
    });

    if (actions.length === 0) {
        showNotification('Debe agregar al menos una acción', 'warning');
        return;
    }

    const testData = { name, description, category, tags, actions };

    try {
        let response;
        if (testId) {
            response = await fetch(`/api/custom-tests/${testId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(testData)
            });
        } else {
            response = await fetch('/api/custom-tests', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(testData)
            });
        }

        const data = await response.json();

        if (data.success) {
            showNotification(testId ? 'Prueba actualizada' : 'Prueba creada', 'success');
            bootstrap.Modal.getInstance(document.getElementById('testModal')).hide();
            loadCustomTests();
        } else {
            showNotification('Error: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Error guardando prueba:', error);
        showNotification('Error al guardar', 'danger');
    }
}

async function duplicateCustomTest(testId) {
    try {
        const response = await fetch(`/api/custom-tests/${testId}/duplicate`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            showNotification('Prueba duplicada', 'success');
            loadCustomTests();
        }
    } catch (error) {
        console.error('Error duplicando prueba:', error);
    }
}

async function deleteCustomTest(testId) {
    if (!confirm('¿Estás seguro de eliminar esta prueba?')) return;

    try {
        const response = await fetch(`/api/custom-tests/${testId}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.success) {
            showNotification('Prueba eliminada', 'success');
            if (dutState.selectedTest && dutState.selectedTest.id === testId) {
                dutState.selectedTest = null;
                document.getElementById('testDetails').innerHTML = '';
            }
            loadCustomTests();
        }
    } catch (error) {
        console.error('Error eliminando prueba:', error);
    }
}

// ==================== EJECUCIÓN DUT-to-DUT ====================

async function startDUTExecution() {
    if (!dutState.selectedTest) {
        showNotification('Selecciona una prueba primero', 'warning');
        return;
    }

    const dut1Serial = document.getElementById('dut1Select').value;
    const dut1Phone = document.getElementById('dut1Phone').value;
    const dut2Serial = document.getElementById('dut2Select').value;
    const dut2Phone = document.getElementById('dut2Phone').value;

    if (!dut1Serial || !dut1Phone || !dut2Serial || !dut2Phone) {
        showNotification('Configura ambos dispositivos', 'warning');
        return;
    }

    if (dut1Serial === dut2Serial) {
        showNotification('DUT1 y DUT2 deben ser dispositivos diferentes', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/dut/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                test_id: dutState.selectedTest.id,
                dut1_serial: dut1Serial,
                dut1_phone: dut1Phone,
                dut2_serial: dut2Serial,
                dut2_phone: dut2Phone
            })
        });

        const data = await response.json();

        if (data.success) {
            // Guardar números en caché para próximas sesiones
            savePhoneToCache(dut1Serial, dut1Phone);
            savePhoneToCache(dut2Serial, dut2Phone);

            dutState.isExecuting = true;
            updateDUTExecutionButtons(true);
            showNotification('Ejecución DUT-to-DUT iniciada', 'success');
            startDUTPolling();
        } else {
            showNotification('Error: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Error iniciando ejecución DUT:', error);
    }
}

async function stopDUTExecution() {
    try {
        await fetch('/api/dut/stop', { method: 'POST' });
        showNotification('Ejecución detenida', 'info');
    } catch (error) {
        console.error('Error deteniendo ejecución:', error);
    }
}

async function pauseDUTExecution() {
    try {
        await fetch('/api/dut/pause', { method: 'POST' });
        showNotification('Ejecución pausada', 'warning');
    } catch (error) {
        console.error('Error pausando:', error);
    }
}

async function resumeDUTExecution() {
    try {
        await fetch('/api/dut/resume', { method: 'POST' });
        showNotification('Ejecución reanudada', 'info');
    } catch (error) {
        console.error('Error reanudando:', error);
    }
}

function startDUTPolling() {
    if (dutState.pollingInterval) {
        clearInterval(dutState.pollingInterval);
    }

    dutState.pollingInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/dut/status');
            const data = await response.json();

            if (data.success) {
                updateDUTExecutionStatus(data.state);

                if (!data.state.is_running) {
                    stopDUTPolling();
                    updateDUTExecutionButtons(false);
                    dutState.isExecuting = false;

                    if (data.state.result === 'pass') {
                        showNotification('Prueba completada exitosamente', 'success');
                    } else if (data.state.result === 'fail') {
                        showNotification('Prueba falló: ' + (data.state.error_message || 'Error desconocido'), 'danger');
                    }
                }
            }
        } catch (error) {
            console.error('Error polling DUT status:', error);
        }
    }, 1000);
}

function stopDUTPolling() {
    if (dutState.pollingInterval) {
        clearInterval(dutState.pollingInterval);
        dutState.pollingInterval = null;
    }
}

function updateDUTExecutionStatus(state) {
    // Actualizar barra de progreso
    const progressBar = document.getElementById('dutProgressBar');
    if (progressBar) {
        progressBar.style.width = state.progress + '%';
        progressBar.textContent = state.progress + '%';
    }

    // Actualizar texto de estado
    const statusText = document.getElementById('dutStatusText');
    if (statusText) {
        statusText.textContent = state.current_action || 'Esperando...';
    }

    // Actualizar progreso de acciones
    const actionProgress = document.getElementById('dutActionProgress');
    if (actionProgress) {
        actionProgress.textContent = `Acción ${state.current_action_index + 1} de ${state.total_actions}`;
    }

    // Actualizar logs
    const logsContainer = document.getElementById('dutLogs');
    if (logsContainer && state.logs) {
        logsContainer.innerHTML = state.logs.map(log =>
            `<div class="small">${escapeHtml(log)}</div>`
        ).join('');
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }
}

function updateDUTExecutionButtons(isRunning) {
    const btnStart = document.getElementById('btnDutStart');
    const btnPause = document.getElementById('btnDutPause');
    const btnStop = document.getElementById('btnDutStop');

    if (btnStart) btnStart.disabled = isRunning;
    if (btnPause) btnPause.disabled = !isRunning;
    if (btnStop) btnStop.disabled = !isRunning;
}

// ==================== UTILIDADES ====================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Mapa de dispositivos para auto-rellenar números
let deviceInfoMap = {};

async function refreshDUTDeviceSelects() {
    try {
        const response = await fetch('/api/devices');
        const data = await response.json();

        const dut1Select = document.getElementById('dut1Select');
        const dut2Select = document.getElementById('dut2Select');

        if (!dut1Select || !dut2Select) return;

        const defaultOption = '<option value="">Seleccionar...</option>';
        let options = defaultOption;

        deviceInfoMap = {};
        if (data.success && data.devices.length > 0) {
            data.devices.forEach(device => {
                deviceInfoMap[device.serial] = device;
                const phone = device.phone_number ? ` - ${device.phone_number}` : '';
                const op = device.sim_operator || '';
                options += `<option value="${device.serial}">${device.model} ${op}${phone} (${device.serial.substring(0, 8)}...)</option>`;
            });
        }

        dut1Select.innerHTML = options;
        dut2Select.innerHTML = options;

        // Agregar listeners para auto-rellenar números
        dut1Select.onchange = () => autoFillPhone('dut1Select', 'dut1Phone');
        dut2Select.onchange = () => autoFillPhone('dut2Select', 'dut2Phone');

        // Persistencia: guardar número cuando el usuario lo escribe manualmente
        setupPhonePersistence('dut1Phone', 'dut1Select');
        setupPhonePersistence('dut2Phone', 'dut2Select');

    } catch (error) {
        console.error('Error cargando dispositivos:', error);
    }
}

function savePhoneToCache(serial, phone) {
    if (!serial || !phone) return;
    try {
        localStorage.setItem('dut_phone_' + serial, phone);
    } catch (e) {
        console.warn('No se pudo guardar en localStorage:', e);
    }
}

function loadPhoneFromCache(serial) {
    if (!serial) return '';
    try {
        return localStorage.getItem('dut_phone_' + serial) || '';
    } catch (e) {
        return '';
    }
}

function setupPhonePersistence(phoneInputId, selectId) {
    const phoneInput = document.getElementById(phoneInputId);
    if (!phoneInput) return;

    phoneInput.addEventListener('input', function() {
        const serial = document.getElementById(selectId)?.value;
        const phone = phoneInput.value.trim();
        if (serial && phone) {
            savePhoneToCache(serial, phone);
            // Indicar que fue guardado localmente
            phoneInput.title = 'Número guardado localmente para este dispositivo';
        }
    });
}

function autoFillPhone(selectId, phoneInputId) {
    const serial = document.getElementById(selectId).value;
    const phoneInput = document.getElementById(phoneInputId);
    if (!phoneInput) return;

    if (!serial) {
        phoneInput.value = '';
        phoneInput.placeholder = 'Numero telefonico';
        phoneInput.classList.remove('is-valid', 'is-invalid');
        phoneInput.title = '';
        return;
    }

    const dev = deviceInfoMap[serial];

    // 1) Intentar número detectado por ADB
    const apiNum = (dev && (dev.phone_sim1 || dev.phone_sim2)) || '';

    // 2) Si ADB no lo detectó, intentar desde caché local (número ingresado previamente)
    const cachedNum = loadPhoneFromCache(serial);

    const num = apiNum || cachedNum;
    phoneInput.value = num;

    if (num) {
        if (apiNum) {
            // Número detectado por ADB
            if (dev.phone_sim1 && dev.phone_sim2) {
                phoneInput.title = `SIM1: ${dev.phone_sim1} | SIM2: ${dev.phone_sim2}`;
            } else {
                phoneInput.title = 'Número detectado automáticamente';
            }
        } else {
            // Número desde caché local
            phoneInput.title = 'Número guardado localmente (ingresado antes)';
        }
        phoneInput.classList.remove('is-invalid');
        phoneInput.classList.add('is-valid');
    } else {
        phoneInput.placeholder = 'No detectado – ingresar manualmente';
        phoneInput.classList.remove('is-valid');
        phoneInput.title = '';
    }
}

// ==================== INICIALIZACIÓN ====================

document.addEventListener('DOMContentLoaded', function() {
    // Solo cargar si estamos en la página correcta
    if (document.getElementById('customTestsList')) {
        loadCustomTests();
        refreshDUTDeviceSelects();

        // Verificar si hay ejecución en curso
        checkDUTExecutionStatus();
    }
});

async function checkDUTExecutionStatus() {
    try {
        const response = await fetch('/api/dut/status');
        const data = await response.json();

        if (data.success && data.state.is_running) {
            dutState.isExecuting = true;
            updateDUTExecutionButtons(true);
            startDUTPolling();
        }
    } catch (error) {
        console.error('Error verificando estado DUT:', error);
    }
}
