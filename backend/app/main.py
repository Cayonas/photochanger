from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager, suppress
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .services.converter import ConversionError, ConversionOptions, convert_image, validate_upload

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"
BATCHES_DIR = BASE_DIR / "backend" / "storage" / "batches"
BATCHES_DIR.mkdir(parents=True, exist_ok=True)

TASK_TTL_SECONDS = 30 * 60
BATCH_TTL_SECONDS = 30 * 60
MAX_CONCURRENT_CONVERSIONS = 4
CLEANUP_INTERVAL_SECONDS = 60

tasks: dict[str, dict[str, Any]] = {}
batches: dict[str, dict[str, Any]] = {}
active_conversions = 0
active_conversions_lock = asyncio.Lock()


def _now() -> float:
    return time.time()


def purge_expired_artifacts() -> None:
    now = _now()

    expired_task_ids = [task_id for task_id, task in tasks.items() if task.get("expires_at", now + 1) <= now]
    for task_id in expired_task_ids:
        tasks.pop(task_id, None)

    expired_batch_ids = [batch_id for batch_id, batch in batches.items() if batch.get("expires_at", now + 1) <= now]
    for batch_id in expired_batch_ids:
        batch = batches.pop(batch_id, None)
        if not batch:
            continue

        output_path = Path(batch["output_path"])
        with suppress(FileNotFoundError):
            output_path.unlink()


async def cleanup_loop() -> None:
    while True:
        purge_expired_artifacts()
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


async def try_acquire_conversion_slot() -> bool:
    global active_conversions

    async with active_conversions_lock:
        if active_conversions >= MAX_CONCURRENT_CONVERSIONS:
            return False
        active_conversions += 1
        return True


async def release_conversion_slot() -> None:
    global active_conversions

    async with active_conversions_lock:
        active_conversions = max(0, active_conversions - 1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        purge_expired_artifacts()


app = FastAPI(title="PhotoChanger API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/convert")
async def create_conversion(
    file: UploadFile = File(...),
    target_format: str = Form(...),
    quality: int = Form(82),
    width: int | None = Form(default=None),
    height: int | None = Form(default=None),
    keep_exif: bool = Form(False),
) -> dict[str, Any]:
    if not await try_acquire_conversion_slot():
        raise HTTPException(
            status_code=429,
            detail=f"当前同时仅支持 {MAX_CONCURRENT_CONVERSIONS} 个转换任务，请稍后再试。",
        )

    raw_bytes = await file.read()
    task_id = str(uuid4())

    try:
        validate_upload(file.filename or "upload", file.content_type, len(raw_bytes))
        result = convert_image(
            raw_bytes,
            ConversionOptions(
                target_format=target_format,
                quality=quality,
                width=width,
                height=height,
                keep_exif=keep_exif,
            ),
        )
    except ConversionError as exc:
        tasks[task_id] = {
            "task_id": task_id,
            "status": "failed",
            "error": str(exc),
            "expires_at": _now() + TASK_TTL_SECONDS,
        }
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await release_conversion_slot()

    purge_expired_artifacts()

    task_data = {
        "task_id": task_id,
        "status": "completed",
        "filename": file.filename,
        "target_format": result.output_format,
        "download_url": f"/api/v1/tasks/{task_id}/result",
        "original_size_bytes": len(raw_bytes),
        "output_size_bytes": len(result.output_bytes),
        "original_width": result.original_width,
        "original_height": result.original_height,
        "output_width": result.output_width,
        "output_height": result.output_height,
        "content_type": f"image/{result.output_format}",
        "output_extension": "jpg" if result.output_format == "jpeg" else result.output_format,
        "output_bytes": result.output_bytes,
        "expires_at": _now() + TASK_TTL_SECONDS,
    }
    tasks[task_id] = task_data
    return _public_task(task_data)


@app.post("/api/v1/batches")
def create_batch_archive(payload: dict[str, list[str]]) -> dict[str, Any]:
    purge_expired_artifacts()

    task_ids = payload.get("task_ids", [])
    if not task_ids:
        raise HTTPException(status_code=400, detail="请至少提供一个任务 ID。")

    selected_tasks = []
    for task_id in task_ids:
        task = tasks.get(task_id)
        if not task or task.get("status") != "completed":
            raise HTTPException(status_code=400, detail=f"任务 {task_id} 不存在或尚未完成。")
        selected_tasks.append(task)

    batch_id = str(uuid4())
    zip_path = BATCHES_DIR / f"{batch_id}.zip"

    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for index, task in enumerate(selected_tasks, start=1):
            output_bytes = task.get("output_bytes")
            if not output_bytes:
                continue

            suffix = f".{task['output_extension']}"
            stem = Path(task.get("filename") or f"file-{index}").stem
            archive.writestr(f"{index:02d}-{stem}{suffix}", output_bytes)

    batch_record = {
        "batch_id": batch_id,
        "status": "completed",
        "task_ids": task_ids,
        "file_count": len(selected_tasks),
        "download_url": f"/api/v1/batches/{batch_id}/result",
        "output_path": str(zip_path),
        "expires_at": _now() + BATCH_TTL_SECONDS,
    }
    batches[batch_id] = batch_record
    return _public_batch(batch_record)


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    purge_expired_artifacts()

    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return _public_task(task)


@app.get("/api/v1/tasks/{task_id}/result")
def download_result(task_id: str) -> StreamingResponse:
    purge_expired_artifacts()

    task = tasks.get(task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(status_code=404, detail="结果不存在。")

    output_bytes = task.get("output_bytes")
    if not output_bytes:
        raise HTTPException(status_code=404, detail="结果文件已失效。")

    suffix = f".{task['output_extension']}"
    stem = Path(task.get("filename") or "converted").stem
    download_name = f"{stem}-converted{suffix}"
    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(
        BytesIO(output_bytes),
        media_type=task["content_type"],
        headers=headers,
    )


@app.get("/api/v1/batches/{batch_id}")
def get_batch(batch_id: str) -> dict[str, Any]:
    purge_expired_artifacts()

    batch = batches.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在。")
    return _public_batch(batch)


@app.get("/api/v1/batches/{batch_id}/result")
def download_batch(batch_id: str) -> FileResponse:
    purge_expired_artifacts()

    batch = batches.get(batch_id)
    if not batch or batch.get("status") != "completed":
        raise HTTPException(status_code=404, detail="批次结果不存在。")

    output_path = Path(batch["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="批次文件已失效。")

    return FileResponse(path=output_path, filename=f"photochanger-batch-{batch_id}.zip")


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in task.items()
        if key not in {"output_bytes", "output_extension", "expires_at"}
    }


def _public_batch(batch: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in batch.items() if key not in {"output_path", "expires_at"}}


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
