import base64
import math
import fitz
from fastapi import HTTPException
from .utils import open_pdf_bytes, doc_to_bytes, parse_page_spec, hex_to_rgb01


def _norm_rect(rect: fitz.Rect, box: dict) -> fitz.Rect:
    return fitz.Rect(
        rect.x0 + float(box.get("x0", 0)) * rect.width,
        rect.y0 + float(box.get("y0", 0)) * rect.height,
        rect.x0 + float(box.get("x1", 0)) * rect.width,
        rect.y0 + float(box.get("y1", 0)) * rect.height,
    )


def apply_annotations(data: bytes, annotations: list[dict]) -> bytes:
    """Burn interactive frontend annotations permanently into the PDF."""
    doc = open_pdf_bytes(data)
    try:
        total = len(doc)
        for ann in annotations:
            p_idx = int(ann.get("page", 0))
            if not (0 <= p_idx < total):
                continue
            page = doc[p_idx]
            rect = page.rect
            kind = ann.get("type", "")
            color = hex_to_rgb01(ann.get("color"), (1.0, 0.85, 0.0))
            opacity = float(ann.get("opacity", 1.0))
            stroke_width = float(ann.get("strokeWidth", 2.0))

            if kind in ("highlight", "underline", "strikethrough"):
                r = _norm_rect(rect, ann)
                if kind == "highlight":
                    annot = page.add_highlight_annot(r)
                    annot.set_colors(stroke=color)
                    annot.set_opacity(min(0.45, opacity))
                    annot.update()
                elif kind == "underline":
                    annot = page.add_underline_annot(r)
                    annot.set_colors(stroke=color)
                    annot.update()
                else:
                    annot = page.add_strikeout_annot(r)
                    annot.set_colors(stroke=color)
                    annot.update()

            elif kind == "draw":
                pts = ann.get("points", [])
                if len(pts) >= 2:
                    ink_pts = [
                        fitz.Point(rect.x0 + p["x"] * rect.width, rect.y0 + p["y"] * rect.height)
                        for p in pts
                    ]
                    shape = page.new_shape()
                    shape.draw_polyline(ink_pts)
                    shape.finish(color=color, width=stroke_width, stroke_opacity=opacity)
                    shape.commit()

            elif kind == "rect":
                r = _norm_rect(rect, ann)
                shape = page.new_shape()
                shape.draw_rect(r)
                shape.finish(color=color, width=stroke_width, stroke_opacity=opacity)
                shape.commit()

            elif kind == "circle":
                r = _norm_rect(rect, ann)
                shape = page.new_shape()
                shape.draw_oval(r)
                shape.finish(color=color, width=stroke_width, stroke_opacity=opacity)
                shape.commit()

            elif kind in ("line", "arrow"):
                p1 = fitz.Point(rect.x0 + float(ann["x0"]) * rect.width, rect.y0 + float(ann["y0"]) * rect.height)
                p2 = fitz.Point(rect.x0 + float(ann["x1"]) * rect.width, rect.y0 + float(ann["y1"]) * rect.height)
                shape = page.new_shape()
                shape.draw_line(p1, p2)
                if kind == "arrow":
                    angle = math.atan2(p2.y - p1.y, p2.x - p1.x)
                    head_len = 10
                    a1 = fitz.Point(p2.x - head_len * math.cos(angle - 0.45), p2.y - head_len * math.sin(angle - 0.45))
                    a2 = fitz.Point(p2.x - head_len * math.cos(angle + 0.45), p2.y - head_len * math.sin(angle + 0.45))
                    shape.draw_line(p2, a1)
                    shape.draw_line(p2, a2)
                shape.finish(color=color, width=stroke_width, stroke_opacity=opacity)
                shape.commit()

            elif kind == "text":
                x = rect.x0 + float(ann.get("x", 0.1)) * rect.width
                y = rect.y0 + float(ann.get("y", 0.1)) * rect.height
                text = str(ann.get("text", "")).strip()
                fs = float(ann.get("fontSize", 14))
                if text:
                    page.insert_text(fitz.Point(x, y + fs), text, fontsize=fs, fontname="helv", color=color)

            elif kind == "note":
                x = rect.x0 + float(ann.get("x", 0.1)) * rect.width
                y = rect.y0 + float(ann.get("y", 0.1)) * rect.height
                text = str(ann.get("text", "Note")).strip()
                annot = page.add_text_annot(fitz.Point(x, y), text, icon="Note")
                annot.set_colors(stroke=color)
                annot.update()

            elif kind == "stamp":
                r = _norm_rect(rect, ann)
                label = str(ann.get("text", "APPROVED")).upper()
                shape = page.new_shape()
                shape.draw_rect(r)
                shape.finish(color=color, width=2.0)
                shape.commit()
                fs = max(10, min(28, r.height * 0.55))
                tw = fitz.get_text_length(label, fontname="hebo", fontsize=fs)
                tx = r.x0 + max(4, (r.width - tw) / 2.0)
                ty = r.y0 + (r.height + fs * 0.7) / 2.0
                page.insert_text(fitz.Point(tx, ty), label, fontsize=fs, fontname="hebo", color=color)

            elif kind == "signature":
                data_url = str(ann.get("imageData", ""))
                if "," in data_url:
                    data_url = data_url.split(",", 1)[1]
                if data_url:
                    img_bytes = base64.b64decode(data_url)
                    r = _norm_rect(rect, ann)
                    page.insert_image(r, stream=img_bytes, keep_proportion=True)

        return doc_to_bytes(doc)
    finally:
        doc.close()


def add_watermark(
    data: bytes,
    text: str = "CONFIDENTIAL",
    image_bytes: bytes | None = None,
    opacity: float = 0.25,
    angle: float = 45.0,
    font_size: int = 44,
    color: str = "#cc2222",
    tiled: bool = False,
    pages: str = "all",
) -> bytes:
    """Overlay a text or image watermark onto selected pages."""
    doc = open_pdf_bytes(data)
    try:
        indices = parse_page_spec(pages, len(doc))
        rgb = hex_to_rgb01(color, (0.8, 0.1, 0.1))

        for idx in indices:
            page = doc[idx]
            rect = page.rect
            if image_bytes:
                w = rect.width * 0.4
                h = rect.height * 0.4
                img_rect = fitz.Rect((rect.width - w) / 2, (rect.height - h) / 2, (rect.width + w) / 2, (rect.height + h) / 2)
                page.insert_image(img_rect, stream=image_bytes, keep_proportion=True, overlay=True)
            elif text.strip():
                if tiled:
                    step_x = max(140, int(rect.width / 3))
                    step_y = max(140, int(rect.height / 4))
                    for gx in range(40, int(rect.width), step_x):
                        for gy in range(60, int(rect.height), step_y):
                            box = fitz.Rect(gx - 80, gy - 40, gx + 140, gy + 40)
                            page.insert_textbox(
                                box,
                                text,
                                fontsize=max(14, font_size // 2),
                                fontname="hebo",
                                color=rgb,
                                align=fitz.TEXT_ALIGN_CENTER,
                                rotate=int(angle) % 360 if int(angle) in (0, 90, 180, 270) else 0,
                                fill_opacity=opacity,
                            )
                else:
                    # Center watermark with rotation via morph
                    tw = fitz.get_text_length(text, fontname="hebo", fontsize=font_size)
                    center = fitz.Point(rect.width / 2.0, rect.height / 2.0)
                    start = fitz.Point(center.x - tw / 2.0, center.y + font_size / 3.0)
                    writer = fitz.TextWriter(rect, opacity=opacity, color=rgb)
                    writer.append(start, text, font=fitz.Font("hebo"), fontsize=font_size)
                    writer.write_text(page, morph=(center, fitz.Matrix(angle)))
        return doc_to_bytes(doc)
    finally:
        doc.close()


def get_form_fields(data: bytes) -> list[dict]:
    """Return all interactive AcroForm fields in the PDF."""
    doc = open_pdf_bytes(data)
    fields: list[dict] = []
    try:
        for p_idx, page in enumerate(doc):
            for widget in page.widgets() or []:
                fields.append({
                    "page": p_idx,
                    "name": widget.field_name or f"field_{p_idx}_{len(fields)}",
                    "label": widget.field_label or widget.field_name or "",
                    "type": widget.field_type_string,
                    "value": widget.field_value,
                    "choices": widget.choice_values or [],
                })
        return fields
    finally:
        doc.close()


def fill_form_fields(data: bytes, values: dict, flatten: bool = False) -> bytes:
    """Fill AcroForm fields and optionally flatten them into static content."""
    doc = open_pdf_bytes(data)
    try:
        for page in doc:
            for widget in page.widgets() or []:
                fname = widget.field_name
                if fname in values:
                    val = values[fname]
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                        widget.field_value = bool(val)
                    else:
                        widget.field_value = str(val)
                    widget.update()
            if flatten:
                # Bake widgets into page appearance
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        if flatten:
            # Recreate clean pages via show_pdf_page to flatten all widgets reliably
            flat = fitz.open()
            for i in range(len(doc)):
                p = doc[i]
                np = flat.new_page(width=p.rect.width, height=p.rect.height)
                np.show_pdf_page(np.rect, doc, i)
            result = doc_to_bytes(flat)
            flat.close()
            return result
        return doc_to_bytes(doc)
    finally:
        doc.close()


def redact_pdf(data: bytes, boxes: list[dict], keywords: list[str], fill_color: str = "#000000") -> bytes:
    """Permanently redact regions and/or keyword matches from the PDF."""
    if not boxes and not keywords:
        raise HTTPException(status_code=400, detail="Draw at least one redaction box or enter a keyword.")
    doc = open_pdf_bytes(data)
    try:
        rgb = hex_to_rgb01(fill_color, (0.0, 0.0, 0.0))
        total = len(doc)

        for box in boxes:
            p_idx = int(box.get("page", 0))
            if 0 <= p_idx < total:
                page = doc[p_idx]
                r = _norm_rect(page.rect, box)
                page.add_redact_annot(r, fill=rgb)

        for kw in keywords:
            term = kw.strip()
            if not term:
                continue
            for page in doc:
                for hit in page.search_for(term):
                    page.add_redact_annot(hit, fill=rgb)

        for page in doc:
            page.apply_redactions()

        return doc_to_bytes(doc)
    finally:
        doc.close()
