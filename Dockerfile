FROM python:3.11-slim

LABEL maintainer="EmareCloud" \
      description="EmareCloud — Altyapı Yönetim Paneli" \
      version="1.0.0"

WORKDIR /app

# Sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Python bağımlılıkları
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyaları
COPY . .

# Instance dizini (SQLite DB)
RUN mkdir -p instance

# Güvenlik: root olmayan kullanıcı
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 5555

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5555/health')" || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
