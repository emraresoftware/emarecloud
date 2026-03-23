"""
Emare Security OS — 5651 log damgalama katmani.

Bu modul, 5651 kayit butunlugu icin hash-zinciri olusturur ve
opsiyonel olarak RFC3161 uyumlu TSA (or. TUBITAK KamuSM) uzerinden
zaman damgasi alip kayda ekler.
"""

import base64
import hashlib
import json
import shutil
import ssl
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast
from urllib import error as url_error
from urllib import request as url_request


class TubitakTimestampClient:
    """RFC3161 TSA istemcisi (openssl + HTTP POST)."""

    def __init__(self, tsa_url: str = '', username: str = '',
                 password: str = '', timeout: int = 10,
                 dry_run: bool = True, ca_file: str = ''):
        self.tsa_url = (tsa_url or '').strip()
        self.username = username or ''
        self.password = password or ''
        self.timeout = int(timeout or 10)
        self.dry_run = bool(dry_run)
        self.ca_file = (ca_file or '').strip()

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _check_openssl(self):
        return shutil.which('openssl') is not None

    def _build_auth_header(self):
        if not self.username:
            return None
        token = f'{self.username}:{self.password}'.encode('utf-8')
        return 'Basic ' + base64.b64encode(token).decode('ascii')

    def request_timestamp(self, digest_hex: str) -> Dict[str, Any]:
        """Digest icin TSA token alir.

        Returns:
            {
                'provider': 'TUBITAK-KamuSM',
                'status': 'stamped|skipped|failed',
                'tsa_time': iso_time,
                'token_b64': '...',
                'error': '...'
            }
        """
        digest_hex = (digest_hex or '').strip().lower()
        if len(digest_hex) != 64:
            return {
                'provider': 'TUBITAK-KamuSM',
                'status': 'failed',
                'tsa_time': self._now(),
                'error': 'Digest SHA-256 hex olmali.',
            }

        if self.dry_run:
            pseudo = hashlib.sha256(f'mock:{digest_hex}:{self._now()}'.encode('utf-8')).digest()
            return {
                'provider': 'TUBITAK-KamuSM',
                'status': 'skipped',
                'tsa_time': self._now(),
                'token_b64': base64.b64encode(pseudo).decode('ascii'),
                'note': 'dry-run modunda gercek TSA cagrisi yapilmadi',
            }

        if not self.tsa_url:
            return {
                'provider': 'TUBITAK-KamuSM',
                'status': 'failed',
                'tsa_time': self._now(),
                'error': 'TSA URL tanimli degil.',
            }

        if not self._check_openssl():
            return {
                'provider': 'TUBITAK-KamuSM',
                'status': 'failed',
                'tsa_time': self._now(),
                'error': 'openssl bulunamadi.',
            }

        with tempfile.TemporaryDirectory(prefix='emare5651_') as td:
            req_path = f'{td}/req.tsq'
            resp_path = f'{td}/resp.tsr'

            q = subprocess.run(
                [
                    'openssl', 'ts', '-query', '-sha256', '-digest', digest_hex,
                    '-cert', '-out', req_path,
                ],
                capture_output=True,
                text=True,
            )
            if q.returncode != 0:
                return {
                    'provider': 'TUBITAK-KamuSM',
                    'status': 'failed',
                    'tsa_time': self._now(),
                    'error': f'TSQ olusturulamadi: {q.stderr.strip()}',
                }

            try:
                with open(req_path, 'rb') as fh:
                    body = fh.read()

                headers = {'Content-Type': 'application/timestamp-query'}
                auth = self._build_auth_header()
                if auth:
                    headers['Authorization'] = auth

                req = url_request.Request(
                    self.tsa_url,
                    data=body,
                    headers=headers,
                    method='POST',
                )
                ssl_ctx = ssl.create_default_context()
                if self.ca_file:
                    ssl_ctx.load_verify_locations(self.ca_file)
                with url_request.urlopen(req, timeout=self.timeout,
                                         context=ssl_ctx) as resp:
                    tsr = resp.read()

                with open(resp_path, 'wb') as fh:
                    fh.write(tsr)
            except url_error.URLError as e:
                return {
                    'provider': 'TUBITAK-KamuSM',
                    'status': 'failed',
                    'tsa_time': self._now(),
                    'error': f'TSA erisim hatasi: {e}',
                }
            except Exception as e:
                return {
                    'provider': 'TUBITAK-KamuSM',
                    'status': 'failed',
                    'tsa_time': self._now(),
                    'error': f'TSA isleme hatasi: {e}',
                }

            if self.ca_file:
                v = subprocess.run(
                    [
                        'openssl', 'ts', '-verify', '-in', resp_path,
                        '-queryfile', req_path, '-CAfile', self.ca_file,
                    ],
                    capture_output=True,
                    text=True,
                )
                if v.returncode != 0:
                    return {
                        'provider': 'TUBITAK-KamuSM',
                        'status': 'failed',
                        'tsa_time': self._now(),
                        'error': f'TSR dogrulama hatasi: {v.stderr.strip()}',
                    }

            return {
                'provider': 'TUBITAK-KamuSM',
                'status': 'stamped',
                'tsa_time': self._now(),
                'token_b64': base64.b64encode(tsr).decode('ascii'),
            }


class Law5651Stamper:
    """5651 uyumlu hash-zinciri ve zaman damgasi yonetimi."""

    def __init__(self, organization: str = 'Emare Security OS',
                 tsa_client: Optional[TubitakTimestampClient] = None,
                 enabled: bool = True, stamp_every: int = 1):
        self.organization = organization
        self.tsa_client = tsa_client
        self.enabled = bool(enabled)
        self.stamp_every = max(1, int(stamp_every or 1))

        self._lock = threading.Lock()
        self._chain_index = 0
        self._last_chain_hash: str = '0' * 64
        self._last_entry_id = 0
        self._total_stamped = 0
        self._total_failed = 0
        self._total_skipped = 0

    def _entry_extra(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        raw = entry.get('extra')
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}

    def _canonical_entry(self, entry: Dict[str, Any]) -> bytes:
        clean_extra: Dict[str, Any] = dict(self._entry_extra(entry))
        clean_extra.pop('law_5651', None)
        payload: Dict[str, Any] = {
            'id': entry.get('id'),
            'ts': entry.get('ts'),
            'level': entry.get('level'),
            'category': entry.get('category'),
            'method': entry.get('method'),
            'path': entry.get('path'),
            'ip': entry.get('ip'),
            'status': entry.get('status'),
            'message': entry.get('message'),
            'server_id': entry.get('server_id'),
            'extra': clean_extra,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':')).encode('utf-8')

    def _sha256_hex(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def restore_from_entries(self, entries: List[Dict[str, Any]]):
        """Servis yeniden basladiginda zincir durumunu son kayittan yukler."""
        if not entries:
            return
        with self._lock:
            for entry in entries:
                extra = self._entry_extra(entry)
                meta_raw = extra.get('law_5651')
                meta: Dict[str, Any] = cast(Dict[str, Any], meta_raw) if isinstance(meta_raw, dict) else {}
                if not meta:
                    continue
                ch = str(meta.get('chain_hash') or '').strip().lower()
                idx = int(meta.get('chain_index') or 0)
                if len(ch) == 64 and idx > self._chain_index:
                    self._chain_index = idx
                    self._last_chain_hash = ch
                    self._last_entry_id = int(entry.get('id') or 0)

    def stamp_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Tek bir log kaydi icin 5651 metadata olusturur."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._chain_index += 1
            prev_hash = self._last_chain_hash
            entry_hash = self._sha256_hex(self._canonical_entry(entry))
            chain_hash = self._sha256_hex(f'{prev_hash}:{entry_hash}'.encode('utf-8'))

            tsa_result: Dict[str, Any] = {
                'provider': 'TUBITAK-KamuSM',
                'status': 'skipped',
                'tsa_time': now,
                'note': 'damga devre disi',
            }

            if self.enabled and self.tsa_client and (self._chain_index % self.stamp_every == 0):
                tsa_result = self.tsa_client.request_timestamp(chain_hash)

            status = tsa_result.get('status', 'skipped')
            if status == 'stamped':
                self._total_stamped += 1
            elif status == 'failed':
                self._total_failed += 1
            else:
                self._total_skipped += 1

            self._last_chain_hash = chain_hash
            self._last_entry_id = int(entry.get('id') or 0)

            return {
                'law': '5651',
                'version': '1.0',
                'organization': self.organization,
                'chain_index': self._chain_index,
                'prev_chain_hash': prev_hash,
                'entry_hash': entry_hash,
                'chain_hash': chain_hash,
                'generated_at': now,
                'tsa': tsa_result,
            }

    def verify_entries(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verilen kayitlari sirayla dogrulayip zincir kirigini raporlar."""
        if not entries:
            return {'ok': True, 'verified': 0, 'broken_at': None, 'reason': ''}

        ordered = sorted(entries, key=lambda e: int(e.get('id') or 0))
        prev_hash = '0' * 64
        verified = 0

        for entry in ordered:
            extra = self._entry_extra(entry)
            meta_raw = extra.get('law_5651')
            meta: Dict[str, Any] = cast(Dict[str, Any], meta_raw) if isinstance(meta_raw, dict) else {}
            if not meta:
                return {
                    'ok': False,
                    'verified': verified,
                    'broken_at': int(entry.get('id') or 0),
                    'reason': '5651 metadatasi eksik.',
                }

            expected_entry_hash = self._sha256_hex(self._canonical_entry(entry))
            if meta.get('entry_hash') != expected_entry_hash:
                return {
                    'ok': False,
                    'verified': verified,
                    'broken_at': int(entry.get('id') or 0),
                    'reason': 'entry_hash uyusmuyor.',
                }

            if meta.get('prev_chain_hash') != prev_hash:
                return {
                    'ok': False,
                    'verified': verified,
                    'broken_at': int(entry.get('id') or 0),
                    'reason': 'prev_chain_hash kirik.',
                }

            expected_chain_hash = self._sha256_hex(f'{prev_hash}:{expected_entry_hash}'.encode('utf-8'))
            if meta.get('chain_hash') != expected_chain_hash:
                return {
                    'ok': False,
                    'verified': verified,
                    'broken_at': int(entry.get('id') or 0),
                    'reason': 'chain_hash uyusmuyor.',
                }

            prev_hash = expected_chain_hash
            verified += 1

        return {'ok': True, 'verified': verified, 'broken_at': None, 'reason': ''}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'enabled': self.enabled,
                'organization': self.organization,
                'last_entry_id': self._last_entry_id,
                'chain_index': self._chain_index,
                'last_chain_hash': self._last_chain_hash,
                'total_stamped': self._total_stamped,
                'total_failed': self._total_failed,
                'total_skipped': self._total_skipped,
                'stamp_every': self.stamp_every,
                'provider': 'TUBITAK-KamuSM',
            }
