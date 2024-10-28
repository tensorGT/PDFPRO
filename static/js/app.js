pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

window.ProPdfState = {
  pdfDoc: null,
  pdfBytes: null,
  fileName: "document.pdf",
  currentPage: 1,
  scale: 1.25,
  searchHighlightPages: new Set(),
};

window.ProPdfApp = (() => {
  const pdfCanvas = document.getElementById("pdf-canvas");
  const annotCanvas = document.getElementById("annot-canvas");
  const pdfCtx = pdfCanvas.getContext("2d");

  function toast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 3200);
  }

  function showModal(title, html) {
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-body").innerHTML = html;
    document.getElementById("modal").classList.remove("hidden");
  }

  async function renderPage(num) {
    const doc = window.ProPdfState.pdfDoc;
    if (!doc) return;
    const clamped = Math.max(1, Math.min(doc.numPages, num));
    window.ProPdfState.currentPage = clamped;

    const page = await doc.getPage(clamped);
    const vp = page.getViewport({ scale: window.ProPdfState.scale });
    pdfCanvas.width = vp.width;
    pdfCanvas.height = vp.height;
    annotCanvas.width = vp.width;
    annotCanvas.height = vp.height;

    await page.render({ canvasContext: pdfCtx, viewport: vp }).promise;

    document.getElementById("page-num-input").value = clamped;
    document.getElementById("btn-prev").disabled = clamped <= 1;
    document.getElementById("btn-next").disabled = clamped >= doc.numPages;
    document.getElementById("zoom-label").textContent = `${Math.round(window.ProPdfState.scale * 100)}%`;

    window.ProPdfThumbnails.highlightActive(clamped);
    window.ProPdfAnnotations.redraw();
    if (window.ProPdfEditor && window.ProPdfEditor.isActive()) {
      window.ProPdfEditor.exitEditMode();
    }
  }

  async function loadPdfBytes(uint8, name = "document.pdf") {
    window.ProPdfState.pdfBytes = uint8;
    window.ProPdfState.fileName = name;
    window.ProPdfState.searchHighlightPages = new Set();

    const loadingTask = pdfjsLib.getDocument({ data: uint8.slice() });
    const doc = await loadingTask.promise;
    window.ProPdfState.pdfDoc = doc;

    document.getElementById("drop-overlay").classList.add("hidden");
    document.getElementById("page-stage").classList.remove("hidden");
    document.getElementById("page-count").textContent = doc.numPages;

    [
      "btn-download",
      "page-num-input",
      "btn-zoom-out",
      "btn-zoom-in",
      "btn-fit-width",
      "search-input",
      "btn-search",
    ].forEach((id) => {
      document.getElementById(id).disabled = false;
    });

    window.ProPdfThumbnails.renderList(doc);
    await renderPage(Math.min(window.ProPdfState.currentPage, doc.numPages) || 1);
  }

  async function openFile(file) {
    if (!file) return;
    const buf = new Uint8Array(await file.arrayBuffer());
    window.ProPdfAnnotations.clearAll();
    window.ProPdfState.currentPage = 1;
    await loadPdfBytes(buf, file.name);
    toast(`Loaded ${file.name}`);
  }

  async function runSearch() {
    const query = document.getElementById("search-input").value.trim().toLowerCase();
    const doc = window.ProPdfState.pdfDoc;
    if (!doc || !query) return;

    const hits = [];
    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i);
      const tc = await page.getTextContent();
      const text = tc.items.map((it) => it.str).join(" ").toLowerCase();
      if (text.includes(query)) hits.push(i);
    }

    window.ProPdfState.searchHighlightPages = new Set(hits);
    document.getElementById("search-status").textContent = hits.length ? `${hits.length} page(s)` : "No hits";
    if (hits.length) {
      await renderPage(hits[0]);
    } else {
      window.ProPdfAnnotations.redraw();
    }
  }

  function init() {
    window.ProPdfAnnotations.init();
    window.ProPdfEditor.init();
    window.ProPdfThumbnails.init();
    window.ProPdfTools.init();

    document.getElementById("file-input").addEventListener("change", (e) => openFile(e.target.files[0]));
    document.getElementById("btn-download").addEventListener("click", () => {
      if (window.ProPdfState.pdfBytes) {
        window.ProPdfTools.triggerDownload(window.ProPdfState.pdfBytes, window.ProPdfState.fileName);
      }
    });

    document.getElementById("btn-prev").addEventListener("click", () => renderPage(window.ProPdfState.currentPage - 1));
    document.getElementById("btn-next").addEventListener("click", () => renderPage(window.ProPdfState.currentPage + 1));
    document.getElementById("page-num-input").addEventListener("change", (e) => renderPage(Number(e.target.value)));

    document.getElementById("btn-zoom-in").addEventListener("click", () => {
      window.ProPdfState.scale = Math.min(3.0, window.ProPdfState.scale + 0.2);
      renderPage(window.ProPdfState.currentPage);
    });
    document.getElementById("btn-zoom-out").addEventListener("click", () => {
      window.ProPdfState.scale = Math.max(0.4, window.ProPdfState.scale - 0.2);
      renderPage(window.ProPdfState.currentPage);
    });
    document.getElementById("btn-fit-width").addEventListener("click", async () => {
      const doc = window.ProPdfState.pdfDoc;
      if (!doc) return;
      const page = await doc.getPage(window.ProPdfState.currentPage);
      const baseVp = page.getViewport({ scale: 1.0 });
      const containerW = document.getElementById("canvas-container").clientWidth - 48;
      window.ProPdfState.scale = Math.max(0.4, containerW / baseVp.width);
      renderPage(window.ProPdfState.currentPage);
    });

    document.getElementById("btn-search").addEventListener("click", runSearch);
    document.getElementById("search-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") runSearch();
    });

    document.getElementById("reading-mode").addEventListener("change", (e) => {
      document.body.className = `theme-${e.target.value}`;
    });

    // Responsive sidebars
    const leftBar = document.getElementById("left-sidebar");
    const rightBar = document.getElementById("right-sidebar");
    document.getElementById("btn-toggle-left").addEventListener("click", () => leftBar.classList.toggle("open"));
    document.getElementById("btn-close-left").addEventListener("click", () => leftBar.classList.remove("open"));
    document.getElementById("btn-toggle-right").addEventListener("click", () => rightBar.classList.toggle("open"));
    document.getElementById("btn-close-right").addEventListener("click", () => rightBar.classList.remove("open"));

    document.getElementById("btn-close-modal").addEventListener("click", () => {
      document.getElementById("modal").classList.add("hidden");
    });

    // Drag and drop anywhere on viewer
    const container = document.getElementById("canvas-container");
    const dropOverlay = document.getElementById("drop-overlay");
    container.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropOverlay.classList.add("dragover");
    });
    container.addEventListener("dragleave", () => dropOverlay.classList.remove("dragover"));
    container.addEventListener("drop", (e) => {
      e.preventDefault();
      dropOverlay.classList.remove("dragover");
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") openFile(file);
    });

    // Keyboard shortcuts
    window.addEventListener("keydown", (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
      if (e.key === "ArrowRight") renderPage(window.ProPdfState.currentPage + 1);
      if (e.key === "ArrowLeft") renderPage(window.ProPdfState.currentPage - 1);
    });
  }

  document.addEventListener("DOMContentLoaded", init);

  return { loadPdfBytes, goToPage: renderPage, toast, showModal };
})();
