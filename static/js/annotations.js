window.ProPdfAnnotations = (() => {
  let activeTool = "pan";
  let annotations = [];
  let redoStack = [];
  let cropBox = null;
  let redactBoxes = [];
  let pendingSigData = null;

  let isDrawing = false;
  let startPt = null;
  let currentPoints = [];

  const canvas = document.getElementById("annot-canvas");
  const ctx = canvas.getContext("2d");

  function getNormPos(evt) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (evt.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (evt.clientY - rect.top) / rect.height)),
    };
  }

  function updateButtons() {
    const hasDoc = Boolean(window.ProPdfState && window.ProPdfState.pdfBytes);
    document.getElementById("btn-undo-annot").disabled = annotations.length === 0 && redactBoxes.length === 0;
    document.getElementById("btn-redo-annot").disabled = redoStack.length === 0;
    document.getElementById("btn-burn-annots").disabled = !hasDoc || annotations.length === 0;
    document.getElementById("btn-apply-crop").classList.toggle("hidden", !cropBox);
    document.getElementById("btn-apply-redact-boxes").classList.toggle("hidden", redactBoxes.length === 0);
  }

  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const pageIdx = window.ProPdfState ? window.ProPdfState.currentPage - 1 : 0;
    const w = canvas.width;
    const h = canvas.height;

    // Draw search highlights for current page
    const searchHits = (window.ProPdfState && window.ProPdfState.searchHighlightPages) || new Set();
    if (searchHits.has(pageIdx + 1)) {
      ctx.save();
      ctx.strokeStyle = "#f97316";
      ctx.lineWidth = 4;
      ctx.strokeRect(4, 4, w - 8, h - 8);
      ctx.restore();
    }

    for (const ann of annotations) {
      if (ann.page !== pageIdx) continue;
      ctx.save();
      ctx.strokeStyle = ann.color || "#facc15";
      ctx.fillStyle = ann.color || "#facc15";
      ctx.lineWidth = ann.strokeWidth || 3;

      if (ann.type === "highlight") {
        ctx.globalAlpha = 0.35;
        ctx.fillRect(ann.x0 * w, ann.y0 * h, (ann.x1 - ann.x0) * w, (ann.y1 - ann.y0) * h);
      } else if (ann.type === "underline") {
        ctx.beginPath();
        ctx.moveTo(ann.x0 * w, ann.y1 * h);
        ctx.lineTo(ann.x1 * w, ann.y1 * h);
        ctx.stroke();
      } else if (ann.type === "strikethrough") {
        const midY = ((ann.y0 + ann.y1) / 2) * h;
        ctx.beginPath();
        ctx.moveTo(ann.x0 * w, midY);
        ctx.lineTo(ann.x1 * w, midY);
        ctx.stroke();
      } else if (ann.type === "draw" && ann.points.length >= 2) {
        ctx.beginPath();
        ctx.moveTo(ann.points[0].x * w, ann.points[0].y * h);
        for (let i = 1; i < ann.points.length; i++) {
          ctx.lineTo(ann.points[i].x * w, ann.points[i].y * h);
        }
        ctx.stroke();
      } else if (ann.type === "rect") {
        ctx.strokeRect(ann.x0 * w, ann.y0 * h, (ann.x1 - ann.x0) * w, (ann.y1 - ann.y0) * h);
      } else if (ann.type === "circle") {
        const cx = ((ann.x0 + ann.x1) / 2) * w;
        const cy = ((ann.y0 + ann.y1) / 2) * h;
        const rx = Math.abs(ann.x1 - ann.x0) * w * 0.5;
        const ry = Math.abs(ann.y1 - ann.y0) * h * 0.5;
        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();
      } else if (ann.type === "arrow") {
        const x1 = ann.x0 * w, y1 = ann.y0 * h;
        const x2 = ann.x1 * w, y2 = ann.y1 * h;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        const angle = Math.atan2(y2 - y1, x2 - x1);
        ctx.lineTo(x2 - 12 * Math.cos(angle - 0.45), y2 - 12 * Math.sin(angle - 0.45));
        ctx.moveTo(x2, y2);
        ctx.lineTo(x2 - 12 * Math.cos(angle + 0.45), y2 - 12 * Math.sin(angle + 0.45));
        ctx.stroke();
      } else if (ann.type === "text") {
        ctx.font = `${ann.fontSize || 16}px sans-serif`;
        ctx.fillText(ann.text || "", ann.x * w, ann.y * h + 16);
      } else if (ann.type === "note") {
        ctx.fillStyle = "#fde047";
        ctx.fillRect(ann.x * w, ann.y * h, 22, 22);
        ctx.strokeStyle = "#854d0e";
        ctx.strokeRect(ann.x * w, ann.y * h, 22, 22);
      } else if (ann.type === "stamp") {
        const bx = ann.x0 * w, by = ann.y0 * h;
        const bw = (ann.x1 - ann.x0) * w, bh = (ann.y1 - ann.y0) * h;
        ctx.lineWidth = 2.5;
        ctx.strokeRect(bx, by, bw, bh);
        ctx.font = `bold ${Math.max(12, Math.min(28, bh * 0.5))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText((ann.text || "APPROVED").toUpperCase(), bx + bw / 2, by + bh / 2);
      } else if (ann.type === "signature" && ann.imgEl) {
        ctx.drawImage(ann.imgEl, ann.x0 * w, ann.y0 * h, (ann.x1 - ann.x0) * w, (ann.y1 - ann.y0) * h);
      }
      ctx.restore();
    }

    // Draw crop box preview
    if (cropBox && cropBox.page === pageIdx) {
      ctx.save();
      ctx.strokeStyle = "#38bdf8";
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 2;
      ctx.strokeRect(cropBox.x0 * w, cropBox.y0 * h, (cropBox.x1 - cropBox.x0) * w, (cropBox.y1 - cropBox.y0) * h);
      ctx.restore();
    }

    // Draw redaction boxes preview
    for (const rb of redactBoxes) {
      if (rb.page !== pageIdx) continue;
      ctx.save();
      ctx.fillStyle = "rgba(0, 0, 0, 0.8)";
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 2;
      const rx = rb.x0 * w, ry = rb.y0 * h, rw = (rb.x1 - rb.x0) * w, rh = (rb.y1 - rb.y0) * h;
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.restore();
    }

    updateButtons();
  }

  function normBox(a, b) {
    return {
      x0: Math.min(a.x, b.x),
      y0: Math.min(a.y, b.y),
      x1: Math.max(a.x, b.x),
      y1: Math.max(a.y, b.y),
    };
  }

  function init() {
    document.querySelectorAll(".tool-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tool-chip").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeTool = btn.dataset.tool;
        canvas.style.cursor = activeTool === "pan" ? "default" : "crosshair";
        if (activeTool === "signature" && !pendingSigData) {
          document.getElementById("sig-modal").classList.remove("hidden");
        }
      });
    });

    canvas.addEventListener("pointerdown", (e) => {
      if (!window.ProPdfState.pdfBytes || activeTool === "pan") return;
      const pt = getNormPos(e);
      const pageIdx = window.ProPdfState.currentPage - 1;
      const color = document.getElementById("annot-color").value;
      const strokeWidth = Number(document.getElementById("annot-width").value || 3);

      if (activeTool === "text") {
        const text = window.prompt("Type text to add:");
        if (text && text.trim()) {
          annotations.push({ page: pageIdx, type: "text", x: pt.x, y: pt.y, text: text.trim(), color, fontSize: 16 });
          redoStack = [];
          redraw();
        }
        return;
      }

      if (activeTool === "note") {
        const text = window.prompt("Sticky note text:");
        if (text && text.trim()) {
          annotations.push({ page: pageIdx, type: "note", x: pt.x, y: pt.y, text: text.trim(), color });
          redoStack = [];
          redraw();
        }
        return;
      }

      isDrawing = true;
      startPt = pt;
      currentPoints = [pt];
      canvas.setPointerCapture(e.pointerId);
    });

    canvas.addEventListener("pointermove", (e) => {
      if (!isDrawing) return;
      const pt = getNormPos(e);
      if (activeTool === "draw") {
        currentPoints.push(pt);
      }
      redraw();
      // Live preview
      const w = canvas.width, h = canvas.height;
      ctx.save();
      ctx.strokeStyle = document.getElementById("annot-color").value;
      ctx.lineWidth = Number(document.getElementById("annot-width").value || 3);
      if (activeTool === "draw") {
        ctx.beginPath();
        ctx.moveTo(currentPoints[0].x * w, currentPoints[0].y * h);
        for (const p of currentPoints) ctx.lineTo(p.x * w, p.y * h);
        ctx.stroke();
      } else if (activeTool === "arrow") {
        ctx.beginPath();
        ctx.moveTo(startPt.x * w, startPt.y * h);
        ctx.lineTo(pt.x * w, pt.y * h);
        ctx.stroke();
      } else {
        const b = normBox(startPt, pt);
        ctx.strokeRect(b.x0 * w, b.y0 * h, (b.x1 - b.x0) * w, (b.y1 - b.y0) * h);
      }
      ctx.restore();
    });

    canvas.addEventListener("pointerup", (e) => {
      if (!isDrawing) return;
      isDrawing = false;
      const endPt = getNormPos(e);
      const pageIdx = window.ProPdfState.currentPage - 1;
      const color = document.getElementById("annot-color").value;
      const strokeWidth = Number(document.getElementById("annot-width").value || 3);

      if (activeTool === "draw") {
        if (currentPoints.length >= 2) {
          annotations.push({ page: pageIdx, type: "draw", points: currentPoints, color, strokeWidth });
          redoStack = [];
        }
      } else {
        const b = normBox(startPt, endPt);
        if (b.x1 - b.x0 < 0.01 && b.y1 - b.y0 < 0.01) {
          redraw();
          return;
        }
        if (activeTool === "crop") {
          cropBox = { page: pageIdx, ...b };
        } else if (activeTool === "redact") {
          redactBoxes.push({ page: pageIdx, ...b });
        } else if (activeTool === "stamp") {
          const text = window.prompt("Stamp label:", "APPROVED") || "APPROVED";
          annotations.push({ page: pageIdx, type: "stamp", ...b, text, color });
          redoStack = [];
        } else if (activeTool === "signature") {
          if (!pendingSigData) {
            document.getElementById("sig-modal").classList.remove("hidden");
          } else {
            const img = new Image();
            img.src = pendingSigData;
            img.onload = () => redraw();
            annotations.push({ page: pageIdx, type: "signature", ...b, imageData: pendingSigData, imgEl: img });
            redoStack = [];
          }
        } else if (activeTool === "arrow") {
          annotations.push({ page: pageIdx, type: "arrow", x0: startPt.x, y0: startPt.y, x1: endPt.x, y1: endPt.y, color, strokeWidth });
          redoStack = [];
        } else {
          annotations.push({ page: pageIdx, type: activeTool, ...b, color, strokeWidth });
          redoStack = [];
        }
      }
      redraw();
    });

    document.getElementById("btn-undo-annot").addEventListener("click", () => {
      if (annotations.length > 0) {
        redoStack.push(annotations.pop());
      } else if (redactBoxes.length > 0) {
        redactBoxes.pop();
      }
      redraw();
    });

    document.getElementById("btn-redo-annot").addEventListener("click", () => {
      if (redoStack.length > 0) {
        annotations.push(redoStack.pop());
        redraw();
      }
    });

    document.getElementById("btn-burn-annots").addEventListener("click", async () => {
      if (!annotations.length) return;
      const payload = annotations.map(({ imgEl, ...rest }) => rest);
      const fd = new FormData();
      fd.append("file", new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" }), "doc.pdf");
      fd.append("annotations", JSON.stringify(payload));
      const newBytes = await window.ProPdfTools.postForBlob("/api/edit/annotations", fd);
      if (newBytes) {
        annotations = [];
        redoStack = [];
        await window.ProPdfApp.loadPdfBytes(newBytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Edits saved right into the PDF!");
      }
    });

    document.getElementById("btn-apply-crop").addEventListener("click", async () => {
      if (!cropBox) return;
      const fd = new FormData();
      fd.append("file", new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" }), "doc.pdf");
      fd.append("pages", String(cropBox.page + 1));
      fd.append("box", JSON.stringify(cropBox));
      const newBytes = await window.ProPdfTools.postForBlob("/api/ops/crop", fd);
      if (newBytes) {
        cropBox = null;
        await window.ProPdfApp.loadPdfBytes(newBytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Page cropped!");
      }
    });

    document.getElementById("btn-apply-redact-boxes").addEventListener("click", async () => {
      if (!redactBoxes.length) return;
      const fd = new FormData();
      fd.append("file", new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" }), "doc.pdf");
      fd.append("boxes", JSON.stringify(redactBoxes));
      fd.append("keywords", "");
      const newBytes = await window.ProPdfTools.postForBlob("/api/edit/redact", fd);
      if (newBytes) {
        redactBoxes = [];
        await window.ProPdfApp.loadPdfBytes(newBytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Selected areas permanently redacted!");
      }
    });

    // Signature pad modal
    const sigPad = document.getElementById("sig-pad");
    const sigCtx = sigPad.getContext("2d");
    let sigDrawing = false;
    sigCtx.lineWidth = 2.5;
    sigCtx.lineCap = "round";
    sigCtx.strokeStyle = "#111827";

    const sigPos = (ev) => {
      const r = sigPad.getBoundingClientRect();
      return {
        x: ((ev.clientX - r.left) / r.width) * sigPad.width,
        y: ((ev.clientY - r.top) / r.height) * sigPad.height,
      };
    };
    sigPad.addEventListener("pointerdown", (e) => {
      sigDrawing = true;
      const p = sigPos(e);
      sigCtx.beginPath();
      sigCtx.moveTo(p.x, p.y);
    });
    sigPad.addEventListener("pointermove", (e) => {
      if (!sigDrawing) return;
      const p = sigPos(e);
      sigCtx.lineTo(p.x, p.y);
      sigCtx.stroke();
    });
    sigPad.addEventListener("pointerup", () => { sigDrawing = false; });

    document.getElementById("btn-clear-sig").addEventListener("click", () => {
      sigCtx.clearRect(0, 0, sigPad.width, sigPad.height);
    });
    document.getElementById("btn-close-sig").addEventListener("click", () => {
      document.getElementById("sig-modal").classList.add("hidden");
    });
    document.getElementById("btn-use-sig").addEventListener("click", () => {
      pendingSigData = sigPad.toDataURL("image/png");
      document.getElementById("sig-modal").classList.add("hidden");
      window.ProPdfApp.toast("Signature ready! Drag a box on the page to place it.");
    });
  }

  function clearAll() {
    annotations = [];
    redoStack = [];
    cropBox = null;
    redactBoxes = [];
    redraw();
  }

  return { init, redraw, clearAll };
})();
