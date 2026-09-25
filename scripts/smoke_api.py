"""Launch the actual ASGI server and test read-only local HTTP behavior."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from src.services.settings import Settings

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
settings = Settings()
if not settings.api_read_key:
    raise SystemExit("Configure .env first")
Path(".local").mkdir(exist_ok=True)
with Path(".local/api-smoke.log").open("w", encoding="utf-8") as output:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
            "--no-proxy-headers",
        ],
        stdout=output,
        stderr=subprocess.STDOUT,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
            for _attempt in range(30):
                if process.poll() is not None:
                    raise RuntimeError("API server exited; inspect .local/api-smoke.log")
                try:
                    client.get("/health").raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("API startup timed out")
            client.get("/ready").raise_for_status()
            assert client.get("/api/v1/incidents").status_code == 401
            response = client.get(
                "/api/v1/incidents",
                headers={"Authorization": f"Bearer {settings.api_read_key.get_secret_value()}"},
            )
            response.raise_for_status()
            assert isinstance(response.json(), list)
            assert response.headers["X-Request-ID"]
            assert "/api/v1/incidents" in client.get("/openapi.json").json()["paths"]
            print(
                json.dumps(
                    {
                        "health": "passed",
                        "ready": "passed",
                        "auth": "passed",
                        "list_incidents": "passed",
                        "openapi": "passed",
                        "returned_incidents": len(response.json()),
                    }
                )
            )
    finally:
        process.terminate()
        process.wait(timeout=10)
