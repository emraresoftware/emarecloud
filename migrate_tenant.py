#!/usr/bin/env python3
"""
EmareCloud — Tenant Migration Script
Mevcut verileri varsayılan organizasyona atar ve yeni kolonları ekler.
Güvenli: birden fazla kez çalıştırılabilir (idempotent).
"""

import sqlite3
import sys
import os

DB_PATH = os.environ.get('DB_PATH', 'instance/emarecloud.db')

def get_db():
    """SQLite bağlantısı döndürür."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn, table, column, col_type='INTEGER', default=None):
    """Kolonu yoksa ekler. Varsa atlar."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row['name'] for row in cursor.fetchall()]
    if column not in columns:
        default_clause = f" DEFAULT {default}" if default is not None else ""
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")
        print(f"  ✅ {table}.{column} kolonu eklendi")
    else:
        print(f"  ⏭️  {table}.{column} zaten mevcut")


def migrate():
    """Ana migrasyon fonksiyonu."""
    if not os.path.exists(DB_PATH):
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        sys.exit(1)

    conn = get_db()
    print(f"\n🔧 EmareCloud Tenant Migration")
    print(f"📂 DB: {os.path.abspath(DB_PATH)}\n")

    # ═══════════════════════════════════════════════
    # 1. Yeni org_id kolonlarını ekle
    # ═══════════════════════════════════════════════
    print("📋 Adım 1: Eksik org_id kolonları ekleniyor...")
    tables_needing_org_id = [
        'alert_rules',
        'webhook_configs',
        'scheduled_tasks',
        'backup_profiles',
        'audit_logs',
    ]
    for table in tables_needing_org_id:
        try:
            ensure_column(conn, table, 'org_id', 'INTEGER')
        except Exception as e:
            print(f"  ⚠️  {table}: {e}")

    conn.commit()

    # ═══════════════════════════════════════════════
    # 2. "Emare" varsayılan organizasyonu oluştur veya bul
    # ═══════════════════════════════════════════════
    print("\n📋 Adım 2: Varsayılan organizasyon kontrol ediliyor...")

    row = conn.execute("SELECT id FROM organizations WHERE slug = 'emare' LIMIT 1").fetchone()
    if row:
        org_id = row['id']
        print(f"  ⏭️  'Emare' organizasyonu zaten mevcut (id={org_id})")
    else:
        # İlk super_admin kullanıcısını bul
        admin = conn.execute(
            "SELECT id FROM users WHERE role = 'super_admin' ORDER BY id LIMIT 1"
        ).fetchone()
        owner_id = admin['id'] if admin else 1

        conn.execute("""
            INSERT INTO organizations (name, slug, owner_id, is_active, settings_json, created_at, updated_at)
            VALUES ('Emare', 'emare', ?, 1, '{}', datetime('now'), datetime('now'))
        """, (owner_id,))
        org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"  ✅ 'Emare' organizasyonu oluşturuldu (id={org_id})")

    conn.commit()

    # ═══════════════════════════════════════════════
    # 3. org_id=NULL olan tüm kayıtları varsayılan org'a ata
    # ═══════════════════════════════════════════════
    print(f"\n📋 Adım 3: org_id=NULL kayıtlar → Emare (id={org_id}) atanıyor...")

    # Users
    r = conn.execute("UPDATE users SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  👤 Users: {r.rowcount} kullanıcı güncellendi")

    # Servers
    r = conn.execute("UPDATE server_credentials SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  🖥️  Servers: {r.rowcount} sunucu güncellendi")

    # DataCenters
    r = conn.execute("UPDATE data_centers SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  🏢 DataCenters: {r.rowcount} DC güncellendi")

    # Alert Rules
    r = conn.execute("UPDATE alert_rules SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  🔔 AlertRules: {r.rowcount} kural güncellendi")

    # Webhook Configs
    r = conn.execute("UPDATE webhook_configs SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  📡 Webhooks: {r.rowcount} webhook güncellendi")

    # Scheduled Tasks
    r = conn.execute("UPDATE scheduled_tasks SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  ⏰ Tasks: {r.rowcount} görev güncellendi")

    # Backup Profiles
    r = conn.execute("UPDATE backup_profiles SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  💾 Backups: {r.rowcount} yedekleme güncellendi")

    # Audit Logs
    r = conn.execute("UPDATE audit_logs SET org_id = ? WHERE org_id IS NULL", (org_id,))
    print(f"  📝 AuditLogs: {r.rowcount} log güncellendi")

    conn.commit()

    # ═══════════════════════════════════════════════
    # 4. Community plan oluştur (yoksa)
    # ═══════════════════════════════════════════════
    print("\n📋 Adım 4: Varsayılan plan kontrol ediliyor...")

    plan_row = conn.execute("SELECT id FROM plans WHERE name = 'community' LIMIT 1").fetchone()
    if plan_row:
        plan_id = plan_row['id']
        print(f"  ⏭️  'community' planı zaten mevcut (id={plan_id})")
    else:
        conn.execute("""
            INSERT INTO plans (name, display_name, price_monthly, price_yearly,
                             max_servers, max_users, max_storage_gb, max_backups,
                             features_json, is_active, sort_order, created_at)
            VALUES ('community', 'Community (Ücretsiz)', 0, 0, 100, 50, 100, 50,
                    '["Sınırsız sunucu","Tüm modüller","Topluluk desteği"]',
                    1, 0, datetime('now'))
        """)
        plan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"  ✅ 'community' planı oluşturuldu (id={plan_id})")
    conn.commit()

    # ═══════════════════════════════════════════════
    # 5. Organizasyona abonelik ve kota ata (yoksa)
    # ═══════════════════════════════════════════════
    print("\n📋 Adım 5: Abonelik ve kaynak kotası kontrol ediliyor...")

    sub_row = conn.execute(
        "SELECT id FROM subscriptions WHERE org_id = ? LIMIT 1", (org_id,)
    ).fetchone()
    if sub_row:
        print(f"  ⏭️  Abonelik zaten mevcut")
    else:
        conn.execute("""
            INSERT INTO subscriptions (org_id, plan_id, status, billing_cycle,
                                      payment_method, starts_at, created_at)
            VALUES (?, ?, 'active', 'monthly', 'none', datetime('now'), datetime('now'))
        """, (org_id, plan_id))
        print(f"  ✅ Abonelik oluşturuldu")

    quota_row = conn.execute(
        "SELECT id FROM resource_quotas WHERE org_id = ? LIMIT 1", (org_id,)
    ).fetchone()
    if quota_row:
        print(f"  ⏭️  Kaynak kotası zaten mevcut")
    else:
        conn.execute("""
            INSERT INTO resource_quotas (org_id, max_servers, max_users, max_storage_gb,
                                         max_backups, max_vms, updated_at)
            VALUES (?, 100, 50, 100, 50, 20, datetime('now'))
        """, (org_id,))
        print(f"  ✅ Kaynak kotası oluşturuldu")

    conn.commit()

    # ═══════════════════════════════════════════════
    # 6. Sonuç raporu
    # ═══════════════════════════════════════════════
    print("\n" + "=" * 50)
    print("✅ Tenant migration tamamlandı!")
    print("=" * 50)

    # İstatistikler
    stats = {}
    for table in ['users', 'server_credentials', 'data_centers', 'alert_rules',
                   'webhook_configs', 'scheduled_tasks', 'backup_profiles', 'audit_logs']:
        try:
            total = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()['c']
            in_org = conn.execute(
                f"SELECT COUNT(*) as c FROM {table} WHERE org_id = ?", (org_id,)
            ).fetchone()['c']
            stats[table] = (total, in_org)
        except Exception:
            stats[table] = (0, 0)

    print(f"\n📊 Organizasyon: Emare (id={org_id})")
    print(f"{'Tablo':<25} {'Toplam':>8} {'Org içinde':>12}")
    print("-" * 50)
    for table, (total, in_org) in stats.items():
        print(f"{table:<25} {total:>8} {in_org:>12}")

    # Org'suz kayıt kontrolü
    orphans = 0
    for table in ['users', 'server_credentials']:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) as c FROM {table} WHERE org_id IS NULL"
            ).fetchone()['c']
            orphans += count
        except Exception:
            pass

    if orphans > 0:
        print(f"\n⚠️  {orphans} kayıt hâlâ org_id=NULL (yetim kayıt)")
    else:
        print(f"\n✅ Tüm kayıtlar bir organizasyona atandı")

    conn.close()
    print()


if __name__ == '__main__':
    migrate()
