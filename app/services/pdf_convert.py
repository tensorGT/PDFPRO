import csv
import io
import json
import shutil
import fitz
import markdown as md_lib
import pdfplumber
from PIL import Image
from fastapi import HTTPException
from .utils import open_pdf_bytes, doc_to_bytes, parse_page_spec, make_zip


def pdf_to_images(data: bytes, fmt: str = "png", dpi: int = 150, pages: str = "all") -> bytes:
    """Render selected pages to PNG, JPEG, or WebP and bundle into a ZIP."""
    fmt_clean = fmt.lower().strip()
    if fmt_clean == "jpg":
        fmt_clean = "jpeg"
    if fmt_clean not in ("png", "jpeg", "webp"):
        raise HTTPException(status_code=400, detail="Format must be png, jpg, or webp.")

    doc = open_pdf_bytes(data)
    items: list[tuple[str, bytes]] = []
    try:
        indices = parse_page_spec(pages, len(doc))
        zoom = max(72, min(400, dpi)) / 72.0
        mat = fitz.Matrix(zoom, zoom)
        ext = "jpg" if fmt_clean == "jpeg" else fmt_clean

        for idx in indices:
            pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            out = io.BytesIO()
            img.save(out, format=fmt_clean.upper(), quality=90)
            items.append((f"page_{idx + 1:03d}.{ext}", out.getvalue()))
        return make_zip(items)
    finally:
        doc.close()


def images_to_pdf(image_files: list[bytes]) -> bytes:
    """Convert one or more images into a multi-page PDF."""
    if not image_files:
        raise HTTPException(status_code=400, detail="Upload at least one image.")
    out = fitz.open()
    try:
        for raw in image_files:
            try:
                img = Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            w, h = img.size
            page = out.new_page(width=w, height=h)
            page.insert_image(fitz.Rect(0, 0, w, h), stream=buf.getvalue())
        return doc_to_bytes(out)
    finally:
        out.close()


def pdf_to_text(data: bytes, mode: str = "plain", pages: str = "all") -> str:
    """Extract plain text or simple markdown from selected pages."""
    doc = open_pdf_bytes(data)
    try:
        indices = parse_page_spec(pages, len(doc))
        chunks: list[str] = []
        for idx in indices:
            page = doc[idx]
            if mode == "markdown":
                # Build clean markdown using text blocks and font sizes
                blocks = page.get_text("dict").get("blocks", [])
                lines_md: list[str] = [f"<!-- Page {idx + 1} -->"]
                for b in blocks:
                    if b.get("type") != 0:
                        continue
                    for line in b.get("lines", []):
                        spans = line.get("spans", [])
                        txt = "".join(s.get("text", "") for s in spans).strip()
                        if not txt:
                            continue
                        max_sz = max((s.get("size", 11) for s in spans), default=11)
                        if max_sz >= 20:
                            lines_md.append(f"# {txt}")
                        elif max_sz >= 15:
                            lines_md.append(f"## {txt}")
                        else:
                            lines_md.append(txt)
                chunks.append("\n\n".join(lines_md))
            else:
                chunks.append(f"--- Page {idx + 1} ---\n{page.get_text('text').strip()}")
        return "\n\n".join(chunks)
    finally:
        doc.close()


def pdf_to_tables(data: bytes, fmt: str = "csv", pages: str = "all") -> tuple[bytes, str]:
    """Extract tables from a PDF using pdfplumber as CSVs (ZIP) or JSON."""
    doc_check = open_pdf_bytes(data)
    total = len(doc_check)
    doc_check.close()
    indices = set(parse_page_spec(pages, total))

    extracted: list[dict] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for idx, page in enumerate(pdf.pages):
            if idx not in indices:
                continue
            tables = page.extract_tables() or []
            for t_idx, table in enumerate(tables, start=1):
                cleaned = [[cell if cell is not None else "" for cell in row] for row in table]
                extracted.append({"page": idx + 1, "table": t_idx, "rows": cleaned})

    if not extracted:
        raise HTTPException(status_code=404, detail="No tables found on those pages.")

    if fmt.lower() == "json":
        return json.dumps(extracted, indent=2).encode("utf-8"), "application/json"

    zip_items: list[tuple[str, bytes]] = []
    for item in extracted:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerows(item["rows"])
        zip_items.append((f"page_{item['page']}_table_{item['table']}.csv", buf.getvalue().encode("utf-8")))
    return make_zip(zip_items), "application/zip"


def html_or_md_to_pdf(content: str, is_markdown: bool = False, page_size: str = "a4") -> bytes:
    """Render HTML or Markdown text into a styled PDF using PyMuPDF Story."""
    if not content.strip():
        raise HTTPException(status_code=400, detail="Give me some HTML or Markdown content first.")

    body_html = md_lib.markdown(content, extensions=["tables", "fenced_code"]) if is_markdown else content
    full_html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; color: #1e293b; }}
          h1, h2, h3 {{ color: #0f172a; margin-top: 16px; }}
          code, pre {{ background: #f1f5f9; padding: 2px 5px; border-radius: 4px; font-family: monospace; }}
          table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
          th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }}
        </style>
      </head>
      <body>{body_html}</body>
    </html>
    """
    rect = fitz.paper_rect(page_size.lower()) if page_size.lower() in ("a4", "letter", "legal", "a3", "a5") else fitz.paper_rect("a4")
    where = rect + (36, 36, -36, -36)
    story = fitz.Story(html=full_html)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev, None)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def extract_assets(data: bytes) -> bytes:
    """Extract all embedded images and file attachments into a ZIP."""
    doc = open_pdf_bytes(data)
    items: list[tuple[str, bytes]] = []
    seen_xrefs: set[int] = set()
    try:
        for p_idx, page in enumerate(doc):
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                base_img = doc.extract_image(xref)
                ext = base_img.get("ext", "png")
                items.append((f"images/p{p_idx + 1}_xref{xref}.{ext}", base_img["image"]))

        for name in doc.embfile_names():
            items.append((f"attachments/{name}", doc.embfile_get(name)))

        if not items:
            raise HTTPException(status_code=404, detail="No embedded images or attachments found in this PDF.")
        return make_zip(items)
    finally:
        doc.close()


def ocr_pdf(data: bytes, lang: str = "eng", pages: str = "all") -> dict:
    """Run OCR on selected pages using Tesseract and return both searchable PDF (base64) and text."""
    import base64
    import pytesseract

    if not shutil.which("tesseract"):
        raise HTTPException(
            status_code=501,
            detail="Tesseract OCR binary is not installed on this machine. Install Tesseract and add it to PATH to run OCR.",
        )

    doc = open_pdf_bytes(data)
    out_doc = fitz.open()
    extracted_pages: list[str] = []
    try:
        indices = set(parse_page_spec(pages, len(doc)))
        mat = fitz.Matrix(2.0, 2.0)
        for i in range(len(doc)):
            if i not in indices:
                out_doc.insert_pdf(doc, from_page=i, to_page=i)
                continue
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang=lang)
            extracted_pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
            pdf_page_bytes = pytesseract.image_to_pdf_or_hocr(img, lang=lang, extension="pdf")
            ocr_page_doc = fitz.open(stream=pdf_page_bytes, filetype="pdf")
            out_doc.insert_pdf(ocr_page_doc)
            ocr_page_doc.close()

        return {
            "text": "\n\n".join(extracted_pages),
            "pdf_base64": base64.b64encode(doc_to_bytes(out_doc)).decode("ascii"),
        }
    finally:
        out_doc.close()
        doc.close()
