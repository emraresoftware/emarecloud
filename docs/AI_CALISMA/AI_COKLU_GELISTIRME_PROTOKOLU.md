# EmareCloud Coklu AI Gelistirme Protokolu

Bu dokuman, birden fazla AI yazilimcinin ayni kod tabaninda birbirini bozmadan calismasi icin zorunlu kurallari tanimlar.

## 1. Isletim Modeli
- Planner AI: Isi parcalar, kabul kriterini yazar.
- Builder AI: Sadece atanan kapsama kod yazar.
- Reviewer AI: Bug, regresyon ve guvenlik riski bulur.
- Integrator AI: PR birlestirme ve release karari verir.

Kural: Ayni PR icinde bu roller karistirilmaz.

## 2. Branch ve PR Kurallari
- `main` dalina dogrudan push yasak.
- Her degisiklik PR uzerinden gelir.
- PR tek amacli olur: bugfix/refactor/feature karismaz.
- PR aciklamasinda `AI Handoff Notu` zorunludur.

## 3. Domain Siniri Kurali
- Route katmaninda domain sinirlari korunur.
- `tools/check_modular_boundaries.py` gecmeden PR merge edilmez.
- Farkli domain dosyasina dokunacak AI, PR'da gerekce yazmak zorundadir.

## 4. Kalite Kapilari (Merge Oncesi)
- Lint gecmeli.
- Boundary check gecmeli.
- Testler gecmeli.
- Guvenlik hassas dosyalarda ikinci review zorunlu.

## 5. Breaking Change Protokolu
- Breaking change varsa PR'da acikca isaretlenir.
- `emare_messenger.py` ile etkilenen ekiplere duyuru gecilir.
- Gecis ve rollback adimlari PR icinde yazilir.

Duyuru formati:
`[Ne yapildi]. [Endpoint/versiyon/detay]. [Etkisi ve rollback notu].`

## 6. Handoff Standardi (Zorunlu)
Her PR sonunda su 5 madde yazilir:
- Ne degisti
- Neye dokunulmadi
- Bilinen risk
- Test kaniti
- Rollback adimi

## 7. Canliya Alma Kurali
- Feature flag varsa asamali acilis yapilir.
- Migration/deploy oncesi yedek alinir.
- Incident durumunda rollback adimi 10 dakika icinde uygulanabilir olmalidir.

## 8. Yasaklar
- Baska AI'nin aktif PR kapsamini izinsiz degistirmek.
- Tek PR'da refactor + davranis degisimi + deploy karistirmak.
- CI kirmizi iken merge etmek.

## 9. Hizli Uygulama Checklist
- [ ] Gorev atamasi net
- [ ] Domain kapsami net
- [ ] PR template dolduruldu
- [ ] Boundary check gecti
- [ ] Test kaniti var
- [ ] Rollback adimi yazildi
