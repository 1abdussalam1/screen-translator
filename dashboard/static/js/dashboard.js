// ── Number formatter ─────────────────────────────────────────────────────────
function fmtNum(n) {
    if (n === undefined || n === null) return '0';
    return Number(n).toLocaleString('ar-SA');
}

// ── Toast notifications ──────────────────────────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500',
    };

    const icons = {
        success: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>',
        error: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>',
        warning: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>',
        info: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    };

    const toast = document.createElement('div');
    toast.className = `toast-enter flex items-center gap-3 ${colors[type] || colors.info} text-white px-4 py-3 rounded-xl shadow-lg min-w-64 max-w-sm`;
    toast.innerHTML = `
        <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            ${icons[type] || icons.info}
        </svg>
        <span class="text-sm font-medium">${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.remove('toast-enter');
        toast.classList.add('toast-exit');
        toast.addEventListener('animationend', () => toast.remove());
    }, 3500);
}

// ── Confirmation modal ───────────────────────────────────────────────────────
let _confirmCallback = null;

function confirmAction(title, message, onConfirm) {
    _confirmCallback = onConfirm;
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    document.getElementById('confirm-modal').classList.remove('hidden');

    const okBtn = document.getElementById('confirm-ok');
    okBtn.onclick = async () => {
        closeConfirmModal();
        if (_confirmCallback) {
            try {
                await _confirmCallback();
            } catch (e) {
                showToast('حدث خطأ غير متوقع', 'error');
            }
        }
    };
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.add('hidden');
    _confirmCallback = null;
}

// Close confirm modal on backdrop click
document.addEventListener('click', (e) => {
    const modal = document.getElementById('confirm-modal');
    if (modal && e.target === modal) closeConfirmModal();
});

// ── Copy to clipboard ────────────────────────────────────────────────────────
function copyToClipboard(text, successMsg = 'تم النسخ!') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => showToast(successMsg, 'success'))
            .catch(() => _fallbackCopy(text, successMsg));
    } else {
        _fallbackCopy(text, successMsg);
    }
}

function _fallbackCopy(text, successMsg) {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.top = '-9999px';
    document.body.appendChild(el);
    el.focus();
    el.select();
    try {
        document.execCommand('copy');
        showToast(successMsg, 'success');
    } catch (e) {
        showToast('تعذر النسخ تلقائياً، يرجى النسخ يدوياً', 'warning');
    }
    document.body.removeChild(el);
}

// ── HTMX global error handler ────────────────────────────────────────────────
document.body.addEventListener('htmx:responseError', function(evt) {
    const status = evt.detail.xhr.status;
    if (status === 401 || status === 403) {
        showToast('انتهت جلسة العمل، يرجى تسجيل الدخول مجدداً', 'error');
        setTimeout(() => { window.location.href = '/dashboard/login'; }, 2000);
    } else {
        showToast(`خطأ في الخادم (${status})`, 'error');
    }
});

// ── Key shortcuts ────────────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        // Close any open modal
        document.querySelectorAll('[id$="-modal"]:not(.hidden)').forEach(m => {
            m.classList.add('hidden');
        });
    }
});

// ── Auto-refresh badge ───────────────────────────────────────────────────────
// Shows a subtle "auto-refresh" countdown in pages that use it
function startAutoRefresh(seconds, callback) {
    let remaining = seconds;
    const interval = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            remaining = seconds;
            callback();
        }
    }, 1000);
    return interval;
}
