"""
Uygulama Pazari - Genisletilmis Acik Kaynak Market + GitHub Entegrasyonu
42 hazir uygulama + GitHub'dan canli arama ve kurulum destegi.
Debian/Ubuntu (apt), RHEL/AlmaLinux/CentOS/Fedora (dnf/yum) ve SUSE (zypper) destekli.
"""

import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# =====================================================================
# EVRENSEL OS ALGILAMA - Her scripte eklenen ortak baslik
# =====================================================================

_OS_DETECT_HEADER = """#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive 2>/dev/null || true

detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
    elif command -v zypper &>/dev/null; then
        PKG_MGR="zypper"
    elif command -v apk &>/dev/null; then
        PKG_MGR="apk"
    else
        echo "Desteklenmeyen paket yoneticisi!" >&2
        exit 1
    fi
    export PKG_MGR
}

pkg_update() {
    case "$PKG_MGR" in
        apt)    apt-get update -qq ;;
        dnf)    dnf makecache -q 2>/dev/null || true ;;
        yum)    yum makecache -q 2>/dev/null || true ;;
        zypper) zypper refresh -q 2>/dev/null || true ;;
        apk)    apk update -q ;;
    esac
}

pkg_install() {
    case "$PKG_MGR" in
        apt)    apt-get install -y -qq "$@" ;;
        dnf)    dnf install -y -q "$@" ;;
        yum)    yum install -y -q "$@" ;;
        zypper) zypper install -y -q "$@" ;;
        apk)    apk add -q "$@" ;;
    esac
}

ensure_epel() {
    if [[ "$PKG_MGR" == "dnf" || "$PKG_MGR" == "yum" ]]; then
        if ! rpm -q epel-release &>/dev/null; then
            $PKG_MGR install -y -q epel-release 2>/dev/null || true
        fi
    fi
}

ensure_docker() {
    if command -v docker &>/dev/null; then
        echo "Docker zaten kurulu."
        return 0
    fi
    echo "Docker kuruluyor..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    elif command -v dnf &>/dev/null || command -v yum &>/dev/null; then
        local YUM_CMD="dnf"
        command -v dnf &>/dev/null || YUM_CMD="yum"
        $YUM_CMD install -y -q yum-utils 2>/dev/null || true
        $YUM_CMD config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo 2>/dev/null || $YUM_CMD config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo 2>/dev/null || true
        $YUM_CMD install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || true
    else
        curl -fsSL https://get.docker.com | sh 2>/dev/null || true
    fi
    systemctl start docker 2>/dev/null || true
    systemctl enable docker 2>/dev/null || true
}

svc_name() {
    local generic="$1"
    case "$generic" in
        apache)
            if [[ "$PKG_MGR" == "apt" ]]; then echo "apache2"; else echo "httpd"; fi ;;
        redis)
            if [[ "$PKG_MGR" == "apt" ]]; then echo "redis-server"; else echo "redis"; fi ;;
        mongo)
            systemctl list-unit-files | grep -q mongod && echo "mongod" || echo "mongodb" ;;
        *)
            echo "$generic" ;;
    esac
}

detect_pkg_manager
echo "Paket yoneticisi: $PKG_MGR"
"""

_DOCKER_HEADER = """#!/usr/bin/env bash
set -euo pipefail

ensure_docker() {
    if command -v docker &>/dev/null; then
        echo "Docker zaten kurulu."
        return 0
    fi
    echo "Docker kuruluyor..."
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    elif command -v dnf &>/dev/null || command -v yum &>/dev/null; then
        YUM_CMD="dnf"
        command -v dnf &>/dev/null || YUM_CMD="yum"
        $YUM_CMD install -y -q yum-utils 2>/dev/null || true
        $YUM_CMD config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo 2>/dev/null || $YUM_CMD config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo 2>/dev/null || true
        $YUM_CMD install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || true
    else
        curl -fsSL https://get.docker.com | sh 2>/dev/null || true
    fi
    systemctl start docker 2>/dev/null || true
    systemctl enable docker 2>/dev/null || true
}

ensure_docker
"""


# =====================================================================
# HAZIR UYGULAMA KATALOGU
# =====================================================================

MARKET_APPS = {
    # ========================= VERITABANI =========================
    "mysql": {
        "id": "mysql", "name": "MySQL", "icon": "fa-database", "category": "Veritabanı",
        "description": "Dünyanın en popüler açık kaynak ilişkisel veritabanı.",
        "github": "mysql/mysql-server", "stars": "10k+",
        "options": [
            {"key": "root_password", "label": "Root şifre", "type": "password", "required": True, "placeholder": "Güçlü bir şifre"},
        ],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install mysql-server
        systemctl start mysql && systemctl enable mysql
        mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '{{root_password}}'; FLUSH PRIVILEGES;" 2>/dev/null || true
        ;;
    dnf|yum)
        pkg_install mysql-server
        systemctl start mysqld && systemctl enable mysqld
        TEMP_PASS=$(grep 'temporary password' /var/log/mysqld.log 2>/dev/null | tail -1 | awk '{print $NF}')
        if [ -n "$TEMP_PASS" ]; then
            mysql --connect-expired-password -u root -p"$TEMP_PASS" -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '{{root_password}}';" 2>/dev/null || true
        else
            mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '{{root_password}}'; FLUSH PRIVILEGES;" 2>/dev/null || true
        fi
        ;;
    zypper)
        pkg_install mysql-server
        systemctl start mysql && systemctl enable mysql
        mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '{{root_password}}'; FLUSH PRIVILEGES;" 2>/dev/null || true
        ;;
esac
echo 'MySQL kuruldu.'
""",
    },
    "postgresql": {
        "id": "postgresql", "name": "PostgreSQL", "icon": "fa-database", "category": "Veritabanı",
        "description": "Gelişmiş açık kaynak nesne-ilişkisel veritabanı sistemi.",
        "github": "postgres/postgres", "stars": "16k+",
        "options": [
            {"key": "postgres_password", "label": "postgres şifresi", "type": "password", "required": True},
        ],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install postgresql postgresql-contrib
        ;;
    dnf|yum)
        pkg_install postgresql-server postgresql
        postgresql-setup --initdb 2>/dev/null || /usr/bin/postgresql-setup initdb 2>/dev/null || true
        ;;
    zypper)
        pkg_install postgresql-server postgresql
        ;;
esac

systemctl start postgresql && systemctl enable postgresql
sudo -u postgres psql -c "ALTER USER postgres PASSWORD '{{postgres_password}}';" 2>/dev/null || true
echo 'PostgreSQL kuruldu.'
""",
    },
    "redis": {
        "id": "redis", "name": "Redis", "icon": "fa-memory", "category": "Veritabanı",
        "description": "Bellek içi veri yapısı deposu — cache, mesaj kuyruğu, veritabanı.",
        "github": "redis/redis", "stars": "66k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
ensure_epel

case "$PKG_MGR" in
    apt)    pkg_install redis-server ;;
    dnf|yum) pkg_install redis ;;
    zypper) pkg_install redis ;;
esac

SVC=$(svc_name redis)
systemctl restart "$SVC" && systemctl enable "$SVC"
echo 'Redis kuruldu.'
""",
    },
    "mongodb": {
        "id": "mongodb", "name": "MongoDB", "icon": "fa-database", "category": "Veritabanı",
        "description": "Doküman tabanlı NoSQL veritabanı — esnek şema, yatay ölçekleme.",
        "github": "mongodb/mongo", "stars": "26k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
pkg_install gnupg curl

case "$PKG_MGR" in
    apt)
        curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg 2>/dev/null || true
        . /etc/os-release
        echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] http://repo.mongodb.org/apt/${ID} ${VERSION_CODENAME}/mongodb-org/7.0 main" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list 2>/dev/null || true
        apt-get update -qq && apt-get install -y -qq mongodb-org 2>/dev/null || true
        ;;
    dnf|yum)
        cat > /etc/yum.repos.d/mongodb-org-7.0.repo << 'MREPO'
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/$releasever/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://pgp.mongodb.com/server-7.0.asc
MREPO
        $PKG_MGR install -y -q mongodb-org 2>/dev/null || true
        ;;
esac

SVC=$(svc_name mongo)
systemctl start "$SVC" 2>/dev/null || true
systemctl enable "$SVC" 2>/dev/null || true
echo 'MongoDB kuruldu.'
""",
    },
    "mariadb": {
        "id": "mariadb", "name": "MariaDB", "icon": "fa-database", "category": "Veritabanı",
        "description": "MySQL'in topluluk destekli forku — daha hızlı, daha açık.",
        "github": "MariaDB/server", "stars": "5.6k+",
        "options": [
            {"key": "root_password", "label": "Root şifre", "type": "password", "required": True},
        ],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install mariadb-server ;;
    dnf|yum) pkg_install mariadb-server mariadb ;;
    zypper) pkg_install mariadb ;;
esac

systemctl start mariadb && systemctl enable mariadb
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '{{root_password}}'; FLUSH PRIVILEGES;" 2>/dev/null || mariadb -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '{{root_password}}'; FLUSH PRIVILEGES;" 2>/dev/null || true
echo 'MariaDB kuruldu.'
""",
    },
    "influxdb": {
        "id": "influxdb", "name": "InfluxDB", "icon": "fa-chart-line", "category": "Veritabanı",
        "description": "Zaman serisi veritabanı — metrikler, IoT, gerçek zamanlı analitik.",
        "github": "influxdata/influxdb", "stars": "29k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        curl -fsSL https://repos.influxdata.com/influxdata-archive_compat.key | gpg --dearmor -o /etc/apt/trusted.gpg.d/influxdata.gpg 2>/dev/null || true
        echo "deb https://repos.influxdata.com/debian stable main" | tee /etc/apt/sources.list.d/influxdata.list
        apt-get update -qq && apt-get install -y -qq influxdb2
        ;;
    dnf|yum)
        cat > /etc/yum.repos.d/influxdata.repo << 'IREPO'
[influxdata]
name=InfluxData Repository
baseurl=https://repos.influxdata.com/rhel/$releasever/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://repos.influxdata.com/influxdata-archive_compat.key
IREPO
        $PKG_MGR install -y -q influxdb2 2>/dev/null || true
        ;;
esac

systemctl start influxdb && systemctl enable influxdb
echo 'InfluxDB kuruldu. http://SUNUCU:8086'
""",
    },
    "clickhouse": {
        "id": "clickhouse", "name": "ClickHouse", "icon": "fa-database", "category": "Veritabanı",
        "description": "Sütun tabanlı OLAP veritabanı — milyarlarca satır üzerinde anlık sorgular.",
        "github": "ClickHouse/ClickHouse", "stars": "37k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install apt-transport-https ca-certificates curl gnupg
        curl -fsSL https://packages.clickhouse.com/rpm/lts/repodata/repomd.xml.key | gpg --dearmor -o /usr/share/keyrings/clickhouse-keyring.gpg 2>/dev/null || true
        echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg] https://packages.clickhouse.com/deb stable main" | tee /etc/apt/sources.list.d/clickhouse.list
        apt-get update -qq && apt-get install -y -qq clickhouse-server clickhouse-client
        ;;
    dnf|yum)
        cat > /etc/yum.repos.d/clickhouse.repo << 'CREPO'
[clickhouse-stable]
name=ClickHouse Stable Repository
baseurl=https://packages.clickhouse.com/rpm/stable/
gpgcheck=0
enabled=1
CREPO
        $PKG_MGR install -y -q clickhouse-server clickhouse-client 2>/dev/null || true
        ;;
esac

systemctl start clickhouse-server && systemctl enable clickhouse-server
echo 'ClickHouse kuruldu.'
""",
    },

    # ========================= WEB SUNUCU =========================
    "nginx": {
        "id": "nginx", "name": "Nginx", "icon": "fa-globe", "category": "Web Sunucu",
        "description": "Yüksek performanslı web sunucusu, ters proxy ve yük dengeleyici.",
        "github": "nginx/nginx", "stars": "25k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
ensure_epel
pkg_install nginx
systemctl start nginx && systemctl enable nginx
echo 'Nginx kuruldu.'
""",
    },
    "apache2": {
        "id": "apache2", "name": "Apache HTTP Server", "icon": "fa-globe", "category": "Web Sunucu",
        "description": "Dünyanın en yaygın kullanılan HTTP sunucusu.",
        "github": "apache/httpd", "stars": "3.8k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install apache2 ;;
    dnf|yum) pkg_install httpd ;;
    zypper) pkg_install apache2 ;;
esac

SVC=$(svc_name apache)
systemctl start "$SVC" && systemctl enable "$SVC"
echo 'Apache HTTP Server kuruldu.'
""",
    },
    "caddy": {
        "id": "caddy", "name": "Caddy", "icon": "fa-lock", "category": "Web Sunucu",
        "description": "Otomatik HTTPS'li modern web sunucusu — sıfır yapılandırma SSL.",
        "github": "caddyserver/caddy", "stars": "58k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install debian-keyring debian-archive-keyring apt-transport-https curl
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null || true
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
        apt-get update -qq && apt-get install -y -qq caddy
        ;;
    dnf|yum)
        $PKG_MGR install -y -q 'dnf-command(copr)' 2>/dev/null || true
        $PKG_MGR copr enable @caddy/caddy -y 2>/dev/null || true
        $PKG_MGR install -y -q caddy 2>/dev/null || {
            curl -fsSL -o /usr/local/bin/caddy "https://caddyserver.com/api/download?os=linux&arch=amd64" 2>/dev/null || true
            chmod +x /usr/local/bin/caddy
        }
        ;;
esac

systemctl start caddy 2>/dev/null || true
systemctl enable caddy 2>/dev/null || true
echo 'Caddy kuruldu.'
""",
    },
    "traefik": {
        "id": "traefik", "name": "Traefik", "icon": "fa-route", "category": "Web Sunucu",
        "description": "Cloud-native ters proxy ve yük dengeleyici — Docker ile mükemmel uyum.",
        "github": "traefik/traefik", "stars": "51k+",
        "options": [{"key": "port", "label": "Dashboard port", "type": "number", "default": 8080}],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
ARCH=$(uname -m)
case "$ARCH" in x86_64) ARCH="amd64";; aarch64) ARCH="arm64";; esac
LATEST=$(curl -fsSL https://api.github.com/repos/traefik/traefik/releases/latest 2>/dev/null | grep -oP '"tag_name":\\s*"v\\K[^"]+' || echo "3.0.0")
curl -fsSL -o /tmp/traefik.tar.gz "https://github.com/traefik/traefik/releases/download/v${LATEST}/traefik_v${LATEST}_linux_${ARCH}.tar.gz" 2>/dev/null || true
tar xzf /tmp/traefik.tar.gz -C /usr/local/bin/ traefik 2>/dev/null || true
chmod +x /usr/local/bin/traefik 2>/dev/null || true
echo "Traefik v${LATEST} kuruldu."
""",
    },

    # ========================= KONTEYNER & ALTYAPI =========================
    "docker": {
        "id": "docker", "name": "Docker", "icon": "fab fa-docker", "category": "Konteyner & Altyapı",
        "description": "Konteyner platformu — uygulamaları izole ortamda çalıştırır.",
        "github": "moby/moby", "stars": "69k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
ensure_docker
docker --version
echo 'Docker kuruldu.'
""",
    },
    "docker-compose": {
        "id": "docker-compose", "name": "Docker Compose", "icon": "fab fa-docker", "category": "Konteyner & Altyapı",
        "description": "Çoklu konteyner uygulamalarını YAML ile tanımlayıp çalıştırın.",
        "github": "docker/compose", "stars": "34k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
ensure_docker

if docker compose version &>/dev/null; then
    echo "Docker Compose plugin zaten mevcut."
else
    COMPOSE_ARCH=$(uname -m)
    curl -fsSL -o /usr/local/bin/docker-compose "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${COMPOSE_ARCH}" 2>/dev/null || true
    chmod +x /usr/local/bin/docker-compose 2>/dev/null || true
fi
echo 'Docker Compose kuruldu.'
""",
    },
    "kubernetes-k3s": {
        "id": "kubernetes-k3s", "name": "K3s (Hafif Kubernetes)", "icon": "fa-dharmachakra", "category": "Konteyner & Altyapı",
        "description": "Rancher'ın hafif Kubernetes dağıtımı — IoT ve edge için ideal.",
        "github": "k3s-io/k3s", "stars": "28k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
curl -sfL https://get.k3s.io | sh -
echo 'K3s kuruldu. kubectl get nodes ile kontrol edin.'
""",
    },
    "portainer": {
        "id": "portainer", "name": "Portainer", "icon": "fab fa-docker", "category": "Konteyner & Altyapı",
        "description": "Docker/Kubernetes için web tabanlı yönetim arayüzü.",
        "github": "portainer/portainer", "stars": "31k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 9443}],
        "install_script": _DOCKER_HEADER + """
docker volume create portainer_data 2>/dev/null || true
docker rm -f portainer 2>/dev/null || true
docker run -d -p 8000:8000 -p {{port}}:9443 --name portainer --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:latest
echo 'Portainer kuruldu. https://SUNUCU:{{port}}'
""",
    },
    "lxd": {
        "id": "lxd", "name": "LXD", "icon": "fa-server", "category": "Konteyner & Altyapı",
        "description": "Sistem konteyner ve VM yöneticisi — hafif sanallaştırma.",
        "github": "canonical/lxd", "stars": "4.4k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
case "$PKG_MGR" in
    apt)
        snap install lxd --classic 2>/dev/null || pkg_install lxd 2>/dev/null || true
        ;;
    dnf|yum)
        if command -v snap &>/dev/null; then
            snap install lxd --classic 2>/dev/null || true
        else
            ensure_epel
            pkg_install snapd 2>/dev/null || true
            systemctl enable --now snapd.socket 2>/dev/null || true
            ln -s /var/lib/snapd/snap /snap 2>/dev/null || true
            snap install lxd --classic 2>/dev/null || true
        fi
        ;;
esac
lxd init --auto 2>/dev/null || true
echo 'LXD kuruldu.'
""",
    },
    "ansible": {
        "id": "ansible", "name": "Ansible", "icon": "fa-cogs", "category": "Konteyner & Altyapı",
        "description": "Agentless otomasyon aracı — sunucu yapılandırma, deployment, orkestrasyon.",
        "github": "ansible/ansible", "stars": "63k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install python3-pip
        pip3 install ansible 2>/dev/null || pip3 install --break-system-packages ansible
        ;;
    dnf|yum)
        ensure_epel
        pkg_install ansible-core 2>/dev/null || { pkg_install python3-pip; pip3 install ansible 2>/dev/null || pip3 install --break-system-packages ansible; }
        ;;
    zypper)
        pkg_install ansible
        ;;
esac
echo "Ansible kuruldu: $(ansible --version | head -1)"
""",
    },
    "terraform": {
        "id": "terraform", "name": "Terraform", "icon": "fa-cloud", "category": "Konteyner & Altyapı",
        "description": "Infrastructure as Code — bulut altyapısını kodla yönetin.",
        "github": "hashicorp/terraform", "stars": "43k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
pkg_install curl gnupg

case "$PKG_MGR" in
    apt)
        pkg_install software-properties-common
        curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg 2>/dev/null || true
        echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(. /etc/os-release && echo "$VERSION_CODENAME") main" | tee /etc/apt/sources.list.d/hashicorp.list
        apt-get update -qq && apt-get install -y -qq terraform
        ;;
    dnf|yum)
        $PKG_MGR install -y -q yum-utils 2>/dev/null || true
        $PKG_MGR config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo 2>/dev/null || true
        $PKG_MGR install -y -q terraform
        ;;
    zypper)
        zypper ar https://rpm.releases.hashicorp.com/SLES/hashicorp.repo 2>/dev/null || true
        zypper install -y terraform
        ;;
esac
echo "Terraform kuruldu: $(terraform version | head -1)"
""",
    },

    # ========================= IZLEME & GOZLEM =========================
    "grafana": {
        "id": "grafana", "name": "Grafana", "icon": "fa-chart-area", "category": "İzleme & Gözlem",
        "description": "Metrik ve log görselleştirme platformu — dashboard oluşturun.",
        "github": "grafana/grafana", "stars": "65k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3000}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install apt-transport-https software-properties-common curl
        curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /usr/share/keyrings/grafana.gpg 2>/dev/null || true
        echo "deb [signed-by=/usr/share/keyrings/grafana.gpg] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list
        apt-get update -qq && apt-get install -y -qq grafana
        ;;
    dnf|yum)
        cat > /etc/yum.repos.d/grafana.repo << 'GREPO'
[grafana]
name=Grafana Repository
baseurl=https://rpm.grafana.com
repo_gpgcheck=1
enabled=1
gpgcheck=1
gpgkey=https://rpm.grafana.com/gpg.key
sslverify=1
sslcacert=/etc/pki/tls/certs/ca-bundle.crt
GREPO
        $PKG_MGR install -y -q grafana
        ;;
esac

systemctl daemon-reload
systemctl start grafana-server && systemctl enable grafana-server
echo 'Grafana kuruldu. http://SUNUCU:{{port}} (admin/admin)'
""",
    },
    "prometheus": {
        "id": "prometheus", "name": "Prometheus", "icon": "fa-fire", "category": "İzleme & Gözlem",
        "description": "Metrik toplama ve uyarı sistemi — Kubernetes izleme standardı.",
        "github": "prometheus/prometheus", "stars": "55k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
useradd --no-create-home --shell /bin/false prometheus 2>/dev/null || true
mkdir -p /etc/prometheus /var/lib/prometheus
LATEST=$(curl -fsSL https://api.github.com/repos/prometheus/prometheus/releases/latest 2>/dev/null | grep -oP '"tag_name":\\s*"v\\K[^"]+' || echo "2.54.1")
ARCH=$(uname -m); case "$ARCH" in x86_64) ARCH="amd64";; aarch64) ARCH="arm64";; esac
cd /tmp
curl -fsSLO "https://github.com/prometheus/prometheus/releases/download/v${LATEST}/prometheus-${LATEST}.linux-${ARCH}.tar.gz"
tar xzf prometheus-${LATEST}.linux-${ARCH}.tar.gz
cd prometheus-${LATEST}.linux-${ARCH}
cp prometheus promtool /usr/local/bin/
cp -r consoles console_libraries /etc/prometheus/ 2>/dev/null || true
[ -f /etc/prometheus/prometheus.yml ] || cp prometheus.yml /etc/prometheus/
chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus 2>/dev/null || true
cat > /etc/systemd/system/prometheus.service << 'PSVC'
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target
[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/var/lib/prometheus/
[Install]
WantedBy=multi-user.target
PSVC
systemctl daemon-reload
systemctl start prometheus && systemctl enable prometheus
echo "Prometheus v${LATEST} kuruldu. http://SUNUCU:9090"
""",
    },
    "netdata": {
        "id": "netdata", "name": "Netdata", "icon": "fa-tachometer-alt", "category": "İzleme & Gözlem",
        "description": "Gerçek zamanlı sunucu izleme — anlık grafikler, sıfır yapılandırma.",
        "github": "netdata/netdata", "stars": "72k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://get.netdata.cloud/kickstart.sh | bash -s -- --dont-wait --non-interactive 2>/dev/null || {
    if command -v apt-get &>/dev/null; then apt-get update -qq && apt-get install -y -qq netdata;
    elif command -v dnf &>/dev/null; then dnf install -y -q epel-release 2>/dev/null || true; dnf install -y -q netdata; fi
}
systemctl start netdata 2>/dev/null || true
systemctl enable netdata 2>/dev/null || true
echo 'Netdata kuruldu. http://SUNUCU:19999'
""",
    },
    "uptime-kuma": {
        "id": "uptime-kuma", "name": "Uptime Kuma", "icon": "fa-heartbeat", "category": "İzleme & Gözlem",
        "description": "Self-hosted uptime izleme aracı — güzel arayüz, bildirimler.",
        "github": "louislam/uptime-kuma", "stars": "60k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3001}],
        "install_script": _DOCKER_HEADER + """
docker rm -f uptime-kuma 2>/dev/null || true
docker run -d --restart=always -p {{port}}:3001 -v uptime-kuma:/app/data --name uptime-kuma louislam/uptime-kuma:1
echo 'Uptime Kuma kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "zabbix": {
        "id": "zabbix", "name": "Zabbix", "icon": "fa-chart-bar", "category": "İzleme & Gözlem",
        "description": "Kurumsal düzeyde ağ ve sunucu izleme platformu.",
        "github": "zabbix/zabbix", "stars": "4.8k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        . /etc/os-release
        wget -q "https://repo.zabbix.com/zabbix/7.0/${ID}/pool/main/z/zabbix-release/zabbix-release_latest+${ID}${VERSION_ID}_all.deb" -O /tmp/zabbix-release.deb 2>/dev/null || true
        dpkg -i /tmp/zabbix-release.deb 2>/dev/null || true
        apt-get update -qq
        apt-get install -y -qq zabbix-server-mysql zabbix-frontend-php zabbix-apache-conf zabbix-agent 2>/dev/null || true
        ;;
    dnf|yum)
        . /etc/os-release
        rpm -Uvh "https://repo.zabbix.com/zabbix/7.0/alma/${VERSION_ID%%.*}/x86_64/zabbix-release-latest-7.0.el${VERSION_ID%%.*}.noarch.rpm" 2>/dev/null || rpm -Uvh "https://repo.zabbix.com/zabbix/7.0/rhel/${VERSION_ID%%.*}/x86_64/zabbix-release-latest-7.0.el${VERSION_ID%%.*}.noarch.rpm" 2>/dev/null || true
        $PKG_MGR clean all 2>/dev/null || true
        $PKG_MGR install -y -q zabbix-server-mysql zabbix-web-mysql zabbix-apache-conf zabbix-agent 2>/dev/null || true
        ;;
esac
echo 'Zabbix paketleri kuruldu. Veritabani yapilandirmasi gerekiyor.'
""",
    },
    "glances": {
        "id": "glances", "name": "Glances", "icon": "fa-eye", "category": "İzleme & Gözlem",
        "description": "Cross-platform sistem izleme aracı — terminal + web arayüzü.",
        "github": "nicolargo/glances", "stars": "27k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
pkg_install python3-pip 2>/dev/null || pkg_install python3 2>/dev/null || true
pip3 install 'glances[web]' 2>/dev/null || pip3 install --break-system-packages 'glances[web]' 2>/dev/null || true
echo 'Glances kuruldu. glances -w ile web modunda baslatin (port 61208).'
""",
    },

    # ========================= GUVENLIK =========================
    "ufw": {
        "id": "ufw", "name": "UFW", "icon": "fa-shield-alt", "category": "Güvenlik",
        "description": "Kolay güvenlik duvarı yönetimi — basit kural tanımlama.",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install ufw ;;
    dnf|yum)
        ensure_epel
        pkg_install ufw 2>/dev/null || {
            echo "UFW RHEL/Alma'da varsayilan degil. firewalld kullaniliyor."
            pkg_install firewalld
            systemctl start firewalld && systemctl enable firewalld
            firewall-cmd --permanent --add-service=ssh
            firewall-cmd --reload
            echo 'firewalld kuruldu ve SSH izin verildi.'
            exit 0
        }
        ;;
esac

ufw default deny incoming 2>/dev/null || true
ufw default allow outgoing 2>/dev/null || true
ufw allow 22/tcp 2>/dev/null || true
echo 'UFW kuruldu (SSH izinli).'
""",
    },
    "fail2ban": {
        "id": "fail2ban", "name": "Fail2Ban", "icon": "fa-ban", "category": "Güvenlik",
        "description": "Brute-force saldırı önleme — tekrarlayan hatalı girişleri otomatik engeller.",
        "github": "fail2ban/fail2ban", "stars": "12k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
ensure_epel
pkg_install fail2ban
systemctl start fail2ban && systemctl enable fail2ban
echo 'Fail2Ban kuruldu.'
""",
    },
    "crowdsec": {
        "id": "crowdsec", "name": "CrowdSec", "icon": "fa-users-cog", "category": "Güvenlik",
        "description": "Topluluk destekli güvenlik motoru — IP reputation + davranış analizi.",
        "github": "crowdsecurity/crowdsec", "stars": "9k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
curl -s https://install.crowdsec.net | bash 2>/dev/null || {
    if command -v apt-get &>/dev/null; then apt-get update -qq && apt-get install -y -qq crowdsec;
    elif command -v dnf &>/dev/null; then dnf install -y -q crowdsec 2>/dev/null || true; fi
}
systemctl start crowdsec 2>/dev/null || true
systemctl enable crowdsec 2>/dev/null || true
echo 'CrowdSec kuruldu.'
""",
    },
    "wireguard": {
        "id": "wireguard", "name": "WireGuard", "icon": "fa-network-wired", "category": "Güvenlik",
        "description": "Modern, hızlı VPN tüneli — basit yapılandırma, yüksek performans.",
        "github": "WireGuard/wireguard-linux", "stars": "4k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install wireguard ;;
    dnf|yum)
        ensure_epel
        pkg_install wireguard-tools
        pkg_install kmod-wireguard 2>/dev/null || modprobe wireguard 2>/dev/null || true
        ;;
    zypper) pkg_install wireguard-tools ;;
esac
echo 'WireGuard kuruldu. wg genkey | tee privatekey | wg pubkey > publickey'
""",
    },
    "certbot": {
        "id": "certbot", "name": "Certbot (Let's Encrypt)", "icon": "fa-certificate", "category": "Güvenlik",
        "description": "Ücretsiz SSL sertifikası otomatik alma ve yenileme.",
        "github": "certbot/certbot", "stars": "31k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install certbot python3-certbot-nginx 2>/dev/null || pkg_install certbot ;;
    dnf|yum)
        ensure_epel
        pkg_install certbot python3-certbot-nginx 2>/dev/null || pkg_install certbot
        ;;
    zypper) pkg_install certbot ;;
esac
echo 'Certbot kuruldu. certbot --nginx ile SSL alin.'
""",
    },
    "vaultwarden": {
        "id": "vaultwarden", "name": "Vaultwarden", "icon": "fa-key", "category": "Güvenlik",
        "description": "Bitwarden uyumlu şifre yöneticisi — self-hosted, hafif.",
        "github": "dani-garcia/vaultwarden", "stars": "39k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8222}],
        "install_script": _DOCKER_HEADER + """
docker rm -f vaultwarden 2>/dev/null || true
docker run -d --name vaultwarden -p {{port}}:80 -v /vw-data/:/data/ --restart unless-stopped vaultwarden/server:latest
echo 'Vaultwarden kuruldu. http://SUNUCU:{{port}}'
""",
    },

    # ========================= GELISTIRME =========================
    "nodejs": {
        "id": "nodejs", "name": "Node.js", "icon": "fab fa-node-js", "category": "Geliştirme",
        "description": "JavaScript çalışma ortamı — backend, araçlar, fullstack.",
        "github": "nodejs/node", "stars": "108k+",
        "options": [{"key": "version", "label": "Majör sürüm", "type": "number", "default": 22}],
        "install_script": _OS_DETECT_HEADER + """
curl -fsSL https://rpm.nodesource.com/setup_{{version}}.x 2>/dev/null | bash - 2>/dev/null || curl -fsSL https://deb.nodesource.com/setup_{{version}}.x | bash - 2>/dev/null || true

case "$PKG_MGR" in
    apt)    apt-get install -y -qq nodejs ;;
    dnf|yum) $PKG_MGR install -y -q nodejs ;;
esac
echo "Node.js kuruldu: $(node -v)"
""",
    },
    "python3": {
        "id": "python3", "name": "Python 3", "icon": "fab fa-python", "category": "Geliştirme",
        "description": "Çok amaçlı programlama dili — web, AI, otomasyon, veri bilimi.",
        "github": "python/cpython", "stars": "64k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install python3 python3-pip python3-venv ;;
    dnf|yum) pkg_install python3 python3-pip python3-devel ;;
    zypper) pkg_install python3 python3-pip ;;
esac
echo "Python kuruldu: $(python3 --version)"
""",
    },
    "go": {
        "id": "go", "name": "Go (Golang)", "icon": "fa-code", "category": "Geliştirme",
        "description": "Google'ın hızlı, derlenmiş programlama dili — sistem araçları, web servisleri.",
        "github": "golang/go", "stars": "124k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
LATEST=$(curl -fsSL https://go.dev/VERSION?m=text 2>/dev/null | head -1 || echo "go1.23.1")
ARCH=$(uname -m); case "$ARCH" in x86_64) ARCH="amd64";; aarch64) ARCH="arm64";; esac
cd /tmp
curl -fsSLO "https://go.dev/dl/${LATEST}.linux-${ARCH}.tar.gz"
rm -rf /usr/local/go && tar -C /usr/local -xzf "${LATEST}.linux-${ARCH}.tar.gz"
echo 'export PATH=$PATH:/usr/local/go/bin' > /etc/profile.d/golang.sh
chmod +x /etc/profile.d/golang.sh
export PATH=$PATH:/usr/local/go/bin
echo "Go kuruldu: $(/usr/local/go/bin/go version)"
""",
    },
    "rust": {
        "id": "rust", "name": "Rust", "icon": "fa-cog", "category": "Geliştirme",
        "description": "Bellek güvenli sistem programlama dili — performans + güvenlik.",
        "github": "rust-lang/rust", "stars": "99k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env" 2>/dev/null || true
echo "Rust kuruldu: $(rustc --version 2>/dev/null || echo 'yeni oturumda kontrol edin')"
""",
    },
    "php": {
        "id": "php", "name": "PHP", "icon": "fab fa-php", "category": "Geliştirme",
        "description": "Web geliştirme dili — WordPress, Laravel, Symfony.",
        "options": [{"key": "version", "label": "PHP sürümü", "type": "text", "default": "8.3"}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install software-properties-common
        add-apt-repository -y ppa:ondrej/php 2>/dev/null || true
        apt-get update -qq
        apt-get install -y -qq php{{version}}-cli php{{version}}-fpm php{{version}}-mysql php{{version}}-xml php{{version}}-curl php{{version}}-mbstring php{{version}}-zip
        ;;
    dnf|yum)
        . /etc/os-release
        $PKG_MGR install -y -q "https://rpms.remirepo.net/enterprise/remi-release-${VERSION_ID%%.*}.rpm" 2>/dev/null || true
        $PKG_MGR module reset php -y 2>/dev/null || true
        $PKG_MGR module enable "php:remi-{{version}}" -y 2>/dev/null || true
        $PKG_MGR install -y -q php php-cli php-fpm php-mysqlnd php-xml php-curl php-mbstring php-zip
        ;;
esac
echo "PHP kuruldu: $(php -v | head -1)"
""",
    },
    "git": {
        "id": "git", "name": "Git", "icon": "fab fa-git-alt", "category": "Geliştirme",
        "description": "Dağıtık versiyon kontrol sistemi — kod yönetiminin temeli.",
        "github": "git/git", "stars": "52k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
pkg_install git
echo "Git kuruldu: $(git --version)"
""",
    },

    # ========================= WEB UYGULAMALAR =========================
    "wordpress": {
        "id": "wordpress", "name": "WordPress", "icon": "fab fa-wordpress", "category": "Web Uygulamalar",
        "description": "Dünyanın en popüler içerik yönetim sistemi (CMS).",
        "github": "WordPress/WordPress", "stars": "19k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)
        pkg_install apache2 php php-mysql libapache2-mod-php php-xml php-mbstring php-curl
        WEB_ROOT="/var/www/html"
        WEB_USER="www-data"
        ;;
    dnf|yum)
        ensure_epel
        pkg_install httpd php php-mysqlnd php-xml php-mbstring php-curl
        WEB_ROOT="/var/www/html"
        WEB_USER="apache"
        systemctl start httpd && systemctl enable httpd
        ;;
esac

cd "$WEB_ROOT"
curl -fsSLO https://wordpress.org/latest.tar.gz && tar xzf latest.tar.gz
chown -R "$WEB_USER":"$WEB_USER" "$WEB_ROOT/wordpress"
rm -f latest.tar.gz
echo "WordPress kuruldu. http://SUNUCU/wordpress"
""",
    },
    "nextcloud": {
        "id": "nextcloud", "name": "Nextcloud", "icon": "fa-cloud-upload-alt", "category": "Web Uygulamalar",
        "description": "Self-hosted dosya paylaşımı ve işbirliği platformu — Google Drive alternatifi.",
        "github": "nextcloud/server", "stars": "27k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8888}],
        "install_script": _DOCKER_HEADER + """
docker rm -f nextcloud 2>/dev/null || true
docker run -d --name nextcloud -p {{port}}:80 -v nextcloud:/var/www/html --restart unless-stopped nextcloud
echo 'Nextcloud kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "gitea": {
        "id": "gitea", "name": "Gitea", "icon": "fab fa-git-alt", "category": "Web Uygulamalar",
        "description": "Hafif self-hosted Git servisi — GitHub alternatifi.",
        "github": "go-gitea/gitea", "stars": "45k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3000}],
        "install_script": _DOCKER_HEADER + """
docker rm -f gitea 2>/dev/null || true
docker run -d --name gitea -p {{port}}:3000 -p 2222:22 -v gitea:/data --restart unless-stopped gitea/gitea:latest
echo 'Gitea kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "ghost": {
        "id": "ghost", "name": "Ghost", "icon": "fa-ghost", "category": "Web Uygulamalar",
        "description": "Modern blog ve yayın platformu — hızlı, temiz, SEO dostu.",
        "github": "TryGhost/Ghost", "stars": "47k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 2368}],
        "install_script": _DOCKER_HEADER + """
docker rm -f ghost 2>/dev/null || true
docker run -d --name ghost -p {{port}}:2368 -v ghost-content:/var/lib/ghost/content --restart unless-stopped ghost
echo 'Ghost kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "minio": {
        "id": "minio", "name": "MinIO", "icon": "fa-archive", "category": "Web Uygulamalar",
        "description": "S3 uyumlu nesne depolama — self-hosted AWS S3 alternatifi.",
        "github": "minio/minio", "stars": "48k+",
        "options": [],
        "install_script": _DOCKER_HEADER + """
docker rm -f minio 2>/dev/null || true
docker run -d --name minio -p 9000:9000 -p 9001:9001 -v minio-data:/data --restart unless-stopped minio/minio server /data --console-address ":9001"
echo 'MinIO kuruldu. Console: http://SUNUCU:9001 (minioadmin/minioadmin)'
""",
    },
    "n8n": {
        "id": "n8n", "name": "n8n", "icon": "fa-project-diagram", "category": "Web Uygulamalar",
        "description": "İş akışı otomasyon aracı — Zapier/Make alternatifi, self-hosted.",
        "github": "n8n-io/n8n", "stars": "48k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 5678}],
        "install_script": _DOCKER_HEADER + """
docker rm -f n8n 2>/dev/null || true
docker run -d --name n8n -p {{port}}:5678 -v n8n_data:/home/node/.n8n --restart unless-stopped n8nio/n8n
echo 'n8n kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "nocodb": {
        "id": "nocodb", "name": "NocoDB", "icon": "fa-table", "category": "Web Uygulamalar",
        "description": "Airtable alternatifi — veritabanlarını akıllı tablolara dönüştürün.",
        "github": "nocodb/nocodb", "stars": "50k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8080}],
        "install_script": _DOCKER_HEADER + """
docker rm -f nocodb 2>/dev/null || true
docker run -d --name nocodb -p {{port}}:8080 -v nocodb:/usr/app/data/ --restart unless-stopped nocodb/nocodb:latest
echo 'NocoDB kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "plausible": {
        "id": "plausible", "name": "Plausible Analytics", "icon": "fa-chart-pie", "category": "Web Uygulamalar",
        "description": "Gizlilik odaklı web analitik — Google Analytics alternatifi.",
        "github": "plausible/analytics", "stars": "20k+",
        "options": [],
        "install_script": _DOCKER_HEADER + """
command -v git &>/dev/null || {
    if command -v apt-get &>/dev/null; then apt-get update -qq && apt-get install -y -qq git;
    elif command -v dnf &>/dev/null; then dnf install -y -q git; fi
}
cd /opt && git clone https://github.com/plausible/community-edition.git plausible 2>/dev/null || true
cd /opt/plausible && docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null || true
echo 'Plausible kuruldu.'
""",
    },
    "homepage": {
        "id": "homepage", "name": "Homepage", "icon": "fa-home", "category": "Web Uygulamalar",
        "description": "Modern self-hosted başlangıç sayfası — servis durumu, widget'lar.",
        "github": "gethomepage/homepage", "stars": "20k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3000}],
        "install_script": _DOCKER_HEADER + """
mkdir -p /opt/homepage
docker rm -f homepage 2>/dev/null || true
docker run -d --name homepage -p {{port}}:3000 -v /opt/homepage:/app/config --restart unless-stopped ghcr.io/gethomepage/homepage:latest
echo 'Homepage kuruldu. http://SUNUCU:{{port}}'
""",
    },

    # ========================= AI / YAPAY ZEKA =========================
    "ollama": {
        "id": "ollama", "name": "Ollama", "icon": "fas fa-brain", "category": "AI / Yapay Zeka",
        "description": "Yerel LLM çalıştırma — LLaMA, Mistral, Gemma, Phi ve daha fazlası.",
        "github": "ollama/ollama", "stars": "100k+",
        "options": [],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://ollama.com/install.sh | sh
systemctl start ollama 2>/dev/null || true
systemctl enable ollama 2>/dev/null || true
echo 'Ollama kuruldu. "ollama run llama3.2" ile baslayin.'
""",
    },
    "open-webui": {
        "id": "open-webui", "name": "Open WebUI", "icon": "fas fa-comments", "category": "AI / Yapay Zeka",
        "description": "Ollama/OpenAI için ChatGPT benzeri web arayüzü.",
        "github": "open-webui/open-webui", "stars": "50k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8080}],
        "install_script": _DOCKER_HEADER + """
docker rm -f open-webui 2>/dev/null || true
docker run -d --name open-webui -p {{port}}:8080 -v open-webui:/app/backend/data --restart unless-stopped --add-host=host.docker.internal:host-gateway -e OLLAMA_BASE_URL=http://host.docker.internal:11434 ghcr.io/open-webui/open-webui:main
echo 'Open WebUI kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "stable-diffusion-webui": {
        "id": "stable-diffusion-webui", "name": "Stable Diffusion WebUI", "icon": "fas fa-image", "category": "AI / Yapay Zeka",
        "description": "AI görsel üretimi — Stable Diffusion ile metin->görsel.",
        "github": "AUTOMATIC1111/stable-diffusion-webui", "stars": "145k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install git python3 python3-venv python3-pip ;;
    dnf|yum) pkg_install git python3 python3-pip python3-devel ;;
esac

cd /opt && git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git 2>/dev/null || true
cd stable-diffusion-webui
python3 -m venv venv
echo 'SD WebUI indirildi. cd /opt/stable-diffusion-webui && ./webui.sh --listen'
""",
    },
    "whisper": {
        "id": "whisper", "name": "OpenAI Whisper", "icon": "fas fa-microphone-alt", "category": "AI / Yapay Zeka",
        "description": "Ses->metin dönüştürme (speech-to-text) — çoklu dil desteği.",
        "github": "openai/whisper", "stars": "72k+",
        "options": [{"key": "model_size", "label": "Model boyutu", "type": "text", "default": "base"}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install python3 python3-pip ffmpeg ;;
    dnf|yum)
        ensure_epel
        pkg_install python3 python3-pip
        $PKG_MGR install -y -q --enablerepo=crb ffmpeg 2>/dev/null || $PKG_MGR install -y -q https://download1.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm 2>/dev/null && $PKG_MGR install -y -q ffmpeg 2>/dev/null || true
        ;;
esac

pip3 install openai-whisper 2>/dev/null || pip3 install --break-system-packages openai-whisper
echo 'Whisper kuruldu. whisper audio.mp3 --model {{model_size}}'
""",
    },
    "code-server": {
        "id": "code-server", "name": "code-server (VS Code)", "icon": "fas fa-code", "category": "AI / Yapay Zeka",
        "description": "Tarayıcıda VS Code — uzaktan geliştirme, AI eklentileri.",
        "github": "coder/code-server", "stars": "69k+",
        "options": [{"key": "port", "label": "Port", "type": "number", "default": 8443}],
        "install_script": """#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://code-server.dev/install.sh | sh
mkdir -p ~/.config/code-server
RND=$(openssl rand -hex 12 2>/dev/null || head -c 24 /dev/urandom | od -A n -t x1 | tr -d ' \\n')
cat > ~/.config/code-server/config.yaml << EOF
bind-addr: 0.0.0.0:{{port}}
auth: password
password: $RND
EOF
systemctl enable --now code-server@root 2>/dev/null || code-server --bind-addr 0.0.0.0:{{port}} &
echo "code-server kuruldu. http://SUNUCU:{{port}} Sifre: $RND"
""",
    },
    "localai": {
        "id": "localai", "name": "LocalAI", "icon": "fas fa-robot", "category": "AI / Yapay Zeka",
        "description": "OpenAI API uyumlu yerel AI sunucusu — drop-in replacement.",
        "github": "mudler/LocalAI", "stars": "26k+",
        "options": [{"key": "port", "label": "API port", "type": "number", "default": 8080}],
        "install_script": _DOCKER_HEADER + """
docker rm -f localai 2>/dev/null || true
docker run -d --name localai -p {{port}}:8080 -v localai-models:/models --restart unless-stopped localai/localai:latest-cpu
echo 'LocalAI kuruldu. http://SUNUCU:{{port}}/v1/models'
""",
    },
    "comfyui": {
        "id": "comfyui", "name": "ComfyUI", "icon": "fas fa-palette", "category": "AI / Yapay Zeka",
        "description": "Node tabanlı Stable Diffusion arayüzü — gelişmiş iş akışları.",
        "github": "comfyanonymous/ComfyUI", "stars": "60k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update

case "$PKG_MGR" in
    apt)    pkg_install git python3 python3-venv python3-pip ;;
    dnf|yum) pkg_install git python3 python3-pip python3-devel ;;
esac

cd /opt && git clone https://github.com/comfyanonymous/ComfyUI.git 2>/dev/null || true
cd ComfyUI
python3 -m venv venv
./venv/bin/pip install -r requirements.txt 2>/dev/null || true
echo 'ComfyUI indirildi. cd /opt/ComfyUI && ./venv/bin/python main.py --listen'
""",
    },
    "text-generation-webui": {
        "id": "text-generation-webui", "name": "Text Generation WebUI", "icon": "fas fa-keyboard", "category": "AI / Yapay Zeka",
        "description": "En popüler yerel LLM arayüzü — LLaMA, Mistral, GGUF, GPTQ modelleri.",
        "github": "oobabooga/text-generation-webui", "stars": "42k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 7860}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
case "$PKG_MGR" in
    apt)    pkg_install git python3 python3-venv python3-pip wget ;;
    dnf|yum) pkg_install git python3 python3-pip python3-devel wget ;;
esac
cd /opt && git clone https://github.com/oobabooga/text-generation-webui.git 2>/dev/null || true
cd text-generation-webui
python3 -m venv venv
./venv/bin/pip install -r requirements.txt 2>/dev/null || true
echo 'Text Generation WebUI indirildi. cd /opt/text-generation-webui && ./start_linux.sh --listen-port {{port}}'
""",
    },
    "privateGPT": {
        "id": "privateGPT", "name": "PrivateGPT", "icon": "fas fa-user-secret", "category": "AI / Yapay Zeka",
        "description": "Belgelerinizle özel AI sohbet — %100 yerel, veri dışarı çıkmaz.",
        "github": "zylon-ai/private-gpt", "stars": "55k+",
        "options": [{"key": "port", "label": "API port", "type": "number", "default": 8001}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
case "$PKG_MGR" in
    apt)    pkg_install git python3 python3-pip python3-venv build-essential ;;
    dnf|yum) pkg_install git python3 python3-pip python3-devel gcc gcc-c++ ;;
esac
curl -fsSL https://ollama.com/install.sh | sh
systemctl start ollama 2>/dev/null || true
cd /opt && git clone https://github.com/zylon-ai/private-gpt.git 2>/dev/null || true
cd private-gpt
python3 -m venv venv
./venv/bin/pip install -e '.[local]' 2>/dev/null || ./venv/bin/pip install -r requirements.txt 2>/dev/null || true
echo 'PrivateGPT indirildi. cd /opt/private-gpt && ./venv/bin/python -m private_gpt'
""",
    },
    "flowise": {
        "id": "flowise", "name": "Flowise", "icon": "fas fa-project-diagram", "category": "AI / Yapay Zeka",
        "description": "Sürükle-bırak LLM zincir oluşturucu — LangChain tabanlı, kodsuz AI iş akışları.",
        "github": "FlowiseAI/Flowise", "stars": "32k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3000}],
        "install_script": _DOCKER_HEADER + """
docker rm -f flowise 2>/dev/null || true
docker run -d --name flowise -p {{port}}:3000 -v flowise-data:/root/.flowise --restart unless-stopped flowiseai/flowise:latest
echo 'Flowise kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "anything-llm": {
        "id": "anything-llm", "name": "AnythingLLM", "icon": "fas fa-infinity", "category": "AI / Yapay Zeka",
        "description": "Hepsi bir arada AI asistan — doküman yükleme, RAG, çoklu LLM desteği.",
        "github": "Mintplex-Labs/anything-llm", "stars": "30k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3001}],
        "install_script": _DOCKER_HEADER + """
docker rm -f anything-llm 2>/dev/null || true
docker pull mintplexlabs/anythingllm:latest
mkdir -p /opt/anything-llm/storage
docker run -d --name anything-llm -p {{port}}:3001 -v /opt/anything-llm/storage:/app/server/storage --restart unless-stopped mintplexlabs/anythingllm:latest
echo 'AnythingLLM kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "lobe-chat": {
        "id": "lobe-chat", "name": "LobeChat", "icon": "fas fa-comment-dots", "category": "AI / Yapay Zeka",
        "description": "Modern ChatGPT/Claude arayüzü — eklentiler, dosya yükleme, çoklu model desteği.",
        "github": "lobehub/lobe-chat", "stars": "50k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3210}],
        "install_script": _DOCKER_HEADER + """
docker rm -f lobe-chat 2>/dev/null || true
docker run -d --name lobe-chat -p {{port}}:3210 -e OLLAMA_PROXY_URL=http://host.docker.internal:11434/v1 --add-host=host.docker.internal:host-gateway --restart unless-stopped lobehub/lobe-chat:latest
echo 'LobeChat kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "jan": {
        "id": "jan", "name": "Jan", "icon": "fas fa-desktop", "category": "AI / Yapay Zeka",
        "description": "Açık kaynak ChatGPT alternatifi — %100 çevrimdışı, kolay model yönetimi.",
        "github": "janhq/jan", "stars": "25k+",
        "options": [{"key": "port", "label": "API port", "type": "number", "default": 1337}],
        "install_script": _DOCKER_HEADER + """
docker rm -f jan 2>/dev/null || true
docker run -d --name jan -p {{port}}:1337 -v jan-data:/app/data --restart unless-stopped ghcr.io/janhq/jan:latest 2>/dev/null || {
    echo 'Docker imajı bulunamadı, snap denenecek...'
    command -v snap &>/dev/null && snap install jan 2>/dev/null || true
}
echo 'Jan kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "tabby": {
        "id": "tabby", "name": "Tabby (AI Coding)", "icon": "fas fa-cat", "category": "AI / Yapay Zeka",
        "description": "Self-hosted AI kod asistanı — GitHub Copilot alternatifi, yerel LLM.",
        "github": "TabbyML/tabby", "stars": "25k+",
        "options": [{"key": "port", "label": "API port", "type": "number", "default": 8080}],
        "install_script": _DOCKER_HEADER + """
docker rm -f tabby 2>/dev/null || true
mkdir -p /opt/tabby-data
docker run -d --name tabby -p {{port}}:8080 -v /opt/tabby-data:/data --restart unless-stopped tabbyml/tabby serve --model TabbyML/StarCoder-1B --device cpu
echo 'Tabby AI kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "searxng": {
        "id": "searxng", "name": "SearXNG", "icon": "fas fa-search", "category": "AI / Yapay Zeka",
        "description": "Gizlilik odaklı meta arama motoru — AI araçlarıyla entegre, self-hosted.",
        "github": "searxng/searxng", "stars": "14k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8888}],
        "install_script": _DOCKER_HEADER + """
docker rm -f searxng 2>/dev/null || true
mkdir -p /opt/searxng
docker run -d --name searxng -p {{port}}:8080 -v /opt/searxng:/etc/searxng --restart unless-stopped searxng/searxng:latest
echo 'SearXNG kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "langflow": {
        "id": "langflow", "name": "Langflow", "icon": "fas fa-bezier-curve", "category": "AI / Yapay Zeka",
        "description": "Görsel LLM uygulama oluşturucu — LangChain iş akışlarını sürükle-bırakla tasarla.",
        "github": "langflow-ai/langflow", "stars": "40k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 7860}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
case "$PKG_MGR" in
    apt)    pkg_install python3 python3-pip python3-venv ;;
    dnf|yum) pkg_install python3 python3-pip ;;
esac
pip3 install langflow 2>/dev/null || pip3 install --break-system-packages langflow 2>/dev/null || true
echo 'Langflow kuruldu. langflow run --host 0.0.0.0 --port {{port}}'
""",
    },
    "dify": {
        "id": "dify", "name": "Dify", "icon": "fas fa-wand-magic-sparkles", "category": "AI / Yapay Zeka",
        "description": "LLM uygulama geliştirme platformu — RAG, Agent, iş akışı, API.",
        "github": "langgenius/dify", "stars": "55k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3000}],
        "install_script": _DOCKER_HEADER + """
cd /opt && git clone https://github.com/langgenius/dify.git 2>/dev/null || true
cd dify/docker
cp .env.example .env 2>/dev/null || true
docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null || true
echo 'Dify kuruldu. http://SUNUCU:{{port}} (varsayılan port: 80)'
""",
    },
    "gpt4all": {
        "id": "gpt4all", "name": "GPT4All", "icon": "fas fa-microchip", "category": "AI / Yapay Zeka",
        "description": "Herkese açık yerel AI — düşük donanımda çalışan LLM, API sunucusu.",
        "github": "nomic-ai/gpt4all", "stars": "72k+",
        "options": [{"key": "port", "label": "API port", "type": "number", "default": 4891}],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
case "$PKG_MGR" in
    apt)    pkg_install python3 python3-pip ;;
    dnf|yum) pkg_install python3 python3-pip ;;
esac
pip3 install gpt4all 2>/dev/null || pip3 install --break-system-packages gpt4all 2>/dev/null || true
echo 'GPT4All kuruldu. python3 -c "from gpt4all import GPT4All; m=GPT4All(\"Meta-Llama-3-8B-Instruct.Q4_0.gguf\"); print(m.generate(\"Merhaba!\"))"'
""",
    },
    "open-interpreter": {
        "id": "open-interpreter", "name": "Open Interpreter", "icon": "fas fa-terminal", "category": "AI / Yapay Zeka",
        "description": "Yerel AI terminal — doğal dilde komut çalıştırma, dosya düzenleme, kod yazma.",
        "github": "OpenInterpreter/open-interpreter", "stars": "55k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
case "$PKG_MGR" in
    apt)    pkg_install python3 python3-pip ;;
    dnf|yum) pkg_install python3 python3-pip ;;
esac
pip3 install open-interpreter 2>/dev/null || pip3 install --break-system-packages open-interpreter 2>/dev/null || true
echo 'Open Interpreter kuruldu. interpreter komutuyla baslatin.'
""",
    },

    # ========================= ILETISIM =========================
    "rocketchat": {
        "id": "rocketchat", "name": "Rocket.Chat", "icon": "fas fa-comments", "category": "İletişim",
        "description": "Açık kaynak takım iletişim platformu — Slack alternatifi.",
        "github": "RocketChat/Rocket.Chat", "stars": "40k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 3000}],
        "install_script": _DOCKER_HEADER + """
docker rm -f rocketchat 2>/dev/null || true
docker run -d --name rocketchat -p {{port}}:3000 -v rocketchat-uploads:/app/uploads --restart unless-stopped rocket.chat:latest
echo 'Rocket.Chat kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "mattermost": {
        "id": "mattermost", "name": "Mattermost", "icon": "fas fa-comment-dots", "category": "İletişim",
        "description": "Güvenli takım mesajlaşma platformu — self-hosted Slack alternatifi.",
        "github": "mattermost/mattermost", "stars": "30k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8065}],
        "install_script": _DOCKER_HEADER + """
docker rm -f mattermost 2>/dev/null || true
docker run -d --name mattermost -p {{port}}:8065 -v mattermost-data:/mattermost/data --restart unless-stopped mattermost/mattermost-team-edition
echo 'Mattermost kuruldu. http://SUNUCU:{{port}}'
""",
    },

    # ========================= MEDYA =========================
    "jellyfin": {
        "id": "jellyfin", "name": "Jellyfin", "icon": "fas fa-film", "category": "Medya",
        "description": "Açık kaynak medya sunucusu — kendi Netflix'inizi kurun.",
        "github": "jellyfin/jellyfin", "stars": "35k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 8096}],
        "install_script": _DOCKER_HEADER + """
docker rm -f jellyfin 2>/dev/null || true
docker run -d --name jellyfin -p {{port}}:8096 -v jellyfin-config:/config -v jellyfin-cache:/cache -v /media:/media --restart unless-stopped jellyfin/jellyfin
echo 'Jellyfin kuruldu. http://SUNUCU:{{port}}'
""",
    },
    "photoprism": {
        "id": "photoprism", "name": "PhotoPrism", "icon": "fas fa-camera", "category": "Medya",
        "description": "AI destekli fotoğraf yöneticisi — Google Photos alternatifi.",
        "github": "photoprism/photoprism", "stars": "35k+",
        "options": [{"key": "port", "label": "Web port", "type": "number", "default": 2342}],
        "install_script": _DOCKER_HEADER + """
docker rm -f photoprism 2>/dev/null || true
docker run -d --name photoprism -p {{port}}:2342 -v photoprism-storage:/photoprism/storage -v ~/Pictures:/photoprism/originals --restart unless-stopped -e PHOTOPRISM_ADMIN_PASSWORD=changeme photoprism/photoprism
echo 'PhotoPrism kuruldu. http://SUNUCU:{{port}} (admin/changeme)'
""",
    },

    # ========================= YEDEKLEME =========================
    "restic": {
        "id": "restic", "name": "Restic", "icon": "fas fa-hdd", "category": "Yedekleme",
        "description": "Hızlı, güvenli, verimli yedekleme programı — şifreli, deduplikasyonlu.",
        "github": "restic/restic", "stars": "26k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
ensure_epel

case "$PKG_MGR" in
    apt)    pkg_install restic ;;
    dnf|yum)
        pkg_install restic 2>/dev/null || {
            ARCH=$(uname -m); [[ "$ARCH" == "x86_64" ]] && ARCH="amd64"
            curl -fsSL -o /usr/local/bin/restic "https://github.com/restic/restic/releases/latest/download/restic_${ARCH}_linux" 2>/dev/null || true
            chmod +x /usr/local/bin/restic
        }
        ;;
esac
echo 'Restic kuruldu.'
""",
    },
    "borgbackup": {
        "id": "borgbackup", "name": "BorgBackup", "icon": "fas fa-shield-alt", "category": "Yedekleme",
        "description": "Deduplikasyonlu yedekleme — disk alanından tasarruf, şifreli.",
        "github": "borgbackup/borg", "stars": "11k+",
        "options": [],
        "install_script": _OS_DETECT_HEADER + """
pkg_update
ensure_epel

case "$PKG_MGR" in
    apt)    pkg_install borgbackup ;;
    dnf|yum) pkg_install borgbackup 2>/dev/null || pip3 install borgbackup 2>/dev/null || true ;;
    zypper) pkg_install borgbackup ;;
esac
echo 'Borg kuruldu.'
""",
    },
}


# =====================================================================
# GitHub API Entegrasyonu
# =====================================================================

_SSL_CTX = None


def _get_ssl_ctx():
    global _SSL_CTX
    if _SSL_CTX is None:
        _SSL_CTX = ssl.create_default_context()
    return _SSL_CTX


def github_search(query, language="", sort="stars", per_page=30, page=1):
    """GitHub API uzerinden repo arama."""
    q_parts = [query]
    if language:
        q_parts.append("language:" + language)
    q = " ".join(q_parts)

    params = urllib.parse.urlencode({
        "q": q, "sort": sort, "order": "desc",
        "per_page": min(per_page, 100), "page": page,
    })
    url = "https://api.github.com/search/repositories?" + params
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "EmareCloud-Panel/2.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=_get_ssl_ctx()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "total_count": data.get("total_count", 0),
                "items": [
                    {
                        "id": r["full_name"].replace("/", "--"),
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "description": (r.get("description") or "")[:200],
                        "stars": r.get("stargazers_count", 0),
                        "language": r.get("language") or "-",
                        "url": r.get("html_url", ""),
                        "owner": r.get("owner", {}).get("login", ""),
                        "avatar": r.get("owner", {}).get("avatar_url", ""),
                        "topics": r.get("topics", [])[:5],
                        "forks": r.get("forks_count", 0),
                        "updated_at": (r.get("updated_at") or "")[:10],
                        "license": (r.get("license") or {}).get("spdx_id", ""),
                        "open_issues": r.get("open_issues_count", 0),
                        "default_branch": r.get("default_branch", "main"),
                    }
                    for r in data.get("items", [])
                ],
            }
    except Exception as e:
        return {"total_count": 0, "items": [], "error": str(e)}


def github_trending(language="", since="weekly"):
    """GitHub'da populer repolari bul."""
    now = datetime.utcnow()
    q = "stars:>1000"
    if language:
        q += " language:" + language
    if since == "daily":
        cutoff = now - timedelta(days=1)
    elif since == "weekly":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = now - timedelta(days=30)
    q += " pushed:>" + cutoff.strftime("%Y-%m-%d")
    return github_search(q, sort="stars", per_page=30)


def github_get_readme(full_name):
    """Bir repo'nun README.md icerigini dondurur."""
    url = "https://api.github.com/repos/" + full_name + "/readme"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": "EmareCloud-Panel/2.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10, context=_get_ssl_ctx()) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return text[:3000]
    except Exception:
        return ""


def github_install_script(full_name, branch="main"):
    """GitHub projesini sunucuya klonlayip kurmak icin generic script uretir."""
    safe_name = full_name.replace("/", "_").replace(" ", "_")
    return (
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        '\n'
        '# OS Algilama\n'
        'if command -v apt-get &>/dev/null; then\n'
        '    PKG_MGR="apt"\n'
        'elif command -v dnf &>/dev/null; then\n'
        '    PKG_MGR="dnf"\n'
        'elif command -v yum &>/dev/null; then\n'
        '    PKG_MGR="yum"\n'
        'else\n'
        '    PKG_MGR="unknown"\n'
        'fi\n'
        '\n'
        'pkg_install_base() {\n'
        '    case "$PKG_MGR" in\n'
        '        apt)  export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && apt-get install -y -qq "$@" ;;\n'
        '        dnf)  dnf install -y -q "$@" ;;\n'
        '        yum)  yum install -y -q "$@" ;;\n'
        '    esac\n'
        '}\n'
        '\n'
        'command -v git &>/dev/null || pkg_install_base git\n'
        '\n'
        'echo "' + full_name + ' klonlaniyor..."\n'
        'mkdir -p /opt/github-apps\n'
        'cd /opt/github-apps\n'
        'rm -rf ' + safe_name + ' 2>/dev/null || true\n'
        'git clone --depth 1 -b ' + branch + ' https://github.com/' + full_name + '.git ' + safe_name + '\n'
        'cd ' + safe_name + '\n'
        '\n'
        'echo "Kurulum yontemi araniyor..."\n'
        '\n'
        'if [ -f docker-compose.yml ] || [ -f docker-compose.yaml ] || [ -f compose.yml ]; then\n'
        '    echo "Docker Compose bulundu..."\n'
        '    command -v docker &>/dev/null || { echo "Docker gerekli."; exit 1; }\n'
        '    docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null || true\n'
        '    echo "' + full_name + ' Docker Compose ile baslatildi."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ -f Dockerfile ]; then\n'
        '    echo "Dockerfile bulundu..."\n'
        '    command -v docker &>/dev/null || { echo "Docker gerekli."; exit 1; }\n'
        '    docker build -t ' + safe_name + ' . 2>/dev/null || true\n'
        '    docker run -d --name ' + safe_name + ' --restart unless-stopped ' + safe_name + ' 2>/dev/null || true\n'
        '    echo "' + full_name + ' Docker ile baslatildi."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ -f Makefile ]; then\n'
        '    echo "Makefile bulundu..."\n'
        '    case "$PKG_MGR" in\n'
        '        apt) apt-get install -y -qq build-essential 2>/dev/null || true ;;\n'
        '        dnf|yum) $PKG_MGR groupinstall -y -q "Development Tools" 2>/dev/null || $PKG_MGR install -y -q gcc make 2>/dev/null || true ;;\n'
        '    esac\n'
        '    make install 2>/dev/null || make 2>/dev/null || true\n'
        '    echo "' + full_name + ' make ile kuruldu."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'for script in install.sh setup.sh start.sh; do\n'
        '    if [ -f "$script" ]; then\n'
        '        chmod +x "$script"\n'
        '        ./"$script" 2>/dev/null || true\n'
        '        echo "' + full_name + ' $script ile kuruldu."\n'
        '        exit 0\n'
        '    fi\n'
        'done\n'
        '\n'
        'if [ -f requirements.txt ]; then\n'
        '    pkg_install_base python3 python3-pip python3-venv 2>/dev/null || pkg_install_base python3 python3-pip 2>/dev/null || true\n'
        '    python3 -m venv venv\n'
        '    ./venv/bin/pip install -r requirements.txt 2>/dev/null || true\n'
        '    echo "' + full_name + ' kuruldu."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ -f setup.py ] || [ -f pyproject.toml ]; then\n'
        '    pkg_install_base python3 python3-pip 2>/dev/null || true\n'
        '    pip3 install . 2>/dev/null || pip3 install --break-system-packages . 2>/dev/null || true\n'
        '    echo "' + full_name + ' pip ile kuruldu."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ -f package.json ]; then\n'
        '    if ! command -v node &>/dev/null; then\n'
        '        case "$PKG_MGR" in\n'
        '            apt) curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y -qq nodejs ;;\n'
        '            dnf|yum) curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - && $PKG_MGR install -y -q nodejs ;;\n'
        '        esac\n'
        '    fi\n'
        '    npm install 2>/dev/null || true\n'
        '    echo "' + full_name + ' kuruldu. npm start ile baslatin."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ -f go.mod ]; then\n'
        '    if ! command -v go &>/dev/null; then pkg_install_base golang 2>/dev/null || true; fi\n'
        '    go build ./... 2>/dev/null || true\n'
        '    echo "' + full_name + ' derlendi."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ -f Cargo.toml ]; then\n'
        '    if ! command -v cargo &>/dev/null; then\n'
        '        curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y\n'
        '        source "$HOME/.cargo/env"\n'
        '    fi\n'
        '    cargo build --release 2>/dev/null || true\n'
        '    echo "' + full_name + ' derlendi."\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'echo "' + full_name + ' /opt/github-apps/' + safe_name + ' konumuna klonlandi."\n'
        'echo "README.md dosyasini okuyarak kurulum talimatlarini takip edin."\n'
    )


# =====================================================================
# Yardimci fonksiyonlar
# =====================================================================

def get_app(app_id):
    """Uygulama tanimini dondurur."""
    return MARKET_APPS.get(app_id)


def get_all_apps():
    """Tum uygulamalari liste olarak dondurur."""
    return list(MARKET_APPS.values())


def get_categories():
    """Benzersiz kategori listesi."""
    return sorted({app["category"] for app in MARKET_APPS.values()})


CATEGORY_META = {
    "Veritabanı":          {"icon": "fa-database",        "color": "#6366f1"},
    "Web Sunucu":          {"icon": "fa-globe",           "color": "#00c9a7"},
    "Konteyner & Altyapı": {"icon": "fa-cubes",           "color": "#7c5cfc"},
    "İzleme & Gözlem":     {"icon": "fa-chart-area",      "color": "#ff6b6b"},
    "Güvenlik":            {"icon": "fa-shield-alt",      "color": "#ffa726"},
    "Geliştirme":          {"icon": "fa-code",            "color": "#26c6da"},
    "Web Uygulamalar":     {"icon": "fa-window-maximize", "color": "#ec407a"},
    "AI / Yapay Zeka":     {"icon": "fa-brain",           "color": "#ab47bc"},
    "İletişim":            {"icon": "fa-comments",        "color": "#42a5f5"},
    "Medya":               {"icon": "fa-photo-video",     "color": "#ef5350"},
    "Yedekleme":           {"icon": "fa-hdd",             "color": "#8d6e63"},
}

CATEGORY_ORDER = [
    "Veritabanı", "Web Sunucu", "Konteyner & Altyapı",
    "İzleme & Gözlem", "Güvenlik", "Geliştirme",
    "Web Uygulamalar", "AI / Yapay Zeka", "İletişim",
    "Medya", "Yedekleme",
]


def get_category_meta():
    """Kategori meta bilgilerini dondurur."""
    return CATEGORY_META


def get_apps_by_category():
    """Uygulamalari kategorilere gore gruplanmis olarak dondurur."""
    from collections import OrderedDict
    grouped = OrderedDict()
    for cat in CATEGORY_ORDER:
        if cat not in grouped:
            grouped[cat] = []
    for app in MARKET_APPS.values():
        cat = app.get("category", "Diger")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(app)
    result = []
    for cat_name, apps in grouped.items():
        if not apps:
            continue
        meta = CATEGORY_META.get(cat_name, {"icon": "fa-folder", "color": "#888"})
        result.append({
            "name": cat_name,
            "icon": meta["icon"],
            "color": meta["color"],
            "count": len(apps),
            "apps": apps,
        })
    return result


def build_install_script(app_id, options):
    """Kullanici secenekleriyle kurulum scriptini olusturur."""
    app = get_app(app_id)
    if not app:
        return ""
    script = app.get("install_script", "")
    for key, value in (options or {}).items():
        safe_val = str(value).replace("'", "'\\''")
        safe_val = safe_val.replace("`", "").replace("$(", "").replace("${", "")
        script = script.replace("{{" + key + "}}", safe_val)
    return script


# =====================================================================
# AI STACK BUILDER - Kullanim Senaryosu Paketleri
# =====================================================================

STACK_BUNDLES = [
    {
        "id": "ai-chatbot",
        "name": "AI Chatbot Sunucusu",
        "icon": "fas fa-robot",
        "color": "#ab47bc",
        "emoji": "🤖",
        "description": "Kendi AI chatbot sunucunuzu kurun — Ollama + Open WebUI ile ChatGPT benzeri deneyim.",
        "use_cases": ["chatbot", "ai", "yapay zeka", "llm", "gpt", "sohbet botu"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "ollama", "role": "LLM çalıştırma motoru", "required": True},
            {"id": "open-webui", "role": "Chat arayüzü", "required": True},
            {"id": "nginx", "role": "Ters proxy & SSL", "required": False},
            {"id": "netdata", "role": "Kaynak izleme", "required": False},
        ],
        "estimated_time": "10-15 dk",
        "min_ram": "8 GB",
        "tags": ["AI", "LLM", "Chatbot"],
    },
    {
        "id": "ai-image-gen",
        "name": "AI Görsel Üretici",
        "icon": "fas fa-palette",
        "color": "#e040fb",
        "emoji": "🎨",
        "description": "Metin→görsel dönüştürme sunucusu — Stable Diffusion + ComfyUI ile profesyonel AI sanat.",
        "use_cases": ["görsel", "resim", "stable diffusion", "ai art", "image generation", "midjourney"],
        "apps": [
            {"id": "python3", "role": "Python çalışma ortamı", "required": True},
            {"id": "stable-diffusion-webui", "role": "SD WebUI (AUTOMATIC1111)", "required": True},
            {"id": "comfyui", "role": "Node tabanlı gelişmiş arayüz", "required": False},
            {"id": "nginx", "role": "Ters proxy & SSL", "required": False},
            {"id": "netdata", "role": "GPU/RAM izleme", "required": False},
        ],
        "estimated_time": "20-30 dk",
        "min_ram": "16 GB (GPU önerilir)",
        "tags": ["AI", "Görsel", "Stable Diffusion"],
    },
    {
        "id": "ai-dev-platform",
        "name": "AI Geliştirme Platformu",
        "icon": "fas fa-brain",
        "color": "#7c4dff",
        "emoji": "🧠",
        "description": "Tam bir AI geliştirme ortamı — yerel LLM, API sunucusu, kod editörü, izleme.",
        "use_cases": ["ai geliştirme", "machine learning", "ml", "ai platform", "geliştirme ortamı"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "python3", "role": "Python çalışma ortamı", "required": True},
            {"id": "ollama", "role": "Yerel LLM motoru", "required": True},
            {"id": "localai", "role": "OpenAI uyumlu API", "required": True},
            {"id": "code-server", "role": "Tarayıcıda VS Code", "required": True},
            {"id": "postgresql", "role": "Veritabanı", "required": False},
            {"id": "redis", "role": "Önbellek", "required": False},
            {"id": "grafana", "role": "Metrik dashboard", "required": False},
        ],
        "estimated_time": "15-25 dk",
        "min_ram": "16 GB",
        "tags": ["AI", "Geliştirme", "Platform"],
    },
    {
        "id": "web-hosting",
        "name": "Web Hosting Paketi",
        "icon": "fas fa-globe",
        "color": "#00c9a7",
        "emoji": "🌐",
        "description": "Web sitesi hosting altyapısı — Nginx, PHP, MySQL, SSL, yedekleme.",
        "use_cases": ["web sitesi", "hosting", "web sunucu", "website", "blog", "site"],
        "apps": [
            {"id": "nginx", "role": "Web sunucusu", "required": True},
            {"id": "php", "role": "PHP çalışma ortamı", "required": True},
            {"id": "mysql", "role": "Veritabanı", "required": True},
            {"id": "certbot", "role": "Ücretsiz SSL sertifikası", "required": True},
            {"id": "fail2ban", "role": "Güvenlik (brute-force koruması)", "required": True},
            {"id": "redis", "role": "Önbellek", "required": False},
            {"id": "restic", "role": "Otomatik yedekleme", "required": False},
        ],
        "estimated_time": "8-12 dk",
        "min_ram": "2 GB",
        "tags": ["Web", "Hosting", "LEMP"],
    },
    {
        "id": "wordpress-pro",
        "name": "WordPress Profesyonel",
        "icon": "fab fa-wordpress",
        "color": "#21759b",
        "emoji": "📝",
        "description": "Optimized WordPress kurulumu — cache, SSL, güvenlik, yedekleme dahil.",
        "use_cases": ["wordpress", "blog", "cms", "içerik yönetimi"],
        "apps": [
            {"id": "nginx", "role": "Web sunucusu", "required": True},
            {"id": "php", "role": "PHP çalışma ortamı", "required": True},
            {"id": "mysql", "role": "Veritabanı", "required": True},
            {"id": "wordpress", "role": "WordPress CMS", "required": True},
            {"id": "redis", "role": "Object cache", "required": True},
            {"id": "certbot", "role": "SSL sertifikası", "required": True},
            {"id": "fail2ban", "role": "Güvenlik", "required": False},
            {"id": "restic", "role": "Yedekleme", "required": False},
        ],
        "estimated_time": "10-15 dk",
        "min_ram": "2 GB",
        "tags": ["WordPress", "CMS", "Blog"],
    },
    {
        "id": "ecommerce",
        "name": "E-Ticaret Altyapısı",
        "icon": "fas fa-shopping-cart",
        "color": "#ff6f00",
        "emoji": "🛒",
        "description": "E-ticaret sunucusu — veritabanı, cache, web sunucu, güvenlik, izleme.",
        "use_cases": ["e-ticaret", "ecommerce", "mağaza", "online satış", "shop"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "nginx", "role": "Web sunucusu & yük dengeleyici", "required": True},
            {"id": "postgresql", "role": "Veritabanı", "required": True},
            {"id": "redis", "role": "Oturum & önbellek", "required": True},
            {"id": "certbot", "role": "SSL sertifikası", "required": True},
            {"id": "fail2ban", "role": "Güvenlik", "required": True},
            {"id": "grafana", "role": "Performans izleme", "required": False},
            {"id": "restic", "role": "Yedekleme", "required": False},
        ],
        "estimated_time": "12-18 dk",
        "min_ram": "4 GB",
        "tags": ["E-Ticaret", "Web", "Veritabanı"],
    },
    {
        "id": "devops-pipeline",
        "name": "DevOps Pipeline",
        "icon": "fas fa-infinity",
        "color": "#6366f1",
        "emoji": "⚙️",
        "description": "CI/CD ve deployment pipeline — Git, Docker, izleme, otomasyon.",
        "use_cases": ["devops", "ci/cd", "deployment", "pipeline", "otomasyon"],
        "apps": [
            {"id": "docker", "role": "Konteyner çalıştırma", "required": True},
            {"id": "docker-compose", "role": "Çoklu servis yönetimi", "required": True},
            {"id": "git", "role": "Versiyon kontrol", "required": True},
            {"id": "gitea", "role": "Self-hosted Git sunucusu", "required": True},
            {"id": "portainer", "role": "Docker yönetim paneli", "required": True},
            {"id": "nginx", "role": "Reverse proxy", "required": False},
            {"id": "prometheus", "role": "Metrik toplama", "required": False},
            {"id": "grafana", "role": "Dashboard", "required": False},
        ],
        "estimated_time": "12-18 dk",
        "min_ram": "4 GB",
        "tags": ["DevOps", "CI/CD", "Docker"],
    },
    {
        "id": "monitoring-stack",
        "name": "İzleme & Gözlem Merkezi",
        "icon": "fas fa-chart-area",
        "color": "#ff6b6b",
        "emoji": "📊",
        "description": "Tam izleme altyapısı — metrikler, loglar, uyarılar, uptime kontrolü.",
        "use_cases": ["izleme", "monitoring", "metrik", "log", "alarm", "gözlem"],
        "apps": [
            {"id": "prometheus", "role": "Metrik toplama", "required": True},
            {"id": "grafana", "role": "Görselleştirme", "required": True},
            {"id": "netdata", "role": "Gerçek zamanlı izleme", "required": True},
            {"id": "uptime-kuma", "role": "Uptime kontrolü", "required": True},
            {"id": "docker", "role": "Konteyner altyapısı", "required": False},
        ],
        "estimated_time": "10-15 dk",
        "min_ram": "4 GB",
        "tags": ["İzleme", "Metrik", "Dashboard"],
    },
    {
        "id": "team-collaboration",
        "name": "Takım İşbirliği Platformu",
        "icon": "fas fa-users",
        "color": "#42a5f5",
        "emoji": "👥",
        "description": "Takım iletişim ve dosya paylaşımı — kendi Slack + Google Drive'ınız.",
        "use_cases": ["takım", "iletişim", "mesajlaşma", "dosya paylaşımı", "işbirliği", "chat"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "mattermost", "role": "Takım mesajlaşma (Slack alternatifi)", "required": True},
            {"id": "nextcloud", "role": "Dosya paylaşımı (Drive alternatifi)", "required": True},
            {"id": "gitea", "role": "Kod deposu", "required": False},
            {"id": "nginx", "role": "Reverse proxy & SSL", "required": False},
            {"id": "certbot", "role": "SSL sertifikası", "required": False},
        ],
        "estimated_time": "10-15 dk",
        "min_ram": "4 GB",
        "tags": ["İletişim", "Dosya", "Takım"],
    },
    {
        "id": "media-server",
        "name": "Medya Sunucusu",
        "icon": "fas fa-film",
        "color": "#ef5350",
        "emoji": "🎬",
        "description": "Kendi Netflix + Google Photos'unuzu kurun — medya streaming ve fotoğraf yönetimi.",
        "use_cases": ["medya", "film", "video", "müzik", "fotoğraf", "netflix", "streaming"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "jellyfin", "role": "Video streaming (Netflix alternatifi)", "required": True},
            {"id": "photoprism", "role": "Fotoğraf yönetimi (Photos alternatifi)", "required": True},
            {"id": "nginx", "role": "Reverse proxy", "required": False},
            {"id": "restic", "role": "Medya yedekleme", "required": False},
        ],
        "estimated_time": "8-12 dk",
        "min_ram": "4 GB",
        "tags": ["Medya", "Streaming", "Fotoğraf"],
    },
    {
        "id": "security-hardening",
        "name": "Güvenlik Sertleştirme",
        "icon": "fas fa-shield-alt",
        "color": "#ffa726",
        "emoji": "🛡️",
        "description": "Sunucu güvenlik paketi — firewall, saldırı önleme, VPN, SSL.",
        "use_cases": ["güvenlik", "firewall", "vpn", "ssl", "koruma", "hardening"],
        "apps": [
            {"id": "ufw", "role": "Güvenlik duvarı", "required": True},
            {"id": "fail2ban", "role": "Brute-force koruması", "required": True},
            {"id": "crowdsec", "role": "Topluluk tabanlı IP koruması", "required": True},
            {"id": "certbot", "role": "SSL sertifikaları", "required": True},
            {"id": "wireguard", "role": "VPN tüneli", "required": False},
        ],
        "estimated_time": "5-10 dk",
        "min_ram": "1 GB",
        "tags": ["Güvenlik", "Firewall", "VPN"],
    },
    {
        "id": "data-analytics",
        "name": "Veri Analitik Platformu",
        "icon": "fas fa-chart-pie",
        "color": "#26a69a",
        "emoji": "📈",
        "description": "Veri toplama, depolama ve görselleştirme — ClickHouse + Grafana + Metabase.",
        "use_cases": ["analitik", "veri", "data", "analytics", "bi", "rapor"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "clickhouse", "role": "OLAP veritabanı", "required": True},
            {"id": "postgresql", "role": "İlişkisel veritabanı", "required": True},
            {"id": "grafana", "role": "Görselleştirme", "required": True},
            {"id": "redis", "role": "Önbellek", "required": False},
            {"id": "nginx", "role": "Reverse proxy", "required": False},
        ],
        "estimated_time": "12-18 dk",
        "min_ram": "8 GB",
        "tags": ["Analitik", "Veri", "BI"],
    },
    {
        "id": "ai-startup",
        "name": "AI Startup Paketi",
        "icon": "fas fa-rocket",
        "color": "#ff5722",
        "emoji": "🚀",
        "description": "AI startup altyapısı — LLM, RAG, görsel arayüz, API, veritabanı, izleme.",
        "use_cases": ["startup", "ai startup", "saas", "ai saas", "girişim"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "ollama", "role": "Yerel LLM motoru", "required": True},
            {"id": "dify", "role": "LLM uygulama platformu", "required": True},
            {"id": "postgresql", "role": "Veritabanı", "required": True},
            {"id": "redis", "role": "Önbellek & kuyruk", "required": True},
            {"id": "nginx", "role": "Reverse proxy & SSL", "required": True},
            {"id": "certbot", "role": "SSL sertifikası", "required": False},
            {"id": "grafana", "role": "İzleme dashboard", "required": False},
            {"id": "restic", "role": "Yedekleme", "required": False},
        ],
        "estimated_time": "20-30 dk",
        "min_ram": "16 GB",
        "tags": ["AI", "Startup", "SaaS"],
    },
    {
        "id": "ai-code-assistant",
        "name": "AI Kod Asistanı",
        "icon": "fas fa-laptop-code",
        "color": "#00bcd4",
        "emoji": "💻",
        "description": "Kendi GitHub Copilot'unuzu kurun — Tabby + VS Code + yerel LLM.",
        "use_cases": ["kod", "code", "copilot", "ai coding", "programlama", "geliştirici"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "tabby", "role": "AI kod tamamlama motoru", "required": True},
            {"id": "code-server", "role": "Tarayıcıda VS Code", "required": True},
            {"id": "ollama", "role": "Yerel LLM (chat)", "required": False},
            {"id": "git", "role": "Versiyon kontrol", "required": True},
            {"id": "nginx", "role": "Reverse proxy", "required": False},
        ],
        "estimated_time": "10-15 dk",
        "min_ram": "8 GB",
        "tags": ["AI", "Kod", "Copilot"],
    },
    {
        "id": "ai-doc-assistant",
        "name": "AI Doküman Asistanı",
        "icon": "fas fa-file-alt",
        "color": "#795548",
        "emoji": "📄",
        "description": "Belgelerinizle konuşun — PrivateGPT + RAG, %100 özel ve yerel.",
        "use_cases": ["doküman", "belge", "rag", "pdf", "özel ai", "private gpt"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "ollama", "role": "LLM motoru", "required": True},
            {"id": "privateGPT", "role": "Doküman AI asistanı", "required": True},
            {"id": "searxng", "role": "Web arama entegrasyonu", "required": False},
            {"id": "nginx", "role": "Reverse proxy", "required": False},
        ],
        "estimated_time": "15-20 dk",
        "min_ram": "8 GB",
        "tags": ["AI", "Doküman", "RAG"],
    },
    {
        "id": "ai-nocode-builder",
        "name": "No-Code AI Builder",
        "icon": "fas fa-wand-magic-sparkles",
        "color": "#9c27b0",
        "emoji": "✨",
        "description": "Kodsuz AI uygulama oluşturucu — Flowise + Dify + Langflow ile görsel AI.",
        "use_cases": ["no-code", "kodsuz", "ai builder", "otomasyon", "görsel ai"],
        "apps": [
            {"id": "docker", "role": "Konteyner altyapısı", "required": True},
            {"id": "flowise", "role": "Görsel LLM zincir oluşturucu", "required": True},
            {"id": "langflow", "role": "LangChain görsel editörü", "required": True},
            {"id": "dify", "role": "LLM uygulama platformu", "required": False},
            {"id": "ollama", "role": "Yerel LLM motoru", "required": True},
            {"id": "nginx", "role": "Reverse proxy & SSL", "required": False},
        ],
        "estimated_time": "12-18 dk",
        "min_ram": "8 GB",
        "tags": ["AI", "No-Code", "Builder"],
    },
]


def get_stack_bundles():
    """Tum stack paketlerini dondurur."""
    return STACK_BUNDLES


def get_stack_by_id(stack_id):
    """ID'ye gore stack paketi dondurur."""
    for s in STACK_BUNDLES:
        if s["id"] == stack_id:
            return s
    return None


def search_stacks(query):
    """Kullanici sorgusuna gore uygun stack'leri bulur."""
    if not query:
        return STACK_BUNDLES
    q = query.lower().strip()
    scored = []
    for stack in STACK_BUNDLES:
        score = 0
        # Isim eslesme
        if q in stack["name"].lower():
            score += 10
        # Aciklama eslesme
        if q in stack["description"].lower():
            score += 5
        # Use-case eslesme
        for uc in stack.get("use_cases", []):
            if q in uc.lower() or uc.lower() in q:
                score += 8
        # Tag eslesme
        for tag in stack.get("tags", []):
            if q in tag.lower() or tag.lower() in q:
                score += 6
        # Kelime kelime eslesme
        words = q.split()
        for w in words:
            if len(w) < 2:
                continue
            if w in stack["name"].lower():
                score += 3
            if w in stack["description"].lower():
                score += 2
            for uc in stack.get("use_cases", []):
                if w in uc.lower():
                    score += 4
        if score > 0:
            scored.append((score, stack))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored]


def get_stack_apps_detail(stack_id):
    """Stack'teki uygulamalarin detaylarini dondurur."""
    stack = get_stack_by_id(stack_id)
    if not stack:
        return None
    result = []
    for item in stack.get("apps", []):
        app = get_app(item["id"])
        if app:
            result.append({
                "id": item["id"],
                "name": app["name"],
                "icon": app.get("icon", "fa-cube"),
                "role": item.get("role", ""),
                "required": item.get("required", False),
                "category": app.get("category", ""),
                "description": app.get("description", ""),
                "options": app.get("options", []),
            })
    return {
        "stack": {k: v for k, v in stack.items() if k != "apps"},
        "apps": result,
    }


# ──────────────────────────────────────────────────────────────────
# EmareCode ile Yazılan Projeler
# ──────────────────────────────────────────────────────────────────

EMARE_PROJECTS = [
    # ─── Production (%100) ───
    {
        "id": "emare-asistan",
        "name": "Emare Asistan",
        "icon": "fas fa-headset",
        "color": "#6366f1",
        "description": "Multi-tenant SaaS AI müşteri hizmetleri platformu — WhatsApp, Instagram, Telegram entegrasyonu.",
        "status": "production",
        "progress": 100,
        "tech": ["FastAPI", "Python", "Gemini AI"],
        "category": "AI & Chatbot",
        "url": "",
    },
    {
        "id": "emarecloud",
        "name": "EmareCloud",
        "icon": "fas fa-cloud",
        "color": "#00c9a7",
        "description": "Multi-tenant altyapı yönetim paneli — SSH, firewall, LXD, market, izleme.",
        "status": "production",
        "progress": 100,
        "tech": ["Flask", "Python", "SQLite"],
        "category": "Altyapı & DevOps",
        "url": "",
    },
    {
        "id": "emare-finance",
        "name": "Emare Finance",
        "icon": "fas fa-coins",
        "color": "#f59e0b",
        "description": "Multi-tenant SaaS POS + işletme yönetim yazılımı — e-Fatura, muhasebe, stok.",
        "status": "production",
        "progress": 100,
        "tech": ["Laravel 12", "PHP 8.4", "MariaDB"],
        "category": "Finans & POS",
        "url": "",
    },
    {
        "id": "emarebot",
        "name": "Emarebot",
        "icon": "fas fa-robot",
        "color": "#ec4899",
        "description": "Trendyol kozmetik mağazası müşteri soru yanıtlama masaüstü uygulaması.",
        "status": "production",
        "progress": 100,
        "tech": ["Python 3.12", "Tkinter", "Trendyol API"],
        "category": "E-Ticaret",
        "url": "",
    },
    {
        "id": "emare-makale",
        "name": "Emare Makale",
        "icon": "fas fa-newspaper",
        "color": "#8b5cf6",
        "description": "Otomatik Türkçe makale üretim + yönetim + paylaşım — Reddit/SEO entegrasyonu.",
        "status": "production",
        "progress": 100,
        "tech": ["Python 3.9", "Flask 3.0", "SQLite"],
        "category": "İçerik & SEO",
        "url": "",
    },
    {
        "id": "emare-team",
        "name": "Emare Team",
        "icon": "fas fa-users",
        "color": "#14b8a6",
        "description": "Emare ekibi için iç proje ve görev yönetim uygulaması — SPA, drag-and-drop.",
        "status": "production",
        "progress": 100,
        "tech": ["Flask", "SQLite", "Vanilla JS"],
        "category": "Proje Yönetimi",
        "url": "",
    },
    {
        "id": "emarecode",
        "name": "Emare Code",
        "icon": "fas fa-code",
        "color": "#3b82f6",
        "description": "Cross-platform AI kod üretici — Multi-AI failover, doğal dil ile kodlama.",
        "status": "production",
        "progress": 100,
        "tech": ["Python", "FastAPI", "Gemini AI"],
        "category": "Geliştirme Araçları",
        "url": "",
    },
    {
        "id": "emare-dashboard",
        "name": "Emare Dashboard",
        "icon": "fas fa-tachometer-alt",
        "color": "#06b6d4",
        "description": "Tüm Emare ekosistemini izleyen Flask tabanlı web kontrol paneli.",
        "status": "production",
        "progress": 100,
        "tech": ["Python 3", "Flask", "Jinja2"],
        "category": "Altyapı & DevOps",
        "url": "",
    },
    # ─── Ready (%90) ───
    {
        "id": "emaredesk",
        "name": "EmareDesk",
        "icon": "fas fa-desktop",
        "color": "#a78bfa",
        "description": "Python + Web tabanlı uzak masaüstü yazılımı — WebSocket ekran paylaşımı.",
        "status": "ready",
        "progress": 90,
        "tech": ["Python", "WebSocket", "Pillow"],
        "category": "Uzak Erişim",
        "url": "",
    },
    {
        "id": "yazilim-ekibi",
        "name": "Hive Coordinator",
        "icon": "fas fa-project-diagram",
        "color": "#f97316",
        "description": "9 Milyar düğümlü hiyerarşik yazılım ekibi koordinasyon sistemi.",
        "status": "ready",
        "progress": 90,
        "tech": ["Python 3.11", "FastAPI", "PostgreSQL 16"],
        "category": "Proje Yönetimi",
        "url": "",
    },
    {
        "id": "emarekatip",
        "name": "Emare Katip",
        "icon": "fas fa-file-alt",
        "color": "#10b981",
        "description": "KINGSTON disk veri toplayıcı ve analizcisi — otomatik proje arşivleme.",
        "status": "ready",
        "progress": 90,
        "tech": ["Python", "Flask", "pytest"],
        "category": "Veri Yönetimi",
        "url": "",
    },
    {
        "id": "emaregithup",
        "name": "Emare GitHub",
        "icon": "fab fa-github",
        "color": "#6366f1",
        "description": "Tüm Emare projelerini toplu olarak GitHub'a repo oluşturup push eden otomasyon.",
        "status": "ready",
        "progress": 90,
        "tech": ["Python 3", "subprocess", "urllib"],
        "category": "Geliştirme Araçları",
        "url": "",
    },
    # ─── Development (değişken %) ───
    {
        "id": "emare-pos",
        "name": "Emare POS",
        "icon": "fas fa-cash-register",
        "color": "#ef4444",
        "description": "Restoran/kafe için web tabanlı POS + adisyon yönetim sistemi.",
        "status": "development",
        "progress": 65,
        "tech": ["Laravel 12", "PHP 8.2", "SQLite"],
        "category": "Finans & POS",
        "url": "",
    },
    {
        "id": "emaresetup",
        "name": "EmareSetup",
        "icon": "fas fa-magic",
        "color": "#8b5cf6",
        "description": "AI destekli yazılım fabrikası CLI — doğal dil ile modül üretimi.",
        "status": "development",
        "progress": 55,
        "tech": ["Python", "FastAPI", "React 19"],
        "category": "Geliştirme Araçları",
        "url": "",
    },
    {
        "id": "emarehup",
        "name": "EmareHup",
        "icon": "fas fa-industry",
        "color": "#06b6d4",
        "description": "Yazılım fabrikası ana üssü + DevM otonom geliştirme platformu.",
        "status": "development",
        "progress": 45,
        "tech": ["Python", "Node.js", "Gemini"],
        "category": "Geliştirme Araçları",
        "url": "",
    },
    {
        "id": "emareoracle",
        "name": "ZeusDB",
        "icon": "fas fa-database",
        "color": "#f59e0b",
        "description": "C dilinde sıfırdan yazılan tam ilişkisel veritabanı motoru — B+Tree, WAL.",
        "status": "development",
        "progress": 35,
        "tech": ["C (C11)", "B+Tree", "WAL"],
        "category": "Veritabanı",
        "url": "",
    },
    {
        "id": "siberemare",
        "name": "SiberEmare",
        "icon": "fas fa-user-secret",
        "color": "#dc2626",
        "description": "Otomatik penetrasyon testi raporlama pipeline — LangGraph multi-agent.",
        "status": "development",
        "progress": 40,
        "tech": ["Python 3.11", "LangGraph", "Claude 3.5"],
        "category": "Güvenlik",
        "url": "",
    },
    {
        "id": "emare-log",
        "name": "Emare Log",
        "icon": "fas fa-network-wired",
        "color": "#0ea5e9",
        "description": "ISS şirketleri için CRM + ERP + NOC paneli — MikroTik, 5651 log.",
        "status": "development",
        "progress": 50,
        "tech": ["Laravel 12", "PHP 8.2", "Bootstrap 5"],
        "category": "Altyapı & DevOps",
        "url": "",
    },
    {
        "id": "emareulak",
        "name": "Emare Ulak",
        "icon": "fas fa-satellite-dish",
        "color": "#7c3aed",
        "description": "Browser extension + WebSocket server — Chat izleyici ve analiz aracı.",
        "status": "development",
        "progress": 45,
        "tech": ["Node.js", "Express.js", "WebSocket"],
        "category": "İletişim",
        "url": "",
    },
    {
        "id": "emareads",
        "name": "Emare Ads",
        "icon": "fas fa-ad",
        "color": "#f43f5e",
        "description": "AI-powered tarayıcı eklentisi — reklam yönetimi ve analiz.",
        "status": "development",
        "progress": 35,
        "tech": ["TypeScript", "React", "Chrome API"],
        "category": "Pazarlama",
        "url": "",
    },
    {
        "id": "emareai",
        "name": "Emare AI",
        "icon": "fas fa-brain",
        "color": "#a855f7",
        "description": "Kendi yapay zeka motorumuz — LLaMA/Mistral fine-tuning, self-hosted AI.",
        "status": "development",
        "progress": 30,
        "tech": ["PyTorch", "LLaMA", "Mistral"],
        "category": "AI & Chatbot",
        "url": "",
    },
    {
        "id": "emareos",
        "name": "Emare OS",
        "icon": "fas fa-microchip",
        "color": "#1e3a5f",
        "description": "NeuroKernel — AI-native işletim sistemi, Ring 0 AI çekirdeği.",
        "status": "development",
        "progress": 20,
        "tech": ["Rust", "QEMU", "NeuroKernel"],
        "category": "İşletim Sistemi",
        "url": "",
    },
    {
        "id": "emarecc",
        "name": "Emare CC",
        "icon": "fas fa-phone-alt",
        "color": "#0891b2",
        "description": "OpenCC Çağrı Merkezi — Asterisk, tahsilat, screen pop, wallboard.",
        "status": "development",
        "progress": 40,
        "tech": ["Node.js", "Express.js", "Asterisk"],
        "category": "İletişim",
        "url": "",
    },
    {
        "id": "emare-vscode-asistan",
        "name": "Emare VS Code Asistan",
        "icon": "fas fa-puzzle-piece",
        "color": "#2563eb",
        "description": "Tüm VS Code kurulumlarını merkezi olarak senkronize eden asistan.",
        "status": "development",
        "progress": 50,
        "tech": ["Python", "Rich", "Watchdog"],
        "category": "Geliştirme Araçları",
        "url": "",
    },
    {
        "id": "emareflow",
        "name": "Emare Flow",
        "icon": "fas fa-project-diagram",
        "color": "#22c55e",
        "description": "n8n benzeri React Flow tabanlı görsel iş akışı otomasyonu.",
        "status": "development",
        "progress": 35,
        "tech": ["React 19", "React Flow v12", "FastAPI"],
        "category": "Otomasyon",
        "url": "",
    },
    {
        "id": "emaresuperapp",
        "name": "Emare SuperApp",
        "icon": "fas fa-rocket",
        "color": "#e11d48",
        "description": "Tüm Emare hizmetlerini tek çatı altında birleştiren süper uygulama.",
        "status": "development",
        "progress": 25,
        "tech": ["FastAPI", "Python", "React"],
        "category": "Platform",
        "url": "",
    },
    {
        "id": "emarefree",
        "name": "EmareFree",
        "icon": "fas fa-gift",
        "color": "#84cc16",
        "description": "Dünya genelindeki ücretsiz hizmetleri otomatik araştıran toplama aracı.",
        "status": "development",
        "progress": 45,
        "tech": ["Python", "requests", "BeautifulSoup"],
        "category": "Veri Yönetimi",
        "url": "",
    },
    {
        "id": "emareaplincedesk",
        "name": "Emare Aplince Desk",
        "icon": "fas fa-tools",
        "color": "#f97316",
        "description": "Çok şubeli teknik servis ve cihaz onarım yönetim sistemi.",
        "status": "development",
        "progress": 55,
        "tech": ["PHP 8.2", "Laravel 12", "Laravel Breeze"],
        "category": "İş Yönetimi",
        "url": "",
    },
    {
        "id": "emaregoogle",
        "name": "Emare Google",
        "icon": "fab fa-google",
        "color": "#4285f4",
        "description": "Google servisleri için Playwright tabanlı tarayıcı otomasyon aracı.",
        "status": "development",
        "progress": 30,
        "tech": ["Node.js", "Playwright", "Puppeteer"],
        "category": "Otomasyon",
        "url": "",
    },
    # ─── Planning (%5-15) ───
    {
        "id": "emareflux",
        "name": "Emare Flux",
        "icon": "fas fa-stream",
        "color": "#6366f1",
        "description": "Veri akışı ve olay tabanlı iş süreçleri otomasyon motoru.",
        "status": "planning",
        "progress": 10,
        "tech": [],
        "category": "Otomasyon",
        "url": "",
    },
    {
        "id": "emareidi",
        "name": "Emare IDI",
        "icon": "fas fa-id-card",
        "color": "#0ea5e9",
        "description": "Merkezi kimlik ve erişim yönetimi (Identity Provider) — SSO, OAuth2.",
        "status": "planning",
        "progress": 10,
        "tech": [],
        "category": "Güvenlik",
        "url": "",
    },
    {
        "id": "emaresebil",
        "name": "Emare Sebil",
        "icon": "fas fa-car",
        "color": "#22c55e",
        "description": "Araç paylaşımı ve mikromobilite platformu — carpooling, e-scooter.",
        "status": "planning",
        "progress": 5,
        "tech": [],
        "category": "Ulaşım",
        "url": "",
    },
    {
        "id": "emaretedarik",
        "name": "Emare Tedarik",
        "icon": "fas fa-truck",
        "color": "#f59e0b",
        "description": "Tedarik zinciri yönetim sistemi — tedarikçi, sipariş, stok takibi.",
        "status": "planning",
        "progress": 8,
        "tech": [],
        "category": "İş Yönetimi",
        "url": "",
    },
    {
        "id": "girhup",
        "name": "Girhup",
        "icon": "fas fa-code-branch",
        "color": "#8b5cf6",
        "description": "Git repo tarayıcı ve kod inceleme arayüzü — yerel/uzak repo desteği.",
        "status": "planning",
        "progress": 10,
        "tech": [],
        "category": "Geliştirme Araçları",
        "url": "",
    },
    {
        "id": "sosyal-medya-yonetim",
        "name": "Sosyal Medya Yönetim",
        "icon": "fas fa-share-alt",
        "color": "#ec4899",
        "description": "Sosyal medya hesaplarının merkezi yönetimi, içerik planlama ve analiz.",
        "status": "planning",
        "progress": 5,
        "tech": [],
        "category": "Pazarlama",
        "url": "",
    },
]


def get_emare_projects():
    """EmareCode ile yazılan projeleri kategoriye göre gruplandırarak döndürür."""

    # Durum sıralama önceliği
    status_order = {"production": 0, "ready": 1, "development": 2, "planning": 3}

    # Projeleri duruma göre sırala
    sorted_projects = sorted(
        EMARE_PROJECTS,
        key=lambda p: (status_order.get(p["status"], 99), -p["progress"]),
    )

    # İstatistikler
    total = len(EMARE_PROJECTS)
    production_count = sum(1 for p in EMARE_PROJECTS if p["status"] == "production")
    development_count = sum(1 for p in EMARE_PROJECTS if p["status"] == "development")
    ready_count = sum(1 for p in EMARE_PROJECTS if p["status"] == "ready")
    planning_count = sum(1 for p in EMARE_PROJECTS if p["status"] == "planning")
    avg_progress = round(sum(p["progress"] for p in EMARE_PROJECTS) / total) if total else 0

    return {
        "projects": sorted_projects,
        "stats": {
            "total": total,
            "production": production_count,
            "ready": ready_count,
            "development": development_count,
            "planning": planning_count,
            "avg_progress": avg_progress,
        },
    }
