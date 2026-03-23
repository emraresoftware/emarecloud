#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Emare Security OS RMM Agent — macOS / Linux Tıkla-Çalıştır Kurulum
# ═══════════════════════════════════════════════════════════════════
#  Finder'da çift tıklayarak veya terminalde çalıştırın.
#  Sunucu adresini sorar, agent'ı kurar ve başlatır.
# ═══════════════════════════════════════════════════════════════════

# Script'in bulunduğu dizine geç
cd "$(dirname "$0")" || exit 1

clear
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║                                                  ║"
echo "║   Emare Security OS RMM Agent Kurulumu               ║"
echo "║   macOS / Linux — Tıkla Çalıştır                 ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ─── GEREKSİNİM KONTROLÜ ───────────────────────────────
if [[ ! -f "EmareAgent.sh" ]]; then
    echo "HATA: EmareAgent.sh bu klasörde bulunamadı!"
    echo "      Kur-EmareAgent.command ve EmareAgent.sh aynı klasörde olmalı."
    echo ""
    echo "Kapatmak için bir tuşa basın..."
    read -n 1 -s
    exit 1
fi

if [[ ! -f "install-emareagent.sh" ]]; then
    echo "HATA: install-emareagent.sh bu klasörde bulunamadı!"
    echo ""
    echo "Kapatmak için bir tuşa basın..."
    read -n 1 -s
    exit 1
fi

# ─── SUNUCU ADRESİ ──────────────────────────────────────
echo "Emare Security OS sunucu adresini girin."
echo "Örnek: https://firewall.example.com"
echo ""
while true; do
    printf "Sunucu adresi: "
    read -r SERVER_URL
    # Boş kontrol
    if [[ -z "$SERVER_URL" ]]; then
        echo "  ⚠  Sunucu adresi boş olamaz."
        continue
    fi
    # http/https kontrol
    if [[ ! "$SERVER_URL" =~ ^https?:// ]]; then
        echo "  ⚠  Adres http:// veya https:// ile başlamalı."
        continue
    fi
    break
done

echo ""

# ─── SELF-SIGNED SERTİFİKA ─────────────────────────────
TRUST_FLAG=""
echo "Self-signed (kendinden imzalı) sertifika kullanılıyor mu?"
printf "(e/H): "
read -r TRUST_ANSWER
if [[ "$TRUST_ANSWER" =~ ^[eEyY]$ ]]; then
    TRUST_FLAG="--trust-all-certs"
    echo "  ✓ Self-signed sertifika kabul edilecek."
fi

echo ""

# ─── İŞLEM SEÇİMİ ──────────────────────────────────────
echo "Ne yapmak istiyorsunuz?"
echo ""
echo "  1) Kur ve başlat  (yeni kurulum)"
echo "  2) Kaldır"
echo "  3) Durum kontrol"
echo "  4) Yeniden başlat"
echo "  5) Çıkış"
echo ""
printf "Seçiminiz [1-5]: "
read -r CHOICE

case "$CHOICE" in
    1) ACTION="install" ;;
    2) ACTION="uninstall" ;;
    3) ACTION="status" ;;
    4) ACTION="restart" ;;
    5) echo "Çıkılıyor..."; exit 0 ;;
    *) echo "Geçersiz seçim."; exit 1 ;;
esac

echo ""
echo "────────────────────────────────────────────────────"

# ─── ROOT YETKİSİ İLE ÇALIŞTIR ─────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "Yönetici yetkisi gerekiyor. Parolanız sorulacak."
    echo ""
    if [[ "$ACTION" == "install" ]]; then
        sudo bash install-emareagent.sh --server "$SERVER_URL" --action "$ACTION" $TRUST_FLAG
    else
        sudo bash install-emareagent.sh --server "${SERVER_URL:-http://localhost}" --action "$ACTION"
    fi
else
    if [[ "$ACTION" == "install" ]]; then
        bash install-emareagent.sh --server "$SERVER_URL" --action "$ACTION" $TRUST_FLAG
    else
        bash install-emareagent.sh --server "${SERVER_URL:-http://localhost}" --action "$ACTION"
    fi
fi

EXIT_CODE=$?
echo ""
echo "────────────────────────────────────────────────────"

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "İşlem başarıyla tamamlandı!"
else
    echo "İşlem sırasında hata oluştu. (Kod: $EXIT_CODE)"
fi

echo ""
echo "Bu pencereyi kapatabilirsiniz."
echo "Kapatmak için bir tuşa basın..."
read -n 1 -s
