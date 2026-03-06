/* ===== SUNUCU YÖNETİMİ - ANA JAVASCRIPT ===== */

// ========== PERFORMANS: API CACHE ==========
const _apiCache = new Map();
const _API_CACHE_TTL = 10000; // 10 saniye

async function cachedFetch(url, options = {}) {
    const cacheKey = url + JSON.stringify(options);
    const cached = _apiCache.get(cacheKey);
    if (cached && Date.now() - cached.time < _API_CACHE_TTL) {
        return cached.data;
    }
    const response = await fetch(url, options);
    const data = await response.json();
    _apiCache.set(cacheKey, { data, time: Date.now() });
    return data;
}

function invalidateCache(pattern) {
    for (const key of _apiCache.keys()) {
        if (key.includes(pattern)) _apiCache.delete(key);
    }
}

// ========== PERFORMANS: DEBOUNCE & THROTTLE ==========
function debounce(fn, ms = 300) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

function throttle(fn, ms = 200) {
    let last = 0;
    return function(...args) {
        const now = Date.now();
        if (now - last >= ms) {
            last = now;
            return fn.apply(this, args);
        }
    };
}

// ========== PERFORMANS: REQUEST ABORT ==========
const _activeRequests = new Map();

function abortableRequest(key) {
    if (_activeRequests.has(key)) {
        _activeRequests.get(key).abort();
    }
    const controller = new AbortController();
    _activeRequests.set(key, controller);
    return controller.signal;
}

// ========== SAAT ==========
function updateClock() {
    const now = new Date();
    const el = document.getElementById('clock');
    if (el) {
        el.textContent = now.toLocaleString('tr-TR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    }
}
setInterval(updateClock, 1000);
updateClock();

// ========== SIDEBAR ==========
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
        sidebar.classList.toggle('show');
    } else {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    }
}

// Sidebar durumunu localStorage'dan yükle
(function restoreSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar && window.innerWidth > 768) {
        const collapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (collapsed) sidebar.classList.add('collapsed');
    }
})();

// ========== TEMA ==========
function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('themeIcon');
    if (html.getAttribute('data-theme') === 'dark') {
        html.setAttribute('data-theme', 'light');
        icon.className = 'fas fa-sun';
        localStorage.setItem('theme', 'light');
    } else {
        html.setAttribute('data-theme', 'dark');
        icon.className = 'fas fa-moon';
        localStorage.setItem('theme', 'dark');
    }
}

// Kayıtlı tema
(function() {
    const saved = localStorage.getItem('theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
        const icon = document.getElementById('themeIcon');
        if (icon) icon.className = saved === 'light' ? 'fas fa-sun' : 'fas fa-moon';
    }
})();

// ========== TOAST BİLDİRİMLERİ ==========
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
        info: 'fas fa-info-circle',
        success: 'fas fa-check-circle',
        error: 'fas fa-exclamation-circle',
        warning: 'fas fa-exclamation-triangle'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = document.createElement('i');
    icon.className = icons[type] || icons.info;
    toast.appendChild(icon);
    toast.appendChild(document.createTextNode(' ' + String(message != null ? message : '')));
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ========== MODAL ==========
function openAddServerModal() {
    document.getElementById('addServerModal').classList.add('show');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

// Modal dışına tıklayınca kapat
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('show');
    }
});

// ========== DROPDOWN ==========
function toggleDropdown(btn) {
    const menu = btn.nextElementSibling;
    // Diğer tüm dropdown'ları kapat
    document.querySelectorAll('.dropdown-menu.show').forEach(m => {
        if (m !== menu) m.classList.remove('show');
    });
    menu.classList.toggle('show');
}

// Dışarı tıklanınca dropdown kapat
document.addEventListener('click', function(e) {
    if (!e.target.closest('.server-actions-dropdown')) {
        document.querySelectorAll('.dropdown-menu.show').forEach(m => m.classList.remove('show'));
    }
});

// ========== SUNUCU İŞLEMLERİ ==========
async function addServer(event) {
    event.preventDefault();
    const form = event.target;
    const btn = form.querySelector('button[type="submit"]');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ekleniyor...'; }

    const formData = new FormData(form);
    const data = {
        name: formData.get('name'),
        host: formData.get('host'),
        port: parseInt(formData.get('port')) || 22,
        username: formData.get('username'),
        password: formData.get('password'),
        group: formData.get('group') || 'Genel',
        description: formData.get('description') || '',
        role: formData.get('role') || '',
        location: formData.get('location') || '',
        installed_at: formData.get('installed_at') || '',
        responsible: formData.get('responsible') || '',
        os_planned: formData.get('os_planned') || ''
    };

    try {
        const response = await fetch('/api/servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        let result;
        try {
            result = await response.json();
        } catch (e) {
            showToast('Sunucu hatası: Sunucudan geçerli yanıt alınamadı (HTTP ' + response.status + ')', 'error', 8000);
            return;
        }
        if (result.success) {
            showToast('Sunucu başarıyla eklendi!', 'success');
            closeModal('addServerModal');
            form.reset();
            invalidateCache('/api/servers');
            setTimeout(() => location.reload(), 800);
        } else {
            showToast(result.message || 'Sunucu eklenemedi', 'error', 8000);
        }
    } catch (err) {
        showToast('Ağ hatası: ' + (err.message || 'Sunucuya ulaşılamadı. Panel çalışıyor mu?'), 'error', 8000);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-plus"></i> Ekle'; }
    }
}

async function deleteServer(serverId, serverName) {
    if (!confirm(`"${serverName}" sunucusunu silmek istediğinize emin misiniz?`)) return;

    try {
        const response = await fetch(`/api/servers/${serverId}`, { method: 'DELETE' });
        const result = await response.json();

        if (result.success) {
            showToast('Sunucu silindi', 'success');
            invalidateCache('/api/servers');
            // Animasyonlu kaldırma
            const card = document.querySelector(`[data-id="${serverId}"]`);
            if (card) {
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '0';
                card.style.transform = 'scale(0.8)';
                setTimeout(() => location.reload(), 400);
            } else {
                setTimeout(() => location.reload(), 800);
            }
        } else {
            showToast(result.message, 'error');
        }
    } catch (err) {
        showToast('Hata: ' + err.message, 'error');
    }
}

async function connectServer(serverId) {
    // Buton durumunu güncelle
    const btn = event?.target?.closest?.('button');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
    showToast('Bağlanılıyor...', 'info');

    try {
        const signal = abortableRequest('connect-' + serverId);
        const response = await fetch(`/api/servers/${serverId}/connect`, { method: 'POST', signal });
        const result = await response.json();

        if (result.success) {
            showToast('Bağlantı başarılı!', 'success');
            invalidateCache('/api/servers');
            setTimeout(() => location.reload(), 800);
        } else {
            showToast(result.message || 'Bağlantı kurulamadı', 'error', 8000);
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-plug"></i> Bağlan'; }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            showToast('Bağlantı hatası: ' + err.message, 'error', 8000);
        }
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-plug"></i> Bağlan'; }
    }
}

async function disconnectServer(serverId) {
    try {
        const response = await fetch(`/api/servers/${serverId}/disconnect`, { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            showToast('Bağlantı kesildi', 'info');
            invalidateCache('/api/servers');
            setTimeout(() => location.reload(), 800);
        } else {
            showToast(result.message, 'error');
        }
    } catch (err) {
        showToast('Hata: ' + err.message, 'error');
    }
}

// ========== PERFORMANS: DASHBOARD OTO-GÜNCELLEME ==========
(function() {
    const refreshMeta = document.querySelector('meta[name="refresh-interval"]');
    const interval = refreshMeta ? parseInt(refreshMeta.content) * 1000 : 30000;
    let _autoRefreshTimer = null;
    let _lastActivity = Date.now();

    // Sayfa aktifse oto-güncelle
    function startAutoRefresh() {
        if (_autoRefreshTimer) return;
        _autoRefreshTimer = setInterval(() => {
            // Son 5 dk içinde aktivite yoksa güncelleme
            if (Date.now() - _lastActivity > 300000) return;
            // Dashboard'da mıyız?
            if (window.location.pathname === '/') {
                refreshDashboardData();
            }
        }, interval);
    }

    // Hafif güncelleme — tam sayfa yenileme yerine
    async function refreshDashboardData() {
        try {
            const data = await cachedFetch('/api/servers');
            if (data.success) {
                updateDashboardCounters(data.servers);
                const upd = document.getElementById('dashLastUpdate');
                if (upd) upd.textContent = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
            }
        } catch (e) { /* sessizce atla */ }
    }

    function updateDashboardCounters(servers) {
        const total = servers.length;
        const online = servers.filter(s => s.reachable).length;
        const connected = servers.filter(s => s.connected).length;
        // Stat kartlarını güncelle
        const statValues = document.querySelectorAll('.dash-stat-value[data-count]');
        if (statValues.length >= 4) {
            statValues[0].textContent = total;
            statValues[1].textContent = online;
            statValues[2].textContent = total - online;
            statValues[3].textContent = connected;
        }
    }

    // Kullanıcı aktivitesi takibi
    ['click', 'keydown', 'mousemove'].forEach(evt => {
        document.addEventListener(evt, throttle(() => { _lastActivity = Date.now(); }, 5000), { passive: true });
    });

    startAutoRefresh();
})();

// ========== PERFORMANS: LAZY IMAGE/ICON LOADING ==========
if ('IntersectionObserver' in window) {
    const lazyObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('dash-visible');
                lazyObserver.unobserve(entry.target);
            }
        });
    }, { rootMargin: '50px' });

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.dash-server-card, .dash-quick-card').forEach(el => {
            lazyObserver.observe(el);
        });
    });
}

// ========== KLAVYE KISAYOLLARI ==========
document.addEventListener('keydown', function(e) {
    // ESC ile modal kapat
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.show').forEach(m => m.classList.remove('show'));
    }
    // Ctrl+K ile sunucu ekle
    if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        openAddServerModal();
    }
    // Ctrl+R ile dashboard güncelle (sayfa yenilemeden)
    if (e.ctrlKey && e.key === 'r' && window.location.pathname === '/') {
        e.preventDefault();
        showToast('Güncelleniyor...', 'info', 2000);
        invalidateCache('/api/servers');
        setTimeout(() => location.reload(), 300);
    }
});

// ========== PERFORMANS: PREFETCH ==========
document.addEventListener('DOMContentLoaded', () => {
    // Sidebar linklerine hover'da prefetch ekle
    document.querySelectorAll('.sidebar-menu a[href]').forEach(link => {
        link.addEventListener('mouseenter', () => {
            const href = link.getAttribute('href');
            if (href && !document.querySelector(`link[href="${href}"]`)) {
                const prefetch = document.createElement('link');
                prefetch.rel = 'prefetch';
                prefetch.href = href;
                document.head.appendChild(prefetch);
            }
        }, { once: true, passive: true });
    });
});

console.log('🖥️ Sunucu Yönetimi - Panel yüklendi (v2.0 — optimized)');

// ========== AI CHATBOT FLOATING WIDGET ==========
function toggleAIChat() {
    const panel = document.getElementById('aiChatPanel');
    const fab = document.getElementById('aiChatFab');
    const fabIcon = document.getElementById('aiChatFabIcon');
    if (!panel || !fab) return;
    const isOpen = panel.classList.toggle('open');
    fab.classList.toggle('open', isOpen);
    fabIcon.className = isOpen ? 'fas fa-times' : 'fas fa-robot';
    if (isOpen) {
        const input = document.getElementById('aiChatInput');
        if (input) setTimeout(() => input.focus(), 200);
    }
}

function aiChatAsk(text) {
    const input = document.getElementById('aiChatInput');
    if (input) { input.value = text; }
    aiChatSend();
}

function aiChatSend() {
    const input = document.getElementById('aiChatInput');
    const messages = document.getElementById('aiChatMessages');
    const suggestions = document.getElementById('aiChatSuggestions');
    if (!input || !messages) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';

    // Hide suggestions after first message
    if (suggestions) suggestions.style.display = 'none';

    // Add user message
    const userMsg = document.createElement('div');
    userMsg.className = 'ai-chat-msg user';
    userMsg.innerHTML = '<div class="ai-chat-msg-avatar"><i class="fas fa-user"></i></div>' +
        '<div class="ai-chat-msg-bubble">' + escapeHtml(text) + '</div>';
    messages.appendChild(userMsg);
    messages.scrollTop = messages.scrollHeight;

    // Typing indicator
    const typing = document.createElement('div');
    typing.className = 'ai-chat-msg bot';
    typing.id = 'aiTyping';
    typing.innerHTML = '<div class="ai-chat-msg-avatar"><i class="fas fa-robot"></i></div>' +
        '<div class="ai-chat-msg-bubble"><div class="ai-chat-typing"><span></span><span></span><span></span></div></div>';
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;

    // ── Gerçek AI API çağrısı (EmareAPI → Gemini) ──
    fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
    })
    .then(r => r.json())
    .then(data => {
        const t = document.getElementById('aiTyping');
        if (t) t.remove();
        const response = data.success
            ? data.response
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,.1);padding:1px 4px;border-radius:3px;">$1</code>')
                .replace(/\n/g, '<br>')
            : (data.message || 'Bir hata oluştu.');
        const botMsg = document.createElement('div');
        botMsg.className = 'ai-chat-msg bot';
        botMsg.innerHTML = '<div class="ai-chat-msg-avatar"><i class="fas fa-robot"></i></div>' +
            '<div class="ai-chat-msg-bubble">' + response + '</div>';
        messages.appendChild(botMsg);
        messages.scrollTop = messages.scrollHeight;
    })
    .catch(() => {
        const t = document.getElementById('aiTyping');
        if (t) t.remove();
        const botMsg = document.createElement('div');
        botMsg.className = 'ai-chat-msg bot';
        botMsg.innerHTML = '<div class="ai-chat-msg-avatar"><i class="fas fa-robot"></i></div>' +
            '<div class="ai-chat-msg-bubble">⚠️ Bağlantı hatası. Lütfen tekrar deneyin.</div>';
        messages.appendChild(botMsg);
        messages.scrollTop = messages.scrollHeight;
    });
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function generateAIResponse(query) {
    const q = query.toLowerCase();

    // EP / Ödül
    if (q.includes('ep') || q.includes('puan') || q.includes('ödül') || q.includes('kazandım') || q.includes('bakiye')) {
        return 'EP kazanmanın en kolay yolları:<br>' +
            '• <strong>AI uygulaması kur → +30 EP</strong><br>' +
            '• <strong>Stack Builder kullan → +50 EP</strong><br>' +
            '• <strong>AI Stack tamamla → +100 EP</strong><br>' +
            '• <strong>Market\'e app yayınla → +300 EP</strong><br>' +
            'Detaylar için <a href="/market" style="color:#6366f1">Market</a> sayfasını ziyaret edin! 🎯';
    }

    // Sunucu durumu
    if (q.includes('sunucu') && (q.includes('durum') || q.includes('nasıl') || q.includes('sağlık'))) {
        return 'Sunucu durumunuzu kontrol etmek için:<br>' +
            '• <a href="/" style="color:#6366f1">Dashboard</a>\'da özet kartları inceleyin<br>' +
            '• <a href="/monitoring" style="color:#6366f1">Monitoring</a> sayfasında detaylı metrikleri görün<br>' +
            '• <a href="/server-map" style="color:#6366f1">Sunucu Haritası</a> ile tüm servisleri kontrol edin 🖥️';
    }

    // Hangi AI app
    if (q.includes('hangi') && (q.includes('app') || q.includes('uygulama') || q.includes('kur'))) {
        return 'Hedefine göre öneri:<br>' +
            '• <strong>Müşteri desteği:</strong> Ollama + PrivateGPT<br>' +
            '• <strong>İçerik üretimi:</strong> Stable Diffusion<br>' +
            '• <strong>Kod yazımı:</strong> Tabby AI<br>' +
            '• <strong>İş otomasyonu:</strong> n8n + Ollama<br>' +
            '<a href="/ai-wizard" style="color:#6366f1">AI Wizard</a> ile 3 soruda sana özel çözüm bul! ✨';
    }

    // Maliyet
    if (q.includes('maliyet') || q.includes('fiyat') || q.includes('ücret') || q.includes('düşür') || q.includes('tasarruf') || q.includes('bütçe')) {
        return 'Maliyet optimizasyonu ipuçları:<br>' +
            '• <strong>Ollama</strong> ile ücretsiz LLM kullanın (API maliyeti $0)<br>' +
            '• <strong>Küçük modeller</strong> (7B) daha az kaynak tüketir<br>' +
            '• <strong>Redis cache</strong> ile tekrarlı sorguları hızlandırın<br>' +
            '• <a href="/ai-cost" style="color:#6366f1">Maliyet Tahmini</a> panelini inceleyin 💰';
    }

    // Market
    if (q.includes('market') || q.includes('uygulama pazarı') || q.includes('plugin')) {
        return 'EmareCloud Market\'te <strong>70+ AI uygulaması</strong> mevcut:<br>' +
            '• Ollama, Stable Diffusion, PrivateGPT...<br>' +
            '• <strong>16 hazır Stack Bundle</strong><br>' +
            '• Kendi uygulamanızı <a href="/app-builder" style="color:#6366f1">App Builder</a> ile oluşturun!<br>' +
            '<a href="/market" style="color:#6366f1">Market\'e Git →</a>';
    }

    // Terminal
    if (q.includes('terminal') || q.includes('komut') || q.includes('ssh')) {
        return 'Terminal kullanımı:<br>' +
            '• Dashboard\'dan sunucuya bağlanın<br>' +
            '• Terminal sayfasında AI asistan mevcut<br>' +
            '• Komut önerileri otomatik gelir<br>' +
            'İpucu: <strong>AI Terminal Asistanı</strong> size komut yazmanıza yardımcı olur! 🤖';
    }

    // Stack builder
    if (q.includes('stack') || q.includes('paket') || q.includes('bundle')) {
        return '<strong>AI Stack Builder</strong> ile hazır paketler:<br>' +
            '• AI Chatbot Starter (Ollama + WebUI)<br>' +
            '• AI Geliştirme Platformu (LLM + API + IDE)<br>' +
            '• E-Commerce AI (Chatbot + Öneri)<br>' +
            '16 paket daha! <a href="/market" style="color:#6366f1">Stack Builder\'a Git →</a>';
    }

    // Wizard / ne yapacağımı bilmiyorum
    if (q.includes('wizard') || q.includes('ne yapacağımı') || q.includes('nereden başla') || q.includes('bilmiyorum') || q.includes('yardım')) {
        return '3 adımda sana özel AI çözümü bul! 🎯<br>' +
            '<a href="/ai-wizard" style="color:#6366f1;font-weight:700">AI Use-Case Wizard\'ı Başlat →</a><br><br>' +
            'Sorular:<br>1️⃣ Hedefin ne?<br>2️⃣ Teknik seviyen?<br>3️⃣ Bütçen?';
    }

    // Güvenlik
    if (q.includes('güvenlik') || q.includes('firewall') || q.includes('ssl') || q.includes('sertifika')) {
        return 'Güvenlik önerileri:<br>' +
            '• <strong>Firewall</strong> kurallarını kontrol edin<br>' +
            '• <strong>SSL/TLS</strong> sertifikası kullanın<br>' +
            '• <strong>Fail2ban</strong> ile brute-force koruması<br>' +
            '• <a href="/monitoring" style="color:#6366f1">Monitoring</a>\'den alarm kuralları oluşturun 🛡️';
    }

    // Genel / default
    return 'Size yardımcı olabileceğim konular:<br>' +
        '• <strong>Sunucu yönetimi</strong> ve durum takibi<br>' +
        '• <strong>AI uygulama</strong> önerileri<br>' +
        '• <strong>EP kazanma</strong> yolları<br>' +
        '• <strong>Maliyet optimizasyonu</strong><br>' +
        '• <strong>Güvenlik</strong> ipuçları<br><br>' +
        'Daha spesifik bir soru sorarsanız daha detaylı yardımcı olabilirim! 😊';
}
// ═══════════════════════════════════════════════════════
//  GERİ BİLDİRİM WIDGET
// ═══════════════════════════════════════════════════════

let _fbCat = 'bug';
let _fbPri = 'normal';
let _fbOpen = false;
let _fbTab = 'new';

function toggleFeedback() {
    const panel = document.getElementById('fbPanel');
    if (!panel) return;
    _fbOpen = !_fbOpen;
    panel.style.display = _fbOpen ? 'flex' : 'none';
    if (_fbOpen) {
        document.getElementById('fbPageUrl').textContent = window.location.pathname + window.location.search;
        document.getElementById('fbMessage').focus();
        // unread dot gizle
        document.getElementById('fbUnreadDot').style.display = 'none';
    }
}

function fbSetTab(tab) {
    _fbTab = tab;
    const newContent  = document.getElementById('fbTabNewContent');
    const listContent = document.getElementById('fbTabListContent');
    const newFooter   = document.getElementById('fbTabNewFooter');
    const btnNew  = document.getElementById('fbTabNew');
    const btnList = document.getElementById('fbTabList');

    const activeStyle = 'background:rgba(255,255,255,.3); color:#fff;';
    const inactiveStyle = 'background:transparent; color:rgba(255,255,255,.8);';

    if (tab === 'new') {
        newContent.style.display = 'flex';
        newFooter.style.display = 'block';
        listContent.style.display = 'none';
        btnNew.style.cssText += activeStyle;
        btnList.style.cssText += inactiveStyle;
    } else {
        newContent.style.display = 'none';
        newFooter.style.display = 'none';
        listContent.style.display = 'block';
        btnNew.style.cssText += inactiveStyle;
        btnList.style.cssText += activeStyle;
        fbLoadList();
    }
}

function fbSetCat(cat) {
    _fbCat = cat;
    ['bug','suggestion','question','other'].forEach(c => {
        const btn = document.getElementById('fbCat' + c.charAt(0).toUpperCase() + c.slice(1));
        if (!btn) return;
        const isActive = c === cat;
        const styles = {
            bug:        isActive ? 'border:1px solid #fca5a5; background:#fef2f2; color:#b91c1c;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
            suggestion: isActive ? 'border:1px solid #93c5fd; background:#eff6ff; color:#1d4ed8;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
            question:   isActive ? 'border:1px solid #c4b5fd; background:#f5f3ff; color:#7c3aed;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
            other:      isActive ? 'border:1px solid #d1d5db; background:#f9fafb; color:#374151;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
        };
        btn.setAttribute('style', btn.getAttribute('style').replace(/border:[^;]+;|background:[^;]+;|color:[^;]+;/g,'') + styles[c]);
    });
}

function fbSetPri(pri) {
    _fbPri = pri;
    ['low','normal','high','critical'].forEach(p => {
        const btn = document.getElementById('fbPri' + p.charAt(0).toUpperCase() + p.slice(1));
        if (!btn) return;
        const isActive = p === pri;
        const styles = {
            low:      isActive ? 'border:1px solid #d1d5db; background:#f9fafb; color:#374151;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
            normal:   isActive ? 'border:1px solid #93c5fd; background:#eff6ff; color:#1d4ed8;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
            high:     isActive ? 'border:1px solid #fdba74; background:#fff7ed; color:#c2410c;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
            critical: isActive ? 'border:1px solid #fca5a5; background:#fef2f2; color:#b91c1c;' : 'border:1px solid var(--border-color); background:var(--bg-secondary); color:var(--text-secondary);',
        };
        btn.setAttribute('style', btn.getAttribute('style').replace(/border:[^;]+;|background:[^;]+;|color:[^;]+;/g,'') + styles[p]);
    });
}

async function fbSubmit() {
    const msg = (document.getElementById('fbMessage').value || '').trim();
    const successEl = document.getElementById('fbSuccessMsg');
    const errorEl   = document.getElementById('fbErrorMsg');
    successEl.style.display = 'none';
    errorEl.style.display   = 'none';
    if (!msg || msg.length < 3) {
        document.getElementById('fbErrorText').textContent = 'Açıklama en az 3 karakter olmalı.';
        errorEl.style.display = 'block'; return;
    }
    const btn = document.getElementById('fbSendBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gönderiliyor…';
    try {
        const r = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message:  msg,
                category: _fbCat,
                priority: _fbPri,
                page_url: window.location.href,
            }),
        });
        const d = await r.json();
        if (d.success) {
            document.getElementById('fbSuccessText').textContent = d.message || 'Gönderildi!';
            successEl.style.display = 'block';
            document.getElementById('fbMessage').value = '';
            document.getElementById('fbCharCount').textContent = '0/2000';
            fbSetCat('bug');
            fbSetPri('normal');
        } else {
            document.getElementById('fbErrorText').textContent = d.message || 'Hata oluştu.';
            errorEl.style.display = 'block';
        }
    } catch(e) {
        document.getElementById('fbErrorText').textContent = 'Ağ hatası. Lütfen tekrar deneyin.';
        errorEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Gönder';
    }
}

async function fbLoadList() {
    const loadingEl = document.getElementById('fbListLoading');
    const emptyEl   = document.getElementById('fbListEmpty');
    const itemsEl   = document.getElementById('fbListItems');
    if (!loadingEl || !emptyEl || !itemsEl) return;
    loadingEl.style.display = 'flex';
    emptyEl.style.display   = 'none';
    itemsEl.innerHTML       = '';
    try {
        const r = await fetch('/api/feedback/my');
        const d = await r.json();
        loadingEl.style.display = 'none';
        if (!d.success || !d.messages.length) {
            emptyEl.style.display = 'block'; return;
        }
        const catColors = {bug:'#b91c1c',suggestion:'#1d4ed8',question:'#7c3aed',other:'#374151'};
        const statusLabels = {open:'Açık',in_progress:'İnceleniyor',resolved:'Çözüldü',closed:'Kapatıldı'};
        const statusColors = {open:'#d97706',in_progress:'#2563eb',resolved:'#16a34a',closed:'#6b7280'};
        itemsEl.innerHTML = d.messages.map(m => `
            <div style="background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:10px; padding:10px 12px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="font-size:11px; font-weight:700; color:${catColors[m.category]||'#374151'}; background:rgba(0,0,0,.05); padding:2px 7px; border-radius:5px;">
                        <i class="fas ${m.category_icon}"></i> ${m.category_label}
                    </span>
                    <span style="font-size:11px; font-weight:600; color:${statusColors[m.status]||'#374151'};">${statusLabels[m.status]||m.status}</span>
                </div>
                <div style="font-size:12px; color:var(--text-primary); line-height:1.5; margin-bottom:4px;">${escapeHtml(m.message)}</div>
                ${m.admin_reply ? `<div style="margin-top:6px; border-left:3px solid var(--accent-primary); padding:5px 8px; background:var(--bg-card); border-radius:0 6px 6px 0; font-size:11px; color:var(--text-secondary);">
                    <i class="fas fa-reply" style="margin-right:4px;"></i>${escapeHtml(m.admin_reply)}
                </div>` : ''}
                <div style="font-size:10px; color:var(--text-secondary); margin-top:6px;">${m.created_at}</div>
            </div>
        `).join('');
    } catch(e) {
        loadingEl.style.display = 'none';
        emptyEl.style.display = 'block';
    }
}