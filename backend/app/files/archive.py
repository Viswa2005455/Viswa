"""Safe ZIP inspection: never extracts to disk, rejects traversal, symlinks and zip bombs."""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import PurePosixPath


class UnsafeArchive(ValueError):
    pass


MAX_RATIO = 200  # uncompressed / compressed; higher suggests a decompression bomb


def check_zip_container(data: bytes, max_entries: int, max_uncompressed: int) -> zipfile.ZipFile:
    """Validate any ZIP-based file (zip, xlsx, docx) before a library opens it."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise UnsafeArchive(f"Corrupt ZIP container: {e}") from e
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise UnsafeArchive(f"Archive has {len(infos)} entries (limit {max_entries}).")
    total = sum(i.file_size for i in infos)
    if total > max_uncompressed:
        raise UnsafeArchive(f"Archive expands to {total / 1e6:.0f} MB (limit {max_uncompressed / 1e6:.0f} MB).")
    for i in infos:
        if i.compress_size and i.file_size / i.compress_size > MAX_RATIO and i.file_size > 1_000_000:
            raise UnsafeArchive(f"Entry '{i.filename}' has a suspicious compression ratio (possible zip bomb).")
    return zf


def is_safe_member(name: str, info: zipfile.ZipInfo) -> str | None:
    """Return a reason if the member is unsafe, else None."""
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (len(name) > 1 and name[1] == ":"):
        return "path traversal"
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return "symbolic link"
    if info.flag_bits & 0x1:
        return "encrypted"
    return None


def list_members(zf: zipfile.ZipFile) -> list[dict]:
    out = []
    for i in zf.infolist():
        reason = is_safe_member(i.filename, i)
        out.append({"name": i.filename, "size": i.file_size, "is_dir": i.is_dir(), "blocked": reason})
    return out
