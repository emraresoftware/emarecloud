#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/emaresecurityos"
VENV_DIR="/opt/emaresecurityos-venv"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"

if [[ ! -d "$APP_DIR" ]]; then
  mkdir -p "$APP_DIR"
fi

cd "$APP_DIR"

if [[ ! -d .git ]]; then
  if [[ -z "$REPO_URL" ]]; then
    echo "REPO_URL bos. Ilk kurulumda REPO_URL verin." >&2
    exit 1
  fi
  git clone -b "$BRANCH" "$REPO_URL" .
else
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

# Paket duzeni: runtime'da emarefirewall.* importlari icin klasor yapisini olustur.
mkdir -p "$APP_DIR/emarefirewall"
cp -f __init__.py manager.py routes.py ssh.py cli.py __main__.py config.py cache.py store.py tenants.py law5651.py rmm.py "$APP_DIR/emarefirewall/"
rm -rf "$APP_DIR/emarefirewall/templates"
cp -R templates "$APP_DIR/emarefirewall/"

"$VENV_DIR/bin/pip" install -e .

mkdir -p "$APP_DIR/data"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp deploy/.env.example "$APP_DIR/.env"
  echo ".env olusturuldu. Secret degerleri duzenleyin." >&2
fi

cp deploy/emaresecurityos.service /etc/systemd/system/emaresecurityos.service
cp deploy/emaresecurityos.emarecloud.tr.conf /etc/nginx/conf.d/emaresecurityos.emarecloud.tr.conf

systemctl daemon-reload
systemctl enable --now emaresecurityos.service
nginx -t
systemctl reload nginx

echo "OK: Emare Security OS deploy tamamlandi"
