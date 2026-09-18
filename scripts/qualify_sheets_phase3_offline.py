"""Offline Phase 3 qualification. External networking forbidden before collection.

Phase 2 spawned fake workers install their own traps. No dependency downloads,
credentials, live fixture, authorization issuance or OAuth action.
"""
from __future__ import annotations

import argparse
import asyncio  # preload socket subclasses before trapping constructors
import http.client
import os
from pathlib import Path
import socket
import ssl
import sys
import urllib.request

import pytest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("phase3", "sheets", "study2"))
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    for name in tuple(os.environ):
        if name.startswith(("STUDY2_", "GOOGLE_", "GROQ_", "FIREWORKS_")):
            del os.environ[name]
    forbidden_attempts = []
    def denied(*args, **kwargs):
        forbidden_attempts.append(True)
        raise AssertionError("offline qualification: external network forbidden")
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
                 "gethostbyname_ex", "getnameinfo"):
        setattr(socket, name, denied)
    http.client.HTTPSConnection.connect = denied
    http.client.HTTPConnection.connect = denied
    ssl.SSLContext.wrap_socket = denied
    urllib.request.urlopen = denied
    if args.warnings_as_errors:
        os.environ["PYTHONWARNINGS"] = "error"
    pattern = {"phase3": "test_study2_sheets_phase3.py", "sheets": "test_study2_sheets*.py",
               "study2": "test_study2*.py"}[args.suite]
    command = ["-q"] + (["-W", "error"] if args.warnings_as_errors else [])
    command += [str(p.relative_to(root)) for p in sorted((root / "tests").glob(pattern))]
    result = pytest.main(command)
    if forbidden_attempts:
        print("BLOCKED: forbidden external network API invoked")
        return 3
    print("Network trap: zero parent forbidden calls; fake spawned workers install independent traps.")
    return result


if __name__ == "__main__":
    sys.exit(main())
