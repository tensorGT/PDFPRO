import io
import zipfile
import fitz
from fastapi import HTTPException


def open_pdf_bytes(data: bytes, password: str | None = None) -> fitz.Document:
    """Open raw PDF bytes with PyMuPDF and unlock if needed."""
    if not data:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read that PDF: {exc}") from exc

    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise HTTPException(status_code=401, detail="This PDF needs a valid password.")
    return doc


def doc_to_bytes(doc: fitz.Document, deflate: bool = True, garbage: int = 3) -> bytes:
    """Serialize a PyMuPDF document back to bytes."""
    buf = io.BytesIO()
    doc.save(buf, deflate=deflate, garbage=garbage, clean=True)
    return buf.getvalue()


def parse_page_spec(spec: str | None, total_pages: int) -> list[int]:
    """Turn a 1-based page string like '1-3, 5, 7-9' into sorted 0-based indices."""
    if not spec or not spec.strip() or spec.strip().lower() == "all":
        return list(range(total_pages))

    indices: list[int] = []
    seen: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            pieces = token.split("-", 1)
            try:
                start = max(1, int(pieces[0].strip()))
                end = min(total_pages, int(pieces[1].strip()))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid page range: {token}") from exc
            if start > end:
                start, end = end, start
            for p in range(start - 1, end):
                if p not in seen:
                    seen.add(p)
                    indices.append(p)
        else:
            try:
                page_num = int(token)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid page number: {token}") from exc
            if 1 <= page_num <= total_pages and (page_num - 1) not in seen:
                seen.add(page_num - 1)
                indices.append(page_num - 1)

    if not indices:
        raise HTTPException(status_code=400, detail="No valid pages matched that range.")
    return indices


def hex_to_rgb01(hex_color: str | None, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    """Convert '#rrggbb' to a (r, g, b) tuple in 0..1."""
    if not hex_color:
        return default
    cleaned = hex_color.strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(c * 2 for c in cleaned)
    if len(cleaned) != 6:
        return default
    try:
        r = int(cleaned[0:2], 16) / 255.0
        g = int(cleaned[2:4], 16) / 255.0
        b = int(cleaned[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return default


def make_zip(items: list[tuple[str, bytes]]) -> bytes:
    """Bundle (filename, bytes) pairs into an in-memory ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in items:
            zf.writestr(name, content)
    return buf.getvalue()
