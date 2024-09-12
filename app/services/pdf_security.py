import base64
import difflib
import io
import fitz
import numpy as np
from PIL import Image
from fastapi import HTTPException
from .utils import open_pdf_bytes, doc_to_bytes


def compress_pdf(data: bytes, level: str = "medium", image_dpi: int = 120) -> tuple[bytes, dict]:
    """Compress PDF by downsampling embedded images and running PyMuPDF garbage collection."""
    doc = open_pdf_bytes(data)
    original_size = len(data)
    try:
        quality_map = {"low": 85, "medium": 65, "high": 40}
        jpeg_q = quality_map.get(level.lower(), 65)
        target_dpi = max(50, min(300, image_dpi))

        if level.lower() in ("medium", "high"):
            seen: set[int] = set()
            for page in doc:
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    try:
                        base_img = doc.extract_image(xref)
                        raw_img = base_img["image"]
                        pil = Image.open(io.BytesIO(raw_img)).convert("RGB")
                        max_dim = int(target_dpi * 11)
                        if max(pil.size) > max_dim:
                            pil.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                        buf = io.BytesIO()
                        pil.save(buf, format="JPEG", quality=jpeg_q, optimize=True)
                        if len(buf.getvalue()) < len(raw_img):
                            doc.update_stream(xref, buf.getvalue())
                    except Exception:
                        continue

        out_bytes = doc_to_bytes(doc, deflate=True, garbage=4)
        new_size = len(out_bytes)
        saved_pct = round(((original_size - new_size) / original_size) * 100, 1) if original_size else 0.0
        return out_bytes, {
            "original_bytes": original_size,
            "compressed_bytes": new_size,
            "saved_percent": saved_pct,
        }
    finally:
        doc.close()


def encrypt_pdf(
    data: bytes,
    user_pw: str = "",
    owner_pw: str = "",
    allow_print: bool = True,
    allow_copy: bool = True,
    allow_edit: bool = False,
) -> bytes:
    """Encrypt a PDF with AES-256 and permission flags."""
    if not user_pw and not owner_pw:
        raise HTTPException(status_code=400, detail="Provide at least a user password or owner password.")
    doc = open_pdf_bytes(data)
    try:
        perm = fitz.PDF_PERM_ACCESSIBILITY
        if allow_print:
            perm |= fitz.PDF_PERM_PRINT
        if allow_copy:
            perm |= fitz.PDF_PERM_COPY
        if allow_edit:
            perm |= fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE

        buf = io.BytesIO()
        doc.save(
            buf,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=user_pw,
            owner_pw=owner_pw or user_pw,
            permissions=perm,
            deflate=True,
        )
        return buf.getvalue()
    finally:
        doc.close()


def decrypt_pdf(data: bytes, password: str) -> bytes:
    """Unlock an encrypted PDF and save an unencrypted copy."""
    doc = open_pdf_bytes(data, password=password)
    try:
        return doc_to_bytes(doc)
    finally:
        doc.close()


def get_metadata(data: bytes) -> dict:
    """Read standard metadata, page count, and security flags."""
    doc = open_pdf_bytes(data)
    try:
        meta = doc.metadata or {}
        return {
            "pages": len(doc),
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
            "creator": meta.get("creator", ""),
            "producer": meta.get("producer", ""),
            "is_encrypted": doc.is_encrypted,
            "has_xmp": bool(doc.get_xml_metadata()),
        }
    finally:
        doc.close()


def update_metadata(data: bytes, meta: dict, sanitize: bool = False) -> bytes:
    """Edit PDF metadata or sanitize all hidden metadata and scripts."""
    doc = open_pdf_bytes(data)
    try:
        if sanitize:
            doc.set_metadata({})
            doc.del_xml_metadata()
            # Scrub any document-level JavaScript names
            try:
                doc.scrub(
                    attached_files=False,
                    clean_pages=True,
                    embedded_files=False,
                    hidden_text=False,
                    javascript=True,
                    metadata=True,
                    redactions=False,
                    reset_fields=False,
                    reset_responses=False,
                    thumbnails=True,
                    xml_metadata=True,
                )
            except Exception:
                pass
        else:
            current = doc.metadata or {}
            for key in ("title", "author", "subject", "keywords", "creator"):
                if key in meta and meta[key] is not None:
                    current[key] = str(meta[key])
            doc.set_metadata(current)
        return doc_to_bytes(doc)
    finally:
        doc.close()


def compare_pdfs(data_a: bytes, data_b: bytes, max_pages: int = 15) -> dict:
    """Compare two PDFs by text diff and pixel-level visual diff."""
    doc_a = open_pdf_bytes(data_a)
    doc_b = open_pdf_bytes(data_b)
    try:
        pages_a = len(doc_a)
        pages_b = len(doc_b)
        total = min(max_pages, max(pages_a, pages_b))
        page_diffs: list[dict] = []

        for i in range(total):
            text_a = doc_a[i].get_text("text").splitlines() if i < pages_a else []
            text_b = doc_b[i].get_text("text").splitlines() if i < pages_b else []
            diff_lines = list(
                difflib.unified_diff(
                    text_a,
                    text_b,
                    fromfile=f"Doc A (p{i + 1})",
                    tofile=f"Doc B (p{i + 1})",
                    lineterm="",
                )
            )

            visual_diff_b64 = None
            changed_pixels_pct = 0.0
            if i < pages_a and i < pages_b:
                pix_a = doc_a[i].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
                pix_b = doc_b[i].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
                img_a = Image.frombytes("RGB", [pix_a.width, pix_a.height], pix_a.samples)
                img_b = Image.frombytes("RGB", [pix_b.width, pix_b.height], pix_b.samples)
                if img_a.size != img_b.size:
                    img_b = img_b.resize(img_a.size)

                arr_a = np.asarray(img_a, dtype=np.int16)
                arr_b = np.asarray(img_b, dtype=np.int16)
                mask = np.any(np.abs(arr_a - arr_b) > 20, axis=2)
                changed_pixels_pct = round(float(np.mean(mask)) * 100.0, 2)

                if changed_pixels_pct > 0.01:
                    vis = np.asarray(img_b, dtype=np.uint8).copy()
                    vis[mask] = [239, 68, 68]
                    out_buf = io.BytesIO()
                    Image.fromarray(vis).save(out_buf, format="PNG")
                    visual_diff_b64 = base64.b64encode(out_buf.getvalue()).decode("ascii")

            page_diffs.append({
                "page": i + 1,
                "text_changed": len(diff_lines) > 0,
                "diff": "\n".join(diff_lines[:120]),
                "changed_pixels_percent": changed_pixels_pct,
                "visual_diff_png": visual_diff_b64,
            })

        return {
            "pages_a": pages_a,
            "pages_b": pages_b,
            "compared_pages": total,
            "results": page_diffs,
        }
    finally:
        doc_a.close()
        doc_b.close()
