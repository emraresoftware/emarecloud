# Emare Security OS — Copilot Workspace Talimatları

## Proje Bağlamı
Emare Security OS, UFW/firewalld/Emare OS destekleyen birleşik güvenlik platformudur.
Python 3.8+ / Flask / Vanilla JS. ~10.800 satır. Standalone ve ISP modları var.

## Dil
- Kod içi yorumlar ve değişken isimleri İngilizce
- UI metinleri, hata mesajları ve dokümantasyon Türkçe
- Commit mesajları Türkçe

## Koordinasyon Dosyaları
Değişiklik yapmadan önce şu dosyaları oku:
1. `.instructions.md` — Kodlama kuralları ve pattern'lar
2. `AGENTS.md` — Dosya bölge haritası ve çakışma önleme kuralları
3. `CHANGELOG.md` — Değişiklik geçmişi

## Kritik Kurallar
- **manager.py TEK iş mantığı katmanıdır** — routes.py'ye iş mantığı koyma
- Her metot **hem Linux hem Emare OS** desteklemeli
- Kullanıcı girdisi → regex validation, shell komutu → `_sq()` escape
- Yeni kod **dosya sonuna** eklenir, ortaya ekleme yapılmaz
- Mevcut public metot imzalarını değiştirme
- Her değişiklikten sonra Docker build + curl ile test et
- `CHANGELOG.md`'yi güncelle, `pyproject.toml` version bump yap
- Proje adı: **Emare Security OS** (Python paket dizini: `emarefirewall`)
