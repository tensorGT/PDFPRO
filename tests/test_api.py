import io
import json
import zipfile
import fitz
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_sample_pdf(texts=("Hello world page one", "Second page secret data")) -> bytes:
    doc = fitz.open()
    for t in texts:
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(72, 100), t, fontsize=14)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_sample_png() -> bytes:
    img = Image.new("RGB", (120, 80), color=(40, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_health_and_index():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    home = client.get("/")
    assert home.status_code == 200
    assert "<title>" not in home.text.lower()


def test_merge_and_split():
    pdf_a = _make_sample_pdf(("Doc A",))
    pdf_b = _make_sample_pdf(("Doc B",))
    r = client.post(
        "/api/ops/merge",
        files=[("files", ("a.pdf", pdf_a, "application/pdf")), ("files", ("b.pdf", pdf_b, "application/pdf"))],
    )
    assert r.status_code == 200
    merged = fitz.open(stream=r.content, filetype="pdf")
    assert len(merged) == 2
    merged.close()

    sr = client.post(
        "/api/ops/split",
        files={"file": ("merged.pdf", r.content, "application/pdf")},
        data={"mode": "each_page"},
    )
    assert sr.status_code == 200
    with zipfile.ZipFile(io.BytesIO(sr.content)) as zf:
        assert len(zf.namelist()) == 2


def test_organize_crop_resize_numbers():
    pdf = _make_sample_pdf(("Page 1", "Page 2"))
    ops = json.dumps([{"page": 1, "rotate": 90}, {"page": 0, "rotate": 0}])
    r = client.post("/api/ops/organize", files={"file": ("a.pdf", pdf, "application/pdf")}, data={"operations": ops})
    assert r.status_code == 200
    doc = fitz.open(stream=r.content, filetype="pdf")
    assert doc[0].rotation == 90
    doc.close()

    cr = client.post(
        "/api/ops/crop",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"pages": "1", "box": json.dumps({"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9})},
    )
    assert cr.status_code == 200

    rr = client.post(
        "/api/ops/resize",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"preset": "letter", "pages": "all"},
    )
    assert rr.status_code == 200

    nr = client.post(
        "/api/ops/page-numbers",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"position": "bottom-center", "fmt": "Page {n}/{total}", "header": "Test Header"},
    )
    assert nr.status_code == 200


def test_annotations_watermark_and_redact():
    pdf = _make_sample_pdf(("Top secret token_123",))
    annots = [
        {"page": 0, "type": "highlight", "x0": 0.1, "y0": 0.1, "x1": 0.4, "y1": 0.2, "color": "#facc15"},
        {"page": 0, "type": "text", "x": 0.2, "y": 0.3, "text": "Nice note", "color": "#2563eb"},
        {"page": 0, "type": "stamp", "x0": 0.5, "y0": 0.5, "x1": 0.8, "y1": 0.6, "text": "APPROVED", "color": "#dc2626"},
    ]
    ar = client.post(
        "/api/edit/annotations",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"annotations": json.dumps(annots)},
    )
    assert ar.status_code == 200

    wr = client.post(
        "/api/edit/watermark",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"text": "DRAFT", "tiled": "true"},
    )
    assert wr.status_code == 200

    rr = client.post(
        "/api/edit/redact",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"keywords": "token_123"},
    )
    assert rr.status_code == 200
    redacted_doc = fitz.open(stream=rr.content, filetype="pdf")
    assert "token_123" not in redacted_doc[0].get_text()
    redacted_doc.close()


def test_word_style_text_editing():
    pdf = _make_sample_pdf(("Original paragraph text here",))
    r = client.post(
        "/api/edit/text-blocks",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"page": "0"},
    )
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert len(blocks) >= 1
    b = blocks[0]

    edit_payload = [{
        "page": 0,
        "x0": b["x0"],
        "y0": b["y0"],
        "x1": max(b["x1"], 0.7),
        "y1": max(b["y1"], 0.25),
        "text": "Updated paragraph with automatic reflow inside the block",
        "font_size": 14,
        "color": "#111827",
        "bold": True,
        "italic": False,
        "bg_color": "#ffffff",
    }]
    ar = client.post(
        "/api/edit/text-blocks/apply",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"edits": json.dumps(edit_payload)},
    )
    assert ar.status_code == 200
    edited = fitz.open(stream=ar.content, filetype="pdf")
    txt = edited[0].get_text()
    assert "Original paragraph" not in txt
    assert "Updated paragraph" in txt
    edited.close()


def test_conversions():
    pdf = _make_sample_pdf(("Heading\nSome body text",))
    ir = client.post(
        "/api/convert/to-images",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"fmt": "png", "dpi": "100", "pages": "1"},
    )
    assert ir.status_code == 200

    png = _make_sample_png()
    fr = client.post(
        "/api/convert/from-images",
        files=[("files", ("img.png", png, "image/png"))],
    )
    assert fr.status_code == 200

    tr = client.post(
        "/api/convert/to-text",
        files={"file": ("a.pdf", pdf, "application/pdf")},
        data={"mode": "markdown", "pages": "1"},
    )
    assert tr.status_code == 200
    assert "Heading" in tr.json()["text"]

    mr = client.post(
        "/api/convert/from-markup",
        data={"content": "# Hi there\n\nThis is **markdown**.", "is_markdown": "true"},
    )
    assert mr.status_code == 200


def test_security_metadata_compare_and_pipeline():
    pdf_a = _make_sample_pdf(("Alpha line",))
    pdf_b = _make_sample_pdf(("Beta line",))

    cr = client.post(
        "/api/security/compress",
        files={"file": ("a.pdf", pdf_a, "application/pdf")},
        data={"level": "medium"},
    )
    assert cr.status_code == 200
    assert "X-Saved-Percent" in cr.headers

    er = client.post(
        "/api/security/encrypt",
        files={"file": ("a.pdf", pdf_a, "application/pdf")},
        data={"user_pw": "pass123"},
    )
    assert er.status_code == 200

    dr = client.post(
        "/api/security/decrypt",
        files={"file": ("enc.pdf", er.content, "application/pdf")},
        data={"password": "pass123"},
    )
    assert dr.status_code == 200

    mr = client.post(
        "/api/security/metadata/update",
        files={"file": ("a.pdf", pdf_a, "application/pdf")},
        data={"meta": json.dumps({"title": "My Doc", "author": "Tester"})},
    )
    assert mr.status_code == 200
    gr = client.post("/api/security/metadata/get", files={"file": ("m.pdf", mr.content, "application/pdf")})
    assert gr.json()["title"] == "My Doc"

    cmp_res = client.post(
        "/api/security/compare",
        files=[("file_a", ("a.pdf", pdf_a, "application/pdf")), ("file_b", ("b.pdf", pdf_b, "application/pdf"))],
    )
    assert cmp_res.status_code == 200
    assert cmp_res.json()["results"][0]["text_changed"] is True

    pr = client.post(
        "/api/pipeline/run",
        files=[("files", ("a.pdf", pdf_a, "application/pdf")), ("files", ("b.pdf", pdf_b, "application/pdf"))],
        data={"steps": json.dumps([{"action": "watermark"}, {"action": "compress"}]), "merge_first": "true"},
    )
    assert pr.status_code == 200
    assert pr.headers["content-type"] == "application/pdf"
