"""Prospective paper scope operator. Default action is refusal; no import-time I/O."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import resource
import subprocess
import sys
import time

from retry_semantics.study2 import sheets_live_preparation as prepared
from retry_semantics.study2 import sheets_paper_scope_provisioning as paper
from retry_semantics.study2 import sheets_phase3_control as phase3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as phase3_operator
from retry_semantics.study2 import sheets_phase4_control as phase4
from retry_semantics.study2 import sheets_phase4_setup as setup
from retry_semantics.study2 import sheets_paper_live_transport as live

ROOT = paper.REPOSITORY_ROOT
CHECKPOINT = "ca0f169bbf4b0846409fb5c29b397565ca383a95"
DOC = "research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_LIVE_BINDING_V1.md"
TRANSPORT = "src/retry_semantics/study2/sheets_paper_live_transport.py"
OPERATOR = "src/retry_semantics/study2/sheets_paper_scope_operator.py"
PINNED = {
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_PROVISIONING_V1.md": "1999e20672f487f8831d7d2f89bd42d954366ee87f10f7d16b9958371998e1ef",
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_SCOPE_CREATE_REQUEST_V1.json": "6596f530ba6fb5799b65c48dc73c84a8a4265b515bfc3b83473176ea1747e880",
    "src/retry_semantics/study2/sheets_paper_scope_provisioning.py": "a3c34e6f4914b5a0d3cea6206feb169fbaf4c421ae301bce366791cd1873d3f7",
    "tests/test_study2_sheets_paper_scope_provisioning.py": "22528e5894ad0c07a1cdf794ebcb2d9cc8e0cc8f510183b08f7616cf4609c632",
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_MANIFEST_INPUTS_V1.md": "15a2357e99df0c856f99b8b5419e923be927cdfeef7535be4d21a475762e6109",
    "research/study2/sheets/GOOGLE_SHEETS_PAPER_NAMESPACE_RESERVATION_V1.json": "a8a8bcd2751c56b05e9a9a569a6ad5f16e7d260b6a8ce5fb57dd244aef594506",
    "src/retry_semantics/study2/sheets_paper_registry.py": "09bec0ece06bacefd357a2067f4c3a6955347825fa692e6ad587d14e1d746fa8",
    "src/retry_semantics/serialization.py": "48cb2030382334abc9ea13079e5bc91ed58be08640667e78570e529ddaa48cce",
    "src/retry_semantics/study2/sheets_live_preparation.py": "c3f4c775d80507cef3776391126b663eb216e7e97d667aaa67bb1b29ea7cb7da",
    "src/retry_semantics/study2/sheets_http_framing.py": "50fb8f45bccaf8f0ff1895bc487cd8c85fe3ef47c79c2b51b2aa7a6b4a4949c8",
    "src/retry_semantics/study2/sheets_phase3_credentials.py": "86d466abfe05da6a648d170836a4142f51020d69881cafa02e642adcaace404b",
    "src/retry_semantics/study2/sheets_phase3_operator.py": "c582e06401c342ace183fceb002210dda01433c1fbc5cd5acad3079e970e3a86",
    "src/retry_semantics/study2/sheets_phase4_setup.py": "f6963dc2aaa45e9a159311ac1600f8831b1728e647dea26867b0587de127f4e5",
    "src/retry_semantics/study2/sheets_phase4_control.py": "22fa217e1e00d61b48b8ab23343a3484b29c94392bcac39a0d122a06755acb43",
    "src/retry_semantics/study2/sheets_phase3_control.py": "446f4edcf5c5be4f2111f1b9d668560c35234c491782c172c707c2b08b7e811a",
    "src/retry_semantics/study2/sheets_phase2_control.py": "1bfd8c9c1f69fb76da7fe95e65957e728d7b077411f462dae977843a24edd178",
    "src/retry_semantics/study2/sheets_phase2_read.py": "ea9d99ba6fb86fe3fe9cc1bf6429d30903389e22b62f4ab618ea6a4c2ee85603",
    "src/retry_semantics/study2/sheets_live_go_phase1.py": "61481329f0a3f2071987c3a63e28fbcf4b9a04dfa63fe1a4ffc03354364386b1",
    "src/retry_semantics/study2/sheets_offline.py": "b43140a566c64699b51e141ab48fadaaeca1d1eb4e3ec1c51fc18c8d4bcc568d",
}


class PaperOperatorRefused(Exception):
    def __init__(self):
        super().__init__("paper scope operator refused")


def _git(*args):
    result = subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c",
                             "core.untrackedCache=false", *args], cwd=ROOT,
                            capture_output=True, check=True)
    return result.stdout


def source_projection(expected_head: str):
    """Require an externally reviewed full commit and its unmodified working tree."""
    try:
        if (type(expected_head) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_head) is None
                or expected_head == CHECKPOINT
                or _git("rev-parse", "HEAD").decode().strip() != expected_head
                or _git("rev-parse", "--show-toplevel").decode().strip() != str(ROOT)
                or _git("status", "--porcelain", "--ignore-submodules=all")):
            raise PaperOperatorRefused()
        doc = (ROOT / DOC).read_text(encoding="utf-8")
        hashes = {}
        for name in (*PINNED, DOC, TRANSPORT, OPERATOR):
            path = ROOT / name
            if path.is_symlink() or not path.is_file():
                raise PaperOperatorRefused()
            raw = path.read_bytes()
            committed = _git("show", "HEAD:" + name)
            digest = hashlib.sha256(raw).hexdigest()
            if raw != committed or name in PINNED and digest != PINNED[name]:
                raise PaperOperatorRefused()
            if name in (TRANSPORT, OPERATOR) and f"| `{name}` | `{digest}` |" not in doc:
                raise PaperOperatorRefused()
            hashes[name] = digest
        return {"expected_head": expected_head, "sources_sha256": hashes,
                "clean_committed_tree": True}
    except Exception:
        raise PaperOperatorRefused() from None


def _authorized(execute_oauth, oauth_confirmation, execute_provisioning, paper_confirmation):
    if (execute_oauth is not True or execute_provisioning is not True
            or oauth_confirmation != credentials.ACQUISITION_CONFIRMATION
            or paper_confirmation != paper.OPERATOR_CONFIRMATION):
        raise PaperOperatorRefused()


def provision_session(*, configuration: Path, client: Path, expected_head: str,
                      execute_oauth: bool, oauth_confirmation: str,
                      execute_provisioning: bool, paper_confirmation: str,
                      present_url=print):
    """One resident acquisition, then at most one call into the frozen paper gate."""
    _authorized(execute_oauth, oauth_confirmation, execute_provisioning, paper_confirmation)
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise PaperOperatorRefused()
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        raise PaperOperatorRefused() from None
    source_projection(expected_head)
    if (paper.EVIDENCE_ROOT.is_symlink() or not paper.EVIDENCE_ROOT.is_dir()
            or (paper.EVIDENCE_ROOT / paper.INTENT_NAME).exists()):
        raise PaperOperatorRefused()
    token = None
    try:
        config = phase3_operator._typed(phase3.load_json(configuration), phase4.OperatorConfiguration)
        if configuration != config.path("operator.json") or config.expected_head != expected_head:
            raise PaperOperatorRefused()
        review = phase3.load_json(config.path("client-review.json"))
        startup = phase3.load_json(config.path("startup.json"))
        pin = phase3.load_json(config.path("offline-pin.json"))
        token, _metadata = setup.acquire(config, review, startup, pin, client,
            execute_oauth=True, operator_confirmation=oauth_confirmation,
            present_url=present_url)
        if type(token) is not prepared.PreparedToken:
            raise PaperOperatorRefused()
        token.check_ready(now=time.time(), dispatch_budget_seconds=live.TIMEOUT_SECONDS)
        source_projection(expected_head)
        def resident_transport(host, port, method, target, body, bearer):
            token.check_ready(now=time.time(), dispatch_budget_seconds=live.TIMEOUT_SECONDS)
            if bearer is not token.value:
                raise PaperOperatorRefused()
            return live.transport(host, port, method, target, body, bearer)
        return paper.execute_create_once(resident_transport, token.value,
            execute_provisioning=True, operator_confirmation=paper_confirmation)
    except Exception:
        raise PaperOperatorRefused() from None
    finally:
        token = None  # Best effort; CPython does not offer a secure heap.


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prospective paper scope live binding")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--expected-head", required=True)
    review = commands.add_parser("client-review")
    review.add_argument("--client", required=True, type=Path)
    session = commands.add_parser("provision-session")
    session.add_argument("--configuration", required=True, type=Path)
    session.add_argument("--client", required=True, type=Path)
    session.add_argument("--expected-head", required=True)
    session.add_argument("--execute-oauth", action="store_true")
    session.add_argument("--oauth-confirmation", required=True)
    session.add_argument("--execute-provisioning", action="store_true")
    session.add_argument("--paper-confirmation", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            source_projection(args.expected_head)
            print("SOURCE_PIN_PASS; PAPER_OBSERVATIONS=0; COLLECTION_BLOCKED")
        elif args.command == "client-review":
            result = setup.review_client(args.client)
            print(result["public_sha256"])
        else:
            result = provision_session(configuration=args.configuration, client=args.client,
                expected_head=args.expected_head, execute_oauth=args.execute_oauth,
                oauth_confirmation=args.oauth_confirmation,
                execute_provisioning=args.execute_provisioning,
                paper_confirmation=args.paper_confirmation,
                present_url=lambda url: print(url, flush=True))
            print(f"{result['state']}; HTTP_STATUS={result['http_status']}")
            return 0 if result["state"] == "CREATE_RESPONSE_VALIDATED_PENDING_AUDIT" else 2
        return 0
    except Exception:
        print("paper scope operator refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
