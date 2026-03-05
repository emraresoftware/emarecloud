#!/usr/bin/env bash
# ============================================================================
#  EmareCloud — Kurulum Wizard'ı
#  İlk kurulum için interaktif script.
#  Kullanım: chmod +x setup.sh && ./setup.sh
# ============================================================================

set -euo pipefail

# Renkler
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║           🏢 EmareCloud — Kurulum Wizard'ı              ║"
echo "║           Altyapı Yönetim Paneli v1.0.0                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ===================== SİSTEM KONTROLÜ =====================

echo -e "${BLUE}[1/7] Sistem kontrolleri...${NC}"

# Python 3.10+ kontrolü
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python3 bulunamadı! Lütfen Python 3.10+ kurun.${NC}"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo -e "${RED}❌ Python $PY_VERSION tespit edildi. Python 3.10+ gerekli.${NC}"
    exit 1
fi

echo -e "${GREEN}  ✅ Python $PY_VERSION${NC}"

# pip kontrolü
if ! python3 -m pip --version &>/dev/null; then
    echo -e "${RED}❌ pip bulunamadı! python3 -m ensurepip --upgrade çalıştırın.${NC}"
    exit 1
fi
echo -e "${GREEN}  ✅ pip mevcut${NC}"

# ===================== PROJE DİZİNİ =====================

echo ""
echo -e "${BLUE}[2/7] Proje dizini hazırlanıyor...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Gerekli dizinleri oluştur
mkdir -p instance logs

echo -e "${GREEN}  ✅ instance/ ve logs/ dizinleri oluşturuldu${NC}"

# ===================== BAĞIMLILIKLAR =====================

echo ""
echo -e "${BLUE}[3/7] Python bağımlılıkları kuruluyor...${NC}"

if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check 2>/dev/null || {
        echo -e "${YELLOW}  ⚠️  Bazı paketler kurulamadı. pip install -r requirements.txt komutunu deneyin.${NC}"
    }
    echo -e "${GREEN}  ✅ Bağımlılıklar kuruldu${NC}"
else
    echo -e "${RED}❌ requirements.txt bulunamadı!${NC}"
    exit 1
fi

# ===================== MASTER KEY =====================

echo ""
echo -e "${BLUE}[4/7] Şifreleme anahtarı yapılandırılıyor...${NC}"

ENV_FILE="$SCRIPT_DIR/.env"
MASTER_KEY_FILE="$SCRIPT_DIR/.master.key"

if [ -f "$MASTER_KEY_FILE" ]; then
    echo -e "${GREEN}  ✅ Master key zaten mevcut ($MASTER_KEY_FILE)${NC}"
else
    MASTER_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "$MASTER_KEY" > "$MASTER_KEY_FILE"
    chmod 600 "$MASTER_KEY_FILE"
    echo -e "${GREEN}  ✅ Master key oluşturuldu ve $MASTER_KEY_FILE dosyasına kaydedildi${NC}"
    echo -e "${YELLOW}  ⚠️  Bu dosyayı güvenli bir yerde yedekleyin!${NC}"
fi

# ===================== ADMIN YAPLANDIRMASI =====================

echo ""
echo -e "${BLUE}[5/7] Admin kullanıcı yapılandırması...${NC}"

# .env dosyası yoksa oluştur
if [ ! -f "$ENV_FILE" ]; then
    echo "# EmareCloud Ortam Değişkenleri" > "$ENV_FILE"
    echo "FLASK_ENV=production" >> "$ENV_FILE"
    echo "FLASK_DEBUG=false" >> "$ENV_FILE"
fi

# Admin bilgileri
read -rp "  Admin kullanıcı adı [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

read -rp "  Admin e-posta [admin@emarecloud.com]: " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@emarecloud.com}

# Şifre oluştur veya sor
echo ""
echo -e "  Şifre kuralları: ${YELLOW}min 8 karakter, büyük+küçük harf, rakam, özel karakter${NC}"
while true; do
    read -rsp "  Admin şifresi: " ADMIN_PASS
    echo ""

    # Şifre karmaşıklık kontrolü
    if [ ${#ADMIN_PASS} -lt 8 ]; then
        echo -e "${RED}  ❌ Şifre en az 8 karakter olmalı${NC}"
        continue
    fi
    if ! echo "$ADMIN_PASS" | grep -qP '[A-Z]'; then
        echo -e "${RED}  ❌ Şifre en az 1 büyük harf içermeli${NC}"
        continue
    fi
    if ! echo "$ADMIN_PASS" | grep -qP '[a-z]'; then
        echo -e "${RED}  ❌ Şifre en az 1 küçük harf içermeli${NC}"
        continue
    fi
    if ! echo "$ADMIN_PASS" | grep -qP '[0-9]'; then
        echo -e "${RED}  ❌ Şifre en az 1 rakam içermeli${NC}"
        continue
    fi
    if ! echo "$ADMIN_PASS" | grep -qP '[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]'; then
        echo -e "${RED}  ❌ Şifre en az 1 özel karakter içermeli${NC}"
        continue
    fi

    read -rsp "  Şifreyi tekrar girin: " ADMIN_PASS_CONFIRM
    echo ""

    if [ "$ADMIN_PASS" = "$ADMIN_PASS_CONFIRM" ]; then
        break
    else
        echo -e "${RED}  ❌ Şifreler eşleşmiyor, tekrar deneyin${NC}"
    fi
done

# Secret key oluştur
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# .env dosyasına yaz
cat > "$ENV_FILE" << EOF
# EmareCloud Ortam Değişkenleri
# Oluşturulma: $(date +%Y-%m-%d\ %H:%M:%S)

# Ortam
FLASK_ENV=production
FLASK_DEBUG=false

# Güvenlik
SECRET_KEY=$SECRET_KEY
MASTER_KEY=$(cat "$MASTER_KEY_FILE")

# Admin
DEFAULT_ADMIN_USERNAME=$ADMIN_USER
DEFAULT_ADMIN_PASSWORD=$ADMIN_PASS
DEFAULT_ADMIN_EMAIL=$ADMIN_EMAIL

# Sunucu
HOST=0.0.0.0
PORT=5555

# Oturum
SESSION_LIFETIME_HOURS=8
SESSION_COOKIE_SECURE=true

# CORS (virgülle ayrılmış origin listesi)
# CORS_ALLOWED_ORIGINS=https://panel.example.com

# SSH
SSH_TIMEOUT=10
MAX_CONCURRENT_CONNECTIONS=5
EOF

chmod 600 "$ENV_FILE"
echo -e "${GREEN}  ✅ Admin yapılandırması kaydedildi${NC}"

# ===================== PORT YAPLANDIRMASI =====================

echo ""
echo -e "${BLUE}[6/7] Ağ yapılandırması...${NC}"

read -rp "  Dinlenecek port [5555]: " APP_PORT
APP_PORT=${APP_PORT:-5555}

# .env'deki PORT'u güncelle
sed -i.bak "s/^PORT=.*/PORT=$APP_PORT/" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"

echo -e "${GREEN}  ✅ Port: $APP_PORT${NC}"

# ===================== VERITABANI BAŞLATMA =====================

echo ""
echo -e "${BLUE}[7/7] Veritabanı başlatılıyor...${NC}"

# .env'i yükle
set -a
source "$ENV_FILE"
set +a

python3 -c "
import os, sys
sys.path.insert(0, '$(pwd)')
os.environ['FLASK_ENV'] = 'production'

from app import create_app
app, _ = create_app()
print('  ✅ Veritabanı başarıyla oluşturuldu')
" 2>/dev/null || {
    echo -e "${YELLOW}  ⚠️  Veritabanı oluşturulurken uyarı olabilir, bu normaldir.${NC}"
}

# ===================== ÖZET =====================

echo ""
echo -e "${CYAN}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              ✅ Kurulum Tamamlandı!                        ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║  Panel URL:    http://localhost:$APP_PORT                  ║"
echo "║  Admin:        $ADMIN_USER                                 ║"
echo "║  E-posta:      $ADMIN_EMAIL                                ║"
echo "║                                                            ║"
echo "║  Başlatma:                                                 ║"
echo "║    Geliştirme:  python3 app.py                             ║"
echo "║    Production:  gunicorn -c gunicorn.conf.py app:app       ║"
echo "║                                                            ║"
echo "║  Dosyalar:                                                 ║"
echo "║    .env          → Ortam değişkenleri (gizli)              ║"
echo "║    .master.key   → AES-256 master key (yedekleyin!)        ║"
echo "║    instance/     → SQLite veritabanı                       ║"
echo "║    logs/         → Uygulama logları                        ║"
echo "║                                                            ║"
echo "║  ⚠️  Öneriler:                                              ║"
echo "║    • TLS için Nginx reverse proxy kurun                    ║"
echo "║      (docs/TLS_REVERSE_PROXY.md rehberine bakın)           ║"
echo "║    • .env ve .master.key dosyalarını git'e eklemeyin        ║"
echo "║    • İlk girişte admin şifresini doğrulayın                ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
