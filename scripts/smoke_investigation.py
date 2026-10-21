"""Exercise real API/worker processes with an isolated, synthetic SQLite database."""

import asyncio
import hashlib
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from src.models.database import Incident
from src.services.db import make_engine, session_factory

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def seed(url: str) -> None:
    engine = make_engine(url)
    try:
        async with session_factory(engine)() as session:
            session.add(
                Incident(
                    source="api:local-writer",
                    source_id="synthetic-smoke",
                    title="Synthetic process smoke fixture",
                    attributes={"synthetic": True},
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ops-worker-smoke-") as directory:
        folder = Path(directory)
        url = "sqlite+aiosqlite:///" + (folder / "smoke.db").as_posix()
        reader, writer = secrets.token_hex(32), secrets.token_hex(32)
        env = {
            **os.environ,
            "DATABASE_URL": url,
            "ENVIRONMENT": "test",
            "OPENSEARCH_REQUIRED": "false",
            "API_READ_KEY": reader,
            "API_WRITE_KEY": writer,
            "ALLOWED_HOSTS": '["127.0.0.1","localhost"]',
        }
        with (folder / "process.log").open("wb") as log:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                check=True,
                timeout=30,
            )
            asyncio.run(seed(url))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            processes: list[subprocess.Popen[bytes]] = []

            def launch(*args: str) -> subprocess.Popen[bytes]:
                process = subprocess.Popen(
                    [sys.executable, "-m", *args], cwd=ROOT, env=env, stdout=log, stderr=log
                )
                processes.append(process)
                return process

            try:
                api = launch(
                    "uvicorn",
                    "apps.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                    "--no-proxy-headers",
                )
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
                    for _ in range(60):
                        require(api.poll() is None, "API exited before readiness")
                        try:
                            client.get("/ready").raise_for_status()
                            break
                        except httpx.HTTPError:
                            time.sleep(0.25)
                    else:
                        raise RuntimeError("API readiness deadline exceeded")
                    headers = {"Authorization": f"Bearer {writer}", "Idempotency-Key": "first"}
                    read = {"Authorization": f"Bearer {reader}"}
                    body = {
                        "incident": {"source": "api:local-writer", "source_id": "synthetic-smoke"},
                        "question": "Read the synthetic incident snapshot",
                    }
                    route = "/api/v1/investigations"
                    require(
                        client.post(route, json=body).status_code == 401, "Missing auth accepted"
                    )
                    require(
                        client.post(
                            route, json=body, headers={**read, "Idempotency-Key": "reader"}
                        ).status_code
                        == 403,
                        "Reader submitted work",
                    )

                    def submit(key: str) -> dict:
                        response = client.post(
                            route, json=body, headers={**headers, "Idempotency-Key": key}
                        )
                        require(response.status_code == 202, "Submission failed")
                        return response.json()

                    def complete(run_id: str) -> float:
                        started = time.perf_counter()
                        for _ in range(100):
                            response = client.get(f"{route}/{run_id}", headers=read)
                            response.raise_for_status()
                            status = response.json()["status"]
                            require(status not in {"failed", "cancelled"}, "Run failed")
                            if status == "completed":
                                report = client.get(f"{route}/{run_id}/report", headers=read)
                                report.raise_for_status()
                                payload = report.json()
                                require(
                                    payload["run_id"] == run_id, "Report belongs to another run"
                                )
                                require(len(payload["evidence"]) == 1, "Expected incident evidence")
                                evidence = payload["evidence"][0]
                                require(evidence["reference"] == body["incident"], "Wrong source")
                                require(
                                    hashlib.sha256(evidence["excerpt"].encode()).hexdigest()
                                    == evidence["content_sha256"],
                                    "Evidence checksum mismatch",
                                )
                                require(payload["hypotheses"] == [], "Unexpected causal assertion")
                                return round((time.perf_counter() - started) * 1000, 2)
                            time.sleep(0.25)
                        raise RuntimeError("Worker completion deadline exceeded")

                    first = submit("first")
                    require(first["status"] == "pending", "Work ran without a worker")
                    require(submit("first")["run_id"] == first["run_id"], "Replay duplicated work")
                    worker = launch("src.services.incident_worker")
                    first_ms = complete(first["run_id"])
                    stop(worker)
                    queued = submit("restart")
                    cancelled = submit("cancel")
                    response = client.post(
                        f"{route}/{cancelled['run_id']}/cancel",
                        headers=headers,
                        json={"expected_revision": cancelled["revision"]},
                    )
                    require(response.status_code == 200, "Cancellation failed")
                    launch("src.services.incident_worker")
                    restart_ms = complete(queued["run_id"])
                    response = client.get(f"{route}/{cancelled['run_id']}", headers=read)
                    response.raise_for_status()
                    require(response.json()["status"] == "cancelled", "Cancelled work executed")
                    require(
                        client.get(
                            f"{route}/{cancelled['run_id']}/report", headers=read
                        ).status_code
                        == 409,
                        "Cancelled work published a report",
                    )
                    print(
                        json.dumps(
                            {
                                "synthetic": True,
                                "backend": "SQLite",
                                "python": platform.python_version(),
                                "platform": platform.system(),
                                "separate_api_worker_processes": True,
                                "authorization": "passed",
                                "idempotent_submission": "passed",
                                "report_checksum": "passed",
                                "queued_work_after_restart": "passed",
                                "cancellation": "passed",
                                "first_completion_ms": first_ms,
                                "restart_completion_ms": restart_ms,
                                "timing_scope": (
                                    "single synthetic run; includes worker startup and polling"
                                ),
                            },
                            indent=2,
                        )
                    )
            finally:
                for process in reversed(processes):
                    stop(process)


if __name__ == "__main__":
    main()
