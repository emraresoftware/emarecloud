# EmareCloud — GitHub Kurulum Talimatları

Bu dosya, projeyi GitHub'a taşımak ve DC-1 sunucusunda `git pull` ile deploy etmek için yapılması gerekenleri adım adım açıklar.

---

## 1. GitHub'da Repository Oluştur

1. https://github.com adresine giriş yap
2. **New repository** → name: `emarecloud`
3. **Private** seç (kaynak kodunu gizli tut)
4. README ekleme (zaten var), **.gitignore** ekleme (aşağıda elle yapacağız)
5. **Create repository** tıkla

---

## 2. Localden İlk Push

Terminalde `/Users/emre/Desktop/Emare/emarecloud` klasöründe çalıştır:

```bash
# Git başlat
git init

# .gitignore oluştur (hassas dosyaları dışla)
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
*.pyd
*.db
*.sqlite3
instance/
.env
.env.*
venv/
*.log
config.json
*.bak
.DS_Store
EOF

# Tüm dosyaları ekle
git add .
git status  # config.json ve .env gibi hassas dosyalar listede OLMAMALI

# İlk commit
git commit -m "feat: initial commit — EmareCloud v1"

# GitHub remote bağla (kendi repo URL'inle değiştir)
git remote add origin https://github.com/KULLANICI_ADI/emarecloud.git

# Push
git branch -M main
git push -u origin main
```

---

## 3. Hassas Dosyaları Kontrol Et

Push'tan önce şu dosyaların `.gitignore`'da olduğunu doğrula:

| Dosya | Neden Gizli? |
|---|---|
| `.env` | DB şifresi, secret key |
| `config.json` | License key, API anahtarları |
| `instance/` | SQLite veritabanı |
| `*.db`, `*.sqlite3` | Kullanıcı verileri |

---

## 4. DC-1 Sunucusunu GitHub'a Bağla

DC-1'e SSH ile bağlan ve şunları çalıştır:

```bash
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104

# Git kur (zaten kurulu olabilir)
dnf install -y git

# Mevcut /opt/emarecloud klasörünü git repo yap
cd /opt/emarecloud
git init
git remote add origin https://github.com/KULLANICI_ADI/emarecloud.git

# GitHub token ile kimlik doğrulama (şifre yerine Personal Access Token kullan)
# GitHub → Settings → Developer settings → Personal access tokens → Fine-grained
# Repo: emarecloud, İzinler: Contents (read/write)
git config credential.helper store
git pull origin main
# Token sorduğunda GitHub PAT'ını gir — bir kez gir, hatırlar
```

---

## 5. Deploy Scripti (Tek Komutla Güncelle)

DC-1'de `/opt/emarecloud/deploy.sh` oluştur:

```bash
cat > /opt/emarecloud/deploy.sh << 'EOF'
#!/bin/bash
set -e
cd /opt/emarecloud
echo "==> Git pull..."
git pull origin main
echo "==> Bağımlılıklar..."
source venv/bin/activate
pip install -r requirements.txt -q
echo "==> Servis yenide başlatılıyor..."
systemctl restart emarecloud
sleep 3
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5555)
echo "==> HTTP: $STATUS"
EOF
chmod +x /opt/emarecloud/deploy.sh
```

Artık her güncellemede:
```bash
# Localden
git add . && git commit -m "feat: değişiklik açıklaması" && git push

# Sunucuda (veya uzaktan)
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 "/opt/emarecloud/deploy.sh"
```

---

## 6. VS Code Remote-SSH ile Direkt Sunucuda Geliştirme (Opsiyonel)

```bash
# Mac terminalde
code --install-extension ms-vscode-remote.remote-ssh
```

`~/.ssh/config` dosyasına ekle:
```
Host dc1-emarecloud
    HostName 185.189.54.104
    User root
    IdentityFile ~/.ssh/id_ed25519
```

VS Code'da `Ctrl+Shift+P` → **Remote-SSH: Connect to Host** → `dc1-emarecloud` seç → `/opt/emarecloud` klasörünü aç.

Sunucuda değişiklik yap → terminal'de `git commit && git push` ile GitHub'a yükle.

---

## 7. Özet İş Akışı

```
Mac (VS Code local/remote)
    ↓  git push
GitHub (private repo — yedek + versiyon geçmişi)
    ↓  git pull (deploy.sh)
DC-1 /opt/emarecloud (canlı)
```
