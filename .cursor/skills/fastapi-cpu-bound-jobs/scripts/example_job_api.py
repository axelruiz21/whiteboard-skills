#!/usr/bin/env python3
"""Minimal FastAPI job API for CPU-bound parse work (demo without Tesseract).

Run:
  pip install fastapi uvicorn
  python3 example_job_api.py --port 8080
  # or: uvicorn example_job_api:app --app-dir scripts --port 8080

POST /jobs  JSON body: {"path": "/abs/file.jpg", "config_hash": "default"}
GET  /jobs/{job_id}
"""

from __future__ import annotations

import argparse
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["queued", "running", "succeeded", "failed"]

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False
    FastAPI = HTTPException = JSONResponse = BaseModel = Field = None  # type: ignore


def fake_parse(path: str, config_hash: str) -> dict[str, Any]:
    """Stand-in for whiteboard OCR — CPU-ish work + deterministic digest result."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    data = p.read_bytes()
    acc = 0
    for i, b in enumerate(data[: 200_000]):
        acc = (acc + b * (i + 1)) % 1_000_000_007
    time.sleep(0.05)
    digest = hashlib.sha256(data).hexdigest()
    return {
        "pipeline_version": "example-fake-0.1.0",
        "config_hash": config_hash,
        "source": {"id": f"sha256:{digest}", "path": str(p), "bytes": len(data)},
        "quality": {"status": "ok", "warnings": ["fake_parse: not real OCR"]},
        "sections": [],
        "unresolved": [],
        "demo_checksum": acc,
    }


class Job:
    __slots__ = (
        "id",
        "status",
        "idempotency_key",
        "path",
        "config_hash",
        "result",
        "error",
        "created_ms",
    )

    def __init__(
        self,
        id: str,
        status: JobStatus,
        idempotency_key: str,
        path: str,
        config_hash: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        created_ms: float | None = None,
    ) -> None:
        self.id = id
        self.status = status
        self.idempotency_key = idempotency_key
        self.path = path
        self.config_hash = config_hash
        self.result = result
        self.error = error
        self.created_ms = time.time() * 1000 if created_ms is None else created_ms


class JobStore:
    def __init__(self) -> None:
        self.by_id: dict[str, Job] = {}
        self.by_key: dict[str, str] = {}

    def get(self, job_id: str) -> Job | None:
        return self.by_id.get(job_id)


def make_idempotency_key(path: str, config_hash: str) -> str:
    p = Path(path)
    if p.is_file():
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
    else:
        digest = hashlib.sha256(path.encode()).hexdigest()
    return hashlib.sha256(f"{digest}:{config_hash}".encode()).hexdigest()


def build_app() -> Any:
    if not _HAS_FASTAPI:
        raise RuntimeError("Install fastapi (and uvicorn to serve): pip install fastapi uvicorn")

    class JobCreate(BaseModel):
        path: str
        config_hash: str = Field(default="default")

    store = JobStore()
    pool = ThreadPoolExecutor(max_workers=2)
    application = FastAPI(title="CPU-bound jobs example", version="0.1.0")

    def _finish(job_id: str, future) -> None:
        job = store.get(job_id)
        if job is None:
            return
        try:
            job.result = future.result()
            job.status = "succeeded"
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            job.status = "failed"

    @application.post("/jobs")
    def create_job(body: JobCreate) -> JSONResponse:
        path = body.path
        if not Path(path).is_file():
            raise HTTPException(status_code=400, detail=f"not a file: {path}")

        key = make_idempotency_key(path, body.config_hash)
        existing_id = store.by_key.get(key)
        if existing_id:
            job = store.by_id[existing_id]
            return JSONResponse(
                status_code=200,
                content={
                    "job_id": job.id,
                    "status": job.status,
                    "status_url": f"/jobs/{job.id}",
                    "idempotent_replay": True,
                },
            )

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            status="queued",
            idempotency_key=key,
            path=path,
            config_hash=body.config_hash,
        )
        store.by_id[job_id] = job
        store.by_key[key] = job_id
        job.status = "running"
        future = pool.submit(fake_parse, path, body.config_hash)
        future.add_done_callback(lambda f, jid=job_id: _finish(jid, f))

        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": job.status,
                "status_url": f"/jobs/{job_id}",
                "idempotent_replay": False,
            },
        )

    @application.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return {
            "job_id": job.id,
            "status": job.status,
            "idempotency_key": job.idempotency_key,
            "path": job.path,
            "config_hash": job.config_hash,
            "result": job.result,
            "error": job.error,
        }

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Expose for direct tests that import create_job-style helpers
    application.state.store = store
    return application


app = build_app() if _HAS_FASTAPI else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Demo FastAPI job API for CPU-bound whiteboard parse work."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if not _HAS_FASTAPI or app is None:
        print(
            "Install fastapi (and uvicorn to serve): pip install fastapi uvicorn",
            file=__import__("sys").stderr,
        )
        return 2
    try:
        import uvicorn
    except ImportError:
        print("pip install uvicorn fastapi", file=__import__("sys").stderr)
        return 2
    uvicorn.run(app, host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
