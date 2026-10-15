"""File-type detection by extension, cross-checked against magic bytes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath

# extension -> (category, language/format label)
EXTENSIONS: dict[str, tuple[str, str]] = {
    ".xlsx": ("spreadsheet", "Excel workbook"),
    ".xlsm": ("spreadsheet", "Excel macro-enabled workbook"),
    ".xls": ("spreadsheet", "Excel 97-2003 workbook"),
    ".csv": ("table", "CSV"),
    ".tsv": ("table", "TSV"),
    ".pdf": ("pdf", "PDF"),
    ".docx": ("word", "Word document"),
    ".doc": ("word_legacy", "Word 97-2003 document"),
    ".txt": ("text", "Plain text"),
    ".md": ("text", "Markdown"),
    ".log": ("text", "Log"),
    ".json": ("data", "JSON"),
    ".xml": ("data", "XML"),
    ".yml": ("data", "YAML"),
    ".yaml": ("data", "YAML"),
    ".toml": ("data", "TOML"),
    ".ipynb": ("notebook", "Jupyter notebook"),
    ".py": ("code", "Python"),
    ".sql": ("code", "SQL"),
    ".java": ("code", "Java"),
    ".js": ("code", "JavaScript"),
    ".jsx": ("code", "JavaScript (JSX)"),
    ".ts": ("code", "TypeScript"),
    ".tsx": ("code", "TypeScript (TSX)"),
    ".html": ("code", "HTML"),
    ".css": ("code", "CSS"),
    ".r": ("code", "R"),
    ".rmd": ("code", "R Markdown"),
    ".sas": ("code", "SAS"),
    ".do": ("code", "Stata"),
    ".m": ("code", "MATLAB"),
    ".mat": ("binary_data", "MATLAB data"),
    ".zip": ("archive", "ZIP archive"),
}

ZIP_BASED = {".xlsx", ".xlsm", ".docx", ".zip"}
OLE_BASED = {".xls", ".doc"}


@dataclass
class Detection:
    extension: str
    category: str
    label: str
    error: str | None = None


def safe_display_name(name: str) -> str:
    """Strip any directory components and control characters from a client-supplied filename.

    The display name is metadata only — stored files are always named by a server-generated id.
    """
    base = PurePath(name.replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip() or "unnamed"
    return base[:180]


def detect(filename: str, head: bytes) -> Detection:
    ext = PurePath(filename.lower()).suffix
    if ext not in EXTENSIONS:
        return Detection(ext, "unsupported", "Unsupported", f"File type '{ext or 'none'}' is not supported yet.")
    category, label = EXTENSIONS[ext]
    if ext in ZIP_BASED and not head.startswith(b"PK\x03\x04"):
        if ext == ".zip" and head.startswith(b"PK\x05\x06"):
            return Detection(ext, category, label)  # empty zip
        return Detection(ext, category, label, f"Content is not a valid {label} (expected a ZIP container).")
    if ext in OLE_BASED and not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return Detection(ext, category, label, f"Content is not a valid {label}.")
    if ext == ".pdf" and b"%PDF" not in head[:1024]:
        return Detection(ext, category, label, "Content is not a valid PDF.")
    if category in ("text", "data", "code", "table", "notebook") and b"\x00" in head[:4096]:
        if not (head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff")):
            return Detection(ext, category, label, "File looks binary, not text.")
    return Detection(ext, category, label)
