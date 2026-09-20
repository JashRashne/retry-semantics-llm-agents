"""Offline Phase 4 qualification. External networking forbidden before collection.

Phase 2 spawned fake workers install their own traps. No dependency downloads,
credentials, live fixture, authorization issuance or OAuth action.
"""
from __future__ import annotations

import argparse
import asyncio  # preload socket subclasses before trapping constructors
import http.client
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import sys
import urllib.request
import webbrowser

import pytest


def run_qualification(command, *, runner=None):
    """Report the in-process pytest invocation and its actual returned status."""
    print(f"QUALIFICATION_COMMAND: pytest.main({command!r})", flush=True)
    try:
        result = (runner or pytest.main)(command)
    except BaseException as error:
        # Avoid displaying arbitrary exception text, which could contain data.
        print(f"QUALIFICATION_LAUNCH_FAILURE: {type(error).__name__}", flush=True)
        print("QUALIFICATION_EXIT_CODE: unavailable", flush=True)
        return 4
    code = int(result)
    print(f"QUALIFICATION_EXIT_CODE: {code}", flush=True)
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("phase4", "sheets", "study2"))
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
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    def loopback(address):
        try:
            host, port = address[:2]
            return type(port) is int and ipaddress.ip_address(host).is_loopback and ':' not in host
        except (TypeError, ValueError, IndexError):
            return False
    class LoopbackOnlySocket(original_socket):
        def bind(self, address):
            if not loopback(address):
                return denied()
            return super().bind(address)
        def connect(self, address):
            if not loopback(address):
                return denied()
            return super().connect(address)
        def connect_ex(self, address):
            if not loopback(address):
                return denied()
            return super().connect_ex(address)
        def sendto(self, data, *args):
            if not args or not loopback(args[-1]):
                return denied()
            return super().sendto(data, *args)
    def local_create_connection(address, *args, **kwargs):
        if not loopback(address):
            return denied()
        return original_create_connection(address, *args, **kwargs)
    def local_getaddrinfo(host, port, *args, **kwargs):
        if not loopback((host, port)):
            return denied()
        return original_getaddrinfo(host, port, *args, **kwargs)
    socket.socket = LoopbackOnlySocket
    socket.create_connection = local_create_connection
    socket.getaddrinfo = local_getaddrinfo
    for name in ("gethostbyname", "gethostbyname_ex", "getnameinfo"):
        setattr(socket, name, denied)
    http.client.HTTPSConnection.connect = denied
    http.client.HTTPConnection.connect = denied
    ssl.SSLContext.wrap_socket = denied
    urllib.request.urlopen = denied
    urllib.request.OpenerDirector.open = denied
    for name in ("open", "open_new", "open_new_tab"):
        setattr(webbrowser, name, denied)
    if args.warnings_as_errors:
        os.environ["PYTHONWARNINGS"] = "error"
    pattern = {"phase4": "test_study2_sheets_phase4.py", "sheets": "test_study2_sheets*.py",
               "study2": "test_study2*.py"}[args.suite]
    command = ["-q"] + (["-W", "error"] if args.warnings_as_errors else [])
    command += [str(p.relative_to(root)) for p in sorted((root / "tests").glob(pattern))]
    result = run_qualification(command)
    if forbidden_attempts:
        print("BLOCKED: forbidden external network API invoked")
        print("QUALIFICATION_RUNNER_EXIT_CODE: 3")
        return 3
    print("Network/browser trap: zero external forbidden calls; numeric IPv4 loopback tests allowed; fake spawned workers install independent traps.")
    print(f"QUALIFICATION_RUNNER_EXIT_CODE: {result}")
    return result


if __name__ == "__main__":
    sys.exit(main())
