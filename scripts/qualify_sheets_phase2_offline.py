"""Offline qualification runner; traps socket/DNS before collecting tests.

Not an operational runner, issuer or source/runtime pin refresher. Child consumer
processes in Phase 2 tests install the same traps themselves before doing work.
"""
from __future__ import annotations

import argparse
import asyncio  # preload socket subclasses before replacing socket.socket
import os
from pathlib import Path
import socket
import ssl
import sys

import pytest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("phase2", "sheets", "study2"))
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    # Names only. No environment dump, credential access or token acquisition.
    for name in tuple(os.environ):
        if name.startswith(("STUDY2_", "GOOGLE_", "GROQ_", "FIREWORKS_")):
            del os.environ[name]
    def denied(*a, **kw):
        raise AssertionError("offline qualification: socket/DNS disabled")
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
                 "gethostbyname_ex", "getnameinfo"):
        setattr(socket, name, denied)
    if args.warnings_as_errors:
        os.environ["PYTHONWARNINGS"] = "error"  # applies to spawned interpreters too
    pattern = {"phase2": "test_study2_sheets_phase2.py", "sheets": "test_study2_sheets*.py",
               "study2": "test_study2*.py"}[args.suite]
    command = ["-q"]
    if args.warnings_as_errors:
        command += ["-W", "error"]
    command += [str(path.relative_to(root)) for path in sorted((root / "tests").glob(pattern))]
    return pytest.main(command)


if __name__ == "__main__":
    sys.exit(main())
