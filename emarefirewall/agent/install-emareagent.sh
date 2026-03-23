#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Emare Security OS RMM Agent — Linux / macOS Kurulum Scripti
# ═══════════════════════════════════════════════════════════════════
#  Kullanım:
#    sudo ./install-emareagent.sh --server https://firewall.example.com --action install
#    sudo ./install-emareagent.sh --action uninstall
#    sudo ./install-emareagent.sh --action status
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

AGENT_DIR="/var/lib/emare-agent"
AGENT_SCRIPT="$AGENT_DIR/EmareAgent.sh"
LOG_FILE="/var/log/emare-agent.log"
SERVICE_NAME="emare-agent"
SERVER_URL=""
ACTION=""
TRUST_CERTS=false

# ─── OS TESPİTİ ─────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Linux*)  OS_TYPE="linux" ;;
        Darwin*) OS_TYPE="macos" ;;
        *)       echo "HATA: Desteklenmeyen OS: $(uname -s)"; exit 1 ;;
    esac
}
detect_os

# ─── ROOT KONTROLÜ ──────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "HATA: Bu script root/sudo ile çalıştırılmalıdır."
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════
#  LİNUX — SYSTEMD
# ═══════════════════════════════════════════════════════════

SYSTEMD_UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

install_linux() {
    echo "[*] Linux kurulumu başlıyor..."

    # Dizin ve dosya
    mkdir -p "$AGENT_DIR"
    local script_dir
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    cp "$script_dir/EmareAgent.sh" "$AGENT_SCRIPT"
    chmod 755 "$AGENT_SCRIPT"

    # config.json
    cat > "$AGENT_DIR/config.json" << CONF
{
    "server_url": "$SERVER_URL",
    "heartbeat_sec": 60,
    "task_poll_sec": 30,
    "deep_collect_sec": 300,
    "trust_all_certs": $TRUST_CERTS
}
CONF
    chmod 600 "$AGENT_DIR/config.json"

    # Systemd service
    local trust_flag=""
    [[ "$TRUST_CERTS" == "true" ]] && trust_flag="--trust-all-certs"

    cat > "$SYSTEMD_UNIT" << UNIT
[Unit]
Description=Emare Security OS RMM Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$AGENT_SCRIPT -s $SERVER_URL $trust_flag
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME
User=root
WorkingDirectory=$AGENT_DIR

# Güvenlik kısıtlamaları
ProtectSystem=strict
ReadWritePaths=$AGENT_DIR /var/log
PrivateTmp=true
NoNewPrivileges=false

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"

    echo "[✓] Kurulum tamamlandı!"
    echo "    Servis: systemctl status $SERVICE_NAME"
    echo "    Log:    journalctl -u $SERVICE_NAME -f"
    echo "    Dizin:  $AGENT_DIR"
}

uninstall_linux() {
    echo "[*] Linux kaldırma..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SYSTEMD_UNIT"
    systemctl daemon-reload
    rm -rf "$AGENT_DIR"
    echo "[✓] Agent kaldırıldı."
}

status_linux() {
    systemctl status "$SERVICE_NAME" --no-pager 2>/dev/null || echo "Servis bulunamadı."
}

start_linux()   { systemctl start "$SERVICE_NAME"; echo "[✓] Başlatıldı."; }
stop_linux()    { systemctl stop "$SERVICE_NAME"; echo "[✓] Durduruldu."; }
restart_linux() { systemctl restart "$SERVICE_NAME"; echo "[✓] Yeniden başlatıldı."; }

# ═══════════════════════════════════════════════════════════
#  MACOS — LAUNCHD
# ═══════════════════════════════════════════════════════════

PLIST_FILE="/Library/LaunchDaemons/com.emare.agent.plist"

install_macos() {
    echo "[*] macOS kurulumu başlıyor..."

    # Dizin ve dosya
    mkdir -p "$AGENT_DIR"
    local script_dir
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    cp "$script_dir/EmareAgent.sh" "$AGENT_SCRIPT"
    chmod 755 "$AGENT_SCRIPT"

    # config.json
    cat > "$AGENT_DIR/config.json" << CONF
{
    "server_url": "$SERVER_URL",
    "heartbeat_sec": 60,
    "task_poll_sec": 30,
    "deep_collect_sec": 300,
    "trust_all_certs": $TRUST_CERTS
}
CONF
    chmod 600 "$AGENT_DIR/config.json"

    # LaunchDaemon plist
    local trust_flag=""
    [[ "$TRUST_CERTS" == "true" ]] && trust_flag="--trust-all-certs"

    cat > "$PLIST_FILE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.emare.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$AGENT_SCRIPT</string>
        <string>-s</string>
        <string>$SERVER_URL</string>
PLIST

    if [[ -n "$trust_flag" ]]; then
        cat >> "$PLIST_FILE" << PLIST
        <string>--trust-all-certs</string>
PLIST
    fi

    cat >> "$PLIST_FILE" << PLIST
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/emare-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/emare-agent-error.log</string>
    <key>WorkingDirectory</key>
    <string>$AGENT_DIR</string>
</dict>
</plist>
PLIST

    launchctl load -w "$PLIST_FILE"

    echo "[✓] Kurulum tamamlandı!"
    echo "    Servis: launchctl list | grep emare"
    echo "    Log:    tail -f /var/log/emare-agent.log"
    echo "    Dizin:  $AGENT_DIR"
}

uninstall_macos() {
    echo "[*] macOS kaldırma..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    rm -rf "$AGENT_DIR"
    echo "[✓] Agent kaldırıldı."
}

status_macos() {
    launchctl list 2>/dev/null | grep -i emare || echo "Servis bulunamadı."
    if [[ -f /var/log/emare-agent.log ]]; then
        echo ""
        echo "Son 5 log satırı:"
        tail -5 /var/log/emare-agent.log
    fi
}

start_macos()   { launchctl load -w "$PLIST_FILE" 2>/dev/null; echo "[✓] Başlatıldı."; }
stop_macos()    { launchctl unload "$PLIST_FILE" 2>/dev/null; echo "[✓] Durduruldu."; }
restart_macos() { stop_macos; sleep 1; start_macos; echo "[✓] Yeniden başlatıldı."; }

# ═══════════════════════════════════════════════════════════
#  ANA — ARGÜMAN PARSE
# ═══════════════════════════════════════════════════════════

show_help() {
    cat << 'EOF'
Emare Security OS RMM Agent Installer — Linux / macOS

Kullanım:
  sudo ./install-emareagent.sh --server URL --action install
  sudo ./install-emareagent.sh --action uninstall
  sudo ./install-emareagent.sh --action status|start|stop|restart

Parametreler:
  --server URL           Sunucu adresi (install için zorunlu)
  --action ACTION        install|uninstall|status|start|stop|restart
  --trust-all-certs      Self-signed sertifika kabul et
  -h, --help             Bu yardım mesajı

Örnekler:
  sudo ./install-emareagent.sh --server https://fw.example.com --action install
  sudo ./install-emareagent.sh --action status
  sudo ./install-emareagent.sh --action restart
  sudo ./install-emareagent.sh --action uninstall
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server)          SERVER_URL="$2"; shift 2 ;;
        --action)          ACTION="$2"; shift 2 ;;
        --trust-all-certs) TRUST_CERTS=true; shift ;;
        -h|--help)         show_help; exit 0 ;;
        *)                 echo "Bilinmeyen parametre: $1"; show_help; exit 1 ;;
    esac
done

if [[ -z "$ACTION" ]]; then
    echo "HATA: --action parametresi zorunlu"
    show_help
    exit 1
fi

check_root

case "$ACTION" in
    install)
        if [[ -z "$SERVER_URL" ]]; then
            echo "HATA: --server parametresi zorunlu (install için)"
            exit 1
        fi
        if [[ "$OS_TYPE" == "linux" ]]; then install_linux; else install_macos; fi
        ;;
    uninstall)
        if [[ "$OS_TYPE" == "linux" ]]; then uninstall_linux; else uninstall_macos; fi
        ;;
    status)
        if [[ "$OS_TYPE" == "linux" ]]; then status_linux; else status_macos; fi
        ;;
    start)
        if [[ "$OS_TYPE" == "linux" ]]; then start_linux; else start_macos; fi
        ;;
    stop)
        if [[ "$OS_TYPE" == "linux" ]]; then stop_linux; else stop_macos; fi
        ;;
    restart)
        if [[ "$OS_TYPE" == "linux" ]]; then restart_linux; else restart_macos; fi
        ;;
    *)
        echo "HATA: Bilinmeyen action: $ACTION"
        echo "Geçerli: install|uninstall|status|start|stop|restart"
        exit 1
        ;;
esac
