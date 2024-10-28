window.ProPdfEditor = (() => {
  let active = false;
  let blocks = [];
  let selectedIdx = null;

  const layer = document.getElementById("text-edit-layer");
  const btnToggle = document.getElementById("btn-word-edit");
  const btnSave = document.getElementById("btn-save-text-edits");
  const formatBar = document.getElementById("word-format-bar");

  async function enterEditMode() {
    if (!window.ProPdfState.pdfBytes) {
      window.ProPdfApp.toast("Open a PDF first!");
      return;
    }
    const pageIdx = window.ProPdfState.currentPage - 1;
    const fd = new FormData();
    fd.append("file", new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" }), "doc.pdf");
    fd.append("page", String(pageIdx));

    const res = await fetch("/api/edit/text-blocks", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      window.ProPdfApp.toast(data.detail || "Could not read text blocks.");
      return;
    }

    active = true;
    blocks = (data.blocks || []).map((b) => ({
      ...b,
      origText: b.text,
      origSize: b.font_size,
      origColor: b.color,
      origBold: b.bold,
      origItalic: b.italic,
      dirty: false,
    }));
    selectedIdx = null;
    btnToggle.classList.add("active");
    btnToggle.textContent = "Exit text edit";
    btnSave.classList.remove("hidden");
    formatBar.classList.remove("hidden");
    renderBlocks();
    window.ProPdfApp.toast(`Found ${blocks.length} editable text block(s). Click any to edit!`);
  }

  function exitEditMode() {
    active = false;
    blocks = [];
    selectedIdx = null;
    layer.innerHTML = "";
    layer.classList.add("hidden");
    btnToggle.classList.remove("active");
    btnToggle.textContent = "Edit text";
    btnSave.classList.add("hidden");
    formatBar.classList.add("hidden");
  }

  function renderBlocks() {
    layer.innerHTML = "";
    if (!active) {
      layer.classList.add("hidden");
      return;
    }
    layer.classList.remove("hidden");
    const scale = window.ProPdfState.scale || 1.0;

    blocks.forEach((b, idx) => {
      const box = document.createElement("div");
      box.className = "editable-pdf-block" + (b.dirty ? " dirty" : "") + (selectedIdx === idx ? " selected" : "");
      box.contentEditable = "true";
      box.style.left = `${b.x0 * 100}%`;
      box.style.top = `${b.y0 * 100}%`;
      box.style.width = `${Math.max(4, (b.x1 - b.x0) * 100)}%`;
      box.style.minHeight = `${Math.max(2, (b.y1 - b.y0) * 100)}%`;
      box.style.fontSize = `${b.font_size * scale}px`;
      box.style.color = b.color;
      box.style.fontWeight = b.bold ? "bold" : "normal";
      box.style.fontStyle = b.italic ? "italic" : "normal";
      box.textContent = b.text;

      box.addEventListener("focus", () => {
        selectedIdx = idx;
        syncFormatControls(b);
        Array.from(layer.children).forEach((el, i) => el.classList.toggle("selected", i === idx));
      });

      box.addEventListener("input", () => {
        b.text = box.innerText;
        b.dirty = true;
        box.classList.add("dirty");
      });

      layer.appendChild(box);
    });
  }

  function syncFormatControls(b) {
    document.getElementById("wf-size").value = b.font_size;
    document.getElementById("wf-color").value = b.color;
    document.getElementById("wf-bold").classList.toggle("active", b.bold);
    document.getElementById("wf-italic").classList.toggle("active", b.italic);
  }

  function updateSelected(updater) {
    if (selectedIdx === null || !blocks[selectedIdx]) return;
    const b = blocks[selectedIdx];
    updater(b);
    b.dirty = true;
    renderBlocks();
    const el = layer.children[selectedIdx];
    if (el) el.focus();
  }

  async function saveEdits() {
    const pageIdx = window.ProPdfState.currentPage - 1;
    const dirty = blocks.filter((b) => b.dirty);
    if (!dirty.length) {
      window.ProPdfApp.toast("No changes to save yet.");
      return;
    }
    const payload = dirty.map((b) => ({
      page: pageIdx,
      x0: b.x0,
      y0: b.y0,
      x1: b.x1,
      y1: b.y1,
      text: b.text,
      font_size: b.font_size,
      color: b.color,
      bold: b.bold,
      italic: b.italic,
      bg_color: "#ffffff",
    }));

    const fd = new FormData();
    fd.append("file", new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" }), "doc.pdf");
    fd.append("edits", JSON.stringify(payload));
    const newBytes = await window.ProPdfTools.postForBlob("/api/edit/text-blocks/apply", fd);
    if (newBytes) {
      exitEditMode();
      await window.ProPdfApp.loadPdfBytes(newBytes, window.ProPdfState.fileName);
      window.ProPdfApp.toast("Text edits saved right into the PDF!");
    }
  }

  function init() {
    btnToggle.addEventListener("click", () => {
      if (active) exitEditMode();
      else enterEditMode();
    });
    btnSave.addEventListener("click", saveEdits);

    document.getElementById("wf-size").addEventListener("change", (e) => {
      const sz = Math.max(6, Math.min(72, Number(e.target.value) || 12));
      updateSelected((b) => { b.font_size = sz; });
    });
    document.getElementById("wf-color").addEventListener("input", (e) => {
      updateSelected((b) => { b.color = e.target.value; });
    });
    document.getElementById("wf-bold").addEventListener("click", () => {
      updateSelected((b) => { b.bold = !b.bold; });
    });
    document.getElementById("wf-italic").addEventListener("click", () => {
      updateSelected((b) => { b.italic = !b.italic; });
    });
    document.getElementById("wf-delete").addEventListener("click", () => {
      updateSelected((b) => { b.text = ""; });
    });
  }

  return { init, exitEditMode, renderBlocks, isActive: () => active };
})();
