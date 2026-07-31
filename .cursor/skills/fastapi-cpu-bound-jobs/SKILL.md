---
name: fastapi-cpu-bound-jobs
description: Designs FastAPI services that run OpenCV and OCR outside the event loop with process pools, 202 Accepted job status, content-hash idempotency, external artifact storage, and bounded temp file lifecycles. Use when exposing whiteboard parsing as an API, wrapping CPU-bound Python vision work in FastAPI, or adding async job queues for OCR pipelines.
---

# FastAPI CPU-Bound Jobs

Use this skill when **serving** extraction, not when implementing OpenCV stages (`python-whiteboard-parser`) or validating uploads (`image-ingest-hardening`).

## Patterns

1. **Never run OpenCV/OCR on the event loop.** Use `ProcessPoolExecutor`, a worker process, or RQ/Celery.
2. **Accept with `202`** and return `{job_id, status_url}`. Poll `GET /jobs/{id}` for `queued|running|succeeded|failed`.
3. **Idempotency:** key on `sha256(file_bytes) + config_hash`. Duplicate uploads return the existing job.
4. **Artifacts outside the API process** (disk/S3/sqlite). API memory holds only job metadata.
5. **Bound** upload size, decode megapixels, OCR wall time, and pool size.
6. **Temp files in `try/finally`.** Delete working copies; keep originals only if the product requires it.
7. **Structured logs:** job id, source id, stage durations, engine version. Do **not** log full extracted text by default.
8. Validate images with `image-ingest-hardening` before enqueue.

## Example app

```bash
pip install fastapi uvicorn
uvicorn example_job_api:app --app-dir scripts --port 8080
# POST /jobs  with JSON {"path": "/abs/path/to.jpg"} or multipart file
# GET  /jobs/{job_id}
```

`scripts/example_job_api.py` uses an in-memory store, a `ThreadPoolExecutor`, and a fake CPU-bound worker so it runs without Tesseract. For real OpenCV/OCR, swap `fake_parse` for the parser pipeline and replace the thread pool with `ProcessPoolExecutor` or an external worker so vision work never shares the API process GIL.

## Production checklist

- [ ] Process pool or external worker for vision
- [ ] 202 + status endpoint
- [ ] Content-hash idempotency
- [ ] Pixel/byte caps before decode
- [ ] Artifact directory with retention policy
- [ ] Temp cleanup in `finally`
- [ ] No full OCR text in default logs
- [ ] Pipeline version stamped on results
