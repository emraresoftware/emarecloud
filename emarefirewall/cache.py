"""
Emare Security OS — Cache Soyutlama Katmanı
=========================================

Küçük ağlar: DictCache (in-memory, sıfır bağımlılık)
ISP modunda : RedisCache (paylaşılan, dağıtık)

Aynı arayüz, farklı backend.
"""

import time
import json
import logging
import threading

logger = logging.getLogger('emarefirewall.cache')


class DictCache:
    """Thread-safe in-memory TTL cache. Tek process'te çalışır.
    Küçük ağlar için ideal — ek bağımlılık yok, ~0ns erişim."""

    def __init__(self, default_ttl: int = 5):
        self._data = {}          # key -> (expire_ts, value)
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            if time.monotonic() > item[0]:
                del self._data[key]
                return None
            return item[1]

    def set(self, key: str, value, ttl: int = None):
        with self._lock:
            expire = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
            self._data[key] = (expire, value)

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str):
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]

    def clear(self):
        with self._lock:
            self._data.clear()

    def incr(self, key: str, ttl: int = None) -> int:
        """Atomik artırma — rate limiter için."""
        with self._lock:
            item = self._data.get(key)
            now = time.monotonic()
            if item is None or now > item[0]:
                expire = now + (ttl if ttl is not None else self._default_ttl)
                self._data[key] = (expire, 1)
                return 1
            val = item[1] + 1
            self._data[key] = (item[0], val)
            return val


class RedisCache:
    """Redis tabanlı cache. ISP modunda çoklu worker arası paylaşım sağlar.
    Redis bağlantı hatası durumunda DictCache'e otomatik fallback yapar (circuit breaker)."""

    def __init__(self, redis_url: str = 'redis://localhost:6379/0',
                 default_ttl: int = 5, prefix: str = 'efw:'):
        try:
            import redis
        except ImportError:
            raise ImportError("ISP modu için redis gerekli: pip install redis")
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._default_ttl = default_ttl
        self._prefix = prefix
        self._fallback = DictCache(default_ttl=default_ttl)
        self._fail_count = 0
        self._circuit_open_until = 0.0   # monotonic timestamp
        self._circuit_threshold = 5      # n hatada circuit aç
        self._circuit_reset_secs = 30    # circuit açıkken bekleme
        # Bağlantı testi
        try:
            self._r.ping()
            logger.info("Redis bağlantısı başarılı: %s", redis_url)
        except Exception as e:
            logger.warning("Redis bağlantısı başarısız, fallback aktif: %s", e)
            self._fail_count = self._circuit_threshold

    def _is_circuit_open(self) -> bool:
        if self._fail_count < self._circuit_threshold:
            return False
        if time.monotonic() > self._circuit_open_until:
            # Half-open: bir kez dene
            return False
        return True

    def _record_success(self):
        if self._fail_count > 0:
            self._fail_count = 0
            logger.info("Redis bağlantısı yeniden kuruldu.")

    def _record_failure(self, e):
        self._fail_count += 1
        if self._fail_count >= self._circuit_threshold:
            self._circuit_open_until = time.monotonic() + self._circuit_reset_secs
            logger.warning("Redis circuit breaker açıldı (%ds). Hata: %s",
                           self._circuit_reset_secs, e)

    def _key(self, key: str) -> str:
        return self._prefix + key

    def get(self, key: str):
        if self._is_circuit_open():
            return self._fallback.get(key)
        try:
            raw = self._r.get(self._key(key))
            self._record_success()
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        except Exception as e:
            self._record_failure(e)
            return self._fallback.get(key)

    def set(self, key: str, value, ttl: int = None):
        t = ttl if ttl is not None else self._default_ttl
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        self._fallback.set(key, value, ttl)
        if self._is_circuit_open():
            return
        try:
            self._r.setex(self._key(key), t, serialized)
            self._record_success()
        except Exception as e:
            self._record_failure(e)

    def delete(self, key: str):
        self._fallback.delete(key)
        if self._is_circuit_open():
            return
        try:
            self._r.delete(self._key(key))
            self._record_success()
        except Exception as e:
            self._record_failure(e)

    def delete_prefix(self, prefix: str):
        self._fallback.delete_prefix(prefix)
        if self._is_circuit_open():
            return
        try:
            pattern = self._key(prefix) + '*'
            cursor = 0
            while True:
                cursor, keys = self._r.scan(cursor, match=pattern, count=100)
                if keys:
                    self._r.delete(*keys)
                if cursor == 0:
                    break
            self._record_success()
        except Exception as e:
            self._record_failure(e)

    def clear(self):
        self._fallback.clear()
        if not self._is_circuit_open():
            try:
                self.delete_prefix('')
            except Exception:
                pass

    def incr(self, key: str, ttl: int = None) -> int:
        """Atomik artırma — dağıtık rate limiter için."""
        if self._is_circuit_open():
            return self._fallback.incr(key, ttl)
        try:
            k = self._key(key)
            val = self._r.incr(k)
            if val == 1:
                self._r.expire(k, ttl if ttl is not None else self._default_ttl)
            self._record_success()
            return val
        except Exception as e:
            self._record_failure(e)
            return self._fallback.incr(key, ttl)


def create_cache(backend: str = 'dict', **kwargs):
    """Yapılandırmaya göre cache backend'i oluştur."""
    if backend == 'redis':
        return RedisCache(
            redis_url=kwargs.get('redis_url', 'redis://localhost:6379/0'),
            default_ttl=kwargs.get('default_ttl', 5),
        )
    return DictCache(default_ttl=kwargs.get('default_ttl', 5))
