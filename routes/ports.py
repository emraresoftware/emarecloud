"""
EmareCloud — Merkezi Port Kayıt Defteri API
Her Derviş projesi bu API üzerinden port tahsis alır.
Manuel port atama yasaktır.

Endpoint'ler:
  GET    /api/ports                  → tüm portları listele
  POST   /api/ports/allocate         → yeni port tahsis et
  POST   /api/ports/seed             → bilinen portları DB'ye yükle (admin-only)
  DELETE /api/ports/<port>           → port serbest bırak
  GET    /api/ports/next             → bir sonraki boş portu göster (tahsis etmez)
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import PortRegistry

ports_bp = Blueprint('ports', __name__, url_prefix='/api/ports')

# ---------------------------------------------------------------------------
# Bilinen projelerin seed verisi
# ---------------------------------------------------------------------------
_SEED_DATA = [
    # port, slug, project_name, dc, stack, description
    (5555, 'emarecloud',      'EmareCloud Panel',          'dc1+dc2', 'python',  'Ana yönetim paneli (Gunicorn/Flask)'),
    (8000, 'emareapi',        'Emare API',                 'dc1+dc2', 'python',  'FastAPI/uvicorn ana API'),
    (3002, 'emare-dapp',      'Emare Token DApp',          'dc1',     'node',    'Next.js token uygulaması (PM2)'),
    (9378, 'docker-proxy',    'Docker Proxy',              'dc1',     'docker',  'Docker iç proxy'),
    (8080, 'emaresuperapp',   'Emare SuperApp',            'local',   'node',    'Ana mobil+web uygulama'),
    (8200, 'emareintranet',   'Emare İntranet',            'local',   'python',  'Şirket içi intranet'),
    (8300, 'emarecripto',     'Emare Kripto',              'local',   'python',  'Kripto/blockchain servisi'),
    (8400, 'emareidi',        'Emare IDI (Kimlik)',        'local',   'python',  'Kimlik doğrulama servisi'),
    (8600, 'emaretedarik',    'Emare Tedarik',             'local',   'python',  'Tedarik zinciri yönetimi'),
    (8700, 'emareaimusic',    'Emare AI Müzik',            'local',   'python',  'AI müzik üretici'),
    (8800, 'emareflow',       'Emare Flow',                'local',   'python',  'İş akışı otomasyon sistemi'),
    (8888, 'emareai',         'Emare AI',                  'local',   'python',  'AI motor servisi'),
    (8900, 'emarewebdizayn',  'Emare Webdizayn',           'dc1',     'python',  'Web tasarım hosting (webdizayn.emarecloud.tr)'),
    (5000, 'emarecc',         'Emare CC Backend',          'local',   'node',    'Komuta kontrol merkezi backend'),
    (3000, 'emarewebdizayn-ui','Emare Webdizayn UI',       'local',   'node',    'Web tasarım Next.js frontend'),
    (8100, 'Emare-Finance',   'Emare Finance',             'dc2',     'php',     'Laravel finans sistemi (finans.emarecloud.tr)'),
    (8101, 'emarebot',        'Emare Bot',                 'local',   'python',  'Otomasyon botu'),
    (8102, 'emaremakale',     'Emare Makale',              'local',   'python',  'İçerik yönetim sistemi'),
    (8103, 'emare-code',      'Emare Code',                'local',   'python',  'Kod editör/IDE servisi'),
    (8104, 'emare-desk',      'Emare Desk',                'local',   'python',  'Uzak masaüstü servisi'),
    (8105, 'emare-dashboard', 'Emare Dashboard',           'local',   'python',  'Analitik pano'),
    (8106, 'emareads',        'Emare Ads',                 'local',   'python',  'Reklam yönetimi'),
    (8107, 'emareasistan',    'Emare Asistan',             'dc2',     'python',  'AI asistan (asistan.emarecloud.tr)'),
    (8108, 'emarecc-front',   'Emare CC Frontend',         'local',   'node',    'Komuta kontrol merkezi frontend'),
    (8109, 'emaredatabase',   'Emare Database',            'local',   'python',  'Veritabanı yönetim servisi'),
    (8110, 'emareflux',       'Emare Flux',                'local',   'python',  'Akış yönetimi'),
    (8111, 'emarefree',       'Emare Free',                'local',   'python',  'Ücretsiz tier servisi'),
    (8112, 'emaregithup',     'Emare Githup',              'local',   'python',  'Git yönetim entegrasyonu'),
    (8113, 'emaregoogle',     'Emare Google',              'local',   'node',    'Google API entegrasyonu'),
    (8114, 'emarekatip',      'Emare Katip',               'local',   'python',  'Belge/yazışma yönetimi'),
    (8115, 'emarepazar',      'Emare Pazar',               'local',   'python',  'E-ticaret/pazar yeri'),
    (8116, 'emarepos',        'Emare POS',                 'local',   'node',    'Satış noktası sistemi'),
    (8117, 'emaresebil',      'Emare Sebil',               'local',   'python',  'Kaynak dağıtım servisi'),
    (8118, 'emaresetup',      'Emare Setup',               'local',   'python',  'Kurulum wizard servisi'),
    (8119, 'emareteam',       'Emare Team',                'local',   'python',  'Ekip yönetimi'),
    (8120, 'emareulak',       'Emare Ulak',                'local',   'node',    'Mesajlaşma/bildirim servisi'),
    (8121, 'emarevscodeasistan','Emare VSCode Asistan',    'local',   'python',  'VS Code yapay zeka eklentisi'),
    (8122, 'emarework',       'Emare Work',                'local',   'python',  'Koordinasyon sistemi'),
    (8123, 'emare-os',        'Emare OS',                  'local',   'docker',  'Neurokernel Linux altyapısı'),
    (8124, 'emare-hup',       'Emare Hup',                 'local',   'node',    'Geliştirici hub platformu'),
    (8125, 'emaresiber',      'Emare Siber',               'local',   'python',  'Siber güvenlik multi-agent'),
    (8126, 'emare-hosting',   'Emare Hosting',             'dc1',     'python',  'Hosting yönetim paneli'),
    (8127, 'emare-log',       'Emare Log',                 'local',   'python',  'Log yönetim sistemi'),
    (8128, 'emareaplincedesk','Emare Aplince Desk',        'local',   'php',     'Laravel destek masası'),
    (8129, 'sosyal-medya',    'Sosyal Medya Yönetim Aracı','local',   'python',  'Sosyal medya otomasyon'),
    (8130, 'girhup',          'Girhup',                    'local',   'python',  'İç git servisi'),
]


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------

def _require_admin():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Giriş gerekli'}), 401
    if not getattr(current_user, 'is_admin', False):
        return jsonify({'error': 'Yetkisiz'}), 403
    return None


# ---------------------------------------------------------------------------
# Endpoint'ler
# ---------------------------------------------------------------------------

@ports_bp.get('')
@login_required
def list_ports():
    """Tüm kayıtlı portları listele."""
    status_filter = request.args.get('status')          # ?status=allocated
    search        = request.args.get('q', '').strip()   # ?q=emareai

    q = PortRegistry.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    if search:
        like = f'%{search}%'
        q = q.filter(
            db.or_(
                PortRegistry.project_name.ilike(like),
                PortRegistry.project_slug.ilike(like),
            )
        )
    records = q.order_by(PortRegistry.port).all()
    return jsonify({
        'total':   len(records),
        'ports':   [r.to_dict() for r in records],
        'next_free': PortRegistry.next_free_port() if not status_filter else None,
    })


@ports_bp.get('/next')
@login_required
def next_free():
    """Bir sonraki boş portu döndür (tahsis ETMEz)."""
    try:
        port = PortRegistry.next_free_port()
        return jsonify({'next_free_port': port})
    except ValueError as e:
        return jsonify({'error': str(e)}), 503


@ports_bp.post('/allocate')
@login_required
def allocate():
    """
    Yeni proje için port tahsis et.
    Body (JSON):
      - project_name  : str  (zorunlu)
      - project_slug  : str  (zorunlu)
      - project_path  : str  (opsiyonel)
      - dc            : str  (opsiyonel, varsayılan dc1)
      - stack         : str  (opsiyonel, varsayılan python)
      - description   : str  (opsiyonel)
      - preferred_port: int  (opsiyonel, istenen port numarası)
    """
    data = request.get_json(force=True, silent=True) or {}

    project_name = data.get('project_name', '').strip()
    project_slug = data.get('project_slug', '').strip()

    if not project_name or not project_slug:
        return jsonify({'error': 'project_name ve project_slug zorunludur'}), 400

    try:
        record = PortRegistry.allocate(
            project_name   = project_name,
            project_slug   = project_slug,
            project_path   = data.get('project_path'),
            dc             = data.get('dc', 'dc1'),
            stack          = data.get('stack', 'python'),
            description    = data.get('description'),
            allocated_by   = current_user.username if current_user.is_authenticated else 'api',
            preferred_port = data.get('preferred_port'),
        )
        return jsonify({
            'success': True,
            'message': f'Port {record.port} başarıyla tahsis edildi.',
            'port':    record.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 409


@ports_bp.delete('/<int:port>')
@login_required
def release(port: int):
    """Portu serbest bırak."""
    err = _require_admin()
    if err:
        return err

    record = PortRegistry.query.filter_by(port=port).first()
    if not record:
        return jsonify({'error': f'Port {port} kayıtlı değil'}), 404

    if record.status == PortRegistry.STATUS_RESERVED:
        return jsonify({'error': f'Port {port} sistem tarafından rezerve edilmiş, serbest bırakılamaz'}), 403

    record.release()
    return jsonify({'success': True, 'message': f'Port {port} serbest bırakıldı.'})


@ports_bp.post('/seed')
@login_required
def seed():
    """
    Bilinen tüm Emare projelerinin portlarını veritabanına yükle.
    Admin yetkisi gerektirir. Var olanları atlar.
    """
    err = _require_admin()
    if err:
        return err

    added   = []
    skipped = []

    for port, slug, name, dc, stack, desc in _SEED_DATA:
        existing = PortRegistry.query.filter_by(port=port).first()
        if existing:
            skipped.append(port)
            continue

        record = PortRegistry(
            port         = port,
            project_name = name,
            project_slug = slug,
            dc           = dc,
            stack        = stack,
            description  = desc,
            status       = PortRegistry.STATUS_ALLOCATED,
            allocated_by = 'system-seed',
        )
        db.session.add(record)
        added.append(port)

    # Rezerve portları da kaydet
    reserved_map = {
        5432:  ('PostgreSQL',    'postgres', 'db', 'db',     'Ana veritabanı'),
        6379:  ('Redis',         'redis',    'all','infra',   'Cache/kuyruk'),
        7474:  ('Neo4j HTTP',    'neo4j',    'all','infra',   'Graf veritabanı HTTP'),
        7687:  ('Neo4j Bolt',    'neo4j',    'all','infra',   'Graf veritabanı Bolt'),
        11434: ('Ollama',        'ollama',   'all','ai',      'Yerel LLM servisi'),
        3001:  ('Nginx Proxy A', 'nginx-a',  'dc1','infra',   'Nginx alt port A'),
        3003:  ('Nginx Proxy B', 'nginx-b',  'dc1','infra',   'Nginx alt port B'),
    }
    for p, (name, slug, dc, stack, desc) in reserved_map.items():
        if not PortRegistry.query.filter_by(port=p).first():
            db.session.add(PortRegistry(
                port=p, project_name=name, project_slug=slug,
                dc=dc, stack=stack, description=desc,
                status=PortRegistry.STATUS_RESERVED, allocated_by='system',
            ))
            added.append(p)
        else:
            skipped.append(p)

    db.session.commit()
    return jsonify({
        'success': True,
        'added':   sorted(added),
        'skipped': sorted(skipped),
        'total_added': len(added),
    })
