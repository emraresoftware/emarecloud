# AI Eszamanli Calisma Kilavuzu

Bu kilavuz, birden fazla AI yazilimcinin ayni proje icinde birbirinin degisikliklerini bozmadan calismasi icin pratik isleyis adimlarini tanimlar.

## 1. Amac
- Ayni dosyada cakismayi en aza indirmek
- Review ve merge surecini hizlandirmak
- Regresyon riskini dusurmek

## 2. Temel Ilke
- Ayni dosyayi ayni anda iki AI degistirmez.
- Ayni dosya gerekiyorsa zaman penceresi (slot) uygulanir.
- Her degisiklik PR uzerinden ilerler.

## 3. Is Akisi (Kisa Surum)
1. Gorev acilir.
2. AI, dokunacagi dosyalari rezerv eder.
3. Kod degisikligi yapilir.
4. Handoff notu yazilir.
5. PR acilir, kalite kapilarindan gecilir.
6. Merge sonrasi rezervasyon kapanir.

## 4. Dosya Rezervasyon Kurali
- Rezervasyon acilmadan kod degisikligine baslanmaz.
- Rezervasyon su bilgileri icerir:
  - Gorev no
  - AI adi
  - Dosya listesi
  - Baslangic zamani
  - Tahmini bitis
- Rezervasyon suresi varsayilan 30 dakikadir.
- Sure asimi varsa AI rezervasyonu yeniler veya dosyayi birakir.

## 5. Slot Kurali (Ayni Dosya Mecburiyeti)
- Ayni dosya icin 15-30 dakikalik slot verilir.
- Slot bitince AI degisiklikleri push eder.
- Diger AI guncel dali cekip kendi slotunda devam eder.
- Slot disinda ayni dosyaya dokunmak yasaktir.

## 6. Domain Bazli Calisma
- Her AI'nin ana domaini net olmalidir (ops/infra/network vb).
- Domain disina cikis gerekirse PR icinde gerekce zorunludur.
- Domain sinir kontrolu CI ile otomatik denetlenir:
  - `tools/check_modular_boundaries.py`

## 7. PR Kurallari
- PR tek amacli olur.
- PR aciklamasinda handoff notu zorunludur.
- `main` dalina dogrudan push yasaktir.
- CI yesil olmadan merge edilmez.

## 8. Handoff Zorunlu Alanlari
- Ne degisti
- Neye dokunulmadi
- Bilinen risk
- Test kaniti
- Rollback adimi

## 9. Cakisma Durumunda Karar Agaci
1. Dosya rezervli mi?
   - Evet: Rezerv sahibi tamamlar, digeri bekler.
   - Hayir: Rezerv acip devam edilir.
2. Acil bug mi?
   - Evet: Integrator AI onayi ile slot devri yapilir.
   - Hayir: Planli slotla devam edilir.

## 10. Onerilen Uygulama Bicimi
- Repository kokunde `.ai-locks/` klasoru tutulur.
- Her aktif gorev icin bir JSON lock dosyasi acilir.
- PR seviyesinde otomatik uyari icin `AI Lock Guard` workflow'u calisir:
  - `.github/workflows/ai-lock-guard.yml`
  - `tools/check_ai_locks.py`

Ornek lock dosyasi:
```json
{
  "gorev": "OPS-142",
  "ai": "builder-ai-1",
  "dosyalar": [
    "routes/domain_ops/monitoring.py",
    "templates/monitoring.html"
  ],
  "baslangic": "2026-03-23T10:00:00Z",
  "bitis_tahmin": "2026-03-23T10:30:00Z",
  "durum": "active"
}
```

## 11. Minimum Kontrol Listesi
- [ ] Dosya rezervasyonu acildi
- [ ] Domain kapsami net
- [ ] Tek amacli PR
- [ ] Boundary check gecti
- [ ] Testler gecti
- [ ] Handoff notu yazildi
- [ ] Rezervasyon kapatildi

## 12. Hizli Baslangic Komutlari
```bash
# Cakisma riski olan dosyalari gor
rg -n "register_blueprints|routes/domain_|core/" app.py routes core

# Domain siniri kontrolu
python tools/check_modular_boundaries.py
```
