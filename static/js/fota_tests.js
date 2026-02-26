// ==================== FOTA TEST CASES ====================

let fotaState = {
    devices: {},
    tests: [],
    isRunning: false,
    pollInterval: null
};

// ==================== DISPOSITIVOS ====================

async function fotaRefreshDevices() {
    try {
        const response = await fetch('/api/devices');
        const data = await response.json();

        const sel1 = document.getElementById('fotaDutSelect');
        const sel2 = document.getElementById('fotaDut2Select');
        if (!sel1 || !sel2) return;

        sel1.innerHTML = '<option value="">Seleccionar DUT...</option>';
        sel2.innerHTML = '<option value="">Sin DUT2</option>';
        fotaState.devices = {};

        if (data.success && data.devices.length > 0) {
            data.devices.forEach(device => {
                fotaState.devices[device.serial] = device;
                const phone = device.phone_number ? ` - ${device.phone_number}` : '';
                const op = device.sim_operator || '';
                const label = `${device.model} ${op}${phone} (${device.serial.substring(0, 8)}...)`;
                sel1.innerHTML += `<option value="${device.serial}">${label}</option>`;
                sel2.innerHTML += `<option value="${device.serial}">${label}</option>`;
            });
        }

        sel1.onchange = fotaOnDeviceChange;
        sel2.onchange = fotaOnDut2Change;
    } catch (error) {
        console.error('Error cargando dispositivos:', error);
    }
}

function fotaOnDeviceChange() {
    const serial = document.getElementById('fotaDutSelect').value;
    const dev = fotaState.devices[serial];

    const info = document.getElementById('fotaDutInfo');
    if (dev) {
        document.getElementById('fotaDutOp').textContent = dev.sim_operator || '-';
        document.getElementById('fotaDutPhone').textContent = dev.phone_number || 'Sin numero';
        info.style.display = 'block';

        // Auto-llenar info del dispositivo
        document.getElementById('fotaModel').value    = dev.model      || '';
        const swVer = dev.sw_version || '';
        document.getElementById('fotaSwVersion').value = swVer;

        // Advertencia si la version SW no corresponde a Claro Colombia (COCL)
        const warn    = document.getElementById('fotaSwVersionWarning');
        const warnMsg = document.getElementById('fotaSwVersionWarningMsg');
        if (warn && warnMsg) {
            if (swVer && !swVer.toUpperCase().includes('COCL')) {
                warnMsg.textContent = `La version "${swVer}" no parece ser de Claro Colombia (no contiene "COCL"). Verifique que el firmware sea correcto antes de ejecutar las pruebas.`;
                warn.style.display = 'block';
            } else {
                warn.style.display = 'none';
            }
        }

        fotaLoadTests();
    } else {
        info.style.display = 'none';
    }
}

function fotaOnDut2Change() {
    const serial = document.getElementById('fotaDut2Select').value;
    const dev = fotaState.devices[serial];

    const info = document.getElementById('fotaDut2Info');
    if (dev) {
        document.getElementById('fotaDut2Op').textContent = dev.sim_operator || '-';
        document.getElementById('fotaDut2Phone').textContent = dev.phone_number || 'Sin numero';
        info.style.display = 'block';
    } else {
        info.style.display = 'none';
    }
}

// ==================== CARGAR TESTS ====================

async function fotaLoadTests() {
    try {
        const response = await fetch('/api/fota/tests');
        const data = await response.json();

        if (data.success) {
            fotaState.tests = data.tests;
            fotaRenderTable();
        }
    } catch (error) {
        console.error('Error cargando FOTA tests:', error);
    }
}

// ==================== TABLA DE TESTS ====================

function fotaRenderTable() {
    const tbody = document.getElementById('fotaTestTableBody');
    if (!fotaState.tests || fotaState.tests.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">No hay tests cargados</td></tr>';
        return;
    }

    let html = '';
    let countPass = 0, countFail = 0, countNA = 0, countPending = 0;

    fotaState.tests.forEach(test => {
        const result = test.result || 'pending';

        // Contar
        if (result === 'Pass') countPass++;
        else if (result === 'Fail') countFail++;
        else if (result === 'NA') countNA++;
        else countPending++;

        // Badge de tipo
        let typeBadge = '';
        if (test.automation === 'auto') typeBadge = '<span class="badge bg-success">Auto</span>';
        else if (test.automation === 'semi') typeBadge = '<span class="badge bg-warning text-dark">Semi</span>';
        else typeBadge = '<span class="badge bg-secondary">Manual</span>';

        // Badge de resultado
        let resultBadge = '';
        if (result === 'Pass') resultBadge = '<span class="badge bg-success">Pass</span>';
        else if (result === 'Fail') resultBadge = '<span class="badge bg-danger">Fail</span>';
        else if (result === 'NA') resultBadge = '<span class="badge bg-dark">N/A</span>';
        else if (result === 'running') resultBadge = '<span class="badge bg-primary"><i class="fas fa-spinner fa-spin"></i></span>';
        else resultBadge = '<span class="badge bg-secondary">Pend</span>';

        // Botones de acción
        let actions = '';
        const disabled = fotaState.isRunning ? 'disabled' : '';

        // Botón ejecutar (para auto y semi)
        if (test.auto_func && test.default_result !== 'NA') {
            actions += `<button class="btn btn-sm btn-outline-primary py-0 px-1" onclick="fotaRunSingle(${test.id})" ${disabled} title="Ejecutar">
                <i class="fas fa-play"></i>
            </button> `;
        }

        // Botones Pass/Fail/NA (para todos)
        actions += `<button class="btn btn-sm btn-outline-success py-0 px-1" onclick="fotaSetResult(${test.id},'Pass')" ${disabled} title="Pass">
            <i class="fas fa-check"></i>
        </button> `;
        actions += `<button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="fotaSetResult(${test.id},'Fail')" ${disabled} title="Fail">
            <i class="fas fa-times"></i>
        </button> `;
        actions += `<button class="btn btn-sm btn-outline-dark py-0 px-1" onclick="fotaSetResult(${test.id},'NA')" ${disabled} title="N/A">
            N/A
        </button>`;

        // Descripción truncada
        const desc = test.description.length > 80
            ? test.description.substring(0, 80) + '...'
            : test.description;

        // Fila con tooltip de remark
        const remarkAttr = test.remark ? `title="${test.remark.replace(/"/g, '&quot;')}"` : '';
        const rowClass = result === 'Fail' ? 'table-danger' : result === 'Pass' ? '' : '';

        html += `
            <tr id="fotaRow_${test.id}" class="${rowClass}" ${remarkAttr}>
                <td class="text-center">${test.id}</td>
                <td><strong>${test.title}</strong></td>
                <td class="small">${desc.replace(/\n/g, '<br>')}</td>
                <td class="text-center">${typeBadge}</td>
                <td class="text-center" id="fotaStatus_${test.id}">${resultBadge}</td>
                <td class="text-center text-nowrap">${actions}</td>
            </tr>`;
    });

    tbody.innerHTML = html;

    document.getElementById('fotaCountPass').textContent = countPass;
    document.getElementById('fotaCountFail').textContent = countFail;
    document.getElementById('fotaCountNA').textContent = countNA;
    document.getElementById('fotaCountPending').textContent = countPending;
}

// ==================== EJECUCIÓN ====================

async function fotaRunSingle(testId) {
    const serial = document.getElementById('fotaDutSelect').value;
    if (!serial) {
        showNotification('Selecciona un dispositivo', 'warning');
        return;
    }

    const dut2Serial = document.getElementById('fotaDut2Select').value || '';
    const dut2Dev = fotaState.devices[dut2Serial];
    const dut2Phone = dut2Dev ? dut2Dev.phone_number || '' : '';

    try {
        const response = await fetch('/api/fota/run-single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                serial: serial,
                test_id: testId,
                dut2_serial: dut2Serial,
                dut2_phone: dut2Phone
            })
        });
        const data = await response.json();
        if (data.success) {
            showNotification(`Test #${testId}: ${data.result.result}`, data.result.result === 'Pass' ? 'success' : 'info');
            fotaLoadTests();
        } else {
            showNotification('Error: ' + data.error, 'danger');
        }
    } catch (error) {
        showNotification('Error de conexion', 'danger');
    }
}

async function fotaRunAllAuto() {
    const serial = document.getElementById('fotaDutSelect').value;
    if (!serial) {
        showNotification('Selecciona un dispositivo', 'warning');
        return;
    }

    const dut2Serial = document.getElementById('fotaDut2Select').value || '';
    const dut2Dev = fotaState.devices[dut2Serial];
    const dut2Phone = dut2Dev ? dut2Dev.phone_number || '' : '';

    try {
        const response = await fetch('/api/fota/run-all-auto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                serial: serial,
                dut2_serial: dut2Serial,
                dut2_phone: dut2Phone
            })
        });
        const data = await response.json();

        if (data.success) {
            fotaState.isRunning = true;
            document.getElementById('btnFotaRunAll').disabled = true;
            document.getElementById('btnFotaStop').disabled = false;
            showNotification('Ejecucion automatica iniciada', 'success');
            fotaStartPolling();
        } else {
            showNotification('Error: ' + data.error, 'danger');
        }
    } catch (error) {
        showNotification('Error de conexion', 'danger');
    }
}

async function fotaStop() {
    try {
        await fetch('/api/fota/stop', { method: 'POST' });
        showNotification('Deteniendo ejecucion...', 'warning');
    } catch (error) {
        console.error('Error stopping:', error);
    }
}

async function fotaSetResult(testId, result) {
    const remark = result === 'Fail'
        ? prompt('Comentario para el fallo (opcional):') || ''
        : '';

    try {
        const response = await fetch('/api/fota/set-result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_id: testId, result: result, remark: remark })
        });
        const data = await response.json();
        if (data.success) {
            fotaLoadTests();
        }
    } catch (error) {
        console.error('Error setting result:', error);
    }
}

// ==================== INFORME ====================

async function fotaGenerateReport() {
    const model = document.getElementById('fotaModel').value;
    const swVersion = document.getElementById('fotaSwVersion').value;
    const tester = document.getElementById('fotaTester').value;
    const spDate = document.getElementById('fotaSpDate').value;

    if (!tester) {
        showNotification('Ingresa el nombre del tester', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/fota/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: model,
                sw_version: swVersion,
                tester: tester,
                sp_date: spDate,
                format: 'excel'
            })
        });
        const data = await response.json();

        if (data.success) {
            showNotification('Informe generado: ' + data.path, 'success');
            // Extraer solo el nombre del archivo
            const filename = data.path.split(/[/\\]/).pop();
            window.open('/api/fota/report/download/' + filename, '_blank');
        } else {
            showNotification('Error: ' + data.error, 'danger');
        }
    } catch (error) {
        showNotification('Error generando informe', 'danger');
    }
}

// ==================== POLLING ====================

function fotaStartPolling() {
    if (fotaState.pollInterval) clearInterval(fotaState.pollInterval);
    fotaState.pollInterval = setInterval(fotaPollStatus, 3000);
    fotaPollStatus();
}

async function fotaPollStatus() {
    try {
        const response = await fetch('/api/fota/status');
        const data = await response.json();
        if (!data.success) return;

        // Progreso
        const prog = data.progress || {};
        const total = prog.total_tests || 1;
        const current = prog.current_test || 0;
        const pct = Math.round((current / total) * 100);

        document.getElementById('fotaProgressBar').style.width = pct + '%';
        document.getElementById('fotaProgressBar').textContent = pct + '%';
        document.getElementById('fotaProgressText').textContent = prog.phase || '';

        // Logs
        if (data.logs && data.logs.length > 0) {
            const logsDiv = document.getElementById('fotaLogs');
            logsDiv.innerHTML = data.logs.map(l => {
                const cls = l.includes('[ERROR]') ? 'text-danger' : l.includes('[WARNING]') ? 'text-warning' : 'text-light';
                return `<div class="${cls}">${l}</div>`;
            }).join('');
            logsDiv.scrollTop = logsDiv.scrollHeight;
        }

        // Contadores
        if (data.counts) {
            document.getElementById('fotaCountPass').textContent = data.counts.Pass || 0;
            document.getElementById('fotaCountFail').textContent = data.counts.Fail || 0;
            document.getElementById('fotaCountNA').textContent = data.counts.NA || 0;
            document.getElementById('fotaCountPending').textContent = data.counts.pending || 0;
        }

        // Actualizar resultados en tabla
        if (data.results) {
            for (const [testId, result] of Object.entries(data.results)) {
                // Actualizar en fotaState.tests
                const test = fotaState.tests.find(t => t.id == testId);
                if (test) {
                    test.result = result.result;
                    test.remark = result.remark;
                }
            }
            fotaRenderTable();
        }

        // Terminado
        if (prog.status === 'completed' || prog.status === 'error') {
            fotaState.isRunning = false;
            clearInterval(fotaState.pollInterval);
            document.getElementById('btnFotaRunAll').disabled = false;
            document.getElementById('btnFotaStop').disabled = true;

            if (prog.status === 'completed') {
                showNotification('Ejecucion automatica completada', 'success');
            }
            fotaLoadTests();
        }
    } catch (error) {
        console.error('Error polling FOTA status:', error);
    }
}

// ==================== INICIALIZACIÓN ====================

document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('fotaModal');
    if (modal) {
        modal.addEventListener('shown.bs.modal', function() {
            fotaRefreshDevices();
        });
    }
});
