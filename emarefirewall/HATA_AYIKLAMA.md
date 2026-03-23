# Emare Security OS — Hata Ayıklama ve Bilinen Sorunlar

Bu dosya, `emarefirewall` (Emare Security OS) paketinde kod incelemesi ve statik kontrollerle tespit edilen **tutarsızlıklar**, **yapılandırma eksikleri** ve **tasarım risklerini** listeler.

**Son güncelleme:** 2026-03-22 (yeni işlemler sonrası kontrol)

---

## 0. Bu turda neler değişti? (özet)

| Durum | Konu |
|--------|------|
| Giderildi | `routes.py` → `GET /api/firewall/health` artık sabit `1.3.0` değil; `from emarefirewall import __version__` kullanılıyor. |
| Yeni — kritik | `app.py` içinde `TenantStore` bağlanırken **`store._backend`** kullanılmış; `LogStore` örneğinde böyle bir öznitelik **yok** (`_db` var). `hasattr(store, '_backend')` her zaman False → ISP + Postgres senaryosunda bile tenant deposu **yalnızca bellek (`DictTenantStore`)** kalıyor. |
| Yeni modüller | `tenants.py` (ISP multi-tenant), `law5651.py` (5651 log damgalama), `store.py` içinde `Law5651Stamper` entegrasyonu, `test_all.py` (endpoint testi). |

---

## 1. Sürüm / dokümantasyon tutarsızlığı

| Konum | Durum (kontrol anı) |
|--------|----------------------|
| `pyproject.toml`, `__init__.py` | `1.5.0` |
| `README.md` (üst bilgi) | Hâlâ `1.3.0` |
| `test_all.py` (banner) | `v1.4.0` — paketle uyumsuz |
| `AGENTS.md` (“Mevcut Durum”) | `v1.4.0` — paketle uyumsuz |
| `GET /api/firewall/health` | `__version__` ile uyumlu |

**Sonuç:** README ve iç dokümanlar/test çıktıları paket sürümüyle hizalı değil.

---

## 2. `app.py` — `create_tenant_store` yanlış öznitelik (kritik)

```text
tenant_store = create_tenant_store(
    db_backend=store._backend if cfg.TENANT_MODE and hasattr(store, '_backend') else None
)
```

- `LogStore` backend referansı **`self._db`** (`store.py`); **`_backend` yok**.
- Bu yüzden koşul pratikte her zaman **`None`** tarafına düşer; gerçek PostgreSQL log havuzu olsa bile **tenant tabloları aynı DB’ye bağlanmaz**.

**Öneri:** `store._db` kullanılmalı; ayrıca `TenantStore` kodu `_get_conn()` beklediği için yalnızca **`PostgresBackend`** ile anlamlı — SQLite `LogStore` backend’i doğrudan verilirse `TenantStore.init()` çalışmayabilir. Koşul: `cfg.TENANT_MODE and cfg.DB_BACKEND == 'postgres' and store._db is not None` gibi netleştirilmeli.

---

## 3. `app.py` — `config` ile `create_store` / `create_cache` (kısmen eski sorun)

`create_app()` içinde hâlâ:

- `create_cache(...)` çağrısında **`default_ttl=cfg.CACHE_TTL`** yok.
- `create_store(...)` çağrısında **`retention_days=cfg.LOG_RETENTION_DAYS`**, **`max_entries=cfg.LOG_MAX_MEMORY`** yok.

**Not:** `rate_limit_per_minute=0` verilmiş; demo için rate limit kapatılmış — bilinçli ise sorun değil, üretimde farklı olmalı.

---

## 4. `routes.py` — `FirewallManager` önbellek süresi

`create_blueprint()` hâlâ `FirewallManager(ssh_executor=..., cache_backend=_cache)` ile **`cache_ttl` iletmiyor**; ortam/config ile hizalanmıyor.

---

## 5. Global `_log_store` (çoklu blueprint / test izolasyonu)

Değişiklik yok: modül seviyesinde paylaşılan `LogStore` ve `create_blueprint` ile global yeniden atama riski devam ediyor.

---

## 6. `wsgi.py` — göreli import

Hâlâ `from app import create_app` — paket kökünden veya farklı CWD ile çalıştırmada kırılgan.

---

## 7. `manager.py` — `_invalidate_cache` ve `fwt:`

Tip önbelleği (`fwt:`) invalidasyonu hâlâ yok; nadir senaryoda eski tip kalabilir.

---

## 8. `_exec_multi` — ayırıcı çakışması

Değişiklik yok; düşük olasılıklı kenar durum.

---

## 9. `test_all.py` — stil / sağlamlık

- Banner sürümü güncellenmeli (`1.5.0` veya dinamik).
- `except:` (satır ~48) — geniş yakalama; `except Exception:` tercih edilir.

---

## 10. Güvenlik notları (tasarım)

| Konu | Açıklama |
|------|-----------|
| `config.SECRET_KEY` | Varsayılan üretimde değiştirilmeli. |
| CSRF | Harici checker yoksa JSON / XHR ile geçiş; API güvenliği ayrı düşünülmeli. |
| `ParamikoExecutor` | Üretimde `host_key_policy='reject'` önerilir. |
| `law5651.py` | TSA kullanıcı/parola ve URL yapılandırması; üretimde gizli bilgiler ortam değişkeninde tutulmalı. |

---

## 11. Statik doğrulama (2026-03-22)

- `python3 -m compileall` (`PYTHONPYCACHEPREFIX` ile workspace içi): **sentaks hatası yok**.
- IDE linter: ek rapor yok (tarama anında).

---

## 12. Özet öncelik tablosu

| Öncelik | Konu |
|---------|------|
| **Yüksek** | `app.py`: `store._backend` → `store._db` + yalnızca Postgres ile tenant bağlama |
| Orta | README / `test_all.py` / `AGENTS.md` sürüm hizası |
| Orta | `create_app`: `CACHE_TTL`, log retention / max memory |
| Düşük–orta | Blueprint’te `FirewallManager(cache_ttl=...)` |
| Düşük | Global `_log_store`, `wsgi` import, `_exec_multi`, `fwt:` |
| Düşük | `test_all.py` bare `except` |

---

*Üretim ortamına özgü hatalar (ağ, SSH, izinler, TSA erişimi) kapsam dışıdır.*
