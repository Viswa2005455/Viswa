"""Maintenance commands.

  uv run python -m app.maintenance purge     delete expired uploads (retention policy) and sessions
"""

from __future__ import annotations

import sys

from .config import get_settings
from .db.session import session_factory
from .files.service import purge_expired


def main(argv: list[str]) -> int:
    if argv[:1] != ["purge"]:
        print(__doc__)
        return 2
    with session_factory()() as db:
        print(purge_expired(db, get_settings()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
