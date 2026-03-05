# EmareCloud — RBAC Yetki Matrisi & Endpoint Mapping

> **Versiyon:** 1.0.0  
> **Tarih:** Mart 2026  
> **Toplam Endpoint:** 48 (42 HTTP + 4 WebSocket + 2 Sayfa Yönetim)

---

## 1. Rol Hiyerarşisi

```
super_admin (seviye 100) ─── Tam yetki ('*' wildcard)
    │
    admin (seviye 75) ─── Sunucu + kullanıcı yönetimi
        │
        operator (seviye 50) ─── Komut çalıştırma + servis yönetimi
            │
            read_only (seviye 10) ─── Sadece görüntüleme
```

> **Kural:** `super_admin` rolü `permission_required()` kontrollerinde her zaman geçer (`'*'` wildcard).
> Blocklist (`command_security.py`) ise super_admin dahil **herkesi** engeller.

---

## 2. Yetki Tanımları (25 Granüler Yetki)

| Yetki | super_admin | admin | operator | read_only |
|-------|:---:|:---:|:---:|:---:|
| `server.view` | ✅ | ✅ | ✅ | ✅ |
| `server.add` | ✅ | ✅ | ❌ | ❌ |
| `server.edit` | ✅ | ✅ | ❌ | ❌ |
| `server.delete` | ✅ | ✅ | ❌ | ❌ |
| `server.connect` | ✅ | ✅ | ✅ | ❌ |
| `server.disconnect` | ✅ | ✅ | ✅ | ❌ |
| `server.metrics` | ✅ | ✅ | ✅ | ✅ |
| `server.execute` | ✅ | ✅ | ✅ | ❌ |
| `server.quick_action` | ✅ | ✅ | ✅ | ❌ |
| `firewall.view` | ✅ | ✅ | ✅ | ✅ |
| `firewall.manage` | ✅ | ✅ | ❌ | ❌ |
| `vm.view` | ✅ | ✅ | ✅ | ✅ |
| `vm.manage` | ✅ | ✅ | ✅ | ❌ |
| `market.view` | ✅ | ✅ | ✅ | ✅ |
| `market.install` | ✅ | ✅ | ✅ | ❌ |
| `storage.view` | ✅ | ✅ | ✅ | ✅ |
| `storage.manage` | ✅ | ✅ | ❌ | ❌ |
| `terminal.access` | ✅ | ✅ | ✅ | ❌ |
| `raid.view` | ✅ | ✅ | ✅ | ✅ |
| `raid.manage` | ✅ | ✅ | ❌ | ❌ |

---

## 3. Komut Yürütme Güvenlik Katmanları

`server.execute` izni olan roller için ek güvenlik katmanı (`command_security.py`):

| Katman | super_admin | admin | operator | read_only |
|--------|:---:|:---:|:---:|:---:|
| Global blocklist (rm -rf /, fork bomb vb.) | 🚫 ENGELLİ | 🚫 ENGELLİ | 🚫 ENGELLİ | 🚫 ENGELLİ |
| OPERATOR_ALLOWED (ls, cat, df, top, systemctl status...) | ✅ | ✅ | ✅ | — |
| ADMIN_EXTRA (apt install, docker, mkdir, chmod...) | ✅ | ✅ | ❌ | — |
| Allowlist dışı komutlar | ✅ | ⚠️ Onay ile | ❌ | — |

---

## 4. Endpoint → Yetki Mapping (Tam Liste)

### 4.1 Genel Sayfalar (auth_routes.py Blueprint)

| # | Endpoint | Metod | Auth | Yetki / Rol | Açıklama |
|---|----------|-------|:---:|-------------|----------|
| 1 | `/login` | GET/POST | 🔓 Public | — | Giriş sayfası + form |
| 2 | `/logout` | GET | 🔒 login | — | Oturum kapatma |
| 3 | `/profile` | GET/POST | 🔒 login | — | Profil + şifre değiştirme |
| 4 | `/admin/users` | GET | 🔒 login | `role: super_admin, admin` | Kullanıcı yönetimi sayfası |
| 5 | `/admin/audit` | GET | 🔒 login | `role: super_admin, admin` | Denetim günlüğü sayfası |

### 4.2 Kullanıcı Yönetim API (auth_routes.py Blueprint)

| # | Endpoint | Metod | Auth | Yetki / Rol | Açıklama |
|---|----------|-------|:---:|-------------|----------|
| 6 | `/api/users` | GET | 🔒 login | `role: super_admin, admin` | Kullanıcı listesi |
| 7 | `/api/users` | POST | 🔒 login | `role: super_admin` | Kullanıcı oluşturma |
| 8 | `/api/users/<id>` | PUT | 🔒 login | `role: super_admin` | Kullanıcı güncelleme |
| 9 | `/api/users/<id>` | DELETE | 🔒 login | `role: super_admin` | Kullanıcı silme |
| 10 | `/api/audit-logs` | GET | 🔒 login | `role: super_admin, admin` | Denetim günlüğü (sayfalı) |

### 4.3 Panel Sayfaları (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama |
|---|----------|-------|:---:|-------|----------|
| 11 | `/health` | GET | 🔓 Public | — | Sağlık kontrolü (healthcheck) |
| 12 | `/` | GET | 🔒 login | — | Dashboard (tüm sunucu özeti) |
| 13 | `/market` | GET | 🔒 login | `market.view` | Uygulama pazarı |
| 14 | `/server/<id>` | GET | 🔒 login | `server.view` | Sunucu detay sayfası |
| 15 | `/terminal/<id>` | GET | 🔒 login | `terminal.access` | Web SSH terminal |
| 16 | `/virtualization` | GET | 🔒 login | `vm.view` | Sanallaştırma sayfası |
| 17 | `/storage` | GET | 🔒 login | `storage.view` | Depolama/RAID sayfası |

### 4.4 Sunucu Yönetim API (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama | Tehdit |
|---|----------|-------|:---:|-------|----------|--------|
| 18 | `/api/servers` | GET | 🔒 | `server.view` | Sunucu listesi | 🟢 Düşük |
| 19 | `/api/servers` | POST | 🔒 | `server.add` | Sunucu ekleme | 🟡 Orta |
| 20 | `/api/servers/<id>` | PUT | 🔒 | `server.edit` | Sunucu düzenleme | 🟡 Orta |
| 21 | `/api/servers/<id>` | DELETE | 🔒 | `server.delete` | Sunucu silme | 🔴 Yüksek |
| 22 | `/api/servers/<id>/connect` | POST | 🔒 | `server.connect` | SSH bağlantı aç | 🟡 Orta |
| 23 | `/api/servers/<id>/disconnect` | POST | 🔒 | `server.disconnect` | SSH bağlantı kapat | 🟢 Düşük |

### 4.5 Metrik / İzleme API (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama | Tehdit |
|---|----------|-------|:---:|-------|----------|--------|
| 24 | `/api/servers/<id>/metrics` | GET | 🔒 | `server.metrics` | Genel metrikler | 🟢 |
| 25 | `/api/servers/<id>/cpu` | GET | 🔒 | `server.metrics` | CPU detay | 🟢 |
| 26 | `/api/servers/<id>/memory` | GET | 🔒 | `server.metrics` | RAM detay | 🟢 |
| 27 | `/api/servers/<id>/disks` | GET | 🔒 | `server.metrics` | Disk kullanımı | 🟢 |
| 28 | `/api/servers/<id>/processes` | GET | 🔒 | `server.metrics` | Süreç listesi | 🟢 |
| 29 | `/api/servers/<id>/services` | GET | 🔒 | `server.metrics` | Servis durumları | 🟢 |
| 30 | `/api/servers/<id>/security` | GET | 🔒 | `server.metrics` | Güvenlik bilgisi | 🟢 |

### 4.6 Firewall API (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama | Tehdit |
|---|----------|-------|:---:|-------|----------|--------|
| 31 | `/api/servers/<id>/firewall/status` | GET | 🔒 | `firewall.view` | Durum sorgula | 🟢 |
| 32 | `/api/servers/<id>/firewall/enable` | POST | 🔒 | `firewall.manage` | Güvenlik duvarı aç | 🔴 Yüksek |
| 33 | `/api/servers/<id>/firewall/disable` | POST | 🔒 | `firewall.manage` | Güvenlik duvarı kapat | 🔴 Yüksek |
| 34 | `/api/servers/<id>/firewall/rules` | POST | 🔒 | `firewall.manage` | Kural ekle | 🔴 Yüksek |
| 35 | `/api/servers/<id>/firewall/rules/<idx>` | DELETE | 🔒 | `firewall.manage` | Kural sil | 🔴 Yüksek |

### 4.7 Sanallaştırma (LXD) API (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama | Tehdit |
|---|----------|-------|:---:|-------|----------|--------|
| 36 | `/api/servers/<id>/vms` | GET | 🔒 | `vm.view` | VM listesi | 🟢 |
| 37 | `/api/servers/<id>/vms/images` | GET | 🔒 | `vm.view` | İmaj listesi | 🟢 |
| 38 | `/api/servers/<id>/vms` | POST | 🔒 | `vm.manage` | VM oluştur | 🟡 Orta |
| 39 | `/api/servers/<id>/vms/<name>/start` | POST | 🔒 | `vm.manage` | VM başlat | 🟡 Orta |
| 40 | `/api/servers/<id>/vms/<name>/stop` | POST | 🔒 | `vm.manage` | VM durdur | 🟡 Orta |
| 41 | `/api/servers/<id>/vms/<name>` | DELETE | 🔒 | `vm.manage` | VM sil | 🔴 Yüksek |
| 42 | `/api/servers/<id>/vms/<name>/exec` | POST | 🔒 | `vm.manage` | VM'de komut çalıştır | 🔴 Yüksek |

### 4.8 Komut Çalıştırma API (app.py) — ⚠️ Kritik Yüzey

| # | Endpoint | Metod | Auth | Yetki | Ek Güvenlik | Tehdit |
|---|----------|-------|:---:|-------|-------------|--------|
| 43 | `/api/servers/<id>/execute` | POST | 🔒 | `server.execute` | `command_security.check_command()` + blocklist + audit log | 🔴🔴 Kritik |
| 44 | `/api/servers/<id>/quick-action` | POST | 🔒 | `server.quick_action` | 10 sabit aksiyon allowlist | 🟡 Orta |

### 4.9 Depolama / RAID API (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama | Tehdit |
|---|----------|-------|:---:|-------|----------|--------|
| 45 | `/api/servers/<id>/storage-status` | GET | 🔒 | `storage.view` | SMART + RAID durumu | 🟢 |
| 46 | `/api/raid-protocols` | GET | 🔒 | `raid.view` | RAID protokol listesi | 🟢 |
| 47 | `/api/raid-protocols` | POST | 🔒 | `raid.manage` | RAID protokol ekle | 🟡 Orta |
| 48 | `/api/raid-protocols/<id>` | PUT | 🔒 | `raid.manage` | RAID protokol düzenle | 🟡 Orta |
| 49 | `/api/raid-protocols/<id>` | DELETE | 🔒 | `raid.manage` | RAID protokol sil | 🟡 Orta |

### 4.10 Market / GitHub API (app.py)

| # | Endpoint | Metod | Auth | Yetki | Açıklama | Tehdit |
|---|----------|-------|:---:|-------|----------|--------|
| 50 | `/api/market/apps` | GET | 🔒 | `market.view` | Uygulama kataloğu | 🟢 |
| 51 | `/api/market/install` | POST | 🔒 | `market.install` | Katalog app kurulumu | 🔴 Yüksek |
| 52 | `/api/market/github/search` | GET | 🔒 | `market.view` | GitHub arama | 🟢 |
| 53 | `/api/market/github/trending` | GET | 🔒 | `market.view` | GitHub trend | 🟢 |
| 54 | `/api/market/github/readme` | GET | 🔒 | `market.view` | GitHub README | 🟢 |
| 55 | `/api/market/github/install` | POST | 🔒 | `market.install` | GitHub repo kurulumu | 🔴 Yüksek |

### 4.11 WebSocket Olayları (app.py SocketIO)

| # | Olay | Auth | Yetki | Açıklama | Tehdit |
|---|------|:---:|-------|----------|--------|
| 56 | `terminal_connect` | 🔒 session | `terminal.access` (sayfa düzeyinde) | SSH WebSocket bağlantı | 🔴🔴 Kritik |
| 57 | `terminal_input` | 🔒 session | (bağlantı var ise) | Klavye girişi gönder | 🔴🔴 Kritik |

---

## 5. Tehdit Yüzeyi Özeti

### 🔴🔴 Kritik Yüzey (4 endpoint)

| Endpoint | Korumalar | Açık Risk |
|----------|-----------|-----------|
| `/api/servers/<id>/execute` | login + RBAC + command_security blocklist/allowlist + audit log | Pipe zinciri bypass riski |
| `/api/market/install` | login + RBAC + audit log | Kurulum scripti kontrolsüz çalışır |
| `/api/market/github/install` | login + RBAC + audit log | Bilinmeyen repo'dan script çalışır |
| `terminal_connect/input` | login + sayfa düzeyinde RBAC | SocketIO event'lerinde ayrı yetki kontrolü yok |

### Öneri: WebSocket Güvenlik İyileştirmesi

```python
# SocketIO event'lerine doğrudan yetki kontrolü eklenmeli:
@socketio.on('terminal_connect')
def handle_terminal_connect(data):
    if not current_user.is_authenticated:
        return emit('error', {'message': 'Unauthorized'})
    if not has_permission(current_user.role, 'terminal.access'):
        return emit('error', {'message': 'Permission denied'})
    # ... mevcut kod
```

---

## 6. Rol Bazlı Ekran Erişimi

| Sayfa / Özellik | super_admin | admin | operator | read_only |
|-----------------|:---:|:---:|:---:|:---:|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Sunucu Detay | ✅ | ✅ | ✅ | ✅ |
| Web Terminal | ✅ | ✅ | ✅ | ❌ |
| Komut Çalıştır | ✅ (sınırsız*) | ✅ (admin allowlist) | ✅ (operator allowlist) | ❌ |
| Hızlı Aksiyonlar | ✅ | ✅ | ✅ | ❌ |
| Firewall Görüntüle | ✅ | ✅ | ✅ | ✅ |
| Firewall Yönet | ✅ | ✅ | ❌ | ❌ |
| VM Görüntüle | ✅ | ✅ | ✅ | ✅ |
| VM Oluştur/Sil | ✅ | ✅ | ✅ | ❌ |
| Market Görüntüle | ✅ | ✅ | ✅ | ✅ |
| Market Kurulum | ✅ | ✅ | ✅ | ❌ |
| Depolama/RAID | ✅ | ✅ | ✅ | ✅ |
| RAID Yönet | ✅ | ✅ | ❌ | ❌ |
| Sunucu Ekle/Sil | ✅ | ✅ | ❌ | ❌ |
| Kullanıcı Yönetimi | ✅ | ✅ (görüntüle) | ❌ | ❌ |
| Kullanıcı CRUD | ✅ | ❌ | ❌ | ❌ |
| Audit Log | ✅ | ✅ | ❌ | ❌ |
| Profil / Şifre | ✅ | ✅ | ✅ | ✅ |

> \* `super_admin` blocklist hariç her komutu çalıştırabilir

---

## 7. Middleware Akış Diyagramı

```
İstek geliyor
    │
    ▼
[Flask Request Pipeline]
    │
    ├── /health → 🟢 Doğrudan yanıt (auth yok)
    │
    ├── /login → 🟢 Public (rate limit: 5/5dk IP bazlı)
    │
    └── Diğer tüm endpoint'ler
         │
         ▼
    [@login_required]
    "Giriş yapılmış mı?"
         │
         ├── Hayır → 302 /login?next=...
         │
         └── Evet
              │
              ▼
    [@permission_required('xxx.yyy') veya @role_required('rol1', 'rol2')]
    "Bu kullanıcının yetkisi var mı?"
         │
         ├── Hayır → 403 Forbidden (JSON veya flash message)
         │
         └── Evet
              │
              ▼
    [CSRF Kontrolü] (POST isteklerinde)
    "X-CSRFToken header geçerli mi?"
         │
         ├── Hayır → 403 CSRF doğrulama hatası
         │
         └── Evet
              │
              ▼
    [Endpoint İşlevi]
    (execute endpoint'lerinde ek command_security kontrolü)
         │
         ▼
    [@app.after_request]
    ├── compress_response (gzip)
    ├── add_security_headers (XSS, nosniff, referrer, frame-options)
    └── Yanıt
```

---

## 8. Audit Log Kapsamı

Otomatik loglanan endpoint'ler:

| Aksiyon | Loglanan Bilgiler |
|---------|-------------------|
| `auth.login` | Kullanıcı adı, IP, başarı/başarısızlık |
| `auth.logout` | Kullanıcı adı |
| `auth.password_change` | Kullanıcı ID |
| `user.create` | Yeni kullanıcı adı, rol |
| `user.update` | Değişen alanlar |
| `user.delete` | Silinen kullanıcı adı |
| `server.add` | Sunucu adı, host |
| `server.delete` | Sunucu ID |
| `server.edit` | Değişen alanlar |
| `server.execute` | Komut, sunucu ID |
| `server.execute.blocked` | Engellenen komut, neden |
| `server.quick_action` | Aksiyon türü, sunucu ID |
| `market.install` | App ID, sunucu ID |
| `market.github_install` | Repo adı, sunucu ID |
| `firewall.*` | Kural detayları, sunucu ID |
| `vm.*` | VM adı, aksiyon, sunucu ID |
