"""Verify a running local Compose API/worker with a scoped synthetic SQL fixture."""

import asyncio
import hashlib
import json
import time
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from sqlalchemy import delete, select

from src.models.database import AuditEvent, Incident, InvestigationRun
from src.services.db import make_engine, session_factory


async def main() -> None:
    values = dotenv_values(".env")
    password = values.get("POSTGRES_PASSWORD")
    reader, writer = values.get("API_READ_KEY"), values.get("API_WRITE_KEY")
    if not password or not reader or not writer:
        raise SystemExit("Generate .env with scripts/init_local.py first")
    engine = make_engine(f"postgresql+asyncpg://ops:{password}@localhost:55432/operations")
    sessions = session_factory(engine)
    fixture = "synthetic-compose-" + uuid4().hex
    source = "api:local-writer"
    try:
        async with sessions() as session, session.begin():
            session.add(
                Incident(
                    source=source,
                    source_id=fixture,
                    title="Synthetic container smoke fixture",
                    attributes={"synthetic": True},
                )
            )
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=5) as client:
            (await client.get("/ready")).raise_for_status()
            started = time.perf_counter()
            response = await client.post(
                "/api/v1/investigations",
                headers={"Authorization": f"Bearer {writer}", "Idempotency-Key": fixture},
                json={
                    "incident": {"source": source, "source_id": fixture},
                    "question": "Read the synthetic container fixture",
                },
            )
            response.raise_for_status()
            run_id = response.json()["run_id"]
            read = {"Authorization": f"Bearer {reader}"}
            path = f"/api/v1/investigations/{run_id}"
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                response = await client.get(path, headers=read)
                response.raise_for_status()
                status = response.json()["status"]
                if status == "completed":
                    break
                if status in {"failed", "cancelled"}:
                    raise RuntimeError("Container investigation did not complete")
                await asyncio.sleep(0.25)
            else:
                raise RuntimeError("Container worker completion deadline exceeded")
            response = await client.get(path + "/report", headers=read)
            response.raise_for_status()
            report = response.json()
            assert report["run_id"] == run_id and len(report["evidence"]) == 1
            evidence = report["evidence"][0]
            assert evidence["reference"] == {"source": source, "source_id": fixture}
            assert (
                hashlib.sha256(evidence["excerpt"].encode()).hexdigest()
                == evidence["content_sha256"]
            )
            assert not report["hypotheses"]
            print(
                json.dumps(
                    {
                        "synthetic": True,
                        "backend": "PostgreSQL",
                        "runtime": "local Docker Compose",
                        "api_ready": "passed",
                        "worker_report": "passed",
                        "evidence_checksum": "passed",
                        "submission_to_report_ms": round((time.perf_counter() - started) * 1000, 2),
                        "timing_scope": (
                            "one synthetic incident; includes polling; not a load benchmark"
                        ),
                    },
                    indent=2,
                )
            )
    finally:
        async with sessions() as session, session.begin():
            incident_ids = select(Incident.id).where(
                Incident.source == source, Incident.source_id == fixture
            )
            run_ids = select(InvestigationRun.id).where(
                InvestigationRun.incident_id.in_(incident_ids)
            )
            await session.execute(delete(AuditEvent).where(AuditEvent.resource_id.in_(run_ids)))
            await session.execute(delete(InvestigationRun).where(InvestigationRun.id.in_(run_ids)))
            await session.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
