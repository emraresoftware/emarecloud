"""
EmareCloud — AES-256-GCM Şifreleme
SSH kimlik bilgilerini güvenli şekilde şifreler ve çözer.
Master key ortam değişkeninden veya otomatik oluşturulan .master.key dosyasından alınır.
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_master_key: bytes | None = None


def _get_master_key() -> bytes:
    """Master key'i döndürür. Yoksa oluşturur."""
    global _master_key
    if _master_key:
        return _master_key

    key_source = os.environ.get('MASTER_KEY')
    if not key_source:
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.master.key')
        if os.path.exists(key_file):
            with open(key_file) as f:
                key_source = f.read().strip()
        else:
            # Geliştirme ortamı: otomatik key oluştur
            key_source = os.urandom(32).hex()
            with open(key_file, 'w') as f:
                f.write(key_source)
            os.chmod(key_file, 0o600)
            print("  ⚠️  Yeni master key oluşturuldu: .master.key")
            print("     Production'da MASTER_KEY ortam değişkeni kullanın!")

    # SHA-256 ile sabit 32 byte key türet
    _master_key = hashlib.sha256(key_source.encode()).digest()
    return _master_key


def encrypt_password(password: str) -> tuple[bytes, bytes]:
    """
    Şifreyi AES-256-GCM ile şifreler.
    Returns: (ciphertext, nonce)
    """
    key = _get_master_key()
    nonce = os.urandom(12)  # 96-bit nonce
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, password.encode('utf-8'), None)
    return ciphertext, nonce


def decrypt_password(ciphertext: bytes, nonce: bytes) -> str:
    """AES-256-GCM ile şifrelenmiş şifreyi çözer."""
    key = _get_master_key()
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception:
        return ''
