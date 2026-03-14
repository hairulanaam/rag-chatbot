/**
 * Dashboard Admin - Frontend Logic
 * Handles all client-side interactions for the chatbot management dashboard.
 */

// ============================================================
// API Helper
// ============================================================

const API_BASE = '/dashboard';

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

    const iconNames = { success: 'check-circle-2', error: 'x-circle', info: 'info', warning: 'alert-triangle' };
    toast.innerHTML = `<i data-lucide="${iconNames[type] || 'info'}" style="width:18px;height:18px;flex-shrink:0"></i> <span>${message}</span>`;

    container.appendChild(toast);
    lucide.createIcons();

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
        loadLogs();
        loadLogStats();
        loadDailyStats();
    } catch {
        showLogin();
    }
}

function showLogin() {
    document.getElementById('loginPage').style.display = 'flex';
    document.getElementById('dashboard').classList.remove('active');
    stopAutoRefresh();
}

function showDashboard() {
    document.getElementById('loginPage').style.display = 'none';
    document.getElementById('dashboard').classList.add('active');
    startAutoRefresh();
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
        loadLogs();
        loadLogStats();
        loadDailyStats();
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
        window.open('/chat', '_blank');
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
    if (page === 'logs') { loadLogs(); loadLogStats(); loadDailyStats(); }

    // Track current page and restart auto-refresh for this page
    currentPage = page;
    startAutoRefresh();

    // Close mobile sidebar
    closeSidebar();
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebarBackdrop');
    sidebar.classList.toggle('open');
    backdrop.classList.toggle('active');
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarBackdrop').classList.remove('active');
}

// ============================================================
// Documents
// ============================================================

async function loadDocuments() {
    try {
        // Fetch document list and indexed status in parallel
        const [data, indexedData] = await Promise.all([
            api('/api/documents'),
            api('/api/documents/indexed').catch(() => ({ indexed: {} }))
        ]);
        const docs = data.documents || [];
        const indexed = indexedData.indexed || {};

        // Update stats
        const statsEl = document.getElementById('docStats');
        const totalSize = docs.reduce((sum, d) => sum + d.size_bytes, 0);
        statsEl.innerHTML = `
            <div class="stat-card">
                <div class="stat-icon"><i data-lucide="file-text"></i></div>
                <div class="stat-value">${docs.length}</div>
                <div class="stat-label">Total Dokumen</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i data-lucide="hard-drive"></i></div>
                <div class="stat-value">${formatSize(totalSize)}</div>
                <div class="stat-label">Total Ukuran</div>
            </div>
        `;

        // Update table
        const tbody = document.getElementById('documentsTable');
        if (docs.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="5">
                    <div class="empty-state">
                        <div class="empty-icon"><i data-lucide="inbox"></i></div>
                        <p>Belum ada dokumen. Upload atau buat dokumen baru.</p>
                        <button class="btn btn-primary" onclick="navigateTo('create')"><i data-lucide="pen-line"></i> Buat Dokumen</button>
                    </div>
                </td></tr>
            `;
            lucide.createIcons();
            return;
        }

        tbody.innerHTML = docs.map(doc => {
            const stem = doc.filename.replace(/\.md$/, '');
            const isIndexed = indexed[stem];
            let statusBadge;
            if (isIndexed === true) {
                statusBadge = `<span class="index-badge index-active">Aktif</span>`;
            } else if (isIndexed === false) {
                statusBadge = `<span class="index-badge index-inactive">Nonaktif</span>`;
            } else {
                statusBadge = `<span class="index-badge index-unknown">—</span>`;
            }
            return `
            <tr>
                <td><span class="file-name" onclick="editDocument('${doc.filename}')">${doc.filename}</span></td>
                <td>${doc.size_display}</td>
                <td>${doc.modified_at}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-outline btn-sm" onclick="editDocument('${doc.filename}')" title="Edit"><i data-lucide="pencil"></i></button>
                        <button class="btn btn-success btn-sm" onclick="indexDocument('${doc.filename}')" title="Unggah"><i data-lucide="upload-cloud"></i></button>
                        <button class="btn btn-danger btn-sm" onclick="deleteDocument('${doc.filename}')" title="Hapus"><i data-lucide="trash-2"></i></button>
                    </div>
                </td>
            </tr>
        `}).join('');

        lucide.createIcons();

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

        showLoading('Mengunggah dokumen...');
        const result = await api(`/api/documents/${currentEditFile}/index`, { method: 'POST' });
        showToast(`Disimpan & diunggah (${result.chunks_count} chunks)`, 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function indexDocument(filename) {
    try {
        showLoading(`Mengunggah ${filename}...`);
        const result = await api(`/api/documents/${filename}/index`, { method: 'POST' });
        showToast(`${filename} berhasil diunggah (${result.chunks_count} chunks)`, 'success');
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
        'Unggah Semua Dokumen?',
        'Proses ini akan menghapus semua vector lama dan mengunggah ulang semua dokumen. Proses ini mungkin memakan waktu beberapa menit.'
    );

    if (!confirmed) return;

    try {
        showLoading('Mengunggah semua dokumen...');
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
            showLoading('Mengunggah dokumen...');
            const realFilename = result.filename;
            await api(`/api/documents/${realFilename}/index`, { method: 'POST' });
            showToast(`Dokumen '${realFilename}' berhasil dibuat dan diunggah`, 'success');
        } else {
            showToast(result.message, 'success');
        }

        // Clear form & close create section
        document.getElementById('newDocName').value = '';
        document.getElementById('newDocContent').value = '';
        document.getElementById('createSection').style.display = 'none';
        loadDocuments();
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

const SUPPORTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.docx', '.doc', '.txt'];

async function uploadFile(file) {
    // Validasi format file sebelum upload
    const fileName = file.name.toLowerCase();
    const fileExt = '.' + fileName.split('.').pop();
    if (!SUPPORTED_EXTENSIONS.includes(fileExt)) {
        const supported = SUPPORTED_EXTENSIONS.map(e => e.toUpperCase().replace('.', '')).join(', ');
        showToast(`Format file "${fileExt}" tidak didukung. Format yang didukung: ${supported}`, 'error', 5000);
        fileInput.value = '';
        return;
    }

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

        // Reset input & close create section
        fileInput.value = '';
        document.getElementById('createSection').style.display = 'none';
        loadDocuments();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Create Section Toggle & Tabs
// ============================================================

function toggleCreateSection() {
    const section = document.getElementById('createSection');
    if (section.style.display === 'none') {
        section.style.display = 'block';
        section.style.animation = 'fadeIn 0.2s ease';
    } else {
        section.style.display = 'none';
    }
}

function switchCreateTab(tab) {
    // Toggle tab buttons
    document.getElementById('tabBtnUpload').classList.toggle('active', tab === 'upload');
    document.getElementById('tabBtnManual').classList.toggle('active', tab === 'manual');

    // Toggle tab content
    document.getElementById('tab-upload').classList.toggle('active', tab === 'upload');
    document.getElementById('tab-manual').classList.toggle('active', tab === 'manual');
}

// ============================================================
// Query Logs
// ============================================================

let logsCurrentOffset = 0;
const LOGS_PER_PAGE = 5;

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
                        <div class="empty-icon"><i data-lucide="inbox"></i></div>
                        <p>Belum ada log query. Log akan tercatat otomatis saat chatbot menerima pertanyaan.</p>
                    </div>
                </td></tr>
            `;
            document.getElementById('logsPagination').innerHTML = '';
            lucide.createIcons();
            return;
        }

        const statusLabel = { success: 'Terjawab', no_result: 'Tidak Terjawab', error: 'Error' };

        tbody.innerHTML = logs.map((log, i) => {
            const num = logsCurrentOffset + i + 1;
            const query = log.query.replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const queryEscaped = log.query.replace(/'/g, "\\'").replace(/"/g, '&quot;');
            const docSource = (log.status === 'success' && log.top_source)
                ? `<span class="source-badge">${log.top_source}</span>`
                : `<span style="color:var(--text-muted)">—</span>`;
            const rt = log.response_time != null
                ? `<span class="rt-badge">${log.response_time} d</span>`
                : `<span style="color:var(--text-muted)">—</span>`;
            const isResolved = log.resolved === 1 || log.resolved === true;
            const addKnowledgeBtn = (log.status === 'no_result' && !isResolved)
                ? `<button class="btn-add-knowledge" onclick="event.stopPropagation(); openKnowledgeModal(${log.id}, '${queryEscaped}')" title="Tambah Knowledge">+</button>`
                : '';
            const resolvedTag = (log.status === 'no_result' && isResolved)
                ? `<span class="badge badge-resolved" title="Knowledge sudah ditambahkan">✓</span>`
                : '';
            const statusCell = log.status === 'no_result'
                ? `<span class="badge badge-no_result">${statusLabel.no_result}</span>${resolvedTag}${addKnowledgeBtn}`
                : `<span class="badge badge-${log.status}">${statusLabel[log.status] || log.status}</span>`;
            return `
                <tr>
                    <td>${num}</td>
                    <td><div class="log-text" title="${query}">${query}</div></td>
                    <td>${docSource}</td>
                    <td><div class="status-cell">${statusCell}</div></td>
                    <td>${rt}</td>
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
        // -- Topic Pie Chart --
        const topicData = await api('/api/logs/topics');
        const topics = topicData.topics || [];
        const pieEl = document.getElementById('topicPieContainer');
        if (topics.length === 0) {
            pieEl.innerHTML = `<p style="color:var(--text-muted)">Belum ada data topik</p>`;
        } else {
            pieEl.innerHTML = renderTopicPie(topics);
        }

        // -- Success Rate Bars --
        const statsData = await api('/api/logs/stats');
        const stats = statsData.stats || {};
        const total = statsData.total || 0;
        const rateEl = document.getElementById('successRateContainer');
        if (total === 0) {
            rateEl.innerHTML = `<p style="color:var(--text-muted)">Belum ada data</p>`;
        } else {
            const successPct = total > 0 ? ((stats.success / total) * 100).toFixed(1) : 0;
            const noResultPct = total > 0 ? ((stats.no_result / total) * 100).toFixed(1) : 0;
            const avgRt = statsData.avg_response_time;
            const avgRtDisplay = avgRt != null ? `${avgRt} detik` : '—';
            rateEl.innerHTML = `
                <div class="rate-item">
                    <div class="rate-header"><span>Terjawab</span><span class="rate-pct success-text">${successPct}%</span></div>
                    <div class="pct-bar-bg"><div class="pct-bar pct-success" style="width:${successPct}%"></div></div>
                    <small style="color:var(--text-muted)">${stats.success || 0} dari ${total} pertanyaan</small>
                </div>
                <div class="rate-item">
                    <div class="rate-header"><span>Tidak Terjawab</span><span class="rate-pct warning-text">${noResultPct}%</span></div>
                    <div class="pct-bar-bg"><div class="pct-bar pct-warning" style="width:${noResultPct}%"></div></div>
                    <small style="color:var(--text-muted)">${stats.no_result || 0} dari ${total} pertanyaan</small>
                </div>
                <div class="rate-item avg-rt-item">
                    <div class="rate-header"><span>Rata-rata Waktu Respons</span><span class="rate-pct" style="color:var(--accent)">${avgRtDisplay}</span></div>
                    <small style="color:var(--text-muted)">Dihitung dari ${total} pertanyaan</small>
                </div>
            `;
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderTopicPie(topics) {
    const colors = ['#16a34a', '#10b981', '#f59e0b', '#3b82f6', '#8b5cf6', '#ef4444', '#ec4899', '#14b8a6'];
    const total = topics.reduce((s, t) => s + t.count, 0);
    const size = 160, cx = size / 2, cy = size / 2, r = 62;
    const circumference = 2 * Math.PI * r;

    let arcs = '';
    let legendItems = '';
    let startAngle = -90;
    topics.forEach((t, i) => {
        const pct = t.count / total;
        const arcLen = pct * circumference;
        const dashOffset = circumference - arcLen;
        arcs += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${colors[i % colors.length]}" stroke-width="22"
            stroke-dasharray="${arcLen} ${dashOffset}" transform="rotate(${startAngle} ${cx} ${cy})"
            style="transition:stroke-dasharray 0.5s ease"/>`;
        startAngle += pct * 360;
        legendItems += `<div class="pie-legend-item">
            <span class="pie-dot" style="background:${colors[i % colors.length]}"></span>
            <span class="pie-name">${t.source}</span>
            <span class="pie-count">${t.count}x</span>
        </div>`;
    });

    return `<div class="pie-layout">
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#e2e8f0" stroke-width="22"/>
            ${arcs}
            <text x="${cx}" y="${cy - 6}" text-anchor="middle" fill="#1e293b" font-size="20" font-weight="700">${topics.length}</text>
            <text x="${cx}" y="${cy + 14}" text-anchor="middle" fill="#64748b" font-size="10">topik</text>
        </svg>
        <div class="pie-legend">${legendItems}</div>
    </div>`;
}

async function clearLogs() {
    const confirmed = await showConfirm(
        'Hapus Semua Log?',
        'Semua riwayat interaksi akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.'
    );
    if (!confirmed) return;

    try {
        showLoading('Menghapus log...');
        const result = await api('/api/logs/clear', { method: 'DELETE' });
        showToast(`${result.deleted_count} log berhasil dihapus`, 'success');
        logsCurrentOffset = 0;
        loadLogs();
        loadLogStats();
        loadDailyStats();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

async function loadDailyStats() {
    try {
        const [dailyData, statsData] = await Promise.all([
            api('/api/logs/daily'),
            api('/api/logs/stats')
        ]);
        const days = dailyData.days || [];
        const counts = dailyData.counts || [];
        const allTimeTotal = statsData.total || 0;

        // Show all-time total (not just 7-day)
        document.getElementById('engagementTotal').textContent = allTimeTotal;

        const el = document.getElementById('lineChartContainer');
        if (days.length === 0) {
            el.innerHTML = `<p style="color:var(--text-muted)">Belum ada data</p>`;
            return;
        }
        el.innerHTML = renderLineChart(days, counts);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderLineChart(days, counts) {
    const W = 460, H = 120, padL = 28, padR = 12, padT = 12, padB = 32;
    const iW = W - padL - padR;
    const iH = H - padT - padB;
    const maxVal = Math.max(...counts, 1);
    const n = days.length;

    // Points
    const pts = counts.map((v, i) => ({
        x: padL + (i / (n - 1)) * iW,
        y: padT + iH - (v / maxVal) * iH
    }));

    // Smooth path (catmull-rom approx)
    function smooth(pts) {
        if (pts.length < 2) return `M${pts[0].x},${pts[0].y}`;
        let d = `M${pts[0].x},${pts[0].y}`;
        for (let i = 0; i < pts.length - 1; i++) {
            const cp1x = pts[i].x + (pts[i + 1].x - pts[i].x) / 3;
            const cp1y = pts[i].y;
            const cp2x = pts[i + 1].x - (pts[i + 1].x - pts[i].x) / 3;
            const cp2y = pts[i + 1].y;
            d += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${pts[i + 1].x},${pts[i + 1].y}`;
        }
        return d;
    }
    const linePath = smooth(pts);
    const areaPath = linePath + ` L${pts[n - 1].x},${padT + iH} L${pts[0].x},${padT + iH} Z`;

    // Day labels (short: e.g. "28/2")
    const labels = days.map(d => {
        const parts = d.split('-');
        return `${parseInt(parts[2])}/${parseInt(parts[1])}`;
    });

    const circles = pts.map((p, i) => `
        <circle cx="${p.x}" cy="${p.y}" r="3.5" fill="var(--accent)" stroke="var(--bg-card)" stroke-width="2">
            <title>${labels[i]}: ${counts[i]} pertanyaan</title>
        </circle>
        ${counts[i] > 0 ? `<text x="${p.x}" y="${p.y - 8}" text-anchor="middle" fill="#16a34a" font-size="9" font-weight="600">${counts[i]}</text>` : ''}`).join('');

    const xLabels = labels.map((l, i) => `
        <text x="${pts[i].x}" y="${H - 4}" text-anchor="middle" fill="#64748b" font-size="9">${l}</text>`).join('');

    // Y gridlines
    const gridLines = [0, 0.5, 1].map(f => {
        const y = padT + iH - f * iH;
        const val = Math.round(f * maxVal);
        return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#d4ddd6" stroke-width="1" stroke-dasharray="3 3"/>
                <text x="${padL - 4}" y="${y + 4}" text-anchor="end" fill="#64748b" font-size="9">${val}</text>`;
    }).join('');

    return `<svg width="100%" viewBox="0 0 ${W} ${H}" style="overflow:visible">
        <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#16a34a" stop-opacity="0.25"/>
                <stop offset="100%" stop-color="#16a34a" stop-opacity="0.0"/>
            </linearGradient>
        </defs>
        ${gridLines}
        <path d="${areaPath}" fill="url(#areaGrad)"/>
        <path d="${linePath}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        ${circles}
        ${xLabels}
    </svg>`;
}

// ============================================================
// Change Password
// ============================================================

document.getElementById('changePasswordForm').addEventListener('submit', async (e) => {
    e.preventDefault();

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
            body: JSON.stringify({ new_password: newPassword }),
        });

        showToast('Password berhasil diubah!', 'success');
        document.getElementById('changePasswordForm').reset();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

// ============================================================
// Knowledge Modal (Tambah Knowledge dari Pertanyaan Tidak Terjawab)
// ============================================================

let knowledgeDocContents = {}; // Cache konten dokumen yang sudah di-fetch
let currentKnowledgeLogId = null; // Track log ID being resolved

async function openKnowledgeModal(logId, question) {
    currentKnowledgeLogId = logId;
    const modal = document.getElementById('knowledgeModal');
    document.getElementById('knowledgeQuestion').textContent = question;

    // Reset form
    document.getElementById('knowledgeNewDocToggle').checked = false;
    document.getElementById('knowledgeSectionTitle').value = '';
    document.getElementById('knowledgeContent').value = '';
    document.getElementById('knowledgeNewDocName').value = '';
    toggleKnowledgeDocMode();

    // Load document list
    const select = document.getElementById('knowledgeDocTarget');
    select.innerHTML = '<option value="">Memuat dokumen...</option>';

    try {
        const data = await api('/api/documents');
        const docs = data.documents || [];
        select.innerHTML = '<option value="">— Pilih dokumen tujuan —</option>' +
            docs.map(d => `<option value="${d.filename}">${d.filename}</option>`).join('');
    } catch (err) {
        select.innerHTML = '<option value="">Gagal memuat dokumen</option>';
        showToast('Gagal memuat daftar dokumen: ' + err.message, 'error');
    }

    knowledgeDocContents = {};
    modal.style.display = 'flex';
    lucide.createIcons();
}

function closeKnowledgeModal() {
    document.getElementById('knowledgeModal').style.display = 'none';
}

function toggleKnowledgeDocMode() {
    const isNew = document.getElementById('knowledgeNewDocToggle').checked;
    document.getElementById('knowledgeDocTarget').style.display = isNew ? 'none' : 'block';
    document.getElementById('knowledgeNewDocName').style.display = isNew ? 'block' : 'none';
    document.getElementById('knowledgeNewDocHint').style.display = isNew ? 'block' : 'none';
}

async function onKnowledgeDocSelect() {
    // Pre-fetch document content when selected (for append later)
    const filename = document.getElementById('knowledgeDocTarget').value;
    if (filename && !knowledgeDocContents[filename]) {
        try {
            const data = await api(`/api/documents/${filename}`);
            knowledgeDocContents[filename] = data.content;
        } catch (err) {
            console.warn('Failed to pre-fetch doc content:', err);
        }
    }
}

async function submitKnowledge(andIndex = false) {
    const isNewDoc = document.getElementById('knowledgeNewDocToggle').checked;
    const sectionTitle = document.getElementById('knowledgeSectionTitle').value.trim();
    const content = document.getElementById('knowledgeContent').value.trim();

    if (!sectionTitle) {
        showToast('Judul section tidak boleh kosong', 'warning');
        return;
    }
    if (!content) {
        showToast('Konten jawaban tidak boleh kosong', 'warning');
        return;
    }

    // Build new section markdown
    const newSection = `\n\n## ${sectionTitle}\n\n${content}`;

    try {
        let targetFilename;

        if (isNewDoc) {
            // === Create new document ===
            const newDocName = document.getElementById('knowledgeNewDocName').value.trim();
            if (!newDocName) {
                showToast('Nama dokumen baru tidak boleh kosong', 'warning');
                return;
            }

            targetFilename = newDocName.endsWith('.md') ? newDocName : newDocName + '.md';
            const docTitle = sectionTitle; // Use section title as H1
            const fullContent = `# ${docTitle}${newSection}`;

            showLoading('Membuat dokumen baru...');
            await api('/api/documents', {
                method: 'POST',
                body: JSON.stringify({ filename: newDocName, content: fullContent }),
            });
        } else {
            // === Append to existing document ===
            targetFilename = document.getElementById('knowledgeDocTarget').value;
            if (!targetFilename) {
                showToast('Pilih dokumen tujuan terlebih dahulu', 'warning');
                return;
            }

            showLoading('Memperbarui dokumen...');

            // Get current content (from cache or fetch)
            let currentContent = knowledgeDocContents[targetFilename];
            if (!currentContent) {
                const data = await api(`/api/documents/${targetFilename}`);
                currentContent = data.content;
            }

            // Append new section
            const updatedContent = currentContent + newSection;

            await api(`/api/documents/${targetFilename}`, {
                method: 'PUT',
                body: JSON.stringify({ content: updatedContent }),
            });
        }

        // Optionally re-index
        if (andIndex) {
            showLoading('Mengunggah dokumen...');
            const result = await api(`/api/documents/${targetFilename}/index`, { method: 'POST' });
            showToast(`Knowledge berhasil ditambahkan & diunggah (${result.chunks_count} chunks)`, 'success');
        } else {
            showToast('Knowledge berhasil ditambahkan. Jangan lupa unggah ulang dokumen agar aktif di chatbot.', 'success', 5000);
        }

        closeKnowledgeModal();
        // Mark this log as resolved via server API and refresh table
        if (currentKnowledgeLogId) {
            try {
                await api(`/api/logs/${currentKnowledgeLogId}/resolve`, { method: 'PATCH' });
            } catch (err) {
                console.warn('Failed to mark log as resolved:', err);
            }
            currentKnowledgeLogId = null;
        }
        loadLogs();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Helpers
// ============================================================

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ============================================================
// Auto-Refresh System
// ============================================================

const AUTO_REFRESH_INTERVAL = 15000; // 15 seconds
let autoRefreshTimer = null;
let currentPage = 'logs'; // track current active page

/**
 * Start auto-refresh polling for the current page.
 * Only the active page is polled. Timer is cleared and re-created on page change.
 */
function startAutoRefresh() {
    stopAutoRefresh();

    autoRefreshTimer = setInterval(() => {
        // Only refresh if the tab is visible
        if (document.hidden) return;

        silentRefresh();
    }, AUTO_REFRESH_INTERVAL);
}

/**
 * Stop auto-refresh polling.
 */
function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}

/**
 * Silently refresh data for the current active page.
 * Does NOT show errors as toasts (to avoid spamming on network issues).
 */
async function silentRefresh() {
    try {
        if (currentPage === 'logs') {
            await Promise.all([
                loadLogs(),
                loadLogStats(),
                loadDailyStats(),
            ]);
        } else if (currentPage === 'documents') {
            await loadDocuments();
        }
    } catch (err) {
        // Silent fail — don't show toast for auto-refresh errors
        console.warn('Auto-refresh failed:', err.message);
    }
}

// Pause auto-refresh when tab is hidden, resume when visible
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        // Resume: immediately refresh and restart polling
        silentRefresh();
        startAutoRefresh();
    }
});

// ============================================================
// Init
// ============================================================

checkAuth();

