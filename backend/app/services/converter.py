from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_FILE_SIZE = 50 * 1024 * 1024
SUPPORTED_FORMATS = {"jpeg", "jpg", "png", "webp", "gif"}
FORMAT_ALIASES = {
    "jpg": "jpeg",
}
PILLOW_FORMATS = {
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "gif": "GIF",
}
CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class ConversionError(Exception):
    pass


@dataclass
class ConversionOptions:
    target_format: str
    quality: int = 82
    width: int | None = None
    height: int | None = None
    keep_exif: bool = False


@dataclass
class ConversionResult:
    output_bytes: bytes
    output_format: str
    original_width: int
    original_height: int
    output_width: int
    output_height: int


def _normalize_format(target_format: str) -> str:
    normalized = FORMAT_ALIASES.get(target_format.lower(), target_format.lower())
    if normalized not in SUPPORTED_FORMATS:
        raise ConversionError(f"暂不支持输出为 {target_format}。当前支持：JPEG、PNG、WebP、GIF。")
    return normalized


def validate_upload(filename: str, content_type: str | None, payload_size: int) -> None:
    suffix = Path(filename).suffix.lower().lstrip(".")
    normalized = FORMAT_ALIASES.get(suffix, suffix)
    if payload_size > MAX_FILE_SIZE:
        raise ConversionError("文件超过 50MB 限制，请压缩后重试。")
    if content_type and content_type not in CONTENT_TYPES:
        raise ConversionError("文件 MIME 类型不受支持，请上传 JPEG、PNG、WebP 或 GIF。")
    if normalized not in SUPPORTED_FORMATS:
        raise ConversionError("文件格式不受支持，请上传 JPEG、PNG、WebP 或 GIF。")


def convert_image(source_bytes: bytes, options: ConversionOptions) -> ConversionResult:
    target_format = _normalize_format(options.target_format)

    try:
        image = Image.open(BytesIO(source_bytes))
        image = ImageOps.exif_transpose(image)
    except UnidentifiedImageError as exc:
        raise ConversionError("无法识别该图片文件，可能已损坏。") from exc

    original_width, original_height = image.size
    output_image = image.copy()

    if target_format in {"jpeg", "webp"} and output_image.mode not in {"RGB", "L"}:
        output_image = output_image.convert("RGB")
    elif target_format == "png" and output_image.mode == "P":
        output_image = output_image.convert("RGBA")

    if options.width or options.height:
        if options.width and options.height:
            width = options.width
            height = options.height
        elif options.width:
            width = options.width
            height = round(original_height * (width / original_width))
        else:
            height = options.height or original_height
            width = round(original_width * (height / original_height))
        output_image = output_image.resize((width, height))

    save_kwargs: dict[str, Any] = {}
    if target_format in {"jpeg", "webp"}:
        save_kwargs["quality"] = max(1, min(options.quality, 100))
    if target_format == "jpeg":
        save_kwargs["optimize"] = True
    if options.keep_exif and "exif" in image.info:
        save_kwargs["exif"] = image.info["exif"]

    output_buffer = BytesIO()
    pillow_format = PILLOW_FORMATS[target_format]
    output_image.save(output_buffer, format=pillow_format, **save_kwargs)

    output_width, output_height = output_image.size
    return ConversionResult(
        output_bytes=output_buffer.getvalue(),
        output_format=target_format,
        original_width=original_width,
        original_height=original_height,
        output_width=output_width,
        output_height=output_height,
    )
