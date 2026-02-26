/**
 * Dashboard Admin - Frontend Logic
 * Handles all client-side interactions for the chatbot management dashboard.
 */

// ============================================================
// API Helper
// ============================================================

const API_BASE = '/admin';

async function api(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        ...options,
    };

    try {
        const response = await fetch(url, config);
        const data = await response.json();

        if (!response.ok) {
            const message = data.detail || data.message || 'Terjadi kesalahan';
            throw new Error(message);
        }
        return data;
    } catch (err) {
        if (err instanceof TypeError && err.message === 'Failed to fetch') {
            throw new Error('Tidak dapat terhubung ke server');
        }
        throw err;
    }
}

// ============================================================
// Toast Notifications
// ============================================================

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
    toast.innerHTML = `<span>${icons[type] || ''}</span> <span>${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ============================================================
// Loading Overlay
// ============================================================

function showLoading(text = 'Memproses...') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// ============================================================
// Confirm Modal
// ============================================================

function showConfirm(title, message) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal">
                <h3>${title}</h3>
                <p>${message}</p>
                <div class="modal-actions">
                    <button class="btn btn-outline" id="modalCancel">Batal</button>
                    <button class="btn btn-danger" id="modalConfirm">Ya, Lanjutkan</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.querySelector('#modalCancel').onclick = () => { overlay.remove(); resolve(false); };
        overlay.querySelector('#modalConfirm').onclick = () => { overlay.remove(); resolve(true); };
    });
}

// ============================================================
// Auth
// ============================================================

async function checkAuth() {
    try {
        await api('/api/auth/check');
        showDashboard();
        loadDocuments();
    } catch {
        showLogin();
    }
}

function showLogin() {
    document.getElementById('loginPage').style.display = 'flex';
    document.getElementById('dashboard').classList.remove('active');
}

function showDashboard() {
    document.getElementById('loginPage').style.display = 'none';
    document.getElementById('dashboard').classList.add('active');
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('loginBtn');
    const origText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Memproses...';

    try {
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        await api('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });

        showToast('Login berhasil!', 'success');
        showDashboard();
        loadDocuments();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = origText;
    }
});

async function doLogout() {
    try {
        await api('/api/auth/logout', { method: 'POST' });
        showToast('Logout berhasil', 'info');
        showLogin();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ============================================================
// Navigation
// ============================================================

let currentEditFile = null;

function navigateTo(page) {
    if (page === 'chatbot') {
        window.open('/', '_blank');
        return;
    }

    // Update nav items
    document.querySelectorAll('.nav-item[data-page]').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
    });

    // Show/hide pages
    document.querySelectorAll('.page').forEach(el => {
        el.classList.remove('active');
    });
    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) pageEl.classList.add('active');

    // Load data for specific pages
    if (page === 'documents') loadDocuments();
    if (page === 'index-status') loadIndexStatus();
    if (page === 'logs') { loadLogs(); loadLogStats(); }

    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('open');
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

// ============================================================
// Documents
// ============================================================

async function loadDocuments() {
    try {
        const data = await api('/api/documents');
        const docs = data.documents || [];

        // Update stats
        const statsEl = document.getElementById('docStats');
        const totalSize = docs.reduce((sum, d) => sum + d.size_bytes, 0);
        statsEl.innerHTML = `
            <div class="stat-card">
                <div class="stat-icon">📄</div>
                <div class="stat-value">${docs.length}</div>
                <div class="stat-label">Total Dokumen</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">💾</div>
                <div class="stat-value">${formatSize(totalSize)}</div>
                <div class="stat-label">Total Ukuran</div>
            </div>
        `;

        // Update table
        const tbody = document.getElementById('documentsTable');
        if (docs.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="4">
                    <div class="empty-state">
                        <div class="empty-icon">📭</div>
                        <p>Belum ada dokumen. Upload atau buat dokumen baru.</p>
                        <button class="btn btn-primary" onclick="navigateTo('create')">✏️ Buat Dokumen</button>
                    </div>
                </td></tr>
            `;
            return;
        }

        tbody.innerHTML = docs.map(doc => `
            <tr>
                <td><span class="file-name" onclick="editDocument('${doc.filename}')">${doc.filename}</span></td>
                <td>${doc.size_display}</td>
                <td>${doc.modified_at}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-outline btn-sm" onclick="editDocument('${doc.filename}')" title="Edit">✏️</button>
                        <button class="btn btn-success btn-sm" onclick="indexDocument('${doc.filename}')" title="Index">⚡</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteDocument('${doc.filename}')" title="Hapus">🗑️</button>
                    </div>
                </td>
            </tr>
        `).join('');

    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function editDocument(filename) {
    try {
        showLoading('Memuat dokumen...');
        const data = await api(`/api/documents/${filename}`);

        currentEditFile = filename;
        document.getElementById('editDocName').textContent = filename;
        document.getElementById('editContent').value = data.content;

        navigateTo('edit');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function saveDocument() {
    if (!currentEditFile) return;

    try {
        showLoading('Menyimpan...');
        const content = document.getElementById('editContent').value;

        await api(`/api/documents/${currentEditFile}`, {
            method: 'PUT',
            body: JSON.stringify({ content }),
        });

        showToast('Dokumen berhasil disimpan', 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function saveAndIndex() {
    if (!currentEditFile) return;

    try {
        showLoading('Menyimpan...');
        const content = document.getElementById('editContent').value;

        await api(`/api/documents/${currentEditFile}`, {
            method: 'PUT',
            body: JSON.stringify({ content }),
        });

        showLoading('Mengindex dokumen...');
        const result = await api(`/api/documents/${currentEditFile}/index`, { method: 'POST' });
        showToast(`Disimpan & di-index (${result.chunks_count} chunks)`, 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function indexDocument(filename) {
    try {
        showLoading(`Mengindex ${filename}...`);
        const result = await api(`/api/documents/${filename}/index`, { method: 'POST' });
        showToast(`${filename} berhasil di-index (${result.chunks_count} chunks)`, 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function deleteDocument(filename) {
    const confirmed = await showConfirm(
        'Hapus Dokumen?',
        `Apakah Anda yakin ingin menghapus <strong>${filename}</strong>? File dan semua data vector terkait akan dihapus permanen.`
    );

    if (!confirmed) return;

    try {
        showLoading(`Menghapus ${filename}...`);
        const result = await api(`/api/documents/${filename}`, { method: 'DELETE' });
        showToast(result.message, 'success');
        loadDocuments();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function indexAllDocuments() {
    const confirmed = await showConfirm(
        'Index Semua Dokumen?',
        'Proses ini akan menghapus semua vector lama dan mengindex ulang semua dokumen. Proses ini mungkin memakan waktu beberapa menit.'
    );

    if (!confirmed) return;

    try {
        showLoading('Mengindex semua dokumen...');
        const result = await api('/api/index/all', { method: 'POST' });
        showToast(result.message, 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Create Document
// ============================================================

async function createDocument(andIndex = false) {
    const filename = document.getElementById('newDocName').value.trim();
    const content = document.getElementById('newDocContent').value;

    if (!filename) {
        showToast('Nama file diperlukan', 'warning');
        return;
    }

    if (!content.trim()) {
        showToast('Konten dokumen tidak boleh kosong', 'warning');
        return;
    }

    try {
        showLoading('Membuat dokumen...');
        const result = await api('/api/documents', {
            method: 'POST',
            body: JSON.stringify({ filename, content }),
        });

        if (andIndex) {
            showLoading('Mengindex dokumen...');
            const realFilename = result.filename;
            await api(`/api/documents/${realFilename}/index`, { method: 'POST' });
            showToast(`Dokumen '${realFilename}' berhasil dibuat dan di-index`, 'success');
        } else {
            showToast(result.message, 'success');
        }

        // Clear form
        document.getElementById('newDocName').value = '';
        document.getElementById('newDocContent').value = '';
        navigateTo('documents');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Upload
// ============================================================

const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');

// Drag events
uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
    try {
        showLoading(`Mengupload & memproses ${file.name}...`);

        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Gagal mengupload file');
        }

        showToast(result.message, 'success');

        // Reset input
        fileInput.value = '';
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Index Status
// ============================================================

async function loadIndexStatus() {
    try {
        const stats = await api('/api/index/status');

        const statsEl = document.getElementById('indexStats');
        statsEl.innerHTML = `
            <div class="stat-card">
                <div class="stat-icon">🔢</div>
                <div class="stat-value">${stats.total_vector_count || 0}</div>
                <div class="stat-label">Total Vectors</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📐</div>
                <div class="stat-value">${stats.dimension || '-'}</div>
                <div class="stat-label">Dimensi</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📄</div>
                <div class="stat-value">${stats.local_document_count || 0}</div>
                <div class="stat-label">Dokumen Lokal</div>
            </div>
        `;

        const detailsEl = document.getElementById('indexDetails');
        detailsEl.innerHTML = `
            <table>
                <tr><td style="color: var(--text-secondary);">Nama Index</td><td><strong>${stats.index_name || '-'}</strong></td></tr>
                <tr><td style="color: var(--text-secondary);">Total Vectors</td><td>${stats.total_vector_count || 0}</td></tr>
                <tr><td style="color: var(--text-secondary);">Dimensi Embedding</td><td>${stats.dimension || '-'}</td></tr>
                <tr><td style="color: var(--text-secondary);">Dokumen Lokal</td><td>${stats.local_document_count || 0}</td></tr>
                <tr><td style="color: var(--text-secondary);">Status</td><td><span class="badge badge-success">Active</span></td></tr>
            </table>
        `;

    } catch (err) {
        showToast(err.message, 'error');
        document.getElementById('indexDetails').innerHTML = `<p style="color: var(--danger);">${err.message}</p>`;
    }
}

// ============================================================
// Query Logs
// ============================================================

let logsCurrentOffset = 0;
const LOGS_PER_PAGE = 20;

async function loadLogs() {
    try {
        const data = await api(`/api/logs?limit=${LOGS_PER_PAGE}&offset=${logsCurrentOffset}`);
        const logs = data.logs || [];
        const total = data.total || 0;

        const tbody = document.getElementById('logsTable');
        if (logs.length === 0 && logsCurrentOffset === 0) {
            tbody.innerHTML = `
                <tr><td colspan="6">
                    <div class="empty-state">
                        <div class="empty-icon">📭</div>
                        <p>Belum ada log query. Log akan tercatat otomatis saat chatbot menerima pertanyaan.</p>
                    </div>
                </td></tr>
            `;
            document.getElementById('logsPagination').innerHTML = '';
            return;
        }

        const statusLabel = { success: 'Sukses', no_result: 'Tidak Ditemukan', error: 'Error' };

        tbody.innerHTML = logs.map((log, i) => {
            const num = logsCurrentOffset + i + 1;
            const response = log.response
                ? log.response.replace(/</g, '&lt;').replace(/>/g, '&gt;')
                : '<span style="color:var(--text-muted)">-</span>';
            const query = log.query.replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return `
                <tr>
                    <td>${num}</td>
                    <td><div class="log-text" title="${query}">${query}</div></td>
                    <td><div class="log-text" title="${response}">${response}</div></td>
                    <td><span class="badge badge-${log.status}">${statusLabel[log.status] || log.status}</span></td>
                    <td style="text-align:center">${log.retrieval_count}</td>
                    <td style="font-size:0.8rem; color:var(--text-secondary)">${log.created_at}</td>
                </tr>
            `;
        }).join('');

        // Pagination
        const pag = document.getElementById('logsPagination');
        const totalPages = Math.ceil(total / LOGS_PER_PAGE);
        const currentPage = Math.floor(logsCurrentOffset / LOGS_PER_PAGE) + 1;

        if (totalPages <= 1) {
            pag.innerHTML = `<span style="color:var(--text-muted);font-size:0.85rem">${total} log tercatat</span>`;
        } else {
            pag.innerHTML = `
                <button class="btn btn-outline btn-sm" ${currentPage <= 1 ? 'disabled' : ''}
                    onclick="logsCurrentOffset -= ${LOGS_PER_PAGE}; loadLogs()">← Prev</button>
                <span style="color:var(--text-secondary);font-size:0.85rem">
                    Halaman ${currentPage} / ${totalPages} (${total} log)
                </span>
                <button class="btn btn-outline btn-sm" ${currentPage >= totalPages ? 'disabled' : ''}
                    onclick="logsCurrentOffset += ${LOGS_PER_PAGE}; loadLogs()">Next →</button>
            `;
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadLogStats() {
    try {
        const data = await api('/api/logs/stats');
        const stats = data.stats || {};
        const total = data.total || 0;

        // Render donut chart
        const chartEl = document.getElementById('logChart');
        if (total === 0) {
            chartEl.innerHTML = `<p style="color:var(--text-muted)">Belum ada data</p>`;
        } else {
            chartEl.innerHTML = renderDonutChart(stats, total);
        }

        // Render stats info
        const successPct = total > 0 ? ((stats.success / total) * 100).toFixed(1) : 0;
        const noResultPct = total > 0 ? ((stats.no_result / total) * 100).toFixed(1) : 0;
        const errorPct = total > 0 ? ((stats.error / total) * 100).toFixed(1) : 0;

        document.getElementById('logStatsInfo').innerHTML = `
            <div class="stat-item">
                <span class="label"><span class="badge badge-success">●</span> Sukses</span>
                <span class="value" style="color:var(--success)">${stats.success} <small style="font-size:0.7rem;font-weight:400">(${successPct}%)</small></span>
            </div>
            <div class="stat-item">
                <span class="label"><span class="badge badge-no_result">●</span> Tidak Ditemukan</span>
                <span class="value" style="color:var(--warning)">${stats.no_result} <small style="font-size:0.7rem;font-weight:400">(${noResultPct}%)</small></span>
            </div>
            <div class="stat-item">
                <span class="label"><span class="badge badge-error">●</span> Error</span>
                <span class="value" style="color:var(--danger)">${stats.error} <small style="font-size:0.7rem;font-weight:400">(${errorPct}%)</small></span>
            </div>
            <div class="stat-item">
                <span class="label">📊 Total Query</span>
                <span class="value">${total}</span>
            </div>
        `;
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderDonutChart(stats, total) {
    const colors = { success: '#10b981', no_result: '#f59e0b', error: '#ef4444' };
    const labels = { success: 'Sukses', no_result: 'Tidak Ditemukan', error: 'Error' };
    const size = 180;
    const cx = size / 2, cy = size / 2;
    const radius = 70;
    const strokeWidth = 24;

    let arcs = '';
    let startAngle = -90; // start from top
    const circumference = 2 * Math.PI * radius;

    for (const key of ['success', 'no_result', 'error']) {
        const value = stats[key] || 0;
        if (value === 0) continue;
        const pct = value / total;
        const arcLen = pct * circumference;
        const dashOffset = circumference - arcLen;
        const rotation = startAngle;

        arcs += `<circle cx="${cx}" cy="${cy}" r="${radius}"
            fill="none" stroke="${colors[key]}" stroke-width="${strokeWidth}"
            stroke-dasharray="${arcLen} ${dashOffset}"
            transform="rotate(${rotation} ${cx} ${cy})"
            style="transition: stroke-dasharray 0.6s ease"
        />`;
        startAngle += pct * 360;
    }

    // Center text
    const successPct = total > 0 ? Math.round((stats.success / total) * 100) : 0;

    return `
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="#2a2d3e" stroke-width="${strokeWidth}" />
            ${arcs}
            <text x="${cx}" y="${cy - 8}" text-anchor="middle" fill="#e8eaf0" font-size="24" font-weight="700">${successPct}%</text>
            <text x="${cx}" y="${cy + 14}" text-anchor="middle" fill="#9ca3af" font-size="11">sukses</text>
        </svg>
    `;
}

async function clearLogs() {
    const confirmed = await showConfirm(
        'Hapus Semua Log?',
        'Semua riwayat query akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.'
    );
    if (!confirmed) return;

    try {
        showLoading('Menghapus log...');
        const result = await api('/api/logs/clear', { method: 'DELETE' });
        showToast(`${result.deleted_count} log berhasil dihapus`, 'success');
        logsCurrentOffset = 0;
        loadLogs();
        loadLogStats();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Change Password
// ============================================================

document.getElementById('changePasswordForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const oldPassword = document.getElementById('oldPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    if (newPassword !== confirmPassword) {
        showToast('Password baru dan konfirmasi tidak cocok', 'warning');
        return;
    }

    if (newPassword.length < 6) {
        showToast('Password baru minimal 6 karakter', 'warning');
        return;
    }

    try {
        await api('/api/auth/change-password', {
            method: 'POST',
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
        });

        showToast('Password berhasil diubah!', 'success');
        document.getElementById('changePasswordForm').reset();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

// ============================================================
// Helpers
// ============================================================

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ============================================================
// Init
// ============================================================

checkAuth();
