"""
EmareCloud — Lisans Doğrulama Modülü
RSA-signed JSON lisans dosyası ile sunucu sayısı ve süre kontrolü.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils

logger = logging.getLogger('emarecloud.license')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LICENSE_FILE = os.path.join(BASE_DIR, 'license.json')
LICENSE_PUBLIC_KEY_FILE = os.path.join(BASE_DIR, 'license_public.pem')


class LicenseError(Exception):
    """Lisans hatası."""
    pass


class LicenseInfo:
    """Doğrulanmış lisans bilgileri."""

    def __init__(self, data: dict):
        self.holder = data.get('holder', 'Bilinmeyen')
        self.email = data.get('email', '')
        self.plan = data.get('plan', 'community')
        self.max_servers = data.get('max_servers', 3)
        self.issued_at = data.get('issued_at', '')
        self.expires_at = data.get('expires_at', '')
        self.features = data.get('features', [])
        self.license_id = data.get('license_id', '')

    @property
    def is_expired(self) -> bool:
        """Lisansın süresinin dolup dolmadığını kontrol eder."""
        if not self.expires_at:
            return False  # Süresiz lisans
        try:
            exp = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > exp
        except (ValueError, TypeError):
            return True

    @property
    def days_remaining(self) -> int:
        """Kalan gün sayısı."""
        if not self.expires_at:
            return 9999
        try:
            exp = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            delta = exp - datetime.now(timezone.utc)
            return max(0, delta.days)
        except (ValueError, TypeError):
            return 0

    def to_dict(self) -> dict:
        return {
            'holder': self.holder,
            'email': self.email,
            'plan': self.plan,
            'max_servers': self.max_servers,
            'issued_at': self.issued_at,
            'expires_at': self.expires_at,
            'features': self.features,
            'license_id': self.license_id,
            'is_expired': self.is_expired,
            'days_remaining': self.days_remaining,
        }


# ==================== DOĞRULAMA ====================

def _load_public_key():
    """Lisans doğrulama için public key'i yükler."""
    if not os.path.exists(LICENSE_PUBLIC_KEY_FILE):
        return None
    with open(LICENSE_PUBLIC_KEY_FILE, 'rb') as f:
        return serialization.load_pem_public_key(f.read(), backend=default_backend())


def verify_license(license_path: str = None) -> LicenseInfo | None:
    """
    Lisans dosyasını doğrular ve LicenseInfo döndürür.
    Doğrulama başarısızsa None döndürür.
    """
    path = license_path or LICENSE_FILE

    if not os.path.exists(path):
        logger.info("Lisans dosyası bulunamadı — Community modunda çalışılıyor")
        return _community_license()

    try:
        with open(path, encoding='utf-8') as f:
            license_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Lisans dosyası okunamadı: {e}")
        return _community_license()

    payload = license_data.get('payload', {})
    signature_b64 = license_data.get('signature', '')

    # İmza doğrulama
    public_key = _load_public_key()
    if public_key and signature_b64:
        try:
            import base64
            signature = base64.b64decode(signature_b64)
            payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')
            payload_hash = hashlib.sha256(payload_bytes).digest()

            public_key.verify(
                signature,
                payload_hash,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                utils.Prehashed(hashes.SHA256()),
            )
            logger.info(f"Lisans doğrulandı: {payload.get('holder')} — Plan: {payload.get('plan')}")
        except InvalidSignature:
            logger.warning("Lisans imzası geçersiz — Community moduna düşülüyor")
            return _community_license()
        except Exception as e:
            logger.error(f"Lisans doğrulama hatası: {e}")
            return _community_license()
    elif not public_key:
        logger.info("Public key bulunamadı — Lisans imza doğrulaması atlanıyor")

    info = LicenseInfo(payload)

    if info.is_expired:
        logger.warning(f"Lisans süresi dolmuş: {info.expires_at}")
        return _community_license()

    return info


def _community_license() -> LicenseInfo:
    """Ücretsiz community lisansı (sınırlı)."""
    return LicenseInfo({
        'holder': 'Community',
        'plan': 'community',
        'max_servers': 3,
        'features': ['basic_monitoring', 'ssh_terminal', 'firewall'],
        'license_id': 'community-free',
    })


# ==================== SUNUCU SAYISI KONTROLÜ ====================

def check_server_limit(current_count: int, license_info: LicenseInfo = None) -> tuple[bool, str]:
    """
    Sunucu ekleme limitini kontrol eder.
    (izin_var, mesaj) tuple'ı döndürür.
    """
    if license_info is None:
        license_info = verify_license()

    if license_info is None:
        license_info = _community_license()

    if current_count >= license_info.max_servers:
        return False, (
            f"Sunucu limiti aşıldı ({current_count}/{license_info.max_servers}). "
            f"Mevcut plan: {license_info.plan}. "
            f"Daha fazla sunucu için lisansınızı yükseltin."
        )

    return True, f"Sunucu eklenebilir ({current_count + 1}/{license_info.max_servers})"


def check_feature(feature: str, license_info: LicenseInfo = None) -> bool:
    """Bir özelliğin lisansta etkin olup olmadığını kontrol eder."""
    if license_info is None:
        license_info = verify_license()
    if license_info is None:
        return False

    # Enterprise ve professional tüm özelliklere sahip
    if license_info.plan in ('enterprise', 'professional'):
        return True

    return feature in license_info.features


# ==================== LİSANS OLUŞTURMA (ADMIN TOOL) ====================

def generate_license_keypair(output_dir: str = None):
    """
    Lisans imzalama için RSA anahtar çifti oluşturur.
    SADECE lisans sunucusunda kullanılır — müşteriye sadece public key gönderilir.
    """
    output_dir = output_dir or BASE_DIR

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend(),
    )

    # Private key (sadece lisans sunucusunda)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_path = os.path.join(output_dir, 'license_private.pem')
    with open(private_path, 'wb') as f:
        f.write(private_pem)
    os.chmod(private_path, 0o600)

    # Public key (müşteriye dağıtılır)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = os.path.join(output_dir, 'license_public.pem')
    with open(public_path, 'wb') as f:
        f.write(public_pem)

    logger.info(f"RSA anahtar çifti oluşturuldu: {private_path}, {public_path}")
    return private_path, public_path


def create_signed_license(payload: dict, private_key_path: str, output_path: str = None):
    """
    İmzalı lisans dosyası oluşturur.
    SADECE lisans sunucusunda kullanılır.
    """
    import base64

    with open(private_key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')
    payload_hash = hashlib.sha256(payload_bytes).digest()

    signature = private_key.sign(
        payload_hash,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        utils.Prehashed(hashes.SHA256()),
    )

    license_data = {
        'payload': payload,
        'signature': base64.b64encode(signature).decode('ascii'),
        'format_version': 1,
    }

    output = output_path or LICENSE_FILE
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(license_data, f, indent=2, ensure_ascii=False)

    logger.info(f"İmzalı lisans dosyası oluşturuldu: {output}")
    return output
