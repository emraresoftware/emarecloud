#!/usr/bin/env python3
"""
Emare Failover Monitor — Mac'te çalışır (cron: */2 * * * *)
DC-1 veya DC-2 çökerse DNS'i otomatik değiştirir.
Log: ~/Library/Logs/emare_failover.log
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── Yapılandırma ──────────────────────────────────────────────
CF_TOKEN  = "YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9"
CF_ZONE   = "a72e4fe4787b786fb91d41a3491949eb"
DC1_IP    = "185.189.54.104"   # Ana sunucu
DC2_IP    = "77.92.152.3"      # Yedek 1
TIMEOUT   = 8                  # Saniye
THRESHOLD = 3                  # Ardışık hata → failover

STATE_FILE = Path.home() / ".emare_failover_state.json"
LOG_FILE   = Path.home() / "Library/Logs/emare_failover.log"

# DC-1 çökerse → DC-2'ye taşı
DC1_RECORDS = {
    "emarecloud.tr":         ("dbb5a07502c3768d13bc720810949484", True),
    "api.emarecloud.tr":     ("5aaf898780a7f34c8edeb41dc9797f70", True),
    "token.emarecloud.tr":   ("503be16263bdbf47c50589c298ae5404", True),
    "webdizayn.emarecloud.tr": ("2e23f0fc369b30280d0b3769ccb68b27", True),
}

# DC-2 çökerse → DC-1'e taşı
DC2_RECORDS = {
    "asistan.emarecloud.tr": ("f94b73ab3e3be741180c580d6c43531b", True),
    "finans.emarecloud.tr":  ("b8abf8d44eea7b1b00e5228c873a9ed6", False),
}

# ── Yardımcılar ───────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "dc1_fails": 0, "dc1_active": DC1_IP,
        "dc2_fails": 0, "dc2_active": DC2_IP,
    }

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def check_health(ip: str, host: str) -> bool:
    """TCP + HTTP çift kontrol: port 80 açık ve nginx yanıt veriyor mu?"""
    # 1) TCP bağlantısı
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        result = sock.connect_ex((ip, 80))
        sock.close()
        if result != 0:
            return False
    except Exception:
        return False

    # 2) HTTP yanıtı (301 dahil herhangi bir HTTP yanıtı = sunucu canlı)
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None  # yönlendirmeyi takip etme

        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(
            f"http://{ip}/health",
            headers={"Host": host, "User-Agent": "EmareFO/1.0"},
        )
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                return r.status < 500
        except urllib.error.HTTPError as e:
            return e.code < 500  # 4xx bile olsa sunucu ayakta
    except Exception:
        return True  # TCP bağlandı ama HTTP parse hatası → sunucu canlı sayılır

def update_dns(records: dict, target_ip: str):
    for name, (record_id, proxied) in records.items():
        data = json.dumps({
            "type": "A", "name": name,
            "content": target_ip, "ttl": 60,
            "proxied": proxied,
        }).encode()
        req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}/dns_records/{record_id}",
            data=data, method="PUT",
            headers={
                "Authorization": f"Bearer {CF_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read())
                status = "OK" if resp.get("success") else resp.get("errors")
                log(f"  DNS: {name} → {target_ip} [{status}]")
        except Exception as e:
            log(f"  DNS hata: {name} → {e}")

# ── Ana mantık ────────────────────────────────────────────────
state = load_state()

# --- DC-1 kontrolü ---
dc1_up = check_health(DC1_IP, "emarecloud.tr")
if dc1_up:
    if state["dc1_active"] != DC1_IP:
        log("✅ DC-1 geri geldi! DNS DC-1'e döndürülüyor...")
        update_dns(DC1_RECORDS, DC1_IP)
        state["dc1_active"] = DC1_IP
    state["dc1_fails"] = 0
    log(f"✅ DC-1 OK (aktif: {state['dc1_active']})")
else:
    state["dc1_fails"] += 1
    log(f"❌ DC-1 erişilemiyor (hata: {state['dc1_fails']}/{THRESHOLD})")
    if state["dc1_fails"] >= THRESHOLD and state["dc1_active"] == DC1_IP:
        log(f"🚨 FAILOVER: DC-1 → DC-2 ({DC2_IP})")
        update_dns(DC1_RECORDS, DC2_IP)
        state["dc1_active"] = DC2_IP
        log("✅ Failover tamamlandı — trafik DC-2'de")

# --- DC-2 kontrolü ---
dc2_up = check_health(DC2_IP, "asistan.emarecloud.tr")
if dc2_up:
    if state["dc2_active"] != DC2_IP:
        log("✅ DC-2 geri geldi! DNS DC-2'ye döndürülüyor...")
        update_dns(DC2_RECORDS, DC2_IP)
        state["dc2_active"] = DC2_IP
    state["dc2_fails"] = 0
    log(f"✅ DC-2 OK (aktif: {state['dc2_active']})")
else:
    state["dc2_fails"] += 1
    log(f"❌ DC-2 erişilemiyor (hata: {state['dc2_fails']}/{THRESHOLD})")
    if state["dc2_fails"] >= THRESHOLD and state["dc2_active"] == DC2_IP:
        log(f"🚨 FAILOVER: DC-2 → DC-1 ({DC1_IP})")
        update_dns(DC2_RECORDS, DC1_IP)
        state["dc2_active"] = DC1_IP
        log("✅ Failover tamamlandı — DC-2 trafiği DC-1'de")

save_state(state)
