from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .services.converter import ConversionError, ConversionOptions, convert_image, validate_upload

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"
RESULTS_DIR = BASE_DIR / "backend" / "storage" / "results"
BATCHES_DIR = BASE_DIR / "backend" / "storage" / "batches"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
BATCHES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PhotoChanger API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks: dict[str, dict[str, Any]] = {}
batches: dict[str, dict[str, Any]] = {}


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
        }
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    extension = "jpg" if result.output_format == "jpeg" else result.output_format
    output_path = RESULTS_DIR / f"{task_id}.{extension}"
    output_path.write_bytes(result.output_bytes)

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
        "output_path": str(output_path),
    }
    tasks[task_id] = task_data
    return task_data


@app.post("/api/v1/batches")
def create_batch_archive(payload: dict[str, list[str]]) -> dict[str, Any]:
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
            source_path = Path(task["output_path"])
            if not source_path.exists():
                continue
            suffix = source_path.suffix
            stem = Path(task.get("filename") or f"file-{index}").stem
            archive.writestr(f"{index:02d}-{stem}{suffix}", source_path.read_bytes())

    batch_record = {
        "batch_id": batch_id,
        "status": "completed",
        "task_ids": task_ids,
        "file_count": len(selected_tasks),
        "download_url": f"/api/v1/batches/{batch_id}/result",
        "output_path": str(zip_path),
    }
    batches[batch_id] = batch_record
    return {key: value for key, value in batch_record.items() if key != "output_path"}


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return {key: value for key, value in task.items() if key != "output_path"}


@app.get("/api/v1/tasks/{task_id}/result")
def download_result(task_id: str) -> FileResponse:
    task = tasks.get(task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(status_code=404, detail="结果不存在。")

    output_path = Path(task["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="结果文件已丢失。")

    suffix = output_path.suffix or f".{task['target_format']}"
    stem = Path(task.get("filename") or "converted").stem
    download_name = f"{stem}-converted{suffix}"
    return FileResponse(path=output_path, filename=download_name)

@app.get("/api/v1/batches/{batch_id}")
def get_batch(batch_id: str) -> dict[str, Any]:
    batch = batches.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在。")
    return {key: value for key, value in batch.items() if key != "output_path"}


@app.get("/api/v1/batches/{batch_id}/result")
def download_batch(batch_id: str) -> FileResponse:
    batch = batches.get(batch_id)
    if not batch or batch.get("status") != "completed":
        raise HTTPException(status_code=404, detail="批次结果不存在。")

    output_path = Path(batch["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="批次文件已丢失。")

    return FileResponse(path=output_path, filename=f"photochanger-batch-{batch_id}.zip")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
