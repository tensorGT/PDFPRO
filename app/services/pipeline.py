from fastapi import HTTPException
from .pdf_ops import merge_pdfs, stamp_page_numbers, resize_pages
from .pdf_edit import add_watermark
from .pdf_security import compress_pdf, encrypt_pdf, update_metadata
from .utils import make_zip


def _apply_steps_to_single(data: bytes, steps: list[dict]) -> bytes:
    current = data
    for step in steps:
        action = step.get("action", "")
        params = step.get("params", {})
        if action == "watermark":
            current = add_watermark(
                current,
                text=params.get("text", "CONFIDENTIAL"),
                opacity=float(params.get("opacity", 0.25)),
                angle=float(params.get("angle", 45)),
                color=params.get("color", "#cc2222"),
                tiled=bool(params.get("tiled", False)),
            )
        elif action == "page_numbers":
            current = stamp_page_numbers(
                current,
                position=params.get("position", "bottom-center"),
                fmt=params.get("fmt", "Page {n} of {total}"),
            )
        elif action == "resize":
            current = resize_pages(current, preset=params.get("preset", "a4"))
        elif action == "sanitize":
            current = update_metadata(current, {}, sanitize=True)
        elif action == "compress":
            current, _ = compress_pdf(current, level=params.get("level", "medium"))
        elif action == "encrypt":
            current = encrypt_pdf(
                current,
                user_pw=params.get("user_pw", ""),
                owner_pw=params.get("owner_pw", ""),
            )
    return current


def run_pipeline(files: list[tuple[str, bytes]], steps: list[dict], merge_first: bool = False) -> tuple[bytes, str, str]:
    """Run a custom multi-step pipeline across one or many PDFs (batch mode)."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF for the pipeline.")
    if not steps:
        raise HTTPException(status_code=400, detail="Add at least one step to the pipeline.")

    if merge_first and len(files) >= 2:
        merged = merge_pdfs([raw for _, raw in files])
        result = _apply_steps_to_single(merged, steps)
        return result, "application/pdf", "pipeline_merged.pdf"

    if len(files) == 1:
        name, raw = files[0]
        result = _apply_steps_to_single(raw, steps)
        out_name = name.rsplit(".", 1)[0] + "_processed.pdf"
        return result, "application/pdf", out_name

    # Batch mode: process each file independently and return a ZIP
    outputs: list[tuple[str, bytes]] = []
    for name, raw in files:
        processed = _apply_steps_to_single(raw, steps)
        out_name = name.rsplit(".", 1)[0] + "_processed.pdf"
        outputs.append((out_name, processed))
    return make_zip(outputs), "application/zip", "batch_processed.zip"
