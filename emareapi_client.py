"""
EmareAPI Client SDK
===================
Tüm Derviş projeleri bu modülü kullanarak merkezi API anahtar servisinden
anahtarlarını güvenli şekilde alır.

Kullanım:
    from emareapi_client import EmareAPIClient

    client = EmareAPIClient()
    openai_key = client.get("OPENAI_API_KEY")
    gemini_key = client.get("GOOGLE_API_KEY")
"""
import os
import httpx
from typing import Optional
from functools import lru_cache


class EmareAPIClient:
    """
    EmareAPI Anahtar Servisi istemcisi.
    Ortam değişkenleri veya parametre ile yapılandırılır.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("EMAREAPI_URL", "http://localhost:8000")).rstrip("/")
        self.username = username or os.getenv("EMAREAPI_USERNAME", "")
        self.password = password or os.getenv("EMAREAPI_PASSWORD", "")
        self._token = token or os.getenv("EMAREAPI_TOKEN", "")
        self._cache: dict = {}

    def _get_token(self) -> str:
        """JWT token al (cache'lenir)."""
        if self._token:
            return self._token
        resp = httpx.post(
            f"{self.base_url}/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=10
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def get(self, key_name: str, use_cache: bool = True) -> str:
        """
        Belirtilen adla API anahtarını getirir.
        Önce cache'e bakar, yoksa servisten çeker.
        """
        key_upper = key_name.upper()
        if use_cache and key_upper in self._cache:
            return self._cache[key_upper]
        token = self._get_token()
        resp = httpx.get(
            f"{self.base_url}/keys/{key_upper}/reveal",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if resp.status_code == 401:
            # Token süresi dolmuş olabilir, yenile
            self._token = ""
            token = self._get_token()
            resp = httpx.get(
                f"{self.base_url}/keys/{key_upper}/reveal",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
        resp.raise_for_status()
        value = resp.json()["value"]
        if use_cache:
            self._cache[key_upper] = value
        return value

    def get_all_for_platform(self, platform: str) -> dict:
        """Belirli bir platforma ait tüm anahtarları getirir."""
        token = self._get_token()
        resp = httpx.get(
            f"{self.base_url}/keys/platform/{platform}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        resp.raise_for_status()
        keys = resp.json()
        result = {}
        for k in keys:
            try:
                result[k["name"]] = self.get(k["name"])
            except Exception:
                pass
        return result

    def clear_cache(self):
        self._cache.clear()
        self._token = ""


# ─── Hazır global istemci (ortam değişkenlerinden) ────────────────────────────
_global_client: Optional[EmareAPIClient] = None


def get_client() -> EmareAPIClient:
    global _global_client
    if _global_client is None:
        _global_client = EmareAPIClient()
    return _global_client


def get_key(name: str) -> str:
    """Kısa yol: get_key("OPENAI_API_KEY")"""
    return get_client().get(name)
