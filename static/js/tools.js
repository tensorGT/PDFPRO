window.ProPdfTools = (() => {
  const pipelineSteps = [];

  function currentPdfBlob() {
    if (!window.ProPdfState.pdfBytes) {
      window.ProPdfApp.toast("Open a PDF first!");
      return null;
    }
    return new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" });
  }

  async function postForBlob(url, formData, downloadName = null) {
    try {
      const res = await fetch(url, { method: "POST", body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Request failed" }));
        window.ProPdfApp.toast(err.detail || "Something went wrong.");
        return null;
      }
      const buf = new Uint8Array(await res.arrayBuffer());
      if (downloadName) {
        triggerDownload(buf, downloadName, res.headers.get("content-type") || "application/octet-stream");
      }
      return { bytes: buf, headers: res.headers };
    } catch (e) {
      window.ProPdfApp.toast("Network error: " + e.message);
      return null;
    }
  }

  // Wrapper returning raw bytes directly for callers that load PDF into viewer
  async function postPdfUpdate(url, formData) {
    const res = await postForBlob(url, formData);
    return res ? res.bytes : null;
  }

  function triggerDownload(uint8, filename, mime = "application/pdf") {
    const blob = new Blob([uint8], { type: mime });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  function renderPipelineList() {
    const ul = document.getElementById("pipe-steps-list");
    ul.innerHTML = "";
    pipelineSteps.forEach((s, idx) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${idx + 1}. ${s.action}</span><button class="small-btn">Remove</button>`;
      li.querySelector("button").addEventListener("click", () => {
        pipelineSteps.splice(idx, 1);
        renderPipelineList();
      });
      ul.appendChild(li);
    });
  }

  function init() {
    // Tabs
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
      });
    });

    // Split mode toggle
    document.getElementById("split-mode").addEventListener("change", (e) => {
      const mode = e.target.value;
      document.getElementById("split-spec").classList.toggle("hidden", mode !== "ranges");
      document.getElementById("split-chunk").classList.toggle("hidden", mode !== "every_n");
    });

    // Resize custom toggle
    document.getElementById("resize-preset").addEventListener("change", (e) => {
      document.getElementById("resize-custom-row").classList.toggle("hidden", e.target.value !== "custom");
    });

    // Merge
    document.getElementById("btn-merge").addEventListener("click", async () => {
      const files = document.getElementById("merge-files").files;
      if (files.length < 2) return window.ProPdfApp.toast("Pick at least 2 PDFs to merge.");
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      const bytes = await postPdfUpdate("/api/ops/merge", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, "merged.pdf");
        window.ProPdfApp.toast("Merged and opened!");
      }
    });

    // Split
    document.getElementById("btn-split").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("mode", document.getElementById("split-mode").value);
      fd.append("spec", document.getElementById("split-spec").value);
      fd.append("chunk_size", document.getElementById("split-chunk").value);
      await postForBlob("/api/ops/split", fd, "split_pdfs.zip");
    });

    // Resize
    document.getElementById("btn-resize").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("preset", document.getElementById("resize-preset").value);
      fd.append("custom_w", document.getElementById("resize-w").value);
      fd.append("custom_h", document.getElementById("resize-h").value);
      fd.append("pages", document.getElementById("resize-pages").value);
      const bytes = await postPdfUpdate("/api/ops/resize", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Pages resized!");
      }
    });

    // Page Numbers & Headers
    document.getElementById("btn-page-numbers").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("position", document.getElementById("num-pos").value);
      fd.append("fmt", document.getElementById("num-fmt").value);
      fd.append("header", document.getElementById("num-header").value);
      fd.append("footer", document.getElementById("num-footer").value);
      const bytes = await postPdfUpdate("/api/ops/page-numbers", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Stamped page numbers!");
      }
    });

    // Watermark
    document.getElementById("btn-watermark").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("text", document.getElementById("wm-text").value);
      fd.append("opacity", document.getElementById("wm-opacity").value);
      fd.append("angle", document.getElementById("wm-angle").value);
      fd.append("color", document.getElementById("wm-color").value);
      fd.append("tiled", String(document.getElementById("wm-tiled").checked));
      const bytes = await postPdfUpdate("/api/edit/watermark", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Watermark added!");
      }
    });

    // PDF to Images
    document.getElementById("btn-to-images").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("fmt", document.getElementById("img-fmt").value);
      fd.append("dpi", document.getElementById("img-dpi").value);
      fd.append("pages", document.getElementById("img-pages").value);
      await postForBlob("/api/convert/to-images", fd, "pages_images.zip");
    });

    // Images to PDF
    document.getElementById("btn-from-images").addEventListener("click", async () => {
      const files = document.getElementById("from-images-files").files;
      if (!files.length) return window.ProPdfApp.toast("Pick some images first.");
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      const bytes = await postPdfUpdate("/api/convert/from-images", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, "images.pdf");
        window.ProPdfApp.toast("Built PDF from your images!");
      }
    });

    // Extract Text / Markdown
    document.getElementById("btn-to-text").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("mode", document.getElementById("text-mode").value);
      fd.append("pages", document.getElementById("text-pages").value);
      const res = await fetch("/api/convert/to-text", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) return window.ProPdfApp.toast(data.detail || "Failed to extract text.");
      window.ProPdfApp.showModal("Extracted text", `<pre>${escapeHtml(data.text || "(no text found)")}</pre>`);
    });

    // Extract Tables
    document.getElementById("btn-to-tables").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fmt = document.getElementById("table-fmt").value;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("fmt", fmt);
      fd.append("pages", document.getElementById("table-pages").value);
      await postForBlob("/api/convert/to-tables", fd, fmt === "json" ? "tables.json" : "tables.zip");
    });

    // HTML / Markdown to PDF
    document.getElementById("btn-from-markup").addEventListener("click", async () => {
      const content = document.getElementById("markup-input").value;
      if (!content.trim()) return window.ProPdfApp.toast("Type some Markdown or HTML first.");
      const fd = new FormData();
      fd.append("content", content);
      fd.append("is_markdown", String(document.getElementById("markup-is-md").checked));
      const bytes = await postPdfUpdate("/api/convert/from-markup", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, "document.pdf");
        window.ProPdfApp.toast("Built PDF from your text!");
      }
    });

    // Extract Assets
    document.getElementById("btn-extract-assets").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      await postForBlob("/api/convert/extract-assets", fd, "extracted_assets.zip");
    });

    // OCR
    document.getElementById("btn-ocr").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("lang", document.getElementById("ocr-lang").value || "eng");
      const res = await fetch("/api/convert/ocr", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) return window.ProPdfApp.toast(data.detail || "OCR failed.");
      window.ProPdfApp.showModal("OCR output", `<pre>${escapeHtml(data.text || "")}</pre>`);
    });

    // Compress
    document.getElementById("btn-compress").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("level", document.getElementById("compress-level").value);
      const res = await postForBlob("/api/security/compress", fd);
      if (res) {
        const saved = res.headers.get("X-Saved-Percent") || "0";
        document.getElementById("compress-stats").textContent = `Saved ${saved}% (${res.bytes.length} bytes)`;
        await window.ProPdfApp.loadPdfBytes(res.bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast(`Compressed! Saved ${saved}%`);
      }
    });

    // Encrypt & Decrypt
    document.getElementById("btn-encrypt").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("user_pw", document.getElementById("enc-user-pw").value);
      fd.append("owner_pw", document.getElementById("enc-owner-pw").value);
      fd.append("allow_print", String(document.getElementById("enc-print").checked));
      fd.append("allow_copy", String(document.getElementById("enc-copy").checked));
      fd.append("allow_edit", String(document.getElementById("enc-edit").checked));
      await postForBlob("/api/security/encrypt", fd, "encrypted.pdf");
    });

    document.getElementById("btn-decrypt").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("password", document.getElementById("dec-pw").value);
      const bytes = await postPdfUpdate("/api/security/decrypt", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, "unlocked.pdf");
        window.ProPdfApp.toast("PDF unlocked!");
      }
    });

    // Keyword Redact
    document.getElementById("btn-redact-kw").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("keywords", document.getElementById("redact-keywords").value);
      const bytes = await postPdfUpdate("/api/edit/redact", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Keywords redacted!");
      }
    });

    // Metadata
    document.getElementById("btn-load-meta").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      const res = await fetch("/api/security/metadata/get", { method: "POST", body: fd });
      const data = await res.json();
      document.getElementById("meta-title").value = data.title || "";
      document.getElementById("meta-author").value = data.author || "";
      document.getElementById("meta-keywords").value = data.keywords || "";
      window.ProPdfApp.toast("Loaded metadata.");
    });

    document.getElementById("btn-save-meta").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("meta", JSON.stringify({
        title: document.getElementById("meta-title").value,
        author: document.getElementById("meta-author").value,
        keywords: document.getElementById("meta-keywords").value,
      }));
      const bytes = await postPdfUpdate("/api/security/metadata/update", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Metadata saved!");
      }
    });

    document.getElementById("btn-sanitize").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("sanitize", "true");
      const bytes = await postPdfUpdate("/api/security/metadata/update", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("All hidden metadata & scripts stripped!");
      }
    });

    // Forms
    document.getElementById("btn-inspect-forms").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      const res = await fetch("/api/edit/forms/inspect", { method: "POST", body: fd });
      const data = await res.json();
      const box = document.getElementById("forms-container");
      box.innerHTML = "";
      if (!data.fields || !data.fields.length) {
        box.innerHTML = `<p class="muted small">No fillable form fields found.</p>`;
        document.getElementById("btn-fill-forms").classList.add("hidden");
        return;
      }
      data.fields.forEach((f) => {
        const row = document.createElement("div");
        row.innerHTML = `<label class="small">${escapeHtml(f.label || f.name)}</label><input data-field="${escapeHtml(f.name)}" type="text" value="${escapeHtml(String(f.value || ""))}" />`;
        box.appendChild(row);
      });
      document.getElementById("btn-fill-forms").classList.remove("hidden");
    });

    document.getElementById("btn-fill-forms").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      if (!blob) return;
      const values = {};
      document.querySelectorAll("#forms-container input[data-field]").forEach((inp) => {
        values[inp.dataset.field] = inp.value;
      });
      const fd = new FormData();
      fd.append("file", blob, "doc.pdf");
      fd.append("values", JSON.stringify(values));
      fd.append("flatten", String(document.getElementById("forms-flatten").checked));
      const bytes = await postPdfUpdate("/api/edit/forms/fill", fd);
      if (bytes) {
        await window.ProPdfApp.loadPdfBytes(bytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Form updated!");
      }
    });

    // Compare
    document.getElementById("btn-compare").addEventListener("click", async () => {
      const blob = currentPdfBlob();
      const fileB = document.getElementById("compare-file-b").files[0];
      if (!blob || !fileB) return window.ProPdfApp.toast("Open a PDF and pick a second PDF to compare.");
      const fd = new FormData();
      fd.append("file_a", blob, "a.pdf");
      fd.append("file_b", fileB);
      const res = await fetch("/api/security/compare", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) return window.ProPdfApp.toast(data.detail || "Compare failed.");
      let html = `<p>Doc A: ${data.pages_a} pages | Doc B: ${data.pages_b} pages</p>`;
      data.results.forEach((r) => {
        html += `<div style="margin-bottom:14px;"><strong>Page ${r.page}</strong> (${r.changed_pixels_percent}% visual diff)`;
        if (r.diff) html += `<pre>${escapeHtml(r.diff)}</pre>`;
        if (r.visual_diff_png) html += `<img src="data:image/png;base64,${r.visual_diff_png}" />`;
        html += `</div>`;
      });
      window.ProPdfApp.showModal("PDF comparison", html);
    });

    // Pipeline
    document.getElementById("btn-pipe-add").addEventListener("click", () => {
      const action = document.getElementById("pipe-add-step").value;
      pipelineSteps.push({ action, params: {} });
      renderPipelineList();
    });

    document.getElementById("btn-pipe-run").addEventListener("click", async () => {
      const files = document.getElementById("pipe-files").files;
      if (!files.length) return window.ProPdfApp.toast("Upload PDFs for the batch pipeline.");
      if (!pipelineSteps.length) return window.ProPdfApp.toast("Add at least one step first.");
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      fd.append("steps", JSON.stringify(pipelineSteps));
      const mergeFirst = document.getElementById("pipe-merge").checked;
      fd.append("merge_first", String(mergeFirst));
      const outName = files.length > 1 && !mergeFirst ? "batch_processed.zip" : "pipeline_output.pdf";
      await postForBlob("/api/pipeline/run", fd, outName);
    });
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  return { init, postForBlob: postPdfUpdate, triggerDownload };
})();
