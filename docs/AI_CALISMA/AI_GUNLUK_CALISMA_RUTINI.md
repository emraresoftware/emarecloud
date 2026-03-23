# AI Gunluk Calisma Rutini (1 Sayfa)

Bu rutin, birden fazla AI yazilimcinin gun icinde koordineli ve cakismasiz calismasi icin uygulanir.

## 1. Gune Baslarken (5 Dakika)
1. Aktif lock dosyalarini kontrol et: `.ai-locks/`
2. Acik PR'lari kontrol et.
3. Bugun dokunacagin domain ve dosyalari netlestir.

## 2. Ise Baslamadan Once (2 Dakika)
1. Lock dosyasi ac.
2. Lock'a gorev no, AI adi, dosya listesi ve tahmini bitis yaz.
3. PR aciklamasina lock dosya adini not et.

## 3. Gelistirme Sirasinda
1. Sadece lock altindaki dosyalari degistir.
2. Domain disina cikman gerekiyorsa PR'a gerekce ekle.
3. Buyuk degisikligi kucuk commit/parcalara bol.

## 4. Kod Bitince (Zorunlu Kontroller)
1. Boundary check:
```bash
python tools/check_modular_boundaries.py
```
2. Test/lint kontrolu (ilgili kapsama gore).
3. Handoff notunu tamamla:
- Ne degisti
- Neye dokunulmadi
- Risk
- Test kaniti
- Rollback

## 5. PR Acarken
1. PR tek amacli olmali.
2. `pull_request_template.md` tam doldurulmali.
3. Breaking change varsa duyuru zorunlu.

## 6. Merge Sonrasi
1. Lock durumunu `closed` yap veya lock dosyasini kaldir.
2. Sonraki AI icin 3 satirlik devir notu birak.
3. Izleme gerekiyorsa issue/PR'a post-merge notu dus.

## 7. Acil Durum Proseduru
1. CI kirmiziysa merge etme.
2. Uretim etkisi varsa Integrator AI'a eskale et.
3. Gerekirse rollback planini hemen uygula.

## 8. Gun Sonu Kapanis (3 Dakika)
1. Acik lock var mi kontrol et.
2. Yarin devredilecek isleri kisa notla yaz.
3. Cok uzun acik kalan lock'lari temizle.

## Hizli Checklist
- [ ] Lock acildi
- [ ] Tek amacli PR
- [ ] Boundary check gecti
- [ ] Handoff yazildi
- [ ] Lock kapatildi
