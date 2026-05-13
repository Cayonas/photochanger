from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .services.converter import ConversionError, ConversionOptions, convert_image, validate_upload

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
RESULTS_DIR = BASE_DIR / "backend" / "storage" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PhotoChanger API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks: dict[str, dict[str, Any]] = {}


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
        "output_path": str(output_path),
    }
    tasks[task_id] = task_data
    return task_data


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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
