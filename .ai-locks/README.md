# AI Locks Rehberi

Bu klasor, ayni dosyada eszamanli AI cakismasini onlemek icin kullanilir.

## Temel kural
- Kod degisikligine baslamadan once lock acilir.
- Is bitince lock kapatilir (dosya silinir veya `durum` `closed` yapilir).
- Rezervasyon yoksa ayni dosyaya birden fazla AI dokunmaz.

## Dosya adlandirma
- Onerilen format: `LOCK-<gorev-no>-<ai-adi>.json`
- Ornek: `LOCK-OPS-142-builder-ai-1.json`

## Asgari alanlar
- `gorev`
- `ai`
- `dosyalar`
- `baslangic`
- `bitis_tahmin`
- `durum`

## Durum degerleri
- `active`: Su an calisiliyor
- `handoff`: Devredildi
- `closed`: Tamamlandi

## Isleyis
1. Lock dosyasini olustur.
2. PR aciklamasina lock dosya adini yaz.
3. Is bitince lock'u kapat.

## Not
- Bu klasor operasyonel amaclidir.
- Cok eski lock dosyalari duzenli temizlenmelidir.
