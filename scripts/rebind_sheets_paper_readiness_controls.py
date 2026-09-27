"""Unsafe static-control rebinding is disabled.

All ten controls require a fresh V4.1-bound live readiness session and
independent audit. No prior qualification boolean may be copied forward.
"""

from __future__ import annotations

from typing import NoReturn


def rebind_sheets_controls(**_kwargs: object) -> NoReturn:
    raise ValueError(
        "Sheets static rebinding is prohibited; run a fresh V4.1-bound "
        "readiness session and independently audit all ten controls"
    )


def main() -> int:
    rebind_sheets_controls()


if __name__ == "__main__":
    raise SystemExit(main())
