#!/usr/bin/env python3
"""Moduler sinir denetimi: routes ve core katmaninda yasak importlari yakalar.

Kural seti:
1. routes/* icinden routes/* importu yasak (sadece routes/__init__.py haric).
2. core/* icinden routes/* importu yasak.

Not:
- String/docstring icerikleri degil, sadece Python AST import dugumleri incelenir.
- Cikis kodu 0: temiz, 1: ihlal var.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = ROOT / 'routes'
CORE_DIR = ROOT / 'core'


@dataclass
class Ihlal:
    dosya: Path
    satir: int
    mesaj: str


def _python_dosyalari(klasor: Path) -> list[Path]:
    if not klasor.exists():
        return []
    return sorted(p for p in klasor.rglob('*.py') if p.is_file())


def _module_metni_dugum(dugum: ast.AST) -> str:
    if isinstance(dugum, ast.Import):
        return ', '.join(alias.name for alias in dugum.names)
    if isinstance(dugum, ast.ImportFrom):
        mod = dugum.module or ''
        if dugum.names:
            isimler = ', '.join(alias.name for alias in dugum.names)
            return f'{mod} -> {isimler}'
        return mod
    return ''


def _routes_icinde_routes_import_kontrol(dosya: Path, agac: ast.AST) -> list[Ihlal]:
    ihlaller: list[Ihlal] = []
    rel = dosya.relative_to(ROOT)

    if rel.as_posix() == 'routes/__init__.py':
        return ihlaller

    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for alias in dugum.names:
                if alias.name == 'routes' or alias.name.startswith('routes.'):
                    ihlaller.append(
                        Ihlal(dosya=rel, satir=dugum.lineno, mesaj=f'Route dosyasinda yasak import: {alias.name}')
                    )
        elif isinstance(dugum, ast.ImportFrom):
            mod = dugum.module or ''
            if mod == 'routes' or mod.startswith('routes.'):
                ihlaller.append(
                    Ihlal(
                        dosya=rel,
                        satir=dugum.lineno,
                        mesaj=f'Route dosyasinda yasak from-import: {_module_metni_dugum(dugum)}',
                    )
                )

    return ihlaller


def _core_icinde_routes_import_kontrol(dosya: Path, agac: ast.AST) -> list[Ihlal]:
    ihlaller: list[Ihlal] = []
    rel = dosya.relative_to(ROOT)

    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for alias in dugum.names:
                if alias.name == 'routes' or alias.name.startswith('routes.'):
                    ihlaller.append(
                        Ihlal(dosya=rel, satir=dugum.lineno, mesaj=f'Core dosyasinda yasak import: {alias.name}')
                    )
        elif isinstance(dugum, ast.ImportFrom):
            mod = dugum.module or ''
            if mod == 'routes' or mod.startswith('routes.'):
                ihlaller.append(
                    Ihlal(
                        dosya=rel,
                        satir=dugum.lineno,
                        mesaj=f'Core dosyasinda yasak from-import: {_module_metni_dugum(dugum)}',
                    )
                )

    return ihlaller


def _agac_oku(dosya: Path) -> ast.AST | None:
    try:
        metin = dosya.read_text(encoding='utf-8')
        return ast.parse(metin, filename=str(dosya))
    except SyntaxError as hata:
        rel = dosya.relative_to(ROOT)
        print(f'[HATA] SyntaxError {rel}:{hata.lineno} -> {hata.msg}')
        return None


def main() -> int:
    ihlaller: list[Ihlal] = []

    for dosya in _python_dosyalari(ROUTES_DIR):
        agac = _agac_oku(dosya)
        if agac is None:
            return 1
        ihlaller.extend(_routes_icinde_routes_import_kontrol(dosya, agac))

    for dosya in _python_dosyalari(CORE_DIR):
        agac = _agac_oku(dosya)
        if agac is None:
            return 1
        ihlaller.extend(_core_icinde_routes_import_kontrol(dosya, agac))

    if not ihlaller:
        print('OK: Moduler sinir denetimi temiz (routes/core).')
        return 0

    print('HATA: Moduler sinir ihlalleri bulundu:')
    for ihlal in sorted(ihlaller, key=lambda x: (str(x.dosya), x.satir)):
        print(f'- {ihlal.dosya}:{ihlal.satir} -> {ihlal.mesaj}')

    return 1


if __name__ == '__main__':
    sys.exit(main())
