# pro pdf thing

so yeah, this is a full pdf toolkit built with python (fastapi + pymupdf + pdfplumber) on the backend and plain vanilla js + pdf.js + html/css on the frontend. no react, no heavy build step, just open it up and mess with pdfs.

## what it can do

- **view and read**: smooth pdf.js viewer, page jump, zoom, fit to width, text search across pages, plus normal, dark, sepia, and high contrast reading modes
- **mess with pages**: drag and drop thumbnails to reorder, rotate, or drop pages, merge a bunch of pdfs together, split by ranges / every n pages / single pages / bookmarks, crop visually, resize to a4/letter/custom, and stamp page numbers or headers and footers
- **draw and edit**: highlight, underline, strike, freehand draw, shapes, arrows, text boxes, sticky notes, stamps, and a signature pad you can draw on and drop onto any page
- **convert stuff**: pdf to png/jpg/webp zip, images to pdf, pull out plain text or markdown, extract tables to csv or json, turn html or markdown into a pdf, grab embedded images and attachments, and run ocr if tesseract is installed on your machine
- **lock it down**: compress files, encrypt with passwords and permissions, unlock encrypted pdfs, permanently redact boxes or keywords, edit or strip all metadata, fill and flatten forms, and compare two pdfs with text + visual diffs
- **batch pipeline**: stack a few actions (watermark, numbers, resize, strip metadata, compress) and run them on one or many pdfs at once

## how to run it

1. install the python stuff:
```bash
pip install -r requirements.txt
```

2. start the server:
```bash
uvicorn app.main:app --reload
```

3. open `http://127.0.0.1:8000` in your browser and drop a pdf in.

## running tests

```bash
pytest
```
