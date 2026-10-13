"""Magic-byte detection, stable identity and isolated legacy conversion."""
from __future__ import annotations
import hashlib
import logging
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

@dataclass
class InputFile:
    path: Path
    kind: str
    sha256: str
    duplicate_of: str | None

def detect_type(path: Path) -> str:
    """Identify OOXML/PDF/OLE/text by content; extensions never decide format."""
    data = path.read_bytes()
    if data.startswith(b'%PDF-'):
        return 'pdf'
    if data.startswith(b'PK'):
        try:
            with zipfile.ZipFile(path) as z:
                if 'word/document.xml' in z.namelist():
                    return 'docx'
        except zipfile.BadZipFile:
            pass
        raise ValueError('ZIP is not a DOCX document')
    if data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        # OLE is shared by Office formats; WordDocument stream is mandatory.
        if 'WordDocument'.encode('utf-16le') in data:
            return 'doc'
        raise ValueError('OLE container has no WordDocument stream')
    try:
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            data.decode('utf-16')
        else:
            if b'\x00' in data:
                raise ValueError('binary data')
            data.decode('utf-8-sig')
        return 'txt'
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Unsupported binary format') from exc

def ingest(path: Path, seen: dict[str, str] | None = None) -> InputFile:
    """Hash bytes and annotate duplicates without skipping their output."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    registry = seen if seen is not None else {}
    duplicate = registry.get(digest)
    registry.setdefault(digest, str(path))
    return InputFile(path, detect_type(path), digest, duplicate)

def convert_doc(path: Path, destination: Path, config: dict[str, Any]) -> Path:
    """Convert Word OLE using a private LibreOffice profile; fail explicitly."""
    executable = shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:
        raise RuntimeError('Legacy .doc requires LibreOffice/soffice on PATH')
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='resume-lo-') as profile:
        command = [executable, '-env:UserInstallation=' + Path(profile).as_uri(),
                   '--headless', '--convert-to', 'docx', '--outdir', str(destination), str(path.resolve())]
        subprocess.run(command, check=True, capture_output=True,
                       timeout=config['ingest']['conversion_timeout_seconds'])
    result = destination / (path.stem + '.docx')
    if not result.exists():
        raise RuntimeError('LibreOffice did not produce a DOCX')
    log.info('Converted legacy input %s', path.name)
    return result
