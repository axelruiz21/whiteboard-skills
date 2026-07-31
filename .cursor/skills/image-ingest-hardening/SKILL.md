---
name: image-ingest-hardening
description: Validates and safely loads images for OCR pipelines by sniffing real MIME types, enforcing byte and pixel caps, correcting EXIF orientation, hashing sources, and rejecting decompression bombs or chat-sized previews. Use when hardening image upload paths, rejecting unsafe whiteboard photos before OCR, or adding ingest gates to a Python vision pipeline.
---

# Image Ingest Hardening

Use this skill for the **safe load** stage that every image pipeline needs. Single-image whiteboard extraction belongs to `python-whiteboard-parser`; daily ingest UX belongs to `board-daily-workflow`. This skill owns validation rules and the gate script.

## Rules

1. **Never trust the extension.** Sniff magic bytes (JPEG/PNG/GIF/WebP) before decoding. Reject unknown payloads.
2. **Cap bytes and pixels before full decode.** Default ceilings: 40 MB file, 40 megapixels after orientation. Treat oversize as reject, not a soft warning.
3. **Apply EXIF orientation** (via Pillow when available) before measuring dimensions used for OCR gates.
4. **Record provenance:** SHA-256 of the original bytes, declared MIME, decoded width/height, and the caps used.
5. **Reuse the resolution gate:** long side under 1200px → `unusable`; under 2000px → `warning` (chat/Photos preview). Align exit codes with `check_image_resolution.py`.
6. **Decompression bombs:** set Pillow `Image.MAX_IMAGE_PIXELS` (or equivalent) and catch overflow errors as reject.

## Script

```bash
python3 scripts/validate_image.py PATH.jpg
python3 scripts/validate_image.py PATH.jpg --json --max-bytes 41943040 --max-megapixels 40
```

Exit codes: `0` ok, `1` warning (usable but low-res), `2` reject (missing, wrong type, bomb, oversize, unusable resolution).

Stdout with `--json` is a machine report; human summary goes to stderr without `--json` (or both streams stay clear when `--json` prints only JSON to stdout).

## Integrating into a pipeline

- Call validation **before** OpenCV/OCR work.
- Preserve the original file unchanged; write oriented working copies next to artifacts if needed.
- Pass `source.id` (`sha256:…`) into parser output and job idempotency keys (`fastapi-cpu-bound-jobs`).
- When building the `whiteboard_parser` package, put these checks in `ingest.py`.
