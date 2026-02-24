// ==================== SPEEDTEST (Appendix 3) ====================

let stState = {
    isRunning: false,
    pollInterval: null,
    devices: {},
    results: {}  // { '5G': [{iteration, download, upload}, ...], '4G': [...] }
};

// ==================== DISPOSITIVOS ====================

async function stRefreshDevices() {
    try {
        const response = await fetch('/api/devices');
        const data = await response.json();
        const select = document.getElementById('stDeviceSelect');
        if (!select) return;

        select.innerHTML = '<option value="">Seleccionar...</option>';
        stState.devices = {};

        if (data.success && data.devices.length > 0) {
            data.devices.forEach(device => {
                stState.devices[device.serial] = device;
                const phone = device.phone_number ? ` - ${device.phone_number}` : '';
                const op = device.sim_operator || '';
                select.innerHTML += `<option value="${device.serial}">${device.model} ${op}${phone} (${device.serial.substring(0, 8)}...)</option>`;
            });
        }

        select.onchange = stOnDeviceChange;
    } catch (error) {
        console.error('Error cargando dispositivos:', error);
    }
}

function stOnDeviceChange() {
    const serial = document.getElementById('stDeviceSelect').value;
    const infoDiv = document.getElementById('stDeviceInfo');

    if (serial && stState.devices[serial]) {
        const dev = stState.devices[serial];
        document.getElementById('stOperator').textContent = dev.sim_operator || '-';
        document.getElementById('stCurrentNet').textContent = dev.network_type || '-';
        document.getElementById('stPhone').textContent = dev.phone_number || '-';
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }
}

// ==================== EJECUCIÓN ====================

async function stStartExecution() {
    const serial = document.getElementById('stDeviceSelect').value;
    if (!serial) {
        showNotification('Selecciona un dispositivo', 'warning');
        return;
    }

    // Obtener redes seleccionadas
    const networks = [];
    if (document.getElementById('stNet5g').checked) networks.push('5g');
    if (document.getElementById('stNet4g').checked) networks.push('4g');
    if (networks.length === 0) {
        showNotification('Selecciona al menos una red', 'warning');
        return;
    }

    const role = document.querySelector('input[name="stRole"]:checked').value;
    const iterations = parseInt(document.getElementById('stIterations').value) || 5;

    // Preparar tabla de resultados
    stState.results = {};
    networks.forEach(net => {
        stState.results[net.toUpperCase()] = [];
        for (let i = 1; i <= iterations; i++) {
            stState.results[net.toUpperCase()].push({
                iteration: i, download: '', upload: '', screenshot: null
            });
        }
    });
    stRenderResultTables();

    try {
        const response = await fetch('/api/speedtest/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                serial: serial,
                role: role,
                operator: stState.devices[serial]?.sim_operator || '',
                networks: networks,
                iterations: iterations
            })
        });
        const data = await response.json();
        if (data.success) {
            stState.isRunning = true;
            document.getElementById('btnStStart').disabled = true;
            document.getElementById('btnStStop').disabled = false;
            showNotification('Prueba de velocidad iniciada', 'success');
            stStartPolling();
        } else {
            showNotification('Error: ' + data.error, 'danger');
        }
    } catch (error) {
        showNotification('Error de conexión', 'danger');
    }
}

async function stStopExecution() {
    try {
        await fetch('/api/speedtest/stop', { method: 'POST' });
        showNotification('Deteniendo prueba de velocidad...', 'warning');
    } catch (error) {
        console.error('Error stopping:', error);
    }
}

// ==================== POLLING ====================

function stStartPolling() {
    if (stState.pollInterval) clearInterval(stState.pollInterval);
    stState.pollInterval = setInterval(stPollStatus, 3000);
    stPollStatus();
}

async function stPollStatus() {
    try {
        const response = await fetch('/api/speedtest/status');
        const data = await response.json();
        if (!data.success) return;

        // Actualizar progreso
        const prog = data.progress || {};
        const total = prog.total_iterations || 1;
        const current = prog.current_iteration || 0;
        const pct = Math.round((current / total) * 100);

        document.getElementById('stProgressBar').style.width = pct + '%';
        document.getElementById('stProgressBar').textContent = pct + '%';

        let statusText = '';
        if (prog.phase === 'switching') statusText = `Cambiando a ${prog.current_network}...`;
        else if (prog.phase === 'testing') statusText = `${prog.current_network} - Iteración ${current}/${total}`;
        else if (prog.phase === 'done') statusText = `Completado`;
        else statusText = prog.phase || '';
        document.getElementById('stProgressText').textContent = statusText;

        // Actualizar logs
        if (data.logs && data.logs.length > 0) {
            const logsDiv = document.getElementById('stLogs');
            logsDiv.innerHTML = data.logs.map(l => {
                const cls = l.includes('[ERROR]') ? 'text-danger' : l.includes('[WARNING]') ? 'text-warning' : 'text-light';
                return `<div class="${cls}">${l}</div>`;
            }).join('');
            logsDiv.scrollTop = logsDiv.scrollHeight;
        }

        // Actualizar resultados (download, upload, ping) desde el servidor
        if (data.results && data.results.length > 0) {
            data.results.forEach(r => {
                const net = r.network;
                const idx = r.iteration - 1;
                if (stState.results[net] && stState.results[net][idx]) {
                    if (r.download) stState.results[net][idx].download = r.download;
                    if (r.upload) stState.results[net][idx].upload = r.upload;
                    if (r.ping) stState.results[net][idx].ping = r.ping;
                }
            });
        }

        // Actualizar screenshots (usa path completo para las URLs)
        if (data.screenshots && data.screenshots.length > 0) {
            data.screenshots.forEach(ss => {
                const net = ss.network;
                const idx = ss.iteration - 1;
                if (stState.results[net] && stState.results[net][idx]) {
                    stState.results[net][idx].screenshot = ss.path;
                }
            });
            stRenderScreenshots(data.screenshots);
        }

        // Re-renderizar tabla y promedios
        stRenderResultTables();
        Object.keys(stState.results).forEach(net => stUpdateAverages(net));

        // Si terminó, parar polling
        if (prog.status === 'completed' || prog.status === 'stopped') {
            stState.isRunning = false;
            clearInterval(stState.pollInterval);
            document.getElementById('btnStStart').disabled = false;
            document.getElementById('btnStStop').disabled = true;

            if (prog.status === 'completed') {
                showNotification('Prueba de velocidad completada', 'success');
            }
        }
    } catch (error) {
        console.error('Error polling status:', error);
    }
}

// ==================== TABLA DE RESULTADOS ====================

function stRenderResultTables() {
    const container = document.getElementById('stResultsContainer');
    const role = document.querySelector('input[name="stRole"]:checked').value;
    const roleLabel = role === 'dut' ? 'DUT (Principal)' : 'REF (Referencia)';

    let html = '';
    for (const [network, iterations] of Object.entries(stState.results)) {
        html += `
        <div class="mb-3">
            <h6 class="bg-dark text-white p-2 rounded-top mb-0">
                <i class="fas fa-signal"></i> ${network} - ${roleLabel}
            </h6>
            <table class="table table-bordered table-sm mb-0">
                <thead class="table-dark">
                    <tr>
                        <th width="80">#</th>
                        <th>Bajada (Mbps)</th>
                        <th>Subida (Mbps)</th>
                        <th width="100">Captura</th>
                    </tr>
                </thead>
                <tbody>`;

        iterations.forEach((iter, idx) => {
            html += `
                    <tr>
                        <td class="text-center fw-bold">${iter.iteration}</td>
                        <td><input type="number" step="0.1" class="form-control form-control-sm st-dl"
                                   data-net="${network}" data-idx="${idx}"
                                   value="${iter.download}" placeholder="Mbps"
                                   onchange="stUpdateResult(this)"></td>
                        <td><input type="number" step="0.1" class="form-control form-control-sm st-ul"
                                   data-net="${network}" data-idx="${idx}"
                                   value="${iter.upload}" placeholder="Mbps"
                                   onchange="stUpdateResult(this)"></td>
                        <td class="text-center">
                            ${iter.screenshot
                                ? `<a href="/api/speedtest/screenshot/${iter.screenshot}" target="_blank" class="btn btn-sm btn-outline-info"><i class="fas fa-image"></i></a>`
                                : '<span class="text-muted">-</span>'}
                        </td>
                    </tr>`;
        });

        // Fila de promedio
        html += `
                    <tr class="table-warning fw-bold">
                        <td class="text-center">Promedio</td>
                        <td id="stAvgDl_${network}">-</td>
                        <td id="stAvgUl_${network}">-</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </div>`;
    }

    container.innerHTML = html;
}

function stUpdateResult(input) {
    const net = input.dataset.net;
    const idx = parseInt(input.dataset.idx);
    const isDownload = input.classList.contains('st-dl');

    if (stState.results[net] && stState.results[net][idx]) {
        if (isDownload) {
            stState.results[net][idx].download = input.value;
        } else {
            stState.results[net][idx].upload = input.value;
        }
    }

    // Recalcular promedio
    stUpdateAverages(net);
}

function stUpdateAverages(network) {
    const iterations = stState.results[network] || [];
    let dlSum = 0, dlCount = 0, ulSum = 0, ulCount = 0;

    iterations.forEach(iter => {
        const dl = parseFloat(iter.download);
        const ul = parseFloat(iter.upload);
        if (!isNaN(dl)) { dlSum += dl; dlCount++; }
        if (!isNaN(ul)) { ulSum += ul; ulCount++; }
    });

    const dlAvg = dlCount > 0 ? (dlSum / dlCount).toFixed(1) : '-';
    const ulAvg = ulCount > 0 ? (ulSum / ulCount).toFixed(1) : '-';

    const dlEl = document.getElementById(`stAvgDl_${network}`);
    const ulEl = document.getElementById(`stAvgUl_${network}`);
    if (dlEl) dlEl.textContent = dlAvg;
    if (ulEl) ulEl.textContent = ulAvg;
}

// ==================== SCREENSHOTS ====================

function stRenderScreenshots(screenshots) {
    const container = document.getElementById('stScreenshots');
    if (!screenshots || screenshots.length === 0) return;

    container.innerHTML = screenshots.map(ss => `
        <a href="/api/speedtest/screenshot/${ss.path}" target="_blank" class="text-decoration-none">
            <div class="border rounded p-1 text-center" style="width: 100px;">
                <img src="/api/speedtest/screenshot/${ss.path}" class="img-fluid rounded" style="max-height: 120px;">
                <div class="small text-muted">${ss.network} #${ss.iteration}</div>
            </div>
        </a>
    `).join('');
}

// ==================== GUARDAR ====================

async function stSaveResults() {
    const role = document.querySelector('input[name="stRole"]:checked').value;
    const serial = document.getElementById('stDeviceSelect').value;
    const dev = stState.devices[serial] || {};

    try {
        const response = await fetch('/api/speedtest/results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                config: {
                    operator: dev.sim_operator || '',
                    role: role,
                    serial: serial,
                    model: dev.model || ''
                },
                results: stState.results
            })
        });
        const data = await response.json();
        if (data.success) {
            showNotification('Resultados guardados', 'success');
        } else {
            showNotification('Error guardando: ' + data.error, 'danger');
        }
    } catch (error) {
        showNotification('Error de conexión', 'danger');
    }
}

// ==================== INICIALIZACIÓN ====================

document.addEventListener('DOMContentLoaded', function() {
    // Cargar dispositivos al abrir el modal
    const modal = document.getElementById('speedtestModal');
    if (modal) {
        modal.addEventListener('shown.bs.modal', function() {
            stRefreshDevices();
        });
    }
});
