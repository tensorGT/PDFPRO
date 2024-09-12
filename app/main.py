import json
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .services import pdf_ops, pdf_edit, pdf_convert, pdf_security, pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="PROPDF")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _zip_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ops/merge")
async def api_merge(files: List[UploadFile] = File(...)):
    raws = [await f.read() for f in files]
    return _pdf_response(pdf_ops.merge_pdfs(raws), "merged.pdf")


@app.post("/api/ops/split")
async def api_split(
    file: UploadFile = File(...),
    mode: str = Form("ranges"),
    spec: str = Form("1"),
    chunk_size: int = Form(1),
):
    data = await file.read()
    return _zip_response(pdf_ops.split_pdf(data, mode=mode, spec=spec, chunk_size=chunk_size), "split_pdfs.zip")


@app.post("/api/ops/organize")
async def api_organize(file: UploadFile = File(...), operations: str = Form(...)):
    data = await file.read()
    ops = json.loads(operations)
    return _pdf_response(pdf_ops.organize_pages(data, ops), "organized.pdf")


@app.post("/api/ops/crop")
async def api_crop(file: UploadFile = File(...), pages: str = Form("all"), box: str = Form(...)):
    data = await file.read()
    return _pdf_response(pdf_ops.crop_pages(data, pages, json.loads(box)), "cropped.pdf")


@app.post("/api/ops/resize")
async def api_resize(
    file: UploadFile = File(...),
    preset: str = Form("a4"),
    custom_w: float = Form(595.0),
    custom_h: float = Form(842.0),
    pages: str = Form("all"),
):
    data = await file.read()
    return _pdf_response(pdf_ops.resize_pages(data, preset, custom_w, custom_h, pages), "resized.pdf")


@app.post("/api/ops/page-numbers")
async def api_page_numbers(
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    start_num: int = Form(1),
    fmt: str = Form("Page {n} of {total}"),
    font_size: int = Form(11),
    color: str = Form("#333333"),
    header: str = Form(""),
    footer: str = Form(""),
    pages: str = Form("all"),
):
    data = await file.read()
    out = pdf_ops.stamp_page_numbers(data, position, start_num, fmt, font_size, color, header, footer, pages)
    return _pdf_response(out, "numbered.pdf")


@app.post("/api/edit/annotations")
async def api_annotations(file: UploadFile = File(...), annotations: str = Form(...)):
    data = await file.read()
    return _pdf_response(pdf_edit.apply_annotations(data, json.loads(annotations)), "annotated.pdf")


@app.post("/api/edit/watermark")
async def api_watermark(
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
    image: Optional[UploadFile] = File(None),
    opacity: float = Form(0.25),
    angle: float = Form(45.0),
    font_size: int = Form(44),
    color: str = Form("#cc2222"),
    tiled: bool = Form(False),
    pages: str = Form("all"),
):
    data = await file.read()
    img_bytes = await image.read() if image else None
    out = pdf_edit.add_watermark(data, text, img_bytes, opacity, angle, font_size, color, tiled, pages)
    return _pdf_response(out, "watermarked.pdf")


@app.post("/api/edit/forms/inspect")
async def api_forms_inspect(file: UploadFile = File(...)):
    data = await file.read()
    return {"fields": pdf_edit.get_form_fields(data)}


@app.post("/api/edit/forms/fill")
async def api_forms_fill(file: UploadFile = File(...), values: str = Form(...), flatten: bool = Form(False)):
    data = await file.read()
    return _pdf_response(pdf_edit.fill_form_fields(data, json.loads(values), flatten), "filled_form.pdf")


@app.post("/api/edit/redact")
async def api_redact(
    file: UploadFile = File(...),
    boxes: str = Form("[]"),
    keywords: str = Form(""),
    fill_color: str = Form("#000000"),
):
    data = await file.read()
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
    return _pdf_response(pdf_edit.redact_pdf(data, json.loads(boxes), kw_list, fill_color), "redacted.pdf")


@app.post("/api/convert/to-images")
async def api_to_images(
    file: UploadFile = File(...),
    fmt: str = Form("png"),
    dpi: int = Form(150),
    pages: str = Form("all"),
):
    data = await file.read()
    return _zip_response(pdf_convert.pdf_to_images(data, fmt, dpi, pages), "pages_images.zip")


@app.post("/api/convert/from-images")
async def api_from_images(files: List[UploadFile] = File(...)):
    raws = [await f.read() for f in files]
    return _pdf_response(pdf_convert.images_to_pdf(raws), "images.pdf")


@app.post("/api/convert/to-text")
async def api_to_text(file: UploadFile = File(...), mode: str = Form("plain"), pages: str = Form("all")):
    data = await file.read()
    return {"text": pdf_convert.pdf_to_text(data, mode, pages)}


@app.post("/api/convert/to-tables")
async def api_to_tables(file: UploadFile = File(...), fmt: str = Form("csv"), pages: str = Form("all")):
    data = await file.read()
    out, media = pdf_convert.pdf_to_tables(data, fmt, pages)
    ext = "json" if fmt.lower() == "json" else "zip"
    return Response(
        content=out,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="tables.{ext}"'},
    )


@app.post("/api/convert/from-markup")
async def api_from_markup(
    content: str = Form(...),
    is_markdown: bool = Form(False),
    page_size: str = Form("a4"),
):
    return _pdf_response(pdf_convert.html_or_md_to_pdf(content, is_markdown, page_size), "document.pdf")


@app.post("/api/convert/extract-assets")
async def api_extract_assets(file: UploadFile = File(...)):
    data = await file.read()
    return _zip_response(pdf_convert.extract_assets(data), "extracted_assets.zip")


@app.post("/api/convert/ocr")
async def api_ocr(file: UploadFile = File(...), lang: str = Form("eng"), pages: str = Form("all")):
    data = await file.read()
    return JSONResponse(pdf_convert.ocr_pdf(data, lang, pages))


@app.post("/api/security/compress")
async def api_compress(file: UploadFile = File(...), level: str = Form("medium"), image_dpi: int = Form(120)):
    data = await file.read()
    out, stats = pdf_security.compress_pdf(data, level, image_dpi)
    return Response(
        content=out,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="compressed.pdf"',
            "X-Original-Bytes": str(stats["original_bytes"]),
            "X-Compressed-Bytes": str(stats["compressed_bytes"]),
            "X-Saved-Percent": str(stats["saved_percent"]),
        },
    )


@app.post("/api/security/encrypt")
async def api_encrypt(
    file: UploadFile = File(...),
    user_pw: str = Form(""),
    owner_pw: str = Form(""),
    allow_print: bool = Form(True),
    allow_copy: bool = Form(True),
    allow_edit: bool = Form(False),
):
    data = await file.read()
    out = pdf_security.encrypt_pdf(data, user_pw, owner_pw, allow_print, allow_copy, allow_edit)
    return _pdf_response(out, "encrypted.pdf")


@app.post("/api/security/decrypt")
async def api_decrypt(file: UploadFile = File(...), password: str = Form(...)):
    data = await file.read()
    return _pdf_response(pdf_security.decrypt_pdf(data, password), "decrypted.pdf")


@app.post("/api/security/metadata/get")
async def api_metadata_get(file: UploadFile = File(...)):
    data = await file.read()
    return pdf_security.get_metadata(data)


@app.post("/api/security/metadata/update")
async def api_metadata_update(file: UploadFile = File(...), meta: str = Form("{}"), sanitize: bool = Form(False)):
    data = await file.read()
    return _pdf_response(pdf_security.update_metadata(data, json.loads(meta), sanitize), "metadata_updated.pdf")


@app.post("/api/security/compare")
async def api_compare(file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    a = await file_a.read()
    b = await file_b.read()
    return pdf_security.compare_pdfs(a, b)


@app.post("/api/pipeline/run")
async def api_pipeline(
    files: List[UploadFile] = File(...),
    steps: str = Form(...),
    merge_first: bool = Form(False),
):
    pairs = [(f.filename or f"doc_{i}.pdf", await f.read()) for i, f in enumerate(files)]
    out, media, filename = pipeline.run_pipeline(pairs, json.loads(steps), merge_first)
    return Response(
        content=out,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))
