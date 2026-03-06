"""
EmareCloud — Merkezi Deploy Sistemi
====================================
Tüm Dervişler bu ücret üzerinden deploy eder.
Kimse kafasına göre manuel SSH ile deploy yapamaz (Anayasa Madde 7).

Endpoint'ler:
  GET  /api/deploy/jobs                     — Tüm deploy geçmişi
  GET  /api/deploy/jobs/<id>                — Belirli job detayı
  POST /api/deploy/<slug>                   — Manuel deploy tetikle
  GET  /api/deploy/manifest/<slug>          — Projenin deploy.json içeriği
  POST /api/deploy/webhook/<secret>         — GitHub push webhook (otomatik deploy)
  GET  /api/deploy/projects                 — Bilinen tüm projelerin listesi

SSH Yapısı:
  ssh -p <port> -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no root@<host>
  Komutlar sırayla çalıştırılır; biri başarısız olursa deploy FAILED olur.
"""

import json
import os
import subprocess
import threading
import hashlib
import hmac
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, g
from flask_login import current_user, login_required

from extensions import db
from models import DeployJob, AuditLog
from core.logging_config import get_logger

logger = get_logger(__name__)

deploy_bp = Blueprint('deploy', __name__)

# ──────────────────────────────────────────
# Sabitler
# ──────────────────────────────────────────
EMARE_BASE = Path('/Users/emre/Desktop/Emare')   # Yerel geliştirme kök dizini
SSH_KEY    = '/root/.ssh/id_ed25519'              # Sunuculardaki deploy anahtarı
WEBHOOK_SECRET = os.environ.get('DEPLOY_WEBHOOK_SECRET', 'emare-deploy-secret-2025')

# stack → varsayılan deploy komutları şablonu
STACK_TEMPLATES: dict[str, list[str]] = {
    'python-gunicorn': [
        'cd {remote_path}',
        'git pull origin {branch}',
        'source venv/bin/activate && pip install -r requirements.txt -q',
        'sudo systemctl restart {slug}',
    ],
    'php-laravel': [
        'cd {remote_path}',
        'git pull origin {branch}',
        'composer install --no-dev --optimize-autoloader --no-interaction -q',
        'php artisan migrate --force',
        'php artisan config:cache',
        'php artisan route:cache',
        'php artisan view:cache',
        'chown -R nginx:nginx {remote_path}/storage {remote_path}/bootstrap/cache',
    ],
    'node-pm2': [
        'cd {remote_path}',
        'git pull origin {branch}',
        'npm ci --silent',
        'pm2 restart {slug} || pm2 start ecosystem.config.js',
    ],
    'node-nextjs': [
        'cd {remote_path}',
        'git pull origin {branch}',
        'npm ci --silent',
        'npm run build',
        'pm2 restart {slug} || pm2 start ecosystem.config.js',
    ],
    'docker': [
        'cd {remote_path}',
        'git pull origin {branch}',
        'docker-compose pull',
        'docker-compose up -d --remove-orphans',
    ],
}


# ──────────────────────────────────────────
# Yardımcı: deploy.json oku
# ──────────────────────────────────────────
def _manifest_oku(slug: str) -> dict | None:
    """
    Projenin deploy.json dosyasını okur.
    Önce GitHub API'den, sonra yerel diskten dener.
    """
    # Yerel disk (geliştirme ortamı)
    local = EMARE_BASE / slug / 'deploy.json'
    if local.exists():
        try:
            return json.loads(local.read_text())
        except Exception as e:
            logger.error(f"deploy.json okuma hatası ({slug}): {e}")
    return None


# ──────────────────────────────────────────
# Yardımcı: SSH ile deploy çalıştır
# ──────────────────────────────────────────
def _deploy_calistir(job: DeployJob, manifest: dict):
    """
    Arka planda SSH ile deploy komutlarını çalıştırır,
    sonucu DeployJob'a yazar.
    """
    from app import app as flask_app
    with flask_app.app_context():
        job_id = job.id
        slug = job.project_slug

        try:
            job.status = DeployJob.STATUS_RUNNING
            job.started_at = datetime.utcnow()
            db.session.commit()

            host        = manifest.get('server_host')
            ssh_port    = manifest.get('server_ssh_port', 22)
            branch      = job.branch or manifest.get('branch', 'main')
            remote_path = manifest.get('remote_path', f'/var/www/{slug}')
            stack       = manifest.get('stack', 'python-gunicorn')
            restart_cmd = manifest.get('restart_command', '')
            custom_cmds = manifest.get('deploy_commands', [])

            if not host:
                raise ValueError("deploy.json'da server_host tanımlı değil!")

            # Komutları belirle
            if custom_cmds:
                cmds = custom_cmds
            else:
                tmpl = STACK_TEMPLATES.get(stack, STACK_TEMPLATES['python-gunicorn'])
                cmds = [
                    c.format(remote_path=remote_path, slug=slug, branch=branch)
                    for c in tmpl
                ]

            if restart_cmd and restart_cmd not in cmds:
                cmds.append(restart_cmd)

            # SSH komutunu birleştir
            full_cmd = ' && '.join(cmds)
            ssh_args = [
                'ssh',
                f'-p{ssh_port}',
                f'-i{SSH_KEY}',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=30',
                f'root@{host}',
                full_cmd,
            ]

            logger.info(f"[deploy] {slug} → {host}:{ssh_port}")
            t_start = datetime.utcnow()

            result = subprocess.run(
                ssh_args,
                capture_output=True, text=True, timeout=600
            )

            t_end = datetime.utcnow()
            duration = (t_end - t_start).total_seconds()

            chikti = (result.stdout or '') + (result.stderr or '')

            # DB güncelle
            j = DeployJob.query.get(job_id)
            j.output_log   = chikti
            j.duration_sec = round(duration, 2)
            j.finished_at  = t_end

            if result.returncode == 0:
                j.status = DeployJob.STATUS_SUCCESS
                logger.info(f"[deploy] {slug} BAŞARILI ({duration:.0f}s)")
            else:
                j.status = DeployJob.STATUS_FAILED
                j.error_message = f"SSH returncode={result.returncode}"
                logger.error(f"[deploy] {slug} BAŞARISIZ — {result.returncode}")

            db.session.commit()

        except subprocess.TimeoutExpired:
            j = DeployJob.query.get(job_id)
            j.status = DeployJob.STATUS_FAILED
            j.error_message = 'SSH komutu 10 dakikada tamamlanamadı (timeout)'
            j.finished_at = datetime.utcnow()
            db.session.commit()
            logger.error(f"[deploy] {slug} TIMEOUT")

        except Exception as e:
            j = DeployJob.query.get(job_id)
            j.status = DeployJob.STATUS_FAILED
            j.error_message = str(e)[:900]
            j.finished_at = datetime.utcnow()
            db.session.commit()
            logger.exception(f"[deploy] {slug} HATA: {e}")


# ──────────────────────────────────────────
# GET /api/deploy/jobs
# ──────────────────────────────────────────
@deploy_bp.route('/api/deploy/jobs', methods=['GET'])
@login_required
def deploy_jobs_listele():
    """Tüm deploy geçmişini döndürür."""
    slug   = request.args.get('slug')
    durum  = request.args.get('status')
    limit  = min(int(request.args.get('limit', 50)), 200)

    q = DeployJob.query.order_by(DeployJob.created_at.desc())
    if slug:
        q = q.filter_by(project_slug=slug)
    if durum:
        q = q.filter_by(status=durum)

    jobs = q.limit(limit).all()
    return jsonify([j.to_dict() for j in jobs])


# ──────────────────────────────────────────
# GET /api/deploy/jobs/<id>
# ──────────────────────────────────────────
@deploy_bp.route('/api/deploy/jobs/<int:job_id>', methods=['GET'])
@login_required
def deploy_job_detay(job_id: int):
    """Belirli bir deploy job'un tüm log çıktısını döndürür."""
    job = DeployJob.query.get_or_404(job_id)
    d = job.to_dict()
    d['output_log'] = job.output_log or ''   # tam log (3000 char sınırı yok)
    return jsonify(d)


# ──────────────────────────────────────────
# GET /api/deploy/manifest/<slug>
# ──────────────────────────────────────────
@deploy_bp.route('/api/deploy/manifest/<slug>', methods=['GET'])
@login_required
def deploy_manifest_goster(slug: str):
    """Projenin deploy.json içeriğini döndürür."""
    manifest = _manifest_oku(slug)
    if not manifest:
        return jsonify({'error': f'{slug} için deploy.json bulunamadı'}), 404
    return jsonify(manifest)


# ──────────────────────────────────────────
# GET /api/deploy/projects
# ──────────────────────────────────────────
@deploy_bp.route('/api/deploy/projects', methods=['GET'])
@login_required
def deploy_projeler_listele():
    """
    EMARE_BASE altındaki tüm deploy.json dosyalarını tarar,
    proje listesi döndürür.
    """
    projeler = []
    if EMARE_BASE.exists():
        for prj_dir in sorted(EMARE_BASE.iterdir()):
            dj = prj_dir / 'deploy.json'
            if dj.exists():
                try:
                    m = json.loads(dj.read_text())
                    projeler.append({
                        'slug':   m.get('slug', prj_dir.name),
                        'name':   m.get('name', prj_dir.name),
                        'dc':     m.get('dc', '?'),
                        'stack':  m.get('stack', '?'),
                        'domain': m.get('domain', ''),
                        'auto_deploy_on_push': m.get('auto_deploy_on_push', False),
                    })
                except Exception:
                    pass
    return jsonify(projeler)


# ──────────────────────────────────────────
# POST /api/deploy/<slug>
# ──────────────────────────────────────────
@deploy_bp.route('/api/deploy/<slug>', methods=['POST'])
@login_required
def deploy_tetikle(slug: str):
    """
    Manuel deploy tetikler.
    Sadece admin ve super_admin tetikleyebilir.
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Yetkisiz — sadece admin deploy başlatabilir'}), 403

    manifest = _manifest_oku(slug)
    if not manifest:
        return jsonify({'error': f'{slug} için deploy.json bulunamadı. Derviş manifest ekleyin!'}), 404

    bilgi = request.get_json(silent=True) or {}
    branch = bilgi.get('branch', manifest.get('branch', 'main'))

    # Aynı proje için halihazırda çalışan job var mı?
    calisaniyor = DeployJob.query.filter_by(
        project_slug=slug, status=DeployJob.STATUS_RUNNING
    ).first()
    if calisaniyor:
        return jsonify({
            'error': f'{slug} zaten deploy ediliyor (job #{calisaniyor.id})',
            'running_job': calisaniyor.to_dict()
        }), 409

    job = DeployJob(
        project_slug   = slug,
        project_name   = manifest.get('name', slug),
        triggered_by   = 'manual',
        triggered_user = current_user.username,
        branch         = branch,
        server_host    = manifest.get('server_host'),
        stack          = manifest.get('stack'),
        status         = DeployJob.STATUS_PENDING,
    )
    db.session.add(job)
    db.session.commit()

    # Arka planda deploy başlat
    t = threading.Thread(target=_deploy_calistir, args=(job, manifest), daemon=True)
    t.start()

    # Audit log
    try:
        log = AuditLog(
            user_id=current_user.id, username=current_user.username,
            action='deploy_manual', target_type='project', target_id=slug,
            ip_address=request.remote_addr,
            details=json.dumps({'branch': branch, 'job_id': job.id})
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

    return jsonify({'ok': True, 'job': job.to_dict()}), 202


# ──────────────────────────────────────────
# POST /api/deploy/webhook/<secret>
# ──────────────────────────────────────────
@deploy_bp.route('/api/deploy/webhook/<secret>', methods=['POST'])
def deploy_webhook(secret: str):
    """
    GitHub push webhook endpoint'i.
    emaregithup/webhook_receiver.py tarafından çağrılır.
    Secret doğrulaması zorunludur.
    """
    # Secret doğrula
    if secret != WEBHOOK_SECRET:
        logger.warning(f"[webhook] Geçersiz secret denemesi: {request.remote_addr}")
        return jsonify({'error': 'Geçersiz webhook secret'}), 403

    # GitHub imzasını doğrula (X-Hub-Signature-256)
    payload_raw = request.get_data()
    gh_sig = request.headers.get('X-Hub-Signature-256', '')
    if gh_sig:
        beklenen = 'sha256=' + hmac.new(
            WEBHOOK_SECRET.encode(), payload_raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(gh_sig, beklenen):
            return jsonify({'error': 'İmza doğrulaması başarısız'}), 403

    data = request.get_json(force=True, silent=True) or {}

    # Sadece push event'i işle
    event = request.headers.get('X-GitHub-Event', 'push')
    if event != 'push':
        return jsonify({'ok': True, 'skipped': f'{event} event yoksayıldı'}), 200

    repo_full = data.get('repository', {}).get('full_name', '')
    # repo full_name → "emraresoftware/emarepos" → slug = "emarepos"
    slug = repo_full.split('/')[-1].lower() if '/' in repo_full else repo_full.lower()
    branch_ref = data.get('ref', 'refs/heads/main')
    branch = branch_ref.replace('refs/heads/', '')
    commit_hash = data.get('after', '')[:40]
    commit_msg = ''
    commits = data.get('commits', [])
    if commits:
        commit_msg = commits[-1].get('message', '')[:490]
    pusher = data.get('pusher', {}).get('name', 'github')

    manifest = _manifest_oku(slug)
    if not manifest:
        logger.info(f"[webhook] {slug} için deploy.json yok — atlandı")
        return jsonify({'ok': True, 'skipped': 'deploy.json bulunamadı'}), 200

    # auto_deploy_on_push kontrolü
    if not manifest.get('auto_deploy_on_push', False):
        return jsonify({'ok': True, 'skipped': 'auto_deploy_on_push=false'}), 200

    # Doğru branch mi?
    manifest_branch = manifest.get('branch', 'main')
    if branch != manifest_branch:
        return jsonify({'ok': True, 'skipped': f'{branch} != {manifest_branch}'}), 200

    # Çalışan deploy var mı?
    calisaniyor = DeployJob.query.filter_by(
        project_slug=slug, status=DeployJob.STATUS_RUNNING
    ).first()
    if calisaniyor:
        logger.info(f"[webhook] {slug} zaten deploy ediliyor — webhook atlandı")
        return jsonify({'ok': True, 'skipped': 'zaten çalışıyor'}), 200

    job = DeployJob(
        project_slug   = slug,
        project_name   = manifest.get('name', slug),
        triggered_by   = 'webhook',
        triggered_user = f'github:{pusher}',
        branch         = branch,
        commit_hash    = commit_hash,
        commit_message = commit_msg,
        server_host    = manifest.get('server_host'),
        stack          = manifest.get('stack'),
        status         = DeployJob.STATUS_PENDING,
    )
    db.session.add(job)
    db.session.commit()

    t = threading.Thread(target=_deploy_calistir, args=(job, manifest), daemon=True)
    t.start()

    logger.info(f"[webhook] {slug}@{branch} deploy başlatıldı (job #{job.id})")
    return jsonify({'ok': True, 'job_id': job.id, 'slug': slug}), 202
