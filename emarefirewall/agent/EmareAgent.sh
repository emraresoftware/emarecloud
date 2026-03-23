#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Emare Security OS RMM Agent — Linux / macOS Deep Monitoring Agent
# ═══════════════════════════════════════════════════════════════════
#  Emre — Emare Cloud | Emare Security OS RMM
#  v1.0.0 | 2026-03-23
#
#  18 kategori derin telemetri, 12 görev tipi, auditd/osquery enteg.
#  Tek script hem Linux hem macOS destekler (otomatik OS tespiti).
#
#  Kullanım:
#    ./EmareAgent.sh -s https://firewall.example.com        # Daemon
#    ./EmareAgent.sh --deep-scan                             # Tek seferlik
#    ./EmareAgent.sh -s https://... --register               # Sadece kayıt
# ═══════════════════════════════════════════════════════════════════

set -eo pipefail

# ═══════════════════════════════════════════════════════════
#  YAPILANDIRMA
# ═══════════════════════════════════════════════════════════

AGENT_VERSION="1.0.0"
AGENT_DIR="/var/lib/emare-agent"
# Root değilse dizinleri kullanıcı home'una taşı
if [[ $EUID -ne 0 ]]; then
    AGENT_DIR="$HOME/.emare-agent"
    LOG_FILE="/tmp/emare-agent.log"
else
    LOG_FILE="/var/log/emare-agent.log"
fi
AGENT_KEY_FILE="$AGENT_DIR/agent.key"
CONFIG_FILE="$AGENT_DIR/config.json"
MAX_LOG_SIZE_KB=10240       # 10 MB
SERVER_URL=""
HEARTBEAT_SEC=60
TASK_POLL_SEC=30
DEEP_COLLECT_SEC=300        # 5 dk
TRUST_ALL_CERTS=false

# ═══════════════════════════════════════════════════════════
#  OS TESPİTİ
# ═══════════════════════════════════════════════════════════

detect_os() {
    local uname_s
    uname_s="$(uname -s)"
    case "$uname_s" in
        Linux*)  OS_TYPE="linux" ;;
        Darwin*) OS_TYPE="macos" ;;
        *)       OS_TYPE="unknown" ;;
    esac
    OS_ARCH="$(uname -m)"
    OS_KERNEL="$(uname -r)"
}
detect_os

# ═══════════════════════════════════════════════════════════
#  TIMEOUT YARDIMCISI (macOS'ta timeout komutu olmayabilir)
# ═══════════════════════════════════════════════════════════

run_with_timeout() {
    # Usage: result=$(run_with_timeout SECS command arg1 arg2 ...)
    # Pipe-safe: captures stdout, kills if exceeds SECS seconds
    local secs="$1"; shift
    if command -v gtimeout &>/dev/null; then
        gtimeout "$secs" "$@" 2>/dev/null || true
    elif command -v timeout &>/dev/null; then
        timeout "$secs" "$@" 2>/dev/null || true
    else
        # macOS fallback: temp file + background + kill
        local tmpf
        tmpf=$(mktemp /tmp/emare_to.XXXXXX)
        "$@" > "$tmpf" 2>/dev/null &
        local pid=$!
        ( sleep "$secs" && kill "$pid" 2>/dev/null ) &
        local watchdog=$!
        wait "$pid" 2>/dev/null || true
        kill "$watchdog" 2>/dev/null || true
        wait "$watchdog" 2>/dev/null || true
        cat "$tmpf"
        rm -f "$tmpf"
    fi
}

# ═══════════════════════════════════════════════════════════
#  LOG SİSTEMİ
# ═══════════════════════════════════════════════════════════

log_msg() {
    local level="${2:-INFO}"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    local line="[$ts] [$level] $1"
    mkdir -p "$(dirname "$LOG_FILE")"
    # Log rotasyonu
    if [[ -f "$LOG_FILE" ]]; then
        local size_kb
        if [[ "$OS_TYPE" == "macos" ]]; then
            size_kb=$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
        else
            size_kb=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
        fi
        size_kb=$((size_kb / 1024))
        if [[ $size_kb -gt $MAX_LOG_SIZE_KB ]]; then
            mv "$LOG_FILE" "${LOG_FILE%.log}_$(date '+%Y%m%d_%H%M%S').log"
        fi
    fi
    echo "$line" >> "$LOG_FILE"
    # Tüm log çıktısı stderr'e — stdout collector JSON verisi için ayrılmış
    if [[ "$level" == "ERROR" ]]; then
        echo -e "\033[31m$line\033[0m" >&2
    elif [[ "$level" == "WARN" ]]; then
        echo -e "\033[33m$line\033[0m" >&2
    else
        echo "$line" >&2
    fi
}

# ═══════════════════════════════════════════════════════════
#  JSON YARDIMCILARI
# ═══════════════════════════════════════════════════════════

# JSON string escape
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# Anahtar-değer çiftinden JSON nesnesi oluştur
# Kullanım: json_obj "key1" "val1" "key2" 42 ...
# Sayısal değerler _NUM_ prefix'i ile geçilir
json_obj() {
    local result="{"
    local first=true
    while [[ $# -ge 2 ]]; do
        local key="$1"; shift
        local val="$1"; shift
        if [[ "$first" == "true" ]]; then first=false; else result+=","; fi
        if [[ "$val" == _NUM_* ]]; then
            result+="\"$key\":${val#_NUM_}"
        elif [[ "$val" == _BOOL_* ]]; then
            result+="\"$key\":${val#_BOOL_}"
        elif [[ "$val" == _RAW_* ]]; then
            result+="\"$key\":${val#_RAW_}"
        elif [[ "$val" == _NULL_ ]]; then
            result+="\"$key\":null"
        else
            result+="\"$key\":\"$(json_escape "$val")\""
        fi
    done
    result+="}"
    printf '%s' "$result"
}

# JSON dizisi oluştur (her eleman RAW JSON string)
json_arr() {
    local result="["
    local first=true
    for item in "$@"; do
        if [[ "$first" == "true" ]]; then first=false; else result+=","; fi
        result+="$item"
    done
    result+="]"
    printf '%s' "$result"
}

# ═══════════════════════════════════════════════════════════
#  HTTP İSTEK
# ═══════════════════════════════════════════════════════════

AGENT_KEY=""

load_agent_key() {
    if [[ -f "$AGENT_KEY_FILE" ]]; then
        AGENT_KEY="$(cat "$AGENT_KEY_FILE")"
        return 0
    fi
    return 1
}

invoke_api() {
    local endpoint="$1"
    local method="${2:-GET}"
    local body="${3:-}"

    local url="${SERVER_URL}/api/rmm/${endpoint}"
    local curl_opts=(-s -S --max-time 30 -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest")

    if [[ -n "$AGENT_KEY" ]]; then
        curl_opts+=(-H "X-Agent-Key: $AGENT_KEY")
    fi

    if [[ "$TRUST_ALL_CERTS" == "true" ]]; then
        curl_opts+=(-k)
    fi

    if [[ "$method" == "POST" ]]; then
        curl_opts+=(-X POST -d "$body")
    fi

    local response
    if response=$(curl "${curl_opts[@]}" "$url" 2>/dev/null); then
        printf '%s' "$response"
    else
        log_msg "HTTP hata [$method $endpoint]: curl çıkış kodu $?" "ERROR"
        return 1
    fi
}

# Basit JSON alanı okuyucu (jq yoksa)
json_val() {
    local json="$1" key="$2"
    # Basit regex ile değer çıkar (iç içe JSON desteklemez)
    if command -v python3 &>/dev/null; then
        python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('$key',''))" <<< "$json" 2>/dev/null
    elif command -v jq &>/dev/null; then
        jq -r ".$key // empty" <<< "$json" 2>/dev/null
    else
        # Fallback: basit sed
        echo "$json" | sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^,\"}]*\).*/\1/p" | head -1
    fi
}

# ═══════════════════════════════════════════════════════════
#  KAYIT (REGISTRATION)
# ═══════════════════════════════════════════════════════════

register_agent() {
    log_msg "Sunucuya kayit baslatiliyor..."

    local hostname os_version ip_addr
    hostname="$(hostname -s 2>/dev/null || hostname)"

    if [[ "$OS_TYPE" == "linux" ]]; then
        os_version="$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -sr)"
        ip_addr="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || hostname -I 2>/dev/null | awk '{print $1}')"
    else
        os_version="$(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"
        ip_addr="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '0.0.0.0')"
    fi

    local body
    body=$(json_obj \
        "hostname" "$hostname" \
        "os_type" "$OS_TYPE" \
        "os_version" "$os_version" \
        "ip_address" "$ip_addr" \
        "agent_version" "$AGENT_VERSION")

    local resp
    if resp=$(invoke_api "agent/register" "POST" "$body"); then
        local key
        key=$(json_val "$resp" "agent_key")
        if [[ -n "$key" && "$key" != "null" ]]; then
            mkdir -p "$AGENT_DIR"
            echo "$key" > "$AGENT_KEY_FILE"
            chmod 600 "$AGENT_KEY_FILE"
            AGENT_KEY="$key"
            log_msg "Kayit basarili — key: ${key:0:12}..."
            return 0
        fi
    fi
    log_msg "Kayit basarisiz!" "ERROR"
    return 1
}

# ═══════════════════════════════════════════════════════════
#  CPU METRİKLERİ
# ═══════════════════════════════════════════════════════════

collect_cpu() {
    local usage=0 cores=0 threads=0 model="" arch="" freq_mhz=0 load1=0 load5=0 load15=0

    if [[ "$OS_TYPE" == "linux" ]]; then
        # CPU kullanım (2 ölçüm arası fark)
        local cpu1 cpu2
        cpu1=$(awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat)
        sleep 1
        cpu2=$(awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat)
        local total1 idle1 total2 idle2
        total1=$(echo "$cpu1" | awk '{print $1}')
        idle1=$(echo "$cpu1" | awk '{print $2}')
        total2=$(echo "$cpu2" | awk '{print $1}')
        idle2=$(echo "$cpu2" | awk '{print $2}')
        local dt=$((total2 - total1))
        local di=$((idle2 - idle1))
        if [[ $dt -gt 0 ]]; then
            usage=$(( (dt - di) * 100 / dt ))
        fi

        cores=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo 1)
        threads=$cores
        model=$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs)
        freq_mhz=$(awk '/cpu MHz/ {printf "%.0f", $4; exit}' /proc/cpuinfo 2>/dev/null || echo 0)
        arch="$OS_ARCH"

        # Physical cores vs logical
        local phys
        phys=$(grep 'core id' /proc/cpuinfo 2>/dev/null | sort -u | wc -l)
        if [[ $phys -gt 0 ]]; then
            threads=$cores
            cores=$phys
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        usage=$(ps -A -o %cpu= 2>/dev/null | awk '{s+=$1} END {printf "%.0f", s/NR}' || echo 0)
        cores=$(sysctl -n hw.physicalcpu 2>/dev/null || echo 1)
        threads=$(sysctl -n hw.logicalcpu 2>/dev/null || echo 1)
        model=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")
        freq_mhz=$(( $(sysctl -n hw.cpufrequency 2>/dev/null || echo 0) / 1000000 ))
        arch="$OS_ARCH"
    fi

    # Load average
    if [[ -f /proc/loadavg ]]; then
        read -r load1 load5 load15 _ < /proc/loadavg
    else
        local la
        la=$(sysctl -n vm.loadavg 2>/dev/null || uptime | grep -oE 'load average[s]?: [0-9.]+ [0-9.]+ [0-9.]+' | grep -oE '[0-9.]+')
        load1=$(echo "$la" | head -1 | tr -d '{}' | awk '{print $1}')
        load5=$(echo "$la" | head -1 | tr -d '{}' | awk '{print $2}')
        load15=$(echo "$la" | head -1 | tr -d '{}' | awk '{print $3}')
    fi
    load1="${load1:-0}"; load5="${load5:-0}"; load15="${load15:-0}"

    json_obj \
        "usage_percent" "_NUM_$usage" \
        "name" "$model" \
        "cores" "_NUM_$cores" \
        "threads" "_NUM_$threads" \
        "arch" "$arch" \
        "frequency_mhz" "_NUM_$freq_mhz" \
        "load_1m" "_NUM_$load1" \
        "load_5m" "_NUM_$load5" \
        "load_15m" "_NUM_$load15"
}

# ═══════════════════════════════════════════════════════════
#  BELLEK METRİKLERİ
# ═══════════════════════════════════════════════════════════

collect_memory() {
    local total_mb=0 used_mb=0 free_mb=0 available_mb=0 usage=0 swap_total=0 swap_used=0 buffers=0 cached=0

    if [[ "$OS_TYPE" == "linux" ]]; then
        while IFS=: read -r key val; do
            val=$(echo "$val" | awk '{print $1}')  # kB değeri
            case "$key" in
                MemTotal)     total_mb=$((val / 1024)) ;;
                MemFree)      free_mb=$((val / 1024)) ;;
                MemAvailable) available_mb=$((val / 1024)) ;;
                Buffers)      buffers=$((val / 1024)) ;;
                Cached)       cached=$((val / 1024)) ;;
                SwapTotal)    swap_total=$((val / 1024)) ;;
                SwapFree)     swap_used=$((val / 1024)) ;;  # geçici
            esac
        done < /proc/meminfo
        swap_used=$((swap_total - swap_used))
        used_mb=$((total_mb - available_mb))
        if [[ $total_mb -gt 0 ]]; then
            usage=$((used_mb * 100 / total_mb))
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        local page_size
        page_size=$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)
        total_mb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1048576 ))

        local vm_stat_out
        vm_stat_out=$(vm_stat 2>/dev/null)
        local pages_free pages_active pages_inactive pages_speculative pages_wired
        pages_free=$(echo "$vm_stat_out" | awk '/Pages free/ {gsub(/\./,"",$3); print $3}')
        pages_active=$(echo "$vm_stat_out" | awk '/Pages active/ {gsub(/\./,"",$3); print $3}')
        pages_inactive=$(echo "$vm_stat_out" | awk '/Pages inactive/ {gsub(/\./,"",$3); print $3}')
        pages_speculative=$(echo "$vm_stat_out" | awk '/Pages speculative/ {gsub(/\./,"",$3); print $3}')
        pages_wired=$(echo "$vm_stat_out" | awk '/Pages wired/ {gsub(/\./,"",$4); print $4}')

        pages_free=${pages_free:-0}; pages_active=${pages_active:-0}
        pages_inactive=${pages_inactive:-0}; pages_speculative=${pages_speculative:-0}
        pages_wired=${pages_wired:-0}

        free_mb=$(( (pages_free + pages_speculative) * page_size / 1048576 ))
        used_mb=$(( (pages_active + pages_wired) * page_size / 1048576 ))
        available_mb=$((total_mb - used_mb))

        if [[ $total_mb -gt 0 ]]; then
            usage=$((used_mb * 100 / total_mb))
        fi

        # Swap
        local swap_info
        swap_info=$(sysctl vm.swapusage 2>/dev/null)
        swap_total=$(echo "$swap_info" | grep -oE 'total = [0-9.]+M' | grep -oE '[0-9.]+' | head -1)
        swap_used=$(echo "$swap_info" | grep -oE 'used = [0-9.]+M' | grep -oE '[0-9.]+' | head -1)
        swap_total="${swap_total:-0}"; swap_used="${swap_used:-0}"
    fi

    local total_gb used_gb free_gb
    total_gb=$(awk "BEGIN {printf \"%.2f\", $total_mb/1024}")
    used_gb=$(awk "BEGIN {printf \"%.2f\", $used_mb/1024}")
    free_gb=$(awk "BEGIN {printf \"%.2f\", ${available_mb:-$free_mb}/1024}")

    json_obj \
        "usage_percent" "_NUM_$usage" \
        "total_gb" "_NUM_$total_gb" \
        "used_gb" "_NUM_$used_gb" \
        "free_gb" "_NUM_$free_gb" \
        "buffers_mb" "_NUM_${buffers:-0}" \
        "cached_mb" "_NUM_${cached:-0}" \
        "swap_total_mb" "_NUM_${swap_total%%.*}" \
        "swap_used_mb" "_NUM_${swap_used%%.*}"
}

# ═══════════════════════════════════════════════════════════
#  DİSK METRİKLERİ
# ═══════════════════════════════════════════════════════════

collect_disks() {
    local volumes=()
    local overall_pct=0 vol_count=0

    while IFS= read -r line; do
        local fs mount total used avail pct
        fs=$(echo "$line" | awk '{print $1}')
        mount=$(echo "$line" | awk '{print $6}')
        total=$(echo "$line" | awk '{print $2}')
        used=$(echo "$line" | awk '{print $3}')
        avail=$(echo "$line" | awk '{print $4}')
        pct=$(echo "$line" | awk '{gsub(/%/,""); print $5}')

        # MB cinsinden
        local total_gb used_gb free_gb
        total_gb=$(awk "BEGIN {printf \"%.2f\", $total/1048576}")
        used_gb=$(awk "BEGIN {printf \"%.2f\", $used/1048576}")
        free_gb=$(awk "BEGIN {printf \"%.2f\", $avail/1048576}")

        # Dosya sistemi tipi
        local fstype=""
        if [[ "$OS_TYPE" == "linux" ]]; then
            fstype=$(findmnt -n -o FSTYPE "$mount" 2>/dev/null || echo "unknown")
        elif [[ "$OS_TYPE" == "macos" ]]; then
            fstype=$(mount | grep " on $mount " | grep -oE 'type [a-z0-9_]+' | awk '{print $2}' || echo "apfs")
        fi

        local vol_json
        vol_json=$(json_obj \
            "mount" "$mount" \
            "device" "$fs" \
            "total_gb" "_NUM_$total_gb" \
            "used_gb" "_NUM_$used_gb" \
            "free_gb" "_NUM_$free_gb" \
            "percent" "_NUM_${pct:-0}" \
            "fs_type" "$fstype")
        volumes+=("$vol_json")

        if [[ "$mount" == "/" ]]; then
            overall_pct=${pct:-0}
        fi
        vol_count=$((vol_count + 1))
    done < <(df -Pk 2>/dev/null | awk 'NR>1 && $1 !~ /^(tmpfs|devtmpfs|overlay|shm)/ && $6 !~ /^\/snap/')

    if [[ $overall_pct -eq 0 && $vol_count -gt 0 ]]; then
        overall_pct=$(df -Pk / 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
    fi

    # Disk I/O
    local io_json="{}"
    if [[ "$OS_TYPE" == "linux" ]]; then
        if command -v iostat &>/dev/null; then
            local iostat_line
            iostat_line=$(iostat -d -k 1 2 2>/dev/null | awk '/^[sv]d|^nvme/ {last=$0} END {print last}')
            if [[ -n "$iostat_line" ]]; then
                local dev tps read_kps write_kps
                dev=$(echo "$iostat_line" | awk '{print $1}')
                tps=$(echo "$iostat_line" | awk '{printf "%.1f", $2}')
                read_kps=$(echo "$iostat_line" | awk '{printf "%.1f", $3}')
                write_kps=$(echo "$iostat_line" | awk '{printf "%.1f", $4}')
                io_json=$(json_obj \
                    "device" "$dev" \
                    "tps" "_NUM_$tps" \
                    "read_kb_sec" "_NUM_$read_kps" \
                    "write_kb_sec" "_NUM_$write_kps")
            fi
        fi
    elif [[ "$OS_TYPE" == "macos" ]]; then
        if command -v iostat &>/dev/null; then
            local io_line
            io_line=$(iostat -d -c 2 -w 1 2>/dev/null | tail -1)
            if [[ -n "$io_line" ]]; then
                local tps read_kps write_kps
                tps=$(echo "$io_line" | awk '{printf "%.1f", $1}')
                read_kps=$(echo "$io_line" | awk '{printf "%.1f", $2}')
                write_kps=$(echo "$io_line" | awk '{printf "%.1f", $3}')
                io_json=$(json_obj \
                    "tps" "_NUM_${tps:-0}" \
                    "read_kb_sec" "_NUM_${read_kps:-0}" \
                    "write_kb_sec" "_NUM_${write_kps:-0}")
            fi
        fi
    fi

    local vol_arr
    vol_arr=$(json_arr "${volumes[@]}")

    printf '{"usage_percent":%s,"volumes":%s,"io":%s}' \
        "${overall_pct:-0}" "$vol_arr" "$io_json"
}

# ═══════════════════════════════════════════════════════════
#  AĞ METRİKLERİ
# ═══════════════════════════════════════════════════════════

collect_network() {
    local interfaces=() total_rx=0 total_tx=0

    if [[ "$OS_TYPE" == "linux" ]]; then
        while IFS=: read -r iface rest; do
            iface=$(echo "$iface" | xargs)
            [[ "$iface" == "lo" ]] && continue
            local rx tx
            rx=$(echo "$rest" | awk '{print $1}')
            tx=$(echo "$rest" | awk '{print $9}')
            total_rx=$((total_rx + rx))
            total_tx=$((total_tx + tx))

            local ip_addr mac speed status
            ip_addr=$(ip -4 addr show "$iface" 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)
            mac=$(ip link show "$iface" 2>/dev/null | awk '/link\/ether/ {print $2}')
            speed=$(cat "/sys/class/net/$iface/speed" 2>/dev/null || echo "0")
            status=$(cat "/sys/class/net/$iface/operstate" 2>/dev/null || echo "unknown")

            local if_json
            if_json=$(json_obj \
                "name" "$iface" \
                "mac" "${mac:-unknown}" \
                "speed_mbps" "_NUM_${speed:-0}" \
                "ip_address" "${ip_addr:-}" \
                "rx_bytes" "_NUM_$rx" \
                "tx_bytes" "_NUM_$tx" \
                "status" "$status")
            interfaces+=("$if_json")
        done < <(grep ':' /proc/net/dev | tail -n +1)

    elif [[ "$OS_TYPE" == "macos" ]]; then
        local ifaces
        ifaces=$(ifconfig -l 2>/dev/null)
        for iface in $ifaces; do
            [[ "$iface" == "lo0" ]] && continue
            [[ "$iface" == gif* || "$iface" == stf* || "$iface" == utun* || "$iface" == awdl* ]] && continue

            local status ip_addr mac
            status=$(ifconfig "$iface" 2>/dev/null | grep -q 'status: active' && echo "up" || echo "down")
            ip_addr=$(ifconfig "$iface" 2>/dev/null | awk '/inet / {print $2}' | head -1)
            mac=$(ifconfig "$iface" 2>/dev/null | awk '/ether/ {print $2}')

            [[ -z "$ip_addr" && "$status" == "down" ]] && continue

            local rx tx
            rx=$(netstat -I "$iface" -b 2>/dev/null | awk 'NR==2 {print $7}')
            tx=$(netstat -I "$iface" -b 2>/dev/null | awk 'NR==2 {print $10}')
            rx=${rx:-0}; tx=${tx:-0}
            total_rx=$((total_rx + rx))
            total_tx=$((total_tx + tx))

            local if_json
            if_json=$(json_obj \
                "name" "$iface" \
                "mac" "${mac:-unknown}" \
                "ip_address" "${ip_addr:-}" \
                "rx_bytes" "_NUM_$rx" \
                "tx_bytes" "_NUM_$tx" \
                "status" "$status")
            interfaces+=("$if_json")
        done
    fi

    # DNS sunucuları
    local dns_arr="[]"
    if [[ -f /etc/resolv.conf ]]; then
        local dns_items=()
        while read -r ns; do
            dns_items+=("\"$ns\"")
        done < <(awk '/^nameserver/ {print $2}' /etc/resolv.conf | head -4)
        dns_arr=$(json_arr "${dns_items[@]}")
    elif [[ "$OS_TYPE" == "macos" ]]; then
        local dns_items=()
        while read -r ns; do
            dns_items+=("\"$ns\"")
        done < <(scutil --dns 2>/dev/null | awk '/nameserver\[/ {print $3}' | sort -u | head -4)
        dns_arr=$(json_arr "${dns_items[@]}")
    fi

    # TCP bağlantı durumu
    local total=0 established=0 listen=0 time_wait=0 close_wait=0
    if [[ "$OS_TYPE" == "linux" ]] && command -v ss &>/dev/null; then
        total=$(ss -t 2>/dev/null | tail -n +2 | wc -l)
        established=$(ss -t state established 2>/dev/null | tail -n +2 | wc -l)
        listen=$(ss -tl 2>/dev/null | tail -n +2 | wc -l)
        time_wait=$(ss -t state time-wait 2>/dev/null | tail -n +2 | wc -l)
        close_wait=$(ss -t state close-wait 2>/dev/null | tail -n +2 | wc -l)
    else
        total=$(netstat -an 2>/dev/null | grep -c 'tcp' || true)
        established=$(netstat -an 2>/dev/null | grep -c 'ESTABLISHED' || true)
        listen=$(netstat -an 2>/dev/null | grep -c 'LISTEN' || true)
        time_wait=$(netstat -an 2>/dev/null | grep -c 'TIME_WAIT' || true)
        close_wait=$(netstat -an 2>/dev/null | grep -c 'CLOSE_WAIT' || true)
    fi

    local iface_arr conn_json
    iface_arr=$(json_arr "${interfaces[@]}")
    conn_json=$(json_obj \
        "total" "_NUM_$total" \
        "established" "_NUM_$established" \
        "listen" "_NUM_$listen" \
        "time_wait" "_NUM_$time_wait" \
        "close_wait" "_NUM_$close_wait")

    printf '{"total_rx_bytes":%s,"total_tx_bytes":%s,"interfaces":%s,"dns_servers":%s,"connections":%s}' \
        "$total_rx" "$total_tx" "$iface_arr" "$dns_arr" "$conn_json"
}

# ═══════════════════════════════════════════════════════════
#  GPU METRİKLERİ
# ═══════════════════════════════════════════════════════════

collect_gpu() {
    local gpus=()

    # NVIDIA (Linux + macOS)
    if command -v nvidia-smi &>/dev/null; then
        while IFS=, read -r name temp usage mem_usage mem_total mem_used mem_free fan power; do
            name=$(echo "$name" | xargs)
            local gpu_json
            gpu_json=$(json_obj \
                "name" "$name" \
                "vendor" "NVIDIA" \
                "temp_c" "_NUM_${temp// /}" \
                "gpu_usage" "_NUM_${usage// /}" \
                "mem_usage" "_NUM_${mem_usage// /}" \
                "mem_total_mb" "_NUM_${mem_total// /}" \
                "mem_used_mb" "_NUM_${mem_used// /}" \
                "mem_free_mb" "_NUM_${mem_free// /}" \
                "fan_percent" "_NUM_${fan// /}" \
                "power_watts" "_NUM_${power// /}")
            gpus+=("$gpu_json")
        done < <(nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,fan.speed,power.draw --format=csv,noheader,nounits 2>/dev/null)
    fi

    # Linux: lspci fallback
    if [[ ${#gpus[@]} -eq 0 && "$OS_TYPE" == "linux" ]]; then
        while read -r line; do
            local gpu_json
            gpu_json=$(json_obj "name" "$line" "vendor" "unknown" "source" "lspci")
            gpus+=("$gpu_json")
        done < <(lspci 2>/dev/null | grep -iE 'vga|3d|display' | sed 's/^[^ ]* //')
    fi

    # macOS: system_profiler
    if [[ ${#gpus[@]} -eq 0 && "$OS_TYPE" == "macos" ]]; then
        local gpu_name gpu_vram
        gpu_name=$(system_profiler SPDisplaysDataType 2>/dev/null | awk -F: '/Chipset Model|Chip/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
        gpu_vram=$(system_profiler SPDisplaysDataType 2>/dev/null | awk -F: '/VRAM|Total Number of Cores/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')
        if [[ -n "$gpu_name" ]]; then
            local gpu_json
            gpu_json=$(json_obj "name" "$gpu_name" "vendor" "Apple" "vram" "${gpu_vram:-unknown}")
            gpus+=("$gpu_json")
        fi
    fi

    local arr
    arr=$(json_arr "${gpus[@]}")
    printf '{"gpus":%s}' "$arr"
}

# ═══════════════════════════════════════════════════════════
#  SİSTEM BİLGİSİ
# ═══════════════════════════════════════════════════════════

collect_system_info() {
    local hostname domain os_name os_version os_build manufacturer model serial
    local uptime_sec uptime_text install_date timezone locale last_boot user_count

    hostname="$(hostname -s 2>/dev/null || hostname)"
    domain="$(hostname -d 2>/dev/null || echo 'local')"
    timezone="$(date +%Z 2>/dev/null || echo 'UTC')"
    locale="$(echo "${LANG:-en_US.UTF-8}")"

    if [[ "$OS_TYPE" == "linux" ]]; then
        os_name="$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || echo "Linux")"
        os_version="$(. /etc/os-release 2>/dev/null && echo "$VERSION_ID" || uname -r)"
        os_build="$OS_KERNEL"
        manufacturer="$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null || echo 'unknown')"
        model="$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo 'unknown')"
        serial="$(cat /sys/class/dmi/id/product_serial 2>/dev/null || echo 'unknown')"
        uptime_sec=$(awk '{printf "%.0f", $1}' /proc/uptime 2>/dev/null)
        last_boot="$(who -b 2>/dev/null | awk '{print $3, $4}' || echo 'unknown')"
        install_date="$(stat -c %w / 2>/dev/null | cut -d' ' -f1 || echo 'unknown')"
        user_count=$(awk -F: '$3 >= 1000 && $3 < 65534 {count++} END {print count+0}' /etc/passwd 2>/dev/null)

    elif [[ "$OS_TYPE" == "macos" ]]; then
        os_name="$(sw_vers -productName 2>/dev/null || echo 'macOS')"
        os_version="$(sw_vers -productVersion 2>/dev/null)"
        os_build="$(sw_vers -buildVersion 2>/dev/null)"
        manufacturer="Apple"
        model="$(sysctl -n hw.model 2>/dev/null || echo 'Mac')"
        serial="$(ioreg -l 2>/dev/null | awk -F'"' '/IOPlatformSerialNumber/ {print $4; exit}')"
        uptime_sec=$(sysctl -n kern.boottime 2>/dev/null | awk -F'[= ,]' '{print $6}')
        if [[ -n "$uptime_sec" ]]; then
            uptime_sec=$(( $(date +%s) - uptime_sec ))
        fi
        last_boot="$(sysctl -n kern.boottime 2>/dev/null | grep -oE 'Mon|Tue|Wed|Thu|Fri|Sat|Sun.*202[0-9]' || who -b 2>/dev/null | awk '{print $3, $4}')"
        install_date="unknown"
        user_count=$(dscl . list /Users 2>/dev/null | grep -cvE '^_|daemon|nobody|root' || true)
    fi

    local uptime_hours
    uptime_hours=$(awk "BEGIN {printf \"%.1f\", ${uptime_sec:-0}/3600}")
    local days hours mins
    days=$(( ${uptime_sec:-0} / 86400 ))
    hours=$(( (${uptime_sec:-0} % 86400) / 3600 ))
    mins=$(( (${uptime_sec:-0} % 3600) / 60 ))
    uptime_text="${days}g ${hours}s ${mins}dk"

    json_obj \
        "hostname" "$hostname" \
        "domain" "$domain" \
        "os_name" "$os_name" \
        "os_version" "$os_version" \
        "os_build" "$os_build" \
        "os_arch" "$OS_ARCH" \
        "manufacturer" "$manufacturer" \
        "model" "$model" \
        "serial" "$serial" \
        "uptime_hours" "_NUM_$uptime_hours" \
        "uptime_text" "$uptime_text" \
        "install_date" "$install_date" \
        "timezone" "$timezone" \
        "locale" "$locale" \
        "last_boot" "$last_boot" \
        "user_count" "_NUM_${user_count:-0}"
}

# ═══════════════════════════════════════════════════════════
#  SÜREÇ LİSTESİ
# ═══════════════════════════════════════════════════════════

collect_processes() {
    local procs=()
    local total_count=0

    total_count=$(ps aux 2>/dev/null | tail -n +2 | wc -l)

    while IFS= read -r line; do
        local user pid cpu mem vsz rss start cmd
        user=$(echo "$line" | awk '{print $1}')
        pid=$(echo "$line" | awk '{print $2}')
        cpu=$(echo "$line" | awk '{print $3}')
        mem=$(echo "$line" | awk '{print $4}')
        rss=$(echo "$line" | awk '{print $6}')
        start=$(echo "$line" | awk '{print $9}')
        cmd=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}' | head -c 200)

        local ram_mb
        ram_mb=$(awk "BEGIN {printf \"%.1f\", $rss/1024}")

        local p_json
        p_json=$(json_obj \
            "name" "$(echo "$cmd" | awk '{print $1}' | xargs basename 2>/dev/null || echo "$cmd")" \
            "pid" "_NUM_$pid" \
            "user" "$user" \
            "cpu_pct" "_NUM_$cpu" \
            "ram_mb" "_NUM_$ram_mb" \
            "start_time" "$start" \
            "command" "$cmd")
        procs+=("$p_json")
    done < <(ps aux --sort=-%mem 2>/dev/null | tail -n +2 | head -25 || ps aux 2>/dev/null | sort -k4 -rn | head -25)

    local arr
    arr=$(json_arr "${procs[@]}")
    printf '{"processes":%s,"total_count":%s}' "$arr" "$total_count"
}

# ═══════════════════════════════════════════════════════════
#  SERVİS DURUMU
# ═══════════════════════════════════════════════════════════

collect_services() {
    local services=() running=0 stopped=0 total=0 criticals=()

    if [[ "$OS_TYPE" == "linux" ]]; then
        # systemd
        if command -v systemctl &>/dev/null; then
            while IFS= read -r line; do
                local unit load active sub
                unit=$(echo "$line" | awk '{print $1}')
                load=$(echo "$line" | awk '{print $2}')
                active=$(echo "$line" | awk '{print $3}')
                sub=$(echo "$line" | awk '{print $4}')

                [[ -z "$unit" ]] && continue
                total=$((total + 1))
                [[ "$active" == "active" ]] && running=$((running + 1)) || stopped=$((stopped + 1))

                local svc_json
                svc_json=$(json_obj "name" "$unit" "status" "$active" "sub_state" "$sub" "load" "$load")
                services+=("$svc_json")
            done < <(systemctl list-units --type=service --no-legend --no-pager 2>/dev/null | head -200)

            # Kritik servisler
            local critical_list="sshd nginx apache2 httpd mysql mariadb postgresql docker containerd cron rsyslog auditd firewalld ufw fail2ban"
            for crit in $critical_list; do
                local crit_status
                crit_status=$(systemctl is-active "$crit" 2>/dev/null || echo "not-found")
                if [[ "$crit_status" != "not-found" ]]; then
                    local c_json
                    c_json=$(json_obj "name" "$crit" "status" "$crit_status")
                    criticals+=("$c_json")
                fi
            done
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        # launchctl
        while IFS= read -r line; do
            local pid status label
            pid=$(echo "$line" | awk '{print $1}')
            status=$(echo "$line" | awk '{print $2}')
            label=$(echo "$line" | awk '{print $3}')

            [[ -z "$label" || "$label" == PID || "$label" == com.apple.* ]] && continue
            total=$((total + 1))

            local state="stopped"
            if [[ "$pid" != "-" && "$pid" -gt 0 ]] 2>/dev/null; then
                state="running"
                running=$((running + 1))
            else
                stopped=$((stopped + 1))
            fi

            local svc_json
            svc_json=$(json_obj "name" "$label" "status" "$state" "exit_code" "$status" "pid" "$pid")
            services+=("$svc_json")
        done < <(launchctl list 2>/dev/null | tail -n +2 | head -200)
    fi

    local svc_arr crit_arr
    svc_arr=$(json_arr "${services[@]}")
    crit_arr=$(json_arr "${criticals[@]}")
    printf '{"total":%s,"running":%s,"stopped":%s,"critical":%s,"all_services":%s}' \
        "$total" "$running" "$stopped" "$crit_arr" "$svc_arr"
}

# ═══════════════════════════════════════════════════════════
#  YÜKLÜ YAZILIMLAR
# ═══════════════════════════════════════════════════════════

collect_software() {
    local apps=() count=0

    if [[ "$OS_TYPE" == "linux" ]]; then
        # dpkg (Debian/Ubuntu)
        if command -v dpkg-query &>/dev/null; then
            while IFS=$'\t' read -r name ver desc; do
                local s_json
                s_json=$(json_obj "name" "$name" "version" "$ver" "description" "$desc" "source" "dpkg")
                apps+=("$s_json")
                count=$((count + 1))
            done < <(dpkg-query -W -f='${Package}\t${Version}\t${Description}\n' 2>/dev/null | head -500)
        # rpm (RHEL/CentOS/Fedora)
        elif command -v rpm &>/dev/null; then
            while IFS=$'\t' read -r name ver; do
                local s_json
                s_json=$(json_obj "name" "$name" "version" "$ver" "source" "rpm")
                apps+=("$s_json")
                count=$((count + 1))
            done < <(rpm -qa --queryformat '%{NAME}\t%{VERSION}-%{RELEASE}\n' 2>/dev/null | sort | head -500)
        # pacman (Arch)
        elif command -v pacman &>/dev/null; then
            while IFS=' ' read -r name ver; do
                local s_json
                s_json=$(json_obj "name" "$name" "version" "$ver" "source" "pacman")
                apps+=("$s_json")
                count=$((count + 1))
            done < <(pacman -Q 2>/dev/null | head -500)
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        # Homebrew
        if command -v brew &>/dev/null; then
            while IFS= read -r line; do
                local name ver
                name=$(echo "$line" | awk '{print $1}')
                ver=$(echo "$line" | awk '{print $2}')
                local s_json
                s_json=$(json_obj "name" "$name" "version" "$ver" "source" "brew")
                apps+=("$s_json")
                count=$((count + 1))
            done < <(brew list --versions 2>/dev/null | head -500)
        fi
        # /Applications
        while IFS= read -r app_path; do
            local app_name
            app_name=$(basename "$app_path" .app)
            local ver
            ver=$(defaults read "$app_path/Contents/Info" CFBundleShortVersionString 2>/dev/null || echo "unknown")
            local s_json
            s_json=$(json_obj "name" "$app_name" "version" "$ver" "source" "applications")
            apps+=("$s_json")
            count=$((count + 1))
        done < <(find /Applications -maxdepth 1 -name "*.app" 2>/dev/null | head -100)
    fi

    local arr
    arr=$(json_arr "${apps[@]}")
    printf '{"count":%s,"software":%s}' "$count" "$arr"
}

# ═══════════════════════════════════════════════════════════
#  GÜVENLİK DURUMU
# ═══════════════════════════════════════════════════════════

collect_security() {
    if [[ "$OS_TYPE" == "linux" ]]; then
        collect_security_linux
    else
        collect_security_macos
    fi
}

collect_security_linux() {
    local fw_json="{}" av_json="{}" updates_json="{}"
    local users="[]" shares="[]"
    local sshd_enabled=false rootlogin="unknown" selinux="unknown" apparmor="unknown"

    # Firewall
    if command -v ufw &>/dev/null; then
        local ufw_status
        ufw_status=$(ufw status 2>/dev/null | head -1 | awk '{print $2}')
        fw_json=$(json_obj "type" "ufw" "status" "${ufw_status:-inactive}")
    elif command -v firewall-cmd &>/dev/null; then
        local zone
        zone=$(firewall-cmd --get-default-zone 2>/dev/null || echo "unknown")
        fw_json=$(json_obj "type" "firewalld" "default_zone" "$zone" "status" "$(systemctl is-active firewalld 2>/dev/null)")
    elif command -v iptables &>/dev/null; then
        local rule_count
        rule_count=$(iptables -L -n 2>/dev/null | grep -c '^[A-Z]' || true)
        fw_json=$(json_obj "type" "iptables" "rule_count" "_NUM_$rule_count")
    fi

    # Antivirus
    if command -v clamscan &>/dev/null; then
        local clam_ver
        clam_ver=$(clamscan --version 2>/dev/null | head -1)
        local freshclam_date
        freshclam_date=$(stat -c %y /var/lib/clamav/daily.cvd 2>/dev/null | cut -d' ' -f1 || echo "unknown")
        av_json=$(json_obj "type" "clamav" "version" "$clam_ver" "last_update" "$freshclam_date")
    fi

    # Updates
    if command -v apt &>/dev/null; then
        local upgradable
        upgradable=$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)
        local sec_updates
        sec_updates=$(apt list --upgradable 2>/dev/null | grep -ic 'security' || echo 0)
        updates_json=$(json_obj "pending" "_NUM_$upgradable" "security" "_NUM_$sec_updates" "source" "apt")
    elif command -v yum &>/dev/null; then
        local upgradable
        upgradable=$(yum check-update --quiet 2>/dev/null | grep -c '^[a-z]' || true)
        updates_json=$(json_obj "pending" "_NUM_$upgradable" "source" "yum")
    fi

    # Users
    local user_arr=()
    while IFS=: read -r uname _ uid gid _ home shell; do
        [[ $uid -lt 1000 || $uid -ge 65534 ]] && continue
        local last_login
        last_login=$(lastlog -u "$uname" 2>/dev/null | tail -1 | awk '{print $4, $5, $6, $7, $9}' || echo "unknown")
        local u_json
        u_json=$(json_obj "name" "$uname" "uid" "_NUM_$uid" "home" "$home" "shell" "$shell" "last_login" "$last_login")
        user_arr+=("$u_json")
    done < /etc/passwd 2>/dev/null
    users=$(json_arr "${user_arr[@]}")

    # SSH root login
    if [[ -f /etc/ssh/sshd_config ]]; then
        rootlogin=$(grep -i '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' || echo "unknown")
        sshd_enabled=true
    fi

    # SELinux
    if command -v getenforce &>/dev/null; then
        selinux=$(getenforce 2>/dev/null || echo "unknown")
    fi

    # AppArmor
    if command -v aa-status &>/dev/null; then
        local profiles
        profiles=$(aa-status 2>/dev/null | head -1)
        apparmor="$profiles"
    fi

    # Samba/NFS paylaşımlar
    local share_arr=()
    if [[ -f /etc/samba/smb.conf ]]; then
        while read -r share; do
            local sh_json
            sh_json=$(json_obj "name" "$share" "type" "samba")
            share_arr+=("$sh_json")
        done < <(grep '^\[' /etc/samba/smb.conf 2>/dev/null | tr -d '[]' | grep -v 'global\|homes\|printers')
    fi
    if [[ -f /etc/exports ]]; then
        while read -r export_line; do
            local sh_json
            sh_json=$(json_obj "name" "$export_line" "type" "nfs")
            share_arr+=("$sh_json")
        done < <(grep -v '^#\|^$' /etc/exports 2>/dev/null)
    fi
    shares=$(json_arr "${share_arr[@]}")

    printf '{"firewall":%s,"antivirus":%s,"updates":%s,"users":%s,"shares":%s,"ssh_root_login":"%s","selinux":"%s","apparmor":"%s","sshd_enabled":%s}' \
        "$fw_json" "$av_json" "$updates_json" "$users" "$shares" \
        "$rootlogin" "$selinux" "$apparmor" "_BOOL_$sshd_enabled"
}

collect_security_macos() {
    local fw_json="{}" sip="unknown" gatekeeper="unknown" filevault="unknown" xprotect_ver="unknown"

    # macOS firewall
    local fw_status
    fw_status=$(/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null | grep -ioE 'enabled|disabled' || echo "unknown")
    local fw_stealth
    fw_stealth=$(/usr/libexec/ApplicationFirewall/socketfilterfw --getstealthmode 2>/dev/null | grep -ioE 'enabled|disabled' || echo "unknown")
    fw_json=$(json_obj "type" "pf" "status" "$fw_status" "stealth_mode" "$fw_stealth")

    # SIP
    sip=$(csrutil status 2>/dev/null | grep -ioE 'enabled|disabled' || echo "unknown")

    # Gatekeeper
    gatekeeper=$(spctl --status 2>/dev/null | awk '{print $2}' || echo "unknown")

    # FileVault
    filevault=$(fdesetup status 2>/dev/null | grep -ioE 'On|Off' || echo "unknown")

    # XProtect
    xprotect_ver=$(defaults read /System/Library/CoreServices/XProtect.bundle/Contents/Info CFBundleShortVersionString 2>/dev/null || echo "unknown")

    # Kullanıcılar
    local user_arr=()
    while read -r uname; do
        [[ "$uname" == _* || "$uname" == daemon || "$uname" == nobody || "$uname" == root ]] && continue
        local is_admin
        is_admin=$(dsmemberutil checkmembership -U "$uname" -G admin 2>/dev/null | grep -qc 'is a member' && echo true || echo false)
        local u_json
        u_json=$(json_obj "name" "$uname" "admin" "_BOOL_$is_admin")
        user_arr+=("$u_json")
    done < <(dscl . list /Users 2>/dev/null)
    local users
    users=$(json_arr "${user_arr[@]}")

    printf '{"firewall":%s,"sip":"%s","gatekeeper":"%s","filevault":"%s","xprotect_version":"%s","users":%s}' \
        "$fw_json" "$sip" "$gatekeeper" "$filevault" "$xprotect_ver" "$users"
}

# ═══════════════════════════════════════════════════════════
#  OLAY GÜNLÜKLERİ
# ═══════════════════════════════════════════════════════════

collect_event_logs() {
    local system_json="{}" security_json="{}" application_json="{}"

    if [[ "$OS_TYPE" == "linux" ]]; then
        if command -v journalctl &>/dev/null; then
            # System — son 24 saat hata/uyarı
            local sys_crit sys_err sys_warn
            sys_crit=$(journalctl -p 0..2 --since "24 hours ago" --no-pager -q 2>/dev/null | wc -l)
            sys_err=$(journalctl -p 3 --since "24 hours ago" --no-pager -q 2>/dev/null | wc -l)
            sys_warn=$(journalctl -p 4 --since "24 hours ago" --no-pager -q 2>/dev/null | wc -l)

            local sys_recent=()
            while IFS= read -r line; do
                local ts msg priority
                ts=$(echo "$line" | awk '{print $1, $2, $3}')
                msg=$(echo "$line" | cut -d' ' -f5-)
                local r_json
                r_json=$(json_obj "time" "$ts" "message" "$(echo "$msg" | head -c 200)")
                sys_recent+=("$r_json")
            done < <(journalctl -p 0..3 --since "24 hours ago" --no-pager -q -n 10 2>/dev/null)

            local recent_arr
            recent_arr=$(json_arr "${sys_recent[@]}")
            system_json=$(printf '{"critical":%s,"errors":%s,"warnings":%s,"recent":%s}' \
                "$sys_crit" "$sys_err" "$sys_warn" "$recent_arr")

            # Security — auth log
            local auth_fail auth_success
            auth_fail=$(journalctl -u sshd --since "24 hours ago" --no-pager -q 2>/dev/null | grep -ic 'failed\|invalid\|refused' || echo 0)
            auth_success=$(journalctl -u sshd --since "24 hours ago" --no-pager -q 2>/dev/null | grep -ic 'accepted\|opened' || echo 0)

            local sec_recent=()
            while IFS= read -r line; do
                local r_json
                r_json=$(json_obj "message" "$(echo "$line" | head -c 200)")
                sec_recent+=("$r_json")
            done < <(journalctl -u sshd --since "24 hours ago" --no-pager -q -n 10 2>/dev/null)

            local sec_arr
            sec_arr=$(json_arr "${sec_recent[@]}")
            security_json=$(printf '{"failed_logins":%s,"successful_logins":%s,"recent":%s}' \
                "$auth_fail" "$auth_success" "$sec_arr")

            # Application
            local app_err
            app_err=$(journalctl --user -p 0..3 --since "24 hours ago" --no-pager -q 2>/dev/null | wc -l)
            application_json=$(printf '{"errors":%s}' "$app_err")
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        # macOS log show
        local sys_err sys_fault
        sys_err=$(run_with_timeout 10 log show --predicate 'messageType == error' --last 1h --style syslog | wc -l || true)
        sys_fault=$(run_with_timeout 10 log show --predicate 'messageType == fault' --last 1h --style syslog | head -20 | wc -l || true)

        local sys_recent=()
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            local r_json
            r_json=$(json_obj "message" "$(echo "$line" | head -c 200)")
            sys_recent+=("$r_json")
        done < <(run_with_timeout 10 log show --predicate 'messageType == fault' --last 1h --style syslog | tail -10)

        local recent_arr
        recent_arr=$(json_arr "${sys_recent[@]}")
        system_json=$(printf '{"errors":%s,"faults":%s,"recent":%s}' "$sys_err" "$sys_fault" "$recent_arr")

        # Security — auth
        local auth_fail=0
        auth_fail=$(run_with_timeout 10 log show --predicate 'category == "authorization" AND messageType == error' --last 1h | wc -l || true)
        security_json=$(printf '{"failed_auth":%s}' "$auth_fail")

        application_json='{"errors":0}'
    fi

    printf '{"system":%s,"security":%s,"application":%s}' \
        "$system_json" "$security_json" "$application_json"
}

# ═══════════════════════════════════════════════════════════
#  AÇIK PORTLAR
# ═══════════════════════════════════════════════════════════

collect_open_ports() {
    local ports=() risky_count=0
    local risky_list="21 22 23 25 53 110 135 139 445 1433 1521 3306 3389 5432 5900 6379 8080 9200 27017"

    if [[ "$OS_TYPE" == "linux" ]] && command -v ss &>/dev/null; then
        while IFS= read -r line; do
            local state recv send local_addr peer_addr process
            state=$(echo "$line" | awk '{print $1}')
            local_addr=$(echo "$line" | awk '{print $4}')
            process=$(echo "$line" | awk '{print $6}' | sed -n 's/.*users:(("\([^"]*\).*/\1/p')
            [[ -z "$process" ]] && process="unknown"
            local port
            port=$(echo "$local_addr" | rev | cut -d: -f1 | rev)

            local is_risky=false
            for rp in $risky_list; do
                [[ "$port" == "$rp" ]] && is_risky=true && risky_count=$((risky_count + 1)) && break
            done

            local p_json
            p_json=$(json_obj \
                "port" "_NUM_${port:-0}" \
                "address" "$local_addr" \
                "process" "$process" \
                "risky" "_BOOL_$is_risky")
            ports+=("$p_json")
        done < <(ss -tlnp 2>/dev/null | tail -n +2 | head -100)

    elif [[ "$OS_TYPE" == "macos" ]]; then
        while IFS= read -r line; do
            local process pid addr port
            process=$(echo "$line" | awk '{print $1}')
            pid=$(echo "$line" | awk '{print $2}')
            addr=$(echo "$line" | awk '{print $9}')
            port=$(echo "$addr" | rev | cut -d: -f1 | rev)

            local is_risky=false
            for rp in $risky_list; do
                [[ "$port" == "$rp" ]] && is_risky=true && risky_count=$((risky_count + 1)) && break
            done

            local p_json
            p_json=$(json_obj \
                "port" "_NUM_${port:-0}" \
                "address" "$addr" \
                "process" "$process" \
                "pid" "_NUM_${pid:-0}" \
                "risky" "_BOOL_$is_risky")
            ports+=("$p_json")
        done < <(lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | tail -n +2 | head -100)
    fi

    local arr
    arr=$(json_arr "${ports[@]}")
    printf '{"listeners":%s,"total":%s,"risky_count":%s}' \
        "$arr" "${#ports[@]}" "$risky_count"
}

# ═══════════════════════════════════════════════════════════
#  KULLANICI OTURUMLARI
# ═══════════════════════════════════════════════════════════

collect_sessions() {
    local sessions=()

    while IFS= read -r line; do
        local user tty from login_time idle
        user=$(echo "$line" | awk '{print $1}')
        tty=$(echo "$line" | awk '{print $2}')
        from=$(echo "$line" | awk '{print $3}')
        login_time=$(echo "$line" | awk '{print $4, $5}')
        idle=$(echo "$line" | awk '{print $6}')

        local s_json
        s_json=$(json_obj \
            "username" "$user" \
            "tty" "$tty" \
            "from" "$from" \
            "login_time" "$login_time" \
            "idle" "${idle:-active}")
        sessions+=("$s_json")
    done < <(w -h 2>/dev/null || who 2>/dev/null)

    local arr
    arr=$(json_arr "${sessions[@]}")
    printf '{"count":%s,"sessions":%s}' "${#sessions[@]}" "$arr"
}

# ═══════════════════════════════════════════════════════════
#  BAŞLANGIÇ PROGRAMLARI
# ═══════════════════════════════════════════════════════════

collect_startups() {
    local items=() count=0

    if [[ "$OS_TYPE" == "linux" ]]; then
        # systemd enabled services
        if command -v systemctl &>/dev/null; then
            while IFS= read -r line; do
                local unit state
                unit=$(echo "$line" | awk '{print $1}')
                state=$(echo "$line" | awk '{print $2}')
                [[ "$state" != "enabled" ]] && continue
                local s_json
                s_json=$(json_obj "name" "$unit" "source" "systemd" "state" "$state")
                items+=("$s_json")
                count=$((count + 1))
            done < <(systemctl list-unit-files --type=service --no-legend --no-pager 2>/dev/null | head -100)
        fi

        # Crontab
        if [[ -f /etc/crontab ]]; then
            while IFS= read -r line; do
                local s_json
                s_json=$(json_obj "name" "$line" "source" "crontab")
                items+=("$s_json")
                count=$((count + 1))
            done < <(grep -v '^#\|^$\|^SHELL\|^PATH\|^MAILTO' /etc/crontab 2>/dev/null | head -20)
        fi

        # /etc/init.d
        if [[ -d /etc/init.d ]]; then
            for script in /etc/init.d/*; do
                [[ -x "$script" ]] || continue
                local s_json
                s_json=$(json_obj "name" "$(basename "$script")" "source" "init.d")
                items+=("$s_json")
                count=$((count + 1))
            done
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        # LaunchDaemons
        for plist in /Library/LaunchDaemons/*.plist; do
            [[ -f "$plist" ]] || continue
            local label
            label=$(defaults read "$plist" Label 2>/dev/null || basename "$plist" .plist)
            local s_json
            s_json=$(json_obj "name" "$label" "source" "LaunchDaemon" "path" "$plist")
            items+=("$s_json")
            count=$((count + 1))
        done

        # LaunchAgents
        for plist in /Library/LaunchAgents/*.plist ~/Library/LaunchAgents/*.plist; do
            [[ -f "$plist" ]] || continue
            local label
            label=$(defaults read "$plist" Label 2>/dev/null || basename "$plist" .plist)
            local s_json
            s_json=$(json_obj "name" "$label" "source" "LaunchAgent" "path" "$plist")
            items+=("$s_json")
            count=$((count + 1))
        done

        # Login Items
        while IFS= read -r item; do
            [[ -z "$item" ]] && continue
            local s_json
            s_json=$(json_obj "name" "$item" "source" "LoginItem")
            items+=("$s_json")
            count=$((count + 1))
        done < <(osascript -e 'tell application "System Events" to get the name of every login item' 2>/dev/null | tr ',' '\n')
    fi

    local arr
    arr=$(json_arr "${items[@]}")
    printf '{"count":%s,"items":%s}' "$count" "$arr"
}

# ═══════════════════════════════════════════════════════════
#  SICAKLIK
# ═══════════════════════════════════════════════════════════

collect_temperature() {
    local sensors=()

    if [[ "$OS_TYPE" == "linux" ]]; then
        # /sys/class/thermal
        for tz in /sys/class/thermal/thermal_zone*; do
            [[ -d "$tz" ]] || continue
            local temp type
            temp=$(cat "$tz/temp" 2>/dev/null || echo 0)
            type=$(cat "$tz/type" 2>/dev/null || echo "unknown")
            local temp_c
            temp_c=$(awk "BEGIN {printf \"%.1f\", $temp/1000}")

            local t_json
            t_json=$(json_obj "zone" "$type" "temp_c" "_NUM_$temp_c" "source" "thermal_zone")
            sensors+=("$t_json")
        done

        # lm-sensors
        if command -v sensors &>/dev/null; then
            while IFS= read -r line; do
                local name temp
                name=$(echo "$line" | cut -d: -f1 | xargs)
                temp=$(echo "$line" | sed -n 's/.*+\([0-9.]*\).*/\1/p')
                [[ -z "$temp" ]] && continue
                local t_json
                t_json=$(json_obj "zone" "$name" "temp_c" "_NUM_$temp" "source" "lm-sensors")
                sensors+=("$t_json")
            done < <(sensors 2>/dev/null | grep -E '°C|temp')
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        # macOS sıcaklık — powermetrics root gerektirir, osx-cpu-temp alternatif
        if command -v osx-cpu-temp &>/dev/null; then
            local temp
            temp=$(osx-cpu-temp 2>/dev/null | grep -oE '[0-9.]+' | head -1)
            if [[ -n "$temp" ]]; then
                local t_json
                t_json=$(json_obj "zone" "CPU" "temp_c" "_NUM_$temp" "source" "osx-cpu-temp")
                sensors+=("$t_json")
            fi
        fi
    fi

    # NVIDIA
    if command -v nvidia-smi &>/dev/null; then
        local nv_temp
        nv_temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
        if [[ -n "$nv_temp" ]]; then
            local t_json
            t_json=$(json_obj "zone" "NVIDIA_GPU" "temp_c" "_NUM_$nv_temp" "source" "nvidia-smi")
            sensors+=("$t_json")
        fi
    fi

    local arr
    arr=$(json_arr "${sensors[@]}")
    printf '{"sensors":%s}' "$arr"
}

# ═══════════════════════════════════════════════════════════
#  BATARYA
# ═══════════════════════════════════════════════════════════

collect_battery() {
    if [[ "$OS_TYPE" == "linux" ]]; then
        local bat_path="/sys/class/power_supply/BAT0"
        [[ -d "$bat_path" ]] || bat_path="/sys/class/power_supply/BAT1"
        if [[ ! -d "$bat_path" ]]; then
            printf '{"has_battery":false}'
            return
        fi
        local charge status cap
        charge=$(cat "$bat_path/capacity" 2>/dev/null || echo 0)
        status=$(cat "$bat_path/status" 2>/dev/null || echo "unknown")
        local design_cap full_cap
        design_cap=$(cat "$bat_path/charge_full_design" 2>/dev/null || echo 0)
        full_cap=$(cat "$bat_path/charge_full" 2>/dev/null || echo 0)
        local health=0
        if [[ $design_cap -gt 0 ]]; then
            health=$((full_cap * 100 / design_cap))
        fi

        json_obj \
            "has_battery" "_BOOL_true" \
            "charge_percent" "_NUM_$charge" \
            "status" "$status" \
            "health_percent" "_NUM_$health"

    elif [[ "$OS_TYPE" == "macos" ]]; then
        local pmset_out
        pmset_out=$(pmset -g batt 2>/dev/null)
        if echo "$pmset_out" | grep -q 'InternalBattery'; then
            local charge status remaining
            charge=$(echo "$pmset_out" | grep -oE '[0-9]+%' | tr -d '%')
            status=$(echo "$pmset_out" | grep -oE 'charging|discharging|charged|AC attached' | head -1)
            remaining=$(echo "$pmset_out" | grep -oE '[0-9]+:[0-9]+' | head -1)
            json_obj \
                "has_battery" "_BOOL_true" \
                "charge_percent" "_NUM_${charge:-0}" \
                "status" "${status:-unknown}" \
                "remaining" "${remaining:-unknown}"
        else
            printf '{"has_battery":false}'
        fi
    else
        printf '{"has_battery":false}'
    fi
}

# ═══════════════════════════════════════════════════════════
#  AUDIT — SYSMON KARŞILIĞI (auditd / osquery / eslogger)
# ═══════════════════════════════════════════════════════════

collect_audit() {
    local available=false status_json="{}" summary_json="{}" details_json="{}" threats="[]"

    if [[ "$OS_TYPE" == "linux" ]]; then
        collect_audit_linux
    elif [[ "$OS_TYPE" == "macos" ]]; then
        collect_audit_macos
    else
        printf '{"available":false,"reason":"unsupported_os"}'
    fi
}

collect_audit_linux() {
    local available=false
    local status_json="{}" summary_json="{}" details="[]" threats=()

    # auditd kontrol
    if command -v auditctl &>/dev/null && systemctl is-active auditd &>/dev/null 2>&1; then
        available=true
        local rules_count
        rules_count=$(auditctl -l 2>/dev/null | wc -l)
        local audit_ver
        audit_ver=$(auditctl -v 2>/dev/null | head -1)
        status_json=$(json_obj "installed" "_BOOL_true" "engine" "auditd" "rules_count" "_NUM_$rules_count" "version" "$audit_ver")
    elif command -v auditctl &>/dev/null; then
        status_json=$(json_obj "installed" "_BOOL_true" "engine" "auditd" "status" "inactive")
    else
        status_json=$(json_obj "installed" "_BOOL_false" "reason" "auditd bulunamadi")
    fi

    if [[ "$available" == "true" ]] && command -v ausearch &>/dev/null; then
        # Süreç oluşturma (execve) — Sysmon EventID 1 karşılığı
        local exec_count=0 exec_events=()
        exec_count=$(ausearch -m EXECVE --start today -i 2>/dev/null | grep -c 'type=EXECVE' || true)
        while IFS= read -r line; do
            local e_json
            e_json=$(json_obj "raw" "$(echo "$line" | head -c 300)")
            exec_events+=("$e_json")
        done < <(ausearch -m EXECVE --start today -i 2>/dev/null | tail -20)

        # Dosya erişim (open/openat) — Sysmon EventID 11 karşılığı
        local file_count
        file_count=$(ausearch -m OPEN --start today 2>/dev/null | grep -c 'type=SYSCALL' || true)

        # Ağ bağlantıları (connect/accept) — Sysmon EventID 3 karşılığı
        local net_count
        net_count=$(ausearch -m SOCKADDR --start today 2>/dev/null | grep -c 'type=SOCKADDR' || true)

        # Yetki yükseltme (setuid/setgid) — Sysmon EventID 10 karşılığı
        local priv_count
        priv_count=$(ausearch -m USER_AUTH --start today -i 2>/dev/null | grep -c 'type=USER_AUTH' || true)

        # Kullanıcı oturum olayları
        local login_count
        login_count=$(ausearch -m USER_LOGIN --start today -i 2>/dev/null | grep -c 'type=USER_LOGIN' || true)

        # Anomaliler
        local anom_count
        anom_count=$(ausearch -m ANOM_PROMISCUOUS,ANOM_ABEND --start today 2>/dev/null | grep -c 'type=ANOM' || true)

        summary_json=$(printf '{"process_exec":%s,"file_access":%s,"network_connect":%s,"privilege_escalation":%s,"user_login":%s,"anomalies":%s}' \
            "$exec_count" "$file_count" "$net_count" "$priv_count" "$login_count" "$anom_count")

        local exec_arr
        exec_arr=$(json_arr "${exec_events[@]}")
        details=$(printf '{"recent_exec":%s}' "$exec_arr")

        # Tehdit tespiti
        if [[ $anom_count -gt 0 ]]; then
            local t_json
            t_json=$(json_obj "category" "anomaly" "count" "_NUM_$anom_count" "severity" "HIGH")
            threats+=("$t_json")
        fi
        if [[ $priv_count -gt 50 ]]; then
            local t_json
            t_json=$(json_obj "category" "privilege_escalation" "count" "_NUM_$priv_count" "severity" "MEDIUM" "note" "Yuksek hacim yetki olaylari")
            threats+=("$t_json")
        fi
    fi

    local threat_arr
    threat_arr=$(json_arr "${threats[@]}")

    printf '{"available":%s,"status":%s,"event_summary":%s,"details":%s,"threat_alerts":%s,"collected_at":"%s"}' \
        "$available" "$status_json" "$summary_json" "$details" "$threat_arr" "$(date -Iseconds)"
}

collect_audit_macos() {
    local available=false
    local status_json="{}" summary_json="{}" details="[]" threats=()

    # OpenBSM audit (macOS yerleşik)
    if [[ -f /var/audit/current ]]; then
        available=true
        local audit_flags
        audit_flags=$(grep '^flags' /etc/security/audit_control 2>/dev/null | cut -d: -f2)
        status_json=$(json_obj "installed" "_BOOL_true" "engine" "OpenBSM" "flags" "${audit_flags:-unknown}")
    fi

    # Endpoint Security / log show tabanlı güvenlik olayları
    local exec_count=0 net_count=0 file_count=0 auth_count=0

    # Process exec olayları
    exec_count=$(run_with_timeout 10 log show --predicate 'eventMessage CONTAINS "exec" AND category == "process"' --last 1h --style syslog | wc -l || true)

    # Auth olayları
    auth_count=$(run_with_timeout 10 log show --predicate 'category == "authorization"' --last 1h | wc -l || true)

    summary_json=$(printf '{"process_exec":%s,"auth_events":%s}' "$exec_count" "$auth_count")

    if [[ $auth_count -gt 100 ]]; then
        local t_json
        t_json=$(json_obj "category" "auth_spike" "count" "_NUM_$auth_count" "severity" "MEDIUM")
        threats+=("$t_json")
    fi

    local threat_arr
    threat_arr=$(json_arr "${threats[@]}")

    printf '{"available":%s,"status":%s,"event_summary":%s,"details":%s,"threat_alerts":%s,"collected_at":"%s"}' \
        "$available" "$status_json" "$summary_json" "$details" "$threat_arr" "$(date -Iseconds)"
}

# ═══════════════════════════════════════════════════════════
#  DERİN TELEMETRİ — HEPSİNİ TOPLA
# ═══════════════════════════════════════════════════════════

collect_deep_telemetry() {
    log_msg "Derin telemetri toplaniyor..."
    local start_ts
    start_ts=$(date +%s)

    local system cpu memory disks network gpu security
    local event_logs open_ports sessions software services
    local processes startups temperature battery audit

    system=$(collect_system_info 2>/dev/null)   || system='{}'
    cpu=$(collect_cpu 2>/dev/null)               || cpu='{}'
    memory=$(collect_memory 2>/dev/null)          || memory='{}'
    disks=$(collect_disks 2>/dev/null)            || disks='{}'
    network=$(collect_network 2>/dev/null)        || network='{}'
    gpu=$(collect_gpu 2>/dev/null)                || gpu='{}'
    security=$(collect_security 2>/dev/null)      || security='{}'
    event_logs=$(collect_event_logs 2>/dev/null)  || event_logs='{}'
    open_ports=$(collect_open_ports 2>/dev/null)  || open_ports='{}'
    sessions=$(collect_sessions 2>/dev/null)      || sessions='{}'
    software=$(collect_software 2>/dev/null)      || software='{}'
    services=$(collect_services 2>/dev/null)      || services='{}'
    processes=$(collect_processes 2>/dev/null)     || processes='{}'
    startups=$(collect_startups 2>/dev/null)      || startups='{}'
    temperature=$(collect_temperature 2>/dev/null) || temperature='{}'
    battery=$(collect_battery 2>/dev/null)        || battery='{}'
    audit=$(collect_audit 2>/dev/null)            || audit='{}'

    local elapsed=$(( $(date +%s) - start_ts ))
    log_msg "Derin telemetri toplandi (${elapsed}s)"

    printf '{"collected_at":"%s","agent_version":"%s","os_type":"%s","system":%s,"cpu":%s,"memory":%s,"disks":%s,"network":%s,"gpu":%s,"security":%s,"event_logs":%s,"open_ports":%s,"sessions":%s,"software":%s,"services":%s,"processes":%s,"startups":%s,"temperature":%s,"battery":%s,"audit":%s}' \
        "$(date -Iseconds)" "$AGENT_VERSION" "$OS_TYPE" \
        "$system" "$cpu" "$memory" "$disks" "$network" "$gpu" \
        "$security" "$event_logs" "$open_ports" "$sessions" \
        "$software" "$services" "$processes" "$startups" \
        "$temperature" "$battery" "$audit"
}

# ═══════════════════════════════════════════════════════════
#  HEARTBEAT — TEMEL METRİKLER
# ═══════════════════════════════════════════════════════════

send_heartbeat() {
    local cpu_json mem_json disk_json net_json
    cpu_json=$(collect_cpu)
    mem_json=$(collect_memory)
    disk_json=$(collect_disks)
    net_json=$(collect_network)

    local cpu_pct mem_pct disk_pct net_rx net_tx
    cpu_pct=$(echo "$cpu_json" | sed -n 's/.*"usage_percent":\([0-9]*\).*/\1/p' | head -1)
    mem_pct=$(echo "$mem_json" | sed -n 's/.*"usage_percent":\([0-9]*\).*/\1/p' | head -1)
    disk_pct=$(echo "$disk_json" | sed -n 's/.*"usage_percent":\([0-9]*\).*/\1/p' | head -1)
    net_rx=$(echo "$net_json" | sed -n 's/.*"total_rx_bytes":\([0-9]*\).*/\1/p' | head -1)
    net_tx=$(echo "$net_json" | sed -n 's/.*"total_tx_bytes":\([0-9]*\).*/\1/p' | head -1)

    local body
    body=$(printf '{"cpu":%s,"ram":%s,"disk":%s,"net_in":%s,"net_out":%s,"extra":{"os_type":"%s"}}' \
        "${cpu_pct:-0}" "${mem_pct:-0}" "${disk_pct:-0}" "${net_rx:-0}" "${net_tx:-0}" "$OS_TYPE")

    local resp
    if resp=$(invoke_api "agent/heartbeat" "POST" "$body"); then
        log_msg "Heartbeat gonderildi [CPU=${cpu_pct:-0}% RAM=${mem_pct:-0}% DISK=${disk_pct:-0}%]"
    else
        log_msg "Heartbeat gonderilemedi!" "WARN"
    fi
}

# ═══════════════════════════════════════════════════════════
#  DERİN TELEMETRİ GÖNDERİMİ
# ═══════════════════════════════════════════════════════════

send_deep_telemetry() {
    local telemetry
    telemetry=$(collect_deep_telemetry)

    local cpu_pct mem_pct disk_pct net_rx net_tx
    cpu_pct=$(echo "$telemetry" | sed -n 's/.*"usage_percent":\([0-9]*\).*/\1/p' | head -1)
    mem_pct=$(echo "$telemetry" | sed -n 's/.*"usage_percent":\([0-9]*\).*/\1/p' | sed -n 2p)
    disk_pct=$(echo "$telemetry" | sed -n 's/.*"usage_percent":\([0-9]*\).*/\1/p' | sed -n 3p)
    net_rx=$(echo "$telemetry" | sed -n 's/.*"total_rx_bytes":\([0-9]*\).*/\1/p' | head -1)
    net_tx=$(echo "$telemetry" | sed -n 's/.*"total_tx_bytes":\([0-9]*\).*/\1/p' | head -1)

    local body
    body=$(printf '{"cpu":%s,"ram":%s,"disk":%s,"net_in":%s,"net_out":%s,"extra":%s}' \
        "${cpu_pct:-0}" "${mem_pct:-0}" "${disk_pct:-0}" "${net_rx:-0}" "${net_tx:-0}" "$telemetry")

    local resp
    if resp=$(invoke_api "agent/heartbeat" "POST" "$body"); then
        log_msg "Derin telemetri gonderildi (tum katmanlar)"
    else
        log_msg "Derin telemetri gonderilemedi!" "WARN"
    fi
}

# ═══════════════════════════════════════════════════════════
#  GÖREV YÜRÜTÜCÜ
# ═══════════════════════════════════════════════════════════

execute_task() {
    local task_id="$1" task_type="$2" payload="$3"
    log_msg "Gorev calistiriliyor: [$task_type] ID=$task_id"

    local success=true result=""

    case "$task_type" in
        shell_exec)
            local cmd
            cmd=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cmd',''))" 2>/dev/null)
            if [[ -z "$cmd" ]]; then
                success=false; result="cmd parametresi eksik"
            else
                result=$(bash -c "$cmd" 2>&1 || true)
            fi
            ;;

        script_exec|powershell_exec)
            local script
            script=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('script',''))" 2>/dev/null)
            if [[ -z "$script" ]]; then
                success=false; result="script parametresi eksik"
            else
                result=$(bash -c "$script" 2>&1 || true)
            fi
            ;;

        sysinfo_collect)
            result=$(collect_deep_telemetry)
            ;;

        config_query|registry_query)
            local path
            path=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('path',''))" 2>/dev/null)
            if [[ -z "$path" ]]; then
                success=false; result="path parametresi eksik"
            elif [[ -f "$path" ]]; then
                result=$(cat "$path" 2>&1)
            else
                success=false; result="Dosya bulunamadi: $path"
            fi
            ;;

        event_log)
            local log_source max_lines
            log_source=$(echo "$payload" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('log','system'))" 2>/dev/null)
            max_lines=$(echo "$payload" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('max_events',50))" 2>/dev/null)
            max_lines=${max_lines:-50}

            if [[ "$OS_TYPE" == "linux" ]]; then
                case "$log_source" in
                    system)   result=$(journalctl -p 0..4 -n "$max_lines" --no-pager -q 2>&1) ;;
                    security|auth) result=$(journalctl -u sshd -n "$max_lines" --no-pager -q 2>&1) ;;
                    *)        result=$(journalctl -u "$log_source" -n "$max_lines" --no-pager -q 2>&1) ;;
                esac
            else
                result=$(run_with_timeout 10 log show --last 1h --style syslog | tail -"$max_lines")
            fi
            ;;

        audit_collect|sysmon_collect)
            result=$(collect_audit)
            ;;

        restart_service)
            local svc_name
            svc_name=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('service',''))" 2>/dev/null)
            if [[ -z "$svc_name" ]]; then
                success=false; result="service parametresi eksik"
            elif [[ "$OS_TYPE" == "linux" ]]; then
                result=$(systemctl restart "$svc_name" 2>&1 && echo "Servis yeniden baslatildi: $svc_name" || echo "HATA: servis yeniden baslatılamadı")
            else
                result=$(launchctl kickstart -k "system/$svc_name" 2>&1 || echo "HATA")
            fi
            ;;

        install_software)
            local pkg
            pkg=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('package',''))" 2>/dev/null)
            if [[ -z "$pkg" ]]; then
                success=false; result="package parametresi eksik"
            elif [[ "$OS_TYPE" == "linux" ]]; then
                if command -v apt-get &>/dev/null; then
                    result=$(apt-get install -y "$pkg" 2>&1)
                elif command -v yum &>/dev/null; then
                    result=$(yum install -y "$pkg" 2>&1)
                elif command -v pacman &>/dev/null; then
                    result=$(pacman -S --noconfirm "$pkg" 2>&1)
                fi
            else
                if command -v brew &>/dev/null; then
                    result=$(brew install "$pkg" 2>&1)
                fi
            fi
            ;;

        uninstall_software)
            local pkg
            pkg=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('package',''))" 2>/dev/null)
            if [[ -z "$pkg" ]]; then
                success=false; result="package parametresi eksik"
            elif [[ "$OS_TYPE" == "linux" ]]; then
                if command -v apt-get &>/dev/null; then
                    result=$(apt-get remove -y "$pkg" 2>&1)
                elif command -v yum &>/dev/null; then
                    result=$(yum remove -y "$pkg" 2>&1)
                fi
            else
                if command -v brew &>/dev/null; then
                    result=$(brew uninstall "$pkg" 2>&1)
                fi
            fi
            ;;

        file_collect)
            local file_path
            file_path=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('path',''))" 2>/dev/null)
            if [[ -z "$file_path" ]]; then
                success=false; result="path parametresi eksik"
            elif [[ ! -f "$file_path" ]]; then
                success=false; result="Dosya bulunamadi: $file_path"
            else
                local file_size
                if [[ "$OS_TYPE" == "macos" ]]; then
                    file_size=$(stat -f%z "$file_path" 2>/dev/null)
                else
                    file_size=$(stat -c%s "$file_path" 2>/dev/null)
                fi
                if [[ ${file_size:-0} -gt 5242880 ]]; then
                    success=false; result="Dosya cok buyuk (max 5MB): $file_size bytes"
                else
                    local content
                    content=$(base64 < "$file_path")
                    result=$(json_obj "file_name" "$(basename "$file_path")" "file_size" "_NUM_$file_size" "content_base64" "$content" "collected_at" "$(date -Iseconds)")
                fi
            fi
            ;;

        update_agent)
            result="Agent guncelleme henuz desteklenmiyor"
            success=false
            ;;

        custom)
            local custom_script
            custom_script=$(echo "$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('script',''))" 2>/dev/null)
            if [[ -n "$custom_script" ]]; then
                result=$(bash -c "$custom_script" 2>&1 || true)
            else
                result="Custom payload alindi"
            fi
            ;;

        *)
            result="Bilinmeyen gorev tipi: $task_type"
            success=false
            ;;
    esac

    # Sonuç boyut limiti (10KB)
    if [[ ${#result} -gt 10240 ]]; then
        result="${result:0:10000}... (kesildi, toplam: ${#result} karakter)"
    fi

    # JSON escape result for safety
    local escaped_result
    escaped_result=$(json_escape "$result")

    local body
    body=$(printf '{"task_id":"%s","success":%s,"result":"%s"}' \
        "$task_id" "$success" "$escaped_result")

    invoke_api "agent/task-result" "POST" "$body" > /dev/null 2>&1
    log_msg "Gorev tamamlandi [$task_type] basari=$success"
}

poll_tasks() {
    local resp
    resp=$(invoke_api "agent/tasks" "GET") || return

    if ! command -v python3 &>/dev/null; then
        log_msg "python3 bulunamadi, gorev parse edilemiyor" "WARN"
        return
    fi

    # Parse tasks with python3
    local task_count
    task_count=$(echo "$resp" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    tasks = d.get('tasks', [])
    for t in tasks:
        print(f\"{t['id']}|{t['task_type']}|{json.dumps(t.get('payload', {}))}\")
except:
    pass
" 2>/dev/null)

    while IFS='|' read -r tid ttype tpayload; do
        [[ -z "$tid" ]] && continue
        execute_task "$tid" "$ttype" "$tpayload"
    done <<< "$task_count"
}

# ═══════════════════════════════════════════════════════════
#  ANA DÖNGÜ
# ═══════════════════════════════════════════════════════════

start_agent_loop() {
    log_msg "============================================"
    log_msg "Emare Security OS RMM Agent v${AGENT_VERSION} ($OS_TYPE)"
    log_msg "Sunucu: $SERVER_URL"
    log_msg "============================================"

    # Key yükle veya kayıt ol
    if ! load_agent_key; then
        if ! register_agent; then
            log_msg "Kayit basarisiz, 30 saniye sonra tekrar denenecek..." "ERROR"
            sleep 30
            start_agent_loop
            return
        fi
    fi

    # İlk derin telemetri
    send_deep_telemetry

    log_msg "Agent dongusu baslatildi [heartbeat=${HEARTBEAT_SEC}s task_poll=${TASK_POLL_SEC}s deep=${DEEP_COLLECT_SEC}s]"

    local last_heartbeat=0 last_task=0 last_deep=0
    local now

    while true; do
        now=$(date +%s)

        # Heartbeat
        if [[ $((now - last_heartbeat)) -ge $HEARTBEAT_SEC ]]; then
            send_heartbeat
            last_heartbeat=$now
        fi

        # Task polling
        if [[ $((now - last_task)) -ge $TASK_POLL_SEC ]]; then
            poll_tasks
            last_task=$now
        fi

        # Derin telemetri
        if [[ $((now - last_deep)) -ge $DEEP_COLLECT_SEC ]]; then
            send_deep_telemetry
            last_deep=$now
        fi

        sleep 5
    done
}

# ═══════════════════════════════════════════════════════════
#  CLI ARGÜMAN PARSE
# ═══════════════════════════════════════════════════════════

show_help() {
    cat << 'EOF'
Emare Security OS RMM Agent — Linux / macOS

Kullanım:
  ./EmareAgent.sh -s <SERVER_URL>              Normal daemon modu
  ./EmareAgent.sh -s <SERVER_URL> --register   Sadece kayıt ol
  ./EmareAgent.sh --deep-scan                  Tek seferlik derin tarama

Parametreler:
  -s, --server URL     Sunucu adresi (zorunlu, daemon modu için)
  --register           Sadece kayıt ol ve çık
  --deep-scan          Tek seferlik derin tarama → ./EmareDeepScan.json
  --trust-all-certs    Self-signed sertifika kabul et
  -h, --help           Bu yardım mesajı

Örnekler:
  ./EmareAgent.sh -s https://firewall.example.com
  sudo ./EmareAgent.sh -s https://10.0.0.1:5555 --trust-all-certs
  ./EmareAgent.sh --deep-scan
EOF
}

DO_REGISTER=false
DO_DEEP_SCAN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--server)
            SERVER_URL="$2"; shift 2 ;;
        --register)
            DO_REGISTER=true; shift ;;
        --deep-scan)
            DO_DEEP_SCAN=true; shift ;;
        --trust-all-certs)
            TRUST_ALL_CERTS=true; shift ;;
        -h|--help)
            show_help; exit 0 ;;
        *)
            echo "Bilinmeyen parametre: $1"; show_help; exit 1 ;;
    esac
done

# Deep scan modu — sunucu gerekmez
if [[ "$DO_DEEP_SCAN" == "true" ]]; then
    log_msg "Tek seferlik derin tarama baslatiliyor..."
    data=$(collect_deep_telemetry)
    output_file="$HOME/EmareDeepScan.json"

    if command -v python3 &>/dev/null; then
        echo "$data" | python3 -m json.tool > "$output_file" 2>/dev/null || echo "$data" > "$output_file"
    else
        echo "$data" > "$output_file"
    fi

    echo "Derin tarama tamamlandi: $output_file"
    exit 0
fi

# Sunucu zorunlu
if [[ -z "$SERVER_URL" ]]; then
    echo "HATA: Sunucu adresi belirtilmeli (-s URL)"
    show_help
    exit 1
fi

# Sadece kayıt
if [[ "$DO_REGISTER" == "true" ]]; then
    register_agent
    exit $?
fi

# Normal çalıştırma
start_agent_loop
