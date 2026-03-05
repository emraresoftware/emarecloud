# Hosting Builder Modül Mimarisi

> EmareCloud OS — Müşterinin kendi hosting/SaaS işini kurabileceği altyapı katmanı.

---

## 1. Vizyon

Hosting Builder, EmareCloud'i "sunucu yönetim paneli"nden "iş kurma platformu"na dönüştüren katmandır.

**Hedef kullanıcı profilleri:**

| Profil | Ne Yapmak İstiyor | Hosting Builder'dan Beklentisi |
|--------|-------------------|-------------------------------|
| Hosting girişimcisi | Kendi hosting şirketi | Müşteri, paket, faturalama, white-label |
| Web ajansı | Müşterilerine sunucu | Domain atama, SSL otomatik, izole kaynaklar |
| SaaS geliştirici | Uygulama dağıtımı | Docker deploy, env yönetimi, rolling restart |
| AI girişimci | AI API servisi | Model expose, API key, kullanım takibi |
| Freelancer | Müşteri projeleri host | Basit panel, otomatik SSL, düşük yönetim yükü |

---

## 2. Modül Haritası

```
Hosting Builder
│
├── 👥 Customer Management
│   ├── Müşteri CRUD
│   ├── Alt kullanıcı oluşturma
│   ├── Müşteri portal (self-service)
│   └── Müşteri başına kaynak atama
│
├── 📦 Package Manager
│   ├── Paket tanımlama (CPU/RAM/disk/BW)
│   ├── Fiyatlandırma (aylık/yıllık)
│   ├── Özellik matrisi (market, terminal, vb.)
│   └── Paket yükseltme/düşürme
│
├── 🌐 Domain & SSL Automation
│   ├── Domain ekleme/doğrulama
│   ├── DNS yönetimi (opsiyonel)
│   ├── Let's Encrypt otomatik SSL
│   ├── Nginx reverse proxy auto-config
│   └── Wildcard SSL desteği
│
├── 🐳 Deployment Engine
│   ├── Docker Compose deploy
│   ├── Git-based deployment
│   ├── Environment variable yönetimi
│   ├── Rolling restart
│   └── Deploy log & rollback
│
├── 📊 Resource Quota System
│   ├── CPU/RAM/disk limitleri
│   ├── Bandwidth tracking
│   ├── Kaynak izolasyonu (cgroup/LXD)
│   └── Otomatik uyarılar (%80, %90, %100)
│
└── 📈 Usage & Analytics
    ├── Müşteri bazlı kullanım
    ├── Sunucu bazlı metrikler
    ├── Bandwidth raporları
    └── Fatura entegrasyonu
```

---

## 3. Customer Management

### 3.1 Veritabanı Şeması

```sql
-- Tenant'ın müşterileri
CREATE TABLE customers (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,            -- Hangi tenant'ın müşterisi
    
    -- Müşteri bilgileri
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    company         TEXT,
    phone           TEXT,
    
    -- Paket & durum
    package_id      TEXT,
    status          TEXT DEFAULT 'active',    -- active | suspended | cancelled
    
    -- Kaynak ataması
    server_id       TEXT,                     -- Atanmış sunucu
    container_id    TEXT,                     -- LXD container (izolasyon)
    
    -- Portal erişimi
    portal_username TEXT,
    portal_password_hash TEXT,
    can_access_terminal BOOLEAN DEFAULT FALSE,
    can_install_apps BOOLEAN DEFAULT FALSE,
    
    -- Meta
    notes           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (package_id) REFERENCES hosting_packages(id)
);

-- Müşterinin domainleri
CREATE TABLE customer_domains (
    id              TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    org_id          TEXT NOT NULL,
    
    domain          TEXT NOT NULL,            -- "example.com"
    type            TEXT DEFAULT 'primary',   -- primary | addon | subdomain
    
    -- SSL durumu
    ssl_status      TEXT DEFAULT 'pending',   -- pending | active | expired | error
    ssl_expires_at  DATETIME,
    ssl_provider    TEXT DEFAULT 'letsencrypt',
    
    -- Nginx config
    nginx_config_path TEXT,
    proxy_target    TEXT,                     -- "http://localhost:3000"
    
    -- DNS (opsiyonel)
    dns_verified    BOOLEAN DEFAULT FALSE,
    dns_records     TEXT,                     -- JSON
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(domain),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### 3.2 Müşteri Portalı

Tenant'ın müşterisi self-service portal üzerinden:

```
Müşteri Portalı (Kısıtlı Erişim)
│
├── Dashboard
│   ├── Kaynak kullanımı (CPU/RAM/disk)
│   ├── Bandwidth kullanımı
│   └── Aktif domainler
│
├── Domainler
│   ├── Domain listesi
│   ├── SSL durumu
│   └── DNS kayıtları
│
├── Dosyalar (opsiyonel)
│   ├── File manager
│   └── FTP bilgileri
│
├── Veritabanı (opsiyonel)
│   ├── DB listesi
│   ├── phpMyAdmin linki
│   └── Bağlantı bilgileri
│
├── E-posta (opsiyonel)
│   ├── E-posta hesapları
│   └── Yönlendirmeler
│
├── Faturalar
│   ├── Fatura listesi
│   ├── Ödeme geçmişi
│   └── Paket bilgisi
│
└── Destek
    ├── Ticket oluştur
    └── Ticket geçmişi
```

---

## 4. Package Manager

### 4.1 Paket Tanımlama

```sql
CREATE TABLE hosting_packages (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    
    name            TEXT NOT NULL,            -- "Başlangıç", "Profesyonel", "İş"
    slug            TEXT NOT NULL,
    description     TEXT,
    
    -- Fiyatlandırma
    price_monthly   INTEGER NOT NULL,         -- cent cinsinden
    price_yearly    INTEGER,                  -- İndirimli yıllık
    currency        TEXT DEFAULT 'TRY',
    setup_fee       INTEGER DEFAULT 0,
    
    -- Kaynak limitleri
    cpu_cores       REAL DEFAULT 1,           -- vCPU
    ram_mb          INTEGER DEFAULT 1024,     -- MB
    disk_gb         INTEGER DEFAULT 10,       -- GB
    bandwidth_gb    INTEGER DEFAULT 100,      -- GB/ay
    
    -- Özellik limitleri
    max_domains     INTEGER DEFAULT 1,
    max_databases   INTEGER DEFAULT 1,
    max_email_accounts INTEGER DEFAULT 5,
    max_ftp_accounts INTEGER DEFAULT 1,
    
    -- İzinler
    ssh_access      BOOLEAN DEFAULT FALSE,
    terminal_access BOOLEAN DEFAULT FALSE,
    market_access   BOOLEAN DEFAULT FALSE,
    docker_access   BOOLEAN DEFAULT FALSE,
    custom_cron     BOOLEAN DEFAULT FALSE,
    
    -- Durum
    is_active       BOOLEAN DEFAULT TRUE,
    is_featured     BOOLEAN DEFAULT FALSE,
    sort_order      INTEGER DEFAULT 0,
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### 4.2 Paket Yönetimi UI

```
┌─────────────────────────────────────────────────────────────────┐
│ 📦 Hosting Paketleri                          [+ Yeni Paket]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │  Başlangıç    │  │  Profesyonel  │  │  İş           │       │
│  │               │  │               │  │               │       │
│  │  ₺49.99/ay    │  │  ₺149.99/ay   │  │  ₺349.99/ay   │       │
│  │               │  │               │  │               │       │
│  │  1 vCPU       │  │  2 vCPU       │  │  4 vCPU       │       │
│  │  1 GB RAM     │  │  4 GB RAM     │  │  8 GB RAM     │       │
│  │  10 GB Disk   │  │  50 GB Disk   │  │  200 GB Disk  │       │
│  │  100 GB BW    │  │  500 GB BW    │  │  2 TB BW      │       │
│  │  1 Domain     │  │  10 Domain    │  │  Sınırsız     │       │
│  │  5 E-posta    │  │  50 E-posta   │  │  Sınırsız     │       │
│  │  ☐ SSH        │  │  ☑ SSH        │  │  ☑ SSH        │       │
│  │  ☐ Docker     │  │  ☑ Docker     │  │  ☑ Docker     │       │
│  │               │  │               │  │               │       │
│  │  12 müşteri   │  │  5 müşteri    │  │  2 müşteri    │       │
│  │               │  │               │  │               │       │
│  │ [Düzenle][Sil]│  │ [Düzenle][Sil]│  │ [Düzenle][Sil]│       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Domain & SSL Automation

### 5.1 Domain Ekleme Akışı

```
Müşteri/Admin domain ekler
         │
         ▼
   DNS doğrulama
   (A record → sunucu IP?)
         │
    ┌────┴────┐
    │         │
   Evet     Hayır
    │         │
    ▼         ▼
  Nginx    DNS talimatları
  config    göster & bekle
  oluştur      │
    │         (cron ile
    ▼          kontrol)
  Let's        │
  Encrypt      ▼
  SSL al     Doğrulandı?
    │         → Evet → ↑
    ▼
  ✅ Aktif
```

### 5.2 Otomatik Nginx Config Üretimi

```python
# hosting/domain_manager.py

def generate_nginx_config(domain: str, proxy_target: str, ssl: bool = True) -> str:
    """Domain için Nginx config oluştur."""
    
    if ssl:
        return f"""
server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain};
    
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Güvenlik başlıkları
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    
    location / {{
        proxy_pass {proxy_target};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
"""
    else:
        return f"""
server {{
    listen 80;
    server_name {domain};
    
    location / {{
        proxy_pass {proxy_target};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
"""


def deploy_nginx_config(server_id: str, domain: str, config: str):
    """Config'i sunucuya yükle ve Nginx'i yeniden yükle."""
    ssh = get_ssh_connection(server_id)
    
    config_path = f"/etc/nginx/sites-available/{domain}"
    enabled_path = f"/etc/nginx/sites-enabled/{domain}"
    
    # Config yaz
    ssh.exec(f"echo '{config}' | sudo tee {config_path}")
    
    # Aktif et
    ssh.exec(f"sudo ln -sf {config_path} {enabled_path}")
    
    # Nginx test & reload
    result = ssh.exec("sudo nginx -t")
    if "successful" in result:
        ssh.exec("sudo systemctl reload nginx")
        return True
    else:
        # Rollback
        ssh.exec(f"sudo rm {enabled_path}")
        ssh.exec("sudo systemctl reload nginx")
        return False


def obtain_ssl_certificate(server_id: str, domain: str, email: str):
    """Let's Encrypt SSL sertifikası al."""
    ssh = get_ssh_connection(server_id)
    
    result = ssh.exec(
        f"sudo certbot certonly --nginx "
        f"-d {domain} "
        f"--email {email} "
        f"--agree-tos --non-interactive"
    )
    
    if "Successfully" in result:
        # Auto-renewal cron zaten certbot tarafından ekleniyor
        return {'status': 'active', 'domain': domain}
    else:
        return {'status': 'error', 'message': result}
```

---

## 6. Deployment Engine

### 6.1 Desteklenen Dağıtım Yöntemleri

| Yöntem | Kullanım | Açıklama |
|--------|----------|----------|
| **Docker Compose** | SaaS, web app | docker-compose.yml ile dağıtım |
| **Git Deploy** | Statik site, Node.js | Git push ile otomatik deploy |
| **Dosya Yükleme** | WordPress, PHP | FTP/SFTP ile dosya yükleme |
| **Market Kurulum** | Hazır uygulamalar | Mevcut market sistemi |

### 6.2 Docker Compose Deploy

```python
# hosting/deployer.py

class DockerDeployer:
    """Docker Compose tabanlı uygulama dağıtımı."""
    
    def deploy(self, server_id: str, customer_id: str, config: dict):
        """
        config = {
            'app_name': 'my-saas',
            'compose_content': '...',   # docker-compose.yml içeriği
            'env_vars': {'DB_HOST': '...', 'SECRET': '...'},
            'domain': 'app.example.com',
            'port': 3000
        }
        """
        ssh = get_ssh_connection(server_id)
        app_dir = f"/opt/apps/{customer_id}/{config['app_name']}"
        
        # 1. Dizin oluştur
        ssh.exec(f"sudo mkdir -p {app_dir}")
        
        # 2. docker-compose.yml yaz
        ssh.exec(f"echo '{config['compose_content']}' | sudo tee {app_dir}/docker-compose.yml")
        
        # 3. .env dosyası oluştur
        env_content = '\n'.join(f"{k}={v}" for k, v in config['env_vars'].items())
        ssh.exec(f"echo '{env_content}' | sudo tee {app_dir}/.env")
        
        # 4. Deploy
        result = ssh.exec(f"cd {app_dir} && sudo docker compose up -d")
        
        # 5. Nginx reverse proxy
        if config.get('domain'):
            nginx_config = generate_nginx_config(
                domain=config['domain'],
                proxy_target=f"http://localhost:{config['port']}"
            )
            deploy_nginx_config(server_id, config['domain'], nginx_config)
            obtain_ssl_certificate(server_id, config['domain'], 'ssl@emarecloud.com')
        
        # 6. Deploy log kaydet
        log_deployment(customer_id, config['app_name'], 'success', result)
        
        return {'status': 'deployed', 'url': f"https://{config['domain']}"}
    
    
    def rolling_restart(self, server_id: str, customer_id: str, app_name: str):
        """Zero-downtime restart."""
        ssh = get_ssh_connection(server_id)
        app_dir = f"/opt/apps/{customer_id}/{app_name}"
        
        # Pull latest images
        ssh.exec(f"cd {app_dir} && sudo docker compose pull")
        
        # Rolling restart
        ssh.exec(f"cd {app_dir} && sudo docker compose up -d --no-deps --build")
        
        return {'status': 'restarted'}
    
    
    def rollback(self, server_id: str, customer_id: str, app_name: str):
        """Son başarılı deployment'a geri dön."""
        last_good = get_last_successful_deployment(customer_id, app_name)
        if last_good:
            return self.deploy(server_id, customer_id, last_good['config'])
        return {'status': 'error', 'message': 'Rollback noktası bulunamadı'}
```

### 6.3 Deployment UI

```
┌─────────────────────────────────────────────────────────────┐
│ 🚀 Deployments — müşteri: AcmeCorp                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Uygulama: my-saas-app                                      │
│  Domain: app.acmecorp.com ✅ SSL aktif                      │
│  Container: 3/3 çalışıyor                                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Deploy Geçmişi                                      │    │
│  ├──────┬──────────────┬────────┬──────────┬──────────┤    │
│  │ #    │ Tarih        │ Durum  │ Süre     │          │    │
│  ├──────┼──────────────┼────────┼──────────┼──────────┤    │
│  │ #12  │ 01.03 14:32  │ ✅ OK  │ 45s      │ Aktif    │    │
│  │ #11  │ 28.02 09:15  │ ✅ OK  │ 52s      │ Rollback │    │
│  │ #10  │ 27.02 18:40  │ ❌ Fail │ 12s      │          │    │
│  └──────┴──────────────┴────────┴──────────┴──────────┘    │
│                                                             │
│  [🔄 Restart]  [⬆️ Deploy]  [⏪ Rollback]  [📋 Logs]      │
│                                                             │
│  Environment Variables:                                     │
│  ┌────────────────┬────────────────────┬──────────┐         │
│  │ Key            │ Value              │          │         │
│  ├────────────────┼────────────────────┼──────────┤         │
│  │ DATABASE_URL   │ ••••••••••••       │ 👁️ Göster│         │
│  │ SECRET_KEY     │ ••••••••••••       │ 👁️ Göster│         │
│  │ NODE_ENV       │ production         │ 👁️ Göster│         │
│  └────────────────┴────────────────────┴──────────┘         │
│  [+ Değişken Ekle]  [💾 Kaydet & Restart]                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Resource Quota System

### 7.1 İzolasyon Stratejisi

| Strateji | Avantaj | Dezavantaj | Kullanım |
|----------|---------|------------|----------|
| **LXD Container** | Tam izolasyon, kernel paylaşımlı | Daha fazla kaynak | Premium paketler |
| **Docker + cgroup** | Hafif, hızlı | Daha az izolasyon | Standart paketler |
| **Process limitleri** | En hafif | Zayıf izolasyon | Giriş paketleri |

### 7.2 Kaynak Kontrol Akışı

```python
# hosting/quota.py

class QuotaManager:
    """Müşteri kaynak kotası yönetimi."""
    
    def check_quota(self, customer_id: str, metric: str, requested: float = 0) -> dict:
        """Kotayı kontrol et."""
        customer = db.get_customer(customer_id)
        package = db.get_package(customer['package_id'])
        
        limits = {
            'cpu_cores': package['cpu_cores'],
            'ram_mb': package['ram_mb'],
            'disk_gb': package['disk_gb'],
            'bandwidth_gb': package['bandwidth_gb'],
            'domains': package['max_domains'],
            'databases': package['max_databases'],
        }
        
        current_usage = self.get_current_usage(customer_id, metric)
        limit = limits.get(metric, float('inf'))
        
        return {
            'metric': metric,
            'current': current_usage,
            'limit': limit,
            'requested': requested,
            'available': max(0, limit - current_usage),
            'allowed': (current_usage + requested) <= limit,
            'percentage': round((current_usage / limit) * 100, 1) if limit > 0 else 0
        }
    
    def enforce_limits(self, server_id: str, customer_id: str, package: dict):
        """LXD/Docker container'a kaynak limiti uygula."""
        ssh = get_ssh_connection(server_id)
        
        container = db.get_customer_container(customer_id)
        if not container:
            return
        
        if container['type'] == 'lxd':
            # LXD resource limits
            ssh.exec(f"lxc config set {container['name']} limits.cpu {package['cpu_cores']}")
            ssh.exec(f"lxc config set {container['name']} limits.memory {package['ram_mb']}MB")
            # Disk quota
            ssh.exec(f"lxc config device set {container['name']} root size={package['disk_gb']}GB")
        
        elif container['type'] == 'docker':
            # Docker resource limits (compose update)
            update_compose_resources(
                server_id, customer_id,
                cpus=package['cpu_cores'],
                memory=f"{package['ram_mb']}m"
            )
    
    def send_quota_alerts(self):
        """Kota uyarıları gönder (%80, %90, %100)."""
        for customer in db.get_active_customers():
            for metric in ['disk_gb', 'bandwidth_gb']:
                usage = self.check_quota(customer['id'], metric)
                
                if usage['percentage'] >= 100:
                    notify(customer, f"⛔ {metric} kotanız doldu!")
                    if metric == 'bandwidth_gb':
                        # Bandwidth aşımında: yavaşlat veya durdur
                        self.throttle_customer(customer['id'])
                elif usage['percentage'] >= 90:
                    notify(customer, f"⚠️ {metric} kotanızın %90'ı kullanıldı")
                elif usage['percentage'] >= 80:
                    notify(customer, f"ℹ️ {metric} kotanızın %80'i kullanıldı")
```

---

## 8. Yeni Route'lar (Blueprint)

```python
# routes/hosting.py — Hosting Builder Blueprint

hosting_bp = Blueprint('hosting', __name__, url_prefix='/api/hosting')

# Müşteri yönetimi
@hosting_bp.route('/customers', methods=['GET'])          # Liste
@hosting_bp.route('/customers', methods=['POST'])         # Oluştur
@hosting_bp.route('/customers/<id>', methods=['GET'])     # Detay
@hosting_bp.route('/customers/<id>', methods=['PUT'])     # Güncelle
@hosting_bp.route('/customers/<id>', methods=['DELETE'])  # Sil
@hosting_bp.route('/customers/<id>/suspend', methods=['POST'])
@hosting_bp.route('/customers/<id>/activate', methods=['POST'])

# Paket yönetimi
@hosting_bp.route('/packages', methods=['GET'])
@hosting_bp.route('/packages', methods=['POST'])
@hosting_bp.route('/packages/<id>', methods=['PUT'])
@hosting_bp.route('/packages/<id>', methods=['DELETE'])

# Domain yönetimi
@hosting_bp.route('/domains', methods=['GET'])
@hosting_bp.route('/domains', methods=['POST'])
@hosting_bp.route('/domains/<id>/verify-dns', methods=['POST'])
@hosting_bp.route('/domains/<id>/ssl', methods=['POST'])   # SSL al
@hosting_bp.route('/domains/<id>', methods=['DELETE'])

# Deployment
@hosting_bp.route('/deploy', methods=['POST'])
@hosting_bp.route('/deploy/<id>/restart', methods=['POST'])
@hosting_bp.route('/deploy/<id>/rollback', methods=['POST'])
@hosting_bp.route('/deploy/<id>/logs', methods=['GET'])
@hosting_bp.route('/deploy/<id>/env', methods=['GET', 'PUT'])

# Kota & kullanım
@hosting_bp.route('/customers/<id>/usage', methods=['GET'])
@hosting_bp.route('/customers/<id>/quota', methods=['GET'])
```

### Yeni Sayfa Route'ları

```python
# Hosting Builder sayfaları
@pages_bp.route('/hosting')                    # Hosting dashboard
@pages_bp.route('/hosting/customers')          # Müşteri listesi
@pages_bp.route('/hosting/customers/<id>')     # Müşteri detay
@pages_bp.route('/hosting/packages')           # Paket yönetimi
@pages_bp.route('/hosting/domains')            # Domain yönetimi
@pages_bp.route('/hosting/deployments')        # Deployment listesi

# Müşteri portalı (ayrı auth)
@portal_bp.route('/portal/login')
@portal_bp.route('/portal/dashboard')
@portal_bp.route('/portal/domains')
@portal_bp.route('/portal/billing')
@portal_bp.route('/portal/support')
```

---

## 9. Sidebar Menü Güncellemesi

```
Mevcut Menü:              Yeni Menü:
─────────────             ─────────────
📊 Dashboard              📊 Dashboard
🏪 Uygulama Pazarı       🏪 Uygulama Pazarı
🖥️ Sanallaştırma         🖥️ Sanallaştırma
💾 Depolama               💾 Depolama
                          ─────────────
                          🏢 Hosting Builder   ← YENİ
                          │ 👥 Müşteriler
                          │ 📦 Paketler
                          │ 🌐 Domainler
                          │ 🚀 Deployments
                          ─────────────
                          🤖 AI Platform       ← YENİ
                          │ 🔑 API Keys
                          │ 📊 Kullanım
                          │ ⚙️ Modeller
                          ─────────────
                          💰 Faturalandırma     ← YENİ
                          ─────────────
📋 Sunucu Listesi         📋 Sunucu Listesi
+ Sunucu Ekle             + Sunucu Ekle
```

---

## 10. Uygulama Öncelik Sırası

| Sıra | Modül | Karmaşıklık | Süre | Bağımlılık |
|------|-------|-------------|------|------------|
| 1 | Customer CRUD + DB | Düşük | 1 hafta | Multi-tenant |
| 2 | Package CRUD + DB | Düşük | 3 gün | #1 |
| 3 | Customer → Package atama | Düşük | 3 gün | #1, #2 |
| 4 | Domain ekleme + DNS doğrulama | Orta | 1 hafta | #1 |
| 5 | Nginx auto-config + deploy | Yüksek | 2 hafta | #4 |
| 6 | Let's Encrypt otomasyon | Yüksek | 1 hafta | #5 |
| 7 | Resource quota (LXD/Docker) | Yüksek | 2 hafta | #1, Multi-tenant |
| 8 | Docker Compose deployer | Yüksek | 2 hafta | #5 |
| 9 | Müşteri portalı (self-service) | Orta | 2 hafta | #1-6 |
| 10 | Usage tracking + billing hook | Orta | 1 hafta | Billing sistemi |

**Toplam tahmini süre: 12-14 hafta**

---

## 11. Rekabet Analizi

| Özellik | cPanel | Plesk | CloudPanel | EmareCloud |
|---------|--------|-------|------------|-------------|
| Multi-tenant | ✅ WHM | ✅ | ❌ | ✅ (planlanıyor) |
| Docker deploy | ❌ | Uzantı | ❌ | ✅ |
| AI platform | ❌ | ❌ | ❌ | ✅ |
| Modern UI | ❌ | Orta | ✅ | ✅ |
| Self-hosted | ✅ | ✅ | ✅ | ✅ |
| API-first | ❌ | ✅ | ❌ | ✅ |
| White-label | 💰 | 💰 | ❌ | ✅ |
| Fiyat | $15/ay | $11/ay | Ücretsiz | $29/ay |
| Fark | Eski, güvenilir | Çok yönlü | Basit | **İş kurma platformu** |

> EmareCloud farkı: Rakipler "sunucu yönetir", EmareCloud "iş kurdurur."

---

*Doküman: EmareCloud OS — Hosting Builder Modül Mimarisi v1.0*
*Tarih: Mart 2026*
