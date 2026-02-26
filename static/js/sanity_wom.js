/**
 * Sanity Check WOM - Logica de UI
 * Checklist post-OTA para WOM Colombia
 */

const SANITY_WOM = {
    tests: [],
    activeCategory: 'all',
    selectedSerial: '',
    lastResultPath: '',

    CATEGORIES: {
        all:     { label: 'Todos',     color: 'secondary' },
        general: { label: 'General',   color: 'primary' },
        csfb:    { label: 'CSFB',      color: 'warning' },
        volte:   { label: 'VoLTE',     color: 'purple' },
        vowifi:  { label: 'VoWiFi',    color: 'success' },
        '5g':    { label: '5G NR',     color: 'danger' },
    },

    AUTO_BADGE: {
        auto:   '<span class="badge bg-success">AUTO</span>',
        semi:   '<span class="badge bg-warning text-dark">SEMI</span>',
        manual: '<span class="badge bg-secondary">MANUAL</span>',
    },

    RESULT_BTN: {
        pass: 'btn-success',
        fail: 'btn-danger',
        na:   'btn-secondary',
    },
};

// ──────────────────────────────────────────────
// Inicializacion al abrir el modal
// ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('sanityWomModal');
    if (modal) {
        modal.addEventListener('show.bs.modal', womOnModalOpen);
    }
});

function womOnModalOpen() {
    womRefreshDevices();
    womLoadTests();
}

// ──────────────────────────────────────────────
// Dispositivos
// ──────────────────────────────────────────────
function womRefreshDevices() {
    fetch('/api/devices')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('womDeviceSelect');
            const prev = sel.value;
            sel.innerHTML = '<option value="">Seleccionar dispositivo...</option>';
            if (data.success && data.devices.length > 0) {
                data.devices.forEach(d => {
                    const op = document.createElement('option');
                    op.value = d.serial;
                    op.textContent = `${d.model || d.serial} (${d.serial})`;
                    op.dataset.model     = d.model      || '';
                    op.dataset.swVersion = d.sw_version || '';
                    sel.appendChild(op);
                });
                if (prev) sel.value = prev;
            }
            SANITY_WOM.selectedSerial = sel.value;
        })
        .catch(() => {});
}

document.addEventListener('change', e => {
    if (e.target.id === 'womDeviceSelect') {
        SANITY_WOM.selectedSerial = e.target.value;
        // Autocompletar modelo si hay dispositivo
        if (e.target.value) {
            const opt = e.target.options[e.target.selectedIndex];
            const model   = opt.dataset.model     || (opt.textContent.split('(')[0] || '').trim();
            const swVer   = opt.dataset.swVersion || '';
            const inpModel = document.getElementById('womModel');
            const inpSW    = document.getElementById('womSwVersion');
            if (inpModel && !inpModel.value) inpModel.value = model;
            if (inpSW)                        inpSW.value   = swVer;
        }
    }
});

// ──────────────────────────────────────────────
// Carga de tests
// ──────────────────────────────────────────────
function womLoadTests() {
    fetch('/api/sanity-wom/tests')
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            SANITY_WOM.tests = data.tests;
            womRender();
            womUpdateSummary();
        })
        .catch(e => console.error('Error loading WOM tests:', e));
}

// ──────────────────────────────────────────────
// Render de la tabla
// ──────────────────────────────────────────────
function womRender() {
    const cat = SANITY_WOM.activeCategory;
    const filtered = cat === 'all'
        ? SANITY_WOM.tests
        : SANITY_WOM.tests.filter(t => t.category === cat);

    const tbody = document.getElementById('womTableBody');
    if (!tbody) return;

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No hay casos en esta categoria</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map((tc, idx) => {
        const resultClass = womResultRowClass(tc.result);
        const hasAuto = tc.auto_func !== '';

        return `
        <tr class="${resultClass}" id="wom-row-${tc.id}">
            <td class="text-center small fw-bold">${idx + 1}</td>
            <td class="small">
                <span class="d-block fw-semibold" style="font-size:0.78em;">${escapeHtml(tc.name)}</span>
                <span class="text-muted" style="font-size:0.7em;">${escapeHtml(tc.number)}</span>
            </td>
            <td class="text-center">${SANITY_WOM.AUTO_BADGE[tc.automation] || tc.automation}</td>
            <td class="text-center">
                <div class="btn-group btn-group-sm" role="group">
                    <button class="btn btn-sm ${tc.result === 'pass' ? 'btn-success' : 'btn-outline-success'}"
                            onclick="womSetResult('${tc.id}', 'pass')" title="PASS">
                        <i class="fas fa-check"></i>
                    </button>
                    <button class="btn btn-sm ${tc.result === 'fail' ? 'btn-danger' : 'btn-outline-danger'}"
                            onclick="womSetResult('${tc.id}', 'fail')" title="FAIL">
                        <i class="fas fa-times"></i>
                    </button>
                    <button class="btn btn-sm ${tc.result === 'na' ? 'btn-secondary' : 'btn-outline-secondary'}"
                            onclick="womSetResult('${tc.id}', 'na')" title="N/A">
                        N/A
                    </button>
                </div>
            </td>
            <td>
                <input type="text" class="form-control form-control-sm"
                       id="wom-remark-${tc.id}"
                       value="${escapeHtml(tc.remark || '')}"
                       placeholder="Observacion..."
                       onblur="womSaveRemark('${tc.id}')"
                       onkeydown="if(event.key==='Enter') womSaveRemark('${tc.id}')">
            </td>
            <td class="text-center">
                ${hasAuto ? `
                <button class="btn btn-sm btn-outline-primary" title="Ejecutar accion ADB"
                        onclick="womRunAuto('${tc.id}')">
                    <i class="fas fa-play"></i>
                </button>` : `<span class="text-muted small">-</span>`}
            </td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-info" title="Ver descripcion"
                        onclick="womShowDetail('${tc.id}')">
                    <i class="fas fa-info-circle"></i>
                </button>
            </td>
        </tr>`;
    }).join('');
}

function womResultRowClass(result) {
    return {
        pass:    'table-success',
        fail:    'table-danger',
        na:      'table-secondary',
        pending: '',
    }[result] || '';
}

// ──────────────────────────────────────────────
// Categorias (tabs)
// ──────────────────────────────────────────────
function womSetCategory(cat) {
    SANITY_WOM.activeCategory = cat;

    // Actualizar botones de categoria
    document.querySelectorAll('.wom-cat-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.cat === cat) btn.classList.add('active');
    });

    womRender();
}

// ──────────────────────────────────────────────
// Resumen / contadores
// ──────────────────────────────────────────────
function womUpdateSummary() {
    const counts = { pass: 0, fail: 0, na: 0, pending: 0 };
    SANITY_WOM.tests.forEach(t => { counts[t.result] = (counts[t.result] || 0) + 1; });

    const total = SANITY_WOM.tests.length;
    const done = counts.pass + counts.fail + counts.na;
    const pct = total > 0 ? Math.round(done / total * 100) : 0;

    setEl('womCountPass',    counts.pass);
    setEl('womCountFail',    counts.fail);
    setEl('womCountNA',      counts.na);
    setEl('womCountPending', counts.pending);

    const bar = document.getElementById('womProgressBar');
    if (bar) {
        bar.style.width = pct + '%';
        bar.textContent = pct + '%';
        bar.className = 'progress-bar ' + (counts.fail > 0 ? 'bg-danger' : 'bg-primary');
    }
}

function setEl(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ──────────────────────────────────────────────
// Resultado manual
// ──────────────────────────────────────────────
function womSetResult(testId, result) {
    const remarkEl = document.getElementById(`wom-remark-${testId}`);
    const remark = remarkEl ? remarkEl.value : '';

    fetch('/api/sanity-wom/set-result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_id: testId, result, remark }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const tc = SANITY_WOM.tests.find(t => t.id === testId);
            if (tc) tc.result = result;
            womRender();
            womUpdateSummary();
        }
    })
    .catch(e => console.error('Error setting result:', e));
}

function womSaveRemark(testId) {
    const remarkEl = document.getElementById(`wom-remark-${testId}`);
    const remark = remarkEl ? remarkEl.value : '';
    const tc = SANITY_WOM.tests.find(t => t.id === testId);
    if (!tc) return;

    fetch('/api/sanity-wom/set-result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_id: testId, result: tc.result, remark }),
    })
    .then(r => r.json())
    .then(data => { if (data.success && tc) tc.remark = remark; })
    .catch(() => {});
}

// ──────────────────────────────────────────────
// Ejecucion ADB (AUTO / SEMI)
// ──────────────────────────────────────────────
function womRunAuto(testId) {
    if (!SANITY_WOM.selectedSerial) {
        showWomFeedback('Selecciona un dispositivo primero.', 'warning');
        return;
    }

    const btn = document.querySelector(`#wom-row-${testId} .btn-outline-primary`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    fetch('/api/sanity-wom/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_id: testId, serial: SANITY_WOM.selectedSerial }),
    })
    .then(r => r.json())
    .then(data => {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-play"></i>';
        }

        // Actualizar test local si vino auto_result
        if (data.auto_result) {
            const tc = SANITY_WOM.tests.find(t => t.id === testId);
            if (tc) tc.result = data.auto_result;
            womRender();
            womUpdateSummary();
        }

        // Mostrar resultado en modal de detalle si esta abierto
        womShowAutoResult(data);
    })
    .catch(e => {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i>'; }
        console.error('Error running auto test:', e);
    });
}

function womShowAutoResult(data) {
    const panel = document.getElementById('womAutoResultPanel');
    const msg   = document.getElementById('womAutoResultMsg');
    if (!panel || !msg) return;

    panel.style.display = 'block';
    panel.className = `alert ${data.success ? 'alert-info' : 'alert-danger'} mt-2`;
    msg.textContent = data.message || (data.success ? 'Ejecutado' : 'Error');
}

// ──────────────────────────────────────────────
// Detalle de caso
// ──────────────────────────────────────────────
function womShowDetail(testId) {
    const tc = SANITY_WOM.tests.find(t => t.id === testId);
    if (!tc) return;

    document.getElementById('womDetailTitle').textContent = tc.name;
    document.getElementById('womDetailNumber').textContent = tc.number;
    document.getElementById('womDetailCat').textContent = (SANITY_WOM.CATEGORIES[tc.category] || {}).label || tc.category;
    document.getElementById('womDetailAuto').innerHTML = SANITY_WOM.AUTO_BADGE[tc.automation] || tc.automation;
    document.getElementById('womDetailDesc').textContent = tc.description || '-';
    document.getElementById('womDetailProc').textContent = tc.procedure || '-';
    document.getElementById('womDetailExpected').textContent = tc.expected || '-';

    // Panel de resultado ADB (limpiar)
    const panel = document.getElementById('womAutoResultPanel');
    if (panel) panel.style.display = 'none';

    // Boton ejecutar en el detalle
    const runBtn = document.getElementById('womDetailRunBtn');
    if (runBtn) {
        if (tc.auto_func) {
            runBtn.style.display = '';
            runBtn.onclick = () => womRunAuto(testId);
        } else {
            runBtn.style.display = 'none';
        }
    }

    const detailModal = new bootstrap.Modal(document.getElementById('womDetailModal'));
    detailModal.show();
}

// ──────────────────────────────────────────────
// Reporte Excel
// ──────────────────────────────────────────────
function womGenerateReport() {
    const model     = (document.getElementById('womModel')     || {}).value || '';
    const tester    = (document.getElementById('womTester')    || {}).value || '';
    const swVersion = (document.getElementById('womSwVersion') || {}).value || '';

    const btn = document.getElementById('btnWomReport');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generando...'; }

    fetch('/api/sanity-wom/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, tester, sw_version: swVersion }),
    })
    .then(r => r.json())
    .then(data => {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-file-excel"></i> Generar Informe Excel'; }

        if (data.success) {
            const filename = data.path.split(/[\\/]/).pop();
            SANITY_WOM.lastResultPath = filename;
            showWomFeedback(`Informe generado: ${filename}`, 'success');

            // Descarga automatica
            window.location.href = `/api/sanity-wom/report/download/${filename}`;
        } else {
            showWomFeedback(`Error: ${data.error}`, 'danger');
        }
    })
    .catch(e => {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-file-excel"></i> Generar Informe Excel'; }
        showWomFeedback('Error de conexion', 'danger');
    });
}

// ──────────────────────────────────────────────
// Reset
// ──────────────────────────────────────────────
function womReset() {
    if (!confirm('¿Desea reiniciar todos los resultados del Sanity Check WOM?\nEsto borrara todos los PASS/FAIL/NA y observaciones guardados.')) return;

    fetch('/api/sanity-wom/reset', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                womLoadTests();
                showWomFeedback('Resultados reiniciados.', 'info');
            }
        })
        .catch(() => {});
}

// ──────────────────────────────────────────────
// Feedback
// ──────────────────────────────────────────────
function showWomFeedback(msg, type = 'info') {
    const el = document.getElementById('womFeedback');
    if (!el) return;
    el.className = `alert alert-${type} py-1 px-2 mt-2 small`;
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 4000);
}

// ──────────────────────────────────────────────
// Utilidades
// ──────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
