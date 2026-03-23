## Ozet
- Bu PR neyi degistiriyor?
- Neden gerekli?

## Degisiklik Tipi
- [ ] Bug fix
- [ ] Refactor
- [ ] Yeni ozellik
- [ ] Altyapi/DevOps
- [ ] Dokumantasyon

## Etki Alani
- Domain: `ops` | `infra` | `network` | `auth` | `pages` | `org` | `deploy`
- Etkilenen dosyalar:
  - 

## AI Handoff Notu
- Bu PR'da neyi bilerek degistirmedim:
- Bir sonraki AI icin kritik not:
- Potansiyel risk:

## Test Kaniti
- [ ] Local test calistirildi
- [ ] CI yesil
- [ ] Boundary check gecti (`tools/check_modular_boundaries.py`)
- [ ] Manuel kritik akis testi yapildi

Calistirilan komutlar:
```bash
# ornek
python tools/check_modular_boundaries.py
pytest -q
```

## Breaking Change Kontrolu
- [ ] Breaking change yok
- [ ] Breaking change var ve duyuru gonderildi (`emare_messenger.py`)

Eger breaking change varsa:
- Etkilenen modul/servis:
- Duyuru metni:
- Gecis/rollback plani:

## Rollback Plani
- Geri alma komutu/adimi:
- Veri/migrasyon geri donus notu:

## Checklist
- [ ] Tek amacli PR (karisik degisiklik yok)
- [ ] Domain siniri ihlali yok
- [ ] Gizli anahtar/token eklenmedi
- [ ] Dokumantasyon guncellendi (gerekliyse)
