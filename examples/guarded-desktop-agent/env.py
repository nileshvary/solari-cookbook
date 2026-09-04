"""Startup: OS trust store + .env loading, with clear key errors. Kept tiny and
self-contained so this folder can be copied and run on its own.

Keys are read from a `.env` in THIS folder; if there isn't one yet, it falls back
to the sibling `agent-security-range/.env` so an existing checkout just works.
Secrets are never printed (only a masked prefix, on request).
"""

from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
_LOCAL = HERE / ".env"
_SIBLING = HERE.parent / "agent-security-range" / ".env"


def _load_dotenv(path: pathlib.Path) -> None:
    # utf-8-sig tolerates a BOM (Notepad on Windows adds one).
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def bootstrap() -> None:
    try:
        import truststore

        truststore.inject_into_ssl()  # verify TLS via the OS store (corp proxies)
    except Exception:
        pass
    for candidate in (_LOCAL, _SIBLING):
        if candidate.exists():
            _load_dotenv(candidate)
            break


def require_key(name: str, where: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(
            f"\n  x  Missing {name}.\n"
            f"     Put it in {_LOCAL} (or {_SIBLING}). Get one at {where}.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return val
