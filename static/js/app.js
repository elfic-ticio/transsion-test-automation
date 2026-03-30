// ==================== APP GLOBAL - TRANSSION ====================

// ==================== VERSION ANDROID ====================

let selectedAndroidVersion = '16';

function getAndroidVersion() {
    return selectedAndroidVersion;
}

function autoSelectAndroidVersion(devices) {
    if (!devices || devices.length === 0) return;

    // Tomar la versión major del primer dispositivo conectado
    const ver = devices[0].android_version || '';
    const major = ver.split('.')[0];

    if (['14', '15', '16'].includes(major)) {
        selectedAndroidVersion = major;
        const radio = document.getElementById('av' + major);
        if (radio) {
            radio.checked = true;
        }
        document.getElementById('androidVersionNote').innerHTML =
            `Detectado automaticamente: Android <strong>${major}</strong> (${devices[0].model})`;
    }
}

// ==================== NOTIFICACIONES ====================

function showNotification(message, type = 'info') {
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert"
             style="position: fixed; top: 20px; right: 20px; z-index: 9999;">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

    const div = document.createElement('div');
    div.innerHTML = toastHtml;
    document.body.appendChild(div);

    const toast = new bootstrap.Toast(div.firstElementChild);
    toast.show();

    setTimeout(() => div.remove(), 5000);
}

// ==================== DISPOSITIVOS (Dashboard) ====================

const OPERATOR_COLORS = {
    'Claro': 'danger',
    'Movistar': 'primary',
    'Tigo': 'info',
    'WOM': 'success'
};

async function refreshDevices() {
    const container = document.getElementById('devicesContainer');
    if (!container) return;

    try {
        const response = await fetch('/api/devices');
        const data = await response.json();

        if (data.success && data.devices.length > 0) {
            // Auto-detectar versión Android
            autoSelectAndroidVersion(data.devices);

            container.innerHTML = data.devices.map(device => {
                const op = device.sim_operator || 'Desconocido';
                const opColor = OPERATOR_COLORS[op] || 'secondary';
                const net = device.network_type || '-';
                const serial = device.serial || '';
                const androidVer = device.android_version || '-';
                const swVer = device.sw_version || '-';
                const mfr = device.manufacturer ? `${device.manufacturer} ` : '';
                const cap5gBadge = device.supports_5g
                    ? `<span class="badge bg-success ms-1" title="Hardware 5G NR compatible"><i class="fas fa-broadcast-tower me-1"></i>5G</span>`
                    : `<span class="badge bg-secondary ms-1" title="Sin soporte 5G NR">No 5G</span>`;

                // Numero de telefono: mostrar SIM1/SIM2 por separado si hay dual SIM
                let phoneHtml = '';
                if (device.phone_sim1 && device.phone_sim2) {
                    phoneHtml = `<i class="fas fa-sim-card me-1"></i>SIM1: ${device.phone_sim1} &nbsp; SIM2: ${device.phone_sim2}`;
                } else if (device.phone_sim1 || device.phone_sim2) {
                    phoneHtml = `<i class="fas fa-sim-card me-1"></i>${device.phone_sim1 || device.phone_sim2}`;
                } else {
                    phoneHtml = `<i class="fas fa-sim-card me-1 text-muted"></i><span class="text-muted fst-italic">Sin numero</span>`;
                }

                return `
                    <div class="col-md-6">
                        <div class="card border-${opColor} shadow-sm">
                            <div class="card-body py-2 px-3">
                                <div class="d-flex align-items-center gap-3">
                                    <i class="fas fa-mobile-alt fa-2x text-${opColor}"></i>
                                    <div class="flex-grow-1 min-width-0">
                                        <div class="fw-bold">${mfr}${device.model || 'Dispositivo desconocido'}${cap5gBadge}</div>
                                        <div class="small text-muted font-monospace">${serial}</div>
                                    </div>
                                    <div class="text-center flex-shrink-0">
                                        <span class="badge bg-${opColor}">${op}</span>
                                        <div class="small mt-1"><i class="fas fa-signal me-1"></i>${net}</div>
                                    </div>
                                </div>
                                <hr class="my-1">
                                <div class="small text-muted d-flex flex-column gap-1">
                                    <div>
                                        <i class="fab fa-android me-1"></i>Android ${androidVer}
                                        &nbsp;&nbsp;
                                        <i class="fas fa-code-branch me-1"></i>${swVer}
                                    </div>
                                    <div>${phoneHtml}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-warning text-center mb-0">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        No se encontraron dispositivos conectados. Conecta un dispositivo via USB y presiona "Actualizar Dispositivos".
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error al obtener dispositivos:', error);
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-danger text-center mb-0">
                    <i class="fas fa-times-circle me-2"></i>
                    Error de conexion con el servidor. Verifica que la aplicacion este ejecutandose.
                </div>
            </div>
        `;
    }
}

// ==================== INICIALIZACION ====================

document.addEventListener('DOMContentLoaded', function() {
    refreshDevices();

    // Selector manual de versión Android
    document.querySelectorAll('input[name="androidVersion"]').forEach(radio => {
        radio.addEventListener('change', function() {
            selectedAndroidVersion = this.value;
            document.getElementById('androidVersionNote').innerHTML =
                `Seleccion manual: Android <strong>${this.value}</strong>`;
        });
    });
});
