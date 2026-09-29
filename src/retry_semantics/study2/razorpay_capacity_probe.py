"""Read-only engineering diagnostic; never consumes an experimental namespace."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit

from retry_semantics.serialization import sha256_hex
from retry_semantics.study2 import provider_operator_launch as base
from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperRequest

REQUESTS = 30
GAP_SECONDS = 10


def probe(stopped_run: Path, output: Path, *, credential: str, send=None,
          clock=None, sleep=None, progress=print) -> dict:
    """Test the stopped Fetch All URL at six requests/minute, no automatic retries."""
    send, clock, sleep = send or base.one_shot_http, clock or time.monotonic, sleep or time.sleep
    if json.loads((stopped_run / "inventory.json").read_bytes()) != base.inventory(stopped_run):
        raise base.PaperCollectionError("Stopped evidence inventory changed")
    if json.loads((stopped_run / "summary.json").read_bytes()).get("state") != "STOPPED":
        raise base.PaperCollectionError("Capacity probe requires a sealed stopped run")
    failures = []
    for path in sorted(stopped_run.rglob("*.result.json")):
        record = json.loads(path.read_bytes())
        if (record.get("provider") == "razorpay" and record.get("http_status") == 429
                and record.get("method") == "GET" and record.get("operation_type") == "fetch_all"):
            failures.append((path, record))
    if not failures:
        raise base.PaperCollectionError("No Razorpay Fetch All rate-limit evidence found")
    source, record = failures[-1]
    parsed = urlsplit(record["target"])
    query = parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.netloc != "api.razorpay.com"
            or parsed.path != "/v1/orders" or parsed.fragment
            or set(query) != {"count", "skip", "from", "to"}
            or query["count"] != ["100"]
            or any(len(v) != 1 or not v[0].isdigit() for v in query.values())):
        raise base.PaperCollectionError("Diagnostic target differs from frozen Orders listing")
    output = base.validate_run_directory(output)
    output.mkdir(parents=True, mode=0o700)
    base.write_once(output / "probe-plan.json", {
        "engineering_only": True, "read_only": True, "requests": REQUESTS,
        "gap_seconds": GAP_SECONDS, "stop_on_first_non200": True,
        "target": record["target"], "source_result": str(source.resolve()),
        "source_result_sha256": sha256_hex(source.read_bytes()),
        "probe_code_sha256": sha256_hex(Path(__file__).read_bytes()),
        "host_identity_sha256": base.host_identity(),
        "independent_audit_claimed": False})
    journal = DurablePaperEvidence(output, provider="razorpay", family_id="ENGINEERING_READ_ONLY",
        arm_id="SUSTAINED_CAPACITY", manifest_sha256=record["manifest_sha256"],
        runtime_sha256=record["runtime_sha256"])
    statuses, last_end = [], clock()
    failure_type = None
    try:
        for index in range(REQUESTS):
            while (remaining := last_end + GAP_SECONDS - clock()) > 0:
                sleep(remaining)
            result = journal.record("engineering_read_only",
                PaperRequest("GET", record["target"], (), b""),
                lambda request: send(request, credential=credential))
            last_end = clock()
            statuses.append(result.status)
            progress(f"Read-only capacity {index+1}/{REQUESTS}: HTTP {result.status}", flush=True)
            if (result.status != 200 or result.error or not result.response_received
                    or not result.local_send_completed or not result.dispatch_initiated):
                failure_type = "provider_response_or_transport"
                break
            body = json.loads(result.body)
            if type(body) is not dict or body.get("entity") != "collection" or type(body.get("items")) is not list:
                failure_type = "invalid_collection_response"
                break
    except Exception as exc:
        failure_type = type(exc).__name__  # Never persist potentially credential-bearing text.
    summary = {"engineering_only": True, "read_only": True, "statuses": statuses,
        "passed": len(statuses) == REQUESTS and failure_type is None,
        "failure_type": failure_type, "requests_planned": REQUESTS, "gap_seconds": GAP_SECONDS,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_stop_responses": base.provider_stops(output),
        "experiment_launch_authorized": False}
    base.write_once(output / "summary.json", summary)
    base.write_once(output / "inventory.json", base.inventory(output))
    return summary
