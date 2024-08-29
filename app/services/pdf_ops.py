import fitz
from fastapi import HTTPException
from .utils import open_pdf_bytes, doc_to_bytes, parse_page_spec, hex_to_rgb01, make_zip

PAGE_PRESETS = {
    "a4": (595.0, 842.0),
    "letter": (612.0, 792.0),
    "legal": (612.0, 1008.0),
    "a3": (842.0, 1191.0),
    "a5": (420.0, 595.0),
}


def merge_pdfs(files: list[bytes]) -> bytes:
    """Merge multiple PDF files in order into one PDF."""
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Give me at least 2 PDFs to merge.")
    out = fitz.open()
    try:
        for raw in files:
            src = open_pdf_bytes(raw)
            try:
                out.insert_pdf(src)
            finally:
                src.close()
        return doc_to_bytes(out)
    finally:
        out.close()


def split_pdf(data: bytes, mode: str = "ranges", spec: str = "", chunk_size: int = 1) -> bytes:
    """Split a PDF into multiple PDFs and return them inside a ZIP."""
    src = open_pdf_bytes(data)
    outputs: list[tuple[str, bytes]] = []
    try:
        total = len(src)
        if total == 0:
            raise HTTPException(status_code=400, detail="PDF has no pages.")

        if mode == "each_page":
            for i in range(total):
                part = fitz.open()
                part.insert_pdf(src, from_page=i, to_page=i)
                outputs.append((f"page_{i + 1:03d}.pdf", doc_to_bytes(part)))
                part.close()
        elif mode == "every_n":
            step = max(1, chunk_size)
            for idx, start in enumerate(range(0, total, step), start=1):
                end = min(total - 1, start + step - 1)
                part = fitz.open()
                part.insert_pdf(src, from_page=start, to_page=end)
                outputs.append((f"part_{idx:03d}_p{start + 1}-{end + 1}.pdf", doc_to_bytes(part)))
                part.close()
        elif mode == "bookmarks":
            toc = src.get_toc(simple=True)
            top_bookmarks = [(title, page - 1) for lvl, title, page in toc if lvl == 1 and 1 <= page <= total]
            if not top_bookmarks:
                raise HTTPException(status_code=400, detail="No top-level bookmarks found to split by.")
            for idx, (title, start) in enumerate(top_bookmarks):
                end = (top_bookmarks[idx + 1][1] - 1) if idx + 1 < len(top_bookmarks) else (total - 1)
                if end < start:
                    end = start
                safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip() or f"section_{idx + 1}"
                part = fitz.open()
                part.insert_pdf(src, from_page=start, to_page=end)
                outputs.append((f"{idx + 1:02d}_{safe_title[:40]}.pdf", doc_to_bytes(part)))
                part.close()
        else:
            # ranges mode: each comma-separated group becomes its own PDF, or single extracted PDF
            groups = [g.strip() for g in spec.split(";") if g.strip()] if ";" in spec else [spec]
            for idx, group in enumerate(groups, start=1):
                pages = parse_page_spec(group, total)
                part = fitz.open()
                for p in pages:
                    part.insert_pdf(src, from_page=p, to_page=p)
                outputs.append((f"split_{idx:02d}.pdf", doc_to_bytes(part)))
                part.close()

        return make_zip(outputs)
    finally:
        src.close()


def organize_pages(data: bytes, page_ops: list[dict]) -> bytes:
    """Reorder, rotate, or drop pages based on [{'page': 0, 'rotate': 90}, ...]."""
    if not page_ops:
        raise HTTPException(status_code=400, detail="No pages selected to keep.")
    src = open_pdf_bytes(data)
    out = fitz.open()
    try:
        total = len(src)
        for item in page_ops:
            p_idx = int(item.get("page", 0))
            rot = int(item.get("rotate", 0)) % 360
            if 0 <= p_idx < total:
                out.insert_pdf(src, from_page=p_idx, to_page=p_idx)
                if rot:
                    new_page = out[-1]
                    new_page.set_rotation((new_page.rotation + rot) % 360)
        if len(out) == 0:
            raise HTTPException(status_code=400, detail="Resulting PDF would be empty.")
        return doc_to_bytes(out)
    finally:
        out.close()
        src.close()


def crop_pages(data: bytes, pages: str, box: dict) -> bytes:
    """Crop selected pages using normalized (0..1) coordinates {x0, y0, x1, y1}."""
    doc = open_pdf_bytes(data)
    try:
        indices = parse_page_spec(pages, len(doc))
        nx0 = max(0.0, min(1.0, float(box.get("x0", 0.0))))
        ny0 = max(0.0, min(1.0, float(box.get("y0", 0.0))))
        nx1 = max(0.0, min(1.0, float(box.get("x1", 1.0))))
        ny1 = max(0.0, min(1.0, float(box.get("y1", 1.0))))
        if nx1 <= nx0 or ny1 <= ny0:
            raise HTTPException(status_code=400, detail="Crop box width and height must be positive.")

        for idx in indices:
            page = doc[idx]
            rect = page.rect
            crop_rect = fitz.Rect(
                rect.x0 + nx0 * rect.width,
                rect.y0 + ny0 * rect.height,
                rect.x0 + nx1 * rect.width,
                rect.y0 + ny1 * rect.height,
            )
            page.set_cropbox(crop_rect)
        return doc_to_bytes(doc)
    finally:
        doc.close()


def resize_pages(data: bytes, preset: str = "a4", custom_w: float = 595.0, custom_h: float = 842.0, pages: str = "all") -> bytes:
    """Scale and center pages onto a target page size."""
    w, h = PAGE_PRESETS.get(preset.lower(), (custom_w, custom_h))
    if w <= 20 or h <= 20:
        raise HTTPException(status_code=400, detail="Target page dimensions are too small.")

    src = open_pdf_bytes(data)
    out = fitz.open()
    try:
        target_indices = set(parse_page_spec(pages, len(src)))
        for i in range(len(src)):
            src_page = src[i]
            if i not in target_indices:
                out.insert_pdf(src, from_page=i, to_page=i)
                continue
            new_page = out.new_page(width=w, height=h)
            src_rect = src_page.rect
            scale = min(w / src_rect.width, h / src_rect.height)
            drawn_w = src_rect.width * scale
            drawn_h = src_rect.height * scale
            x_off = (w - drawn_w) / 2.0
            y_off = (h - drawn_h) / 2.0
            dest_rect = fitz.Rect(x_off, y_off, x_off + drawn_w, y_off + drawn_h)
            new_page.show_pdf_page(dest_rect, src, i)
        return doc_to_bytes(out)
    finally:
        out.close()
        src.close()


def stamp_page_numbers(
    data: bytes,
    position: str = "bottom-center",
    start_num: int = 1,
    fmt: str = "Page {n} of {total}",
    font_size: int = 11,
    color: str = "#333333",
    header: str = "",
    footer: str = "",
    pages: str = "all",
) -> bytes:
    """Stamp page numbers, headers, and footers onto pages."""
    doc = open_pdf_bytes(data)
    try:
        total = len(doc)
        indices = parse_page_spec(pages, total)
        rgb = hex_to_rgb01(color, (0.2, 0.2, 0.2))
        margin = 28

        for idx in indices:
            page = doc[idx]
            rect = page.rect
            label = fmt.replace("{n}", str(start_num + idx)).replace("{total}", str(total))

            # Place page number
            if label.strip():
                tw = fitz.get_text_length(label, fontname="helv", fontsize=font_size)
                if "left" in position:
                    x = margin
                elif "right" in position:
                    x = max(margin, rect.width - margin - tw)
                else:
                    x = max(margin, (rect.width - tw) / 2.0)

                y = (margin + font_size) if "top" in position else (rect.height - margin)
                page.insert_text(fitz.Point(x, y), label, fontsize=font_size, fontname="helv", color=rgb)

            if header.strip():
                page.insert_text(fitz.Point(margin, margin + font_size), header.strip(), fontsize=font_size, fontname="helv", color=rgb)

            if footer.strip():
                page.insert_text(fitz.Point(margin, rect.height - margin), footer.strip(), fontsize=font_size, fontname="helv", color=rgb)

        return doc_to_bytes(doc)
    finally:
        doc.close()
