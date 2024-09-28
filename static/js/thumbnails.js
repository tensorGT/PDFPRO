window.ProPdfThumbnails = (() => {
  let pageOrder = [];
  let dragIdx = null;

  function renderList(pdfDoc) {
    const list = document.getElementById("thumbnails-list");
    list.innerHTML = "";
    pageOrder = Array.from({ length: pdfDoc.numPages }, (_, i) => ({ page: i, rotate: 0 }));
    document.getElementById("btn-apply-organize").disabled = false;

    pageOrder.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = "thumb-item";
      card.draggable = true;
      card.dataset.idx = String(idx);

      const canvas = document.createElement("canvas");
      const meta = document.createElement("div");
      meta.className = "thumb-meta";
      meta.innerHTML = `
        <span>Page ${item.page + 1}</span>
        <span class="thumb-btns">
          <button class="small-btn btn-rot" title="Rotate 90">Rot</button>
          <button class="small-btn btn-del" title="Drop page">Del</button>
        </span>
      `;

      card.appendChild(canvas);
      card.appendChild(meta);
      list.appendChild(card);

      pdfDoc.getPage(item.page + 1).then((page) => {
        const vp = page.getViewport({ scale: 0.28 });
        canvas.width = vp.width;
        canvas.height = vp.height;
        page.render({ canvasContext: canvas.getContext("2d"), viewport: vp });
      });

      card.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        window.ProPdfApp.goToPage(item.page + 1);
      });

      meta.querySelector(".btn-rot").addEventListener("click", (e) => {
        e.stopPropagation();
        const pos = Array.from(list.children).indexOf(card);
        pageOrder[pos].rotate = (pageOrder[pos].rotate + 90) % 360;
        canvas.style.transform = `rotate(${pageOrder[pos].rotate}deg)`;
      });

      meta.querySelector(".btn-del").addEventListener("click", (e) => {
        e.stopPropagation();
        if (pageOrder.length <= 1) {
          window.ProPdfApp.toast("Gotta keep at least one page!");
          return;
        }
        const pos = Array.from(list.children).indexOf(card);
        pageOrder.splice(pos, 1);
        card.remove();
      });

      card.addEventListener("dragstart", () => {
        dragIdx = Array.from(list.children).indexOf(card);
      });
      card.addEventListener("dragover", (e) => e.preventDefault());
      card.addEventListener("drop", (e) => {
        e.preventDefault();
        const dropIdx = Array.from(list.children).indexOf(card);
        if (dragIdx === null || dragIdx === dropIdx) return;
        const [moved] = pageOrder.splice(dragIdx, 1);
        pageOrder.splice(dropIdx, 0, moved);
        const nodes = Array.from(list.children);
        const draggedNode = nodes[dragIdx];
        if (dragIdx < dropIdx) {
          card.after(draggedNode);
        } else {
          card.before(draggedNode);
        }
        dragIdx = null;
      });
    });
  }

  function highlightActive(pageNum) {
    const list = document.getElementById("thumbnails-list");
    Array.from(list.children).forEach((el, i) => {
      const item = pageOrder[i];
      el.classList.toggle("active", item && item.page + 1 === pageNum);
    });
  }

  function init() {
    document.getElementById("btn-apply-organize").addEventListener("click", async () => {
      if (!window.ProPdfState.pdfBytes || !pageOrder.length) return;
      const fd = new FormData();
      fd.append("file", new Blob([window.ProPdfState.pdfBytes], { type: "application/pdf" }), "doc.pdf");
      fd.append("operations", JSON.stringify(pageOrder));
      const newBytes = await window.ProPdfTools.postForBlob("/api/ops/organize", fd);
      if (newBytes) {
        await window.ProPdfApp.loadPdfBytes(newBytes, window.ProPdfState.fileName);
        window.ProPdfApp.toast("Page order and rotations saved!");
      }
    });
  }

  return { init, renderList, highlightActive };
})();
