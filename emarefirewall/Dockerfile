FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ISP ölçek bağımlılıkları (Redis, PostgreSQL, Gunicorn, gevent)
RUN pip install --no-cache-dir redis>=4.5.0 psycopg2-binary>=2.9.0 gunicorn>=21.2.0 gevent>=23.9.0

# Paket yapısını oluştur: /app/emarefirewall/
COPY __init__.py manager.py routes.py ssh.py cli.py __main__.py config.py cache.py store.py tenants.py law5651.py rmm.py ./emarefirewall/
COPY templates/ ./emarefirewall/templates/
COPY app.py wsgi.py pyproject.toml ./

RUN pip install --no-cache-dir . && \
    find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 5555

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV EMARE_MODE=standalone

# Standalone: Flask dev server — ISP: Gunicorn (docker-compose ile override edilir)
CMD ["python", "app.py"]
