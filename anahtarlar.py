"""
EmareCloud — Merkezi Anahtar Yöneticisi
EmareAPI kasasından API anahtarları çeker.

Kullanım:
    from anahtarlar import gemini_key, openai_key, groq_key
    # veya
    from anahtarlar import anahtar
    val = anahtar("ANTHROPIC_API_KEY")
"""
from __future__ import annotations

import os
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@lru_cache(maxsize=1)
def _client():
    try:
        from emareapi_client import EmareAPIClient
        return EmareAPIClient()
    except Exception as e:
        print(f"[anahtarlar] EmareAPI client başlatılamadı: {e}")
        return None


def anahtar(isim: str) -> str:
    """EmareAPI'den veya .env'den API anahtarı döndürür."""
    isim = isim.upper()
    client = _client()
    if client:
        try:
            val = client.get(isim)
            if val and val != "BURAYA_EKLENECEK":
                return val
        except Exception as e:
            print(f"[anahtarlar] EmareAPI'den {isim} alınamadı: {e}")
    fallback = os.getenv(isim, "")
    if fallback:
        return fallback
    raise ValueError(
        f"'{isim}' anahtarı bulunamadı.\n"
        f"  1. EmareAPI çalışıyor mu? → http://localhost:8000\n"
        f"  2. .env dosyasında EMAREAPI_USERNAME/PASSWORD doğru mu?\n"
        f"  3. Admin panelde is_active=true yapıldı mı? → /docs\n"
    )


class _LazyKey:
    def __init__(self, isim: str):
        self._isim = isim
        self._deger: str | None = None
    def _al(self) -> str:
        if self._deger is None:
            self._deger = anahtar(self._isim)
        return self._deger
    def __str__(self):       return self._al()
    def __repr__(self):      return f"LazyKey({self._isim})"
    def __len__(self):       return len(self._al())
    def __bool__(self):      return bool(self._al())
    def __eq__(self, other): return self._al() == other
    def __add__(self, other): return self._al() + other


gemini_key    = _LazyKey("GEMINI_API_KEY")
google_key    = _LazyKey("GOOGLE_API_KEY")
openai_key    = _LazyKey("OPENAI_API_KEY")
anthropic_key = _LazyKey("ANTHROPIC_API_KEY")
groq_key      = _LazyKey("GROQ_API_KEY")
deepseek_key  = _LazyKey("DEEPSEEK_API_KEY")
mistral_key   = _LazyKey("MISTRAL_API_KEY")
