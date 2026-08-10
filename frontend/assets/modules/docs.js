import { renderMarkdown } from "./markdown.js";

// Browses the repository documentation inside the dashboard. Documents are
// fetched once per session and kept in memory - the whole guide is ~110 KB, so
// the Pi never needs to re-read it while the modal is open.
export function createDocsController({ apiBase, elements }) {
  const {
    modal,
    list,
    content,
    documentTitle,
    pagerLabel,
    prevButton,
    nextButton,
    closeButton,
    status,
  } = elements;

  const markdownCache = new Map();
  let documents = [];
  let activeId = "";
  let indexLoaded = false;
  let listenersBound = false;

  function isOpen() {
    return modal.classList.contains("is-open");
  }

  function setStatus(message) {
    status.textContent = message;
    status.hidden = !message;
  }

  function activeIndex() {
    return documents.findIndex((entry) => entry.id === activeId);
  }

  function renderList() {
    list.innerHTML = "";
    let currentGroup = "";

    documents.forEach((entry) => {
      if (entry.group && entry.group !== currentGroup) {
        currentGroup = entry.group;
        const groupLabel = document.createElement("p");
        groupLabel.className = "docs__group";
        groupLabel.textContent = currentGroup;
        list.appendChild(groupLabel);
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = "docs__entry";
      button.classList.toggle("is-active", entry.id === activeId);
      button.textContent = entry.title;
      button.dataset.docId = entry.id;
      list.appendChild(button);
    });
  }

  function renderPager() {
    const index = activeIndex();
    const total = documents.length;
    pagerLabel.textContent = total > 0 && index >= 0 ? `${index + 1} / ${total}` : "-";
    prevButton.disabled = index <= 0;
    nextButton.disabled = index < 0 || index >= total - 1;
  }

  async function fetchJson(path) {
    const response = await fetch(`${apiBase}${path}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  }

  async function loadIndex() {
    if (indexLoaded) {
      return;
    }
    const payload = await fetchJson("/api/docs");
    documents = Array.isArray(payload?.documents)
      ? payload.documents
          .map((entry) => ({
            id: String(entry?.id || "").trim(),
            title: String(entry?.title || "").trim() || String(entry?.id || ""),
            group: String(entry?.group || "").trim(),
          }))
          .filter((entry) => entry.id)
      : [];
    indexLoaded = true;
  }

  function resolveDocumentId(target) {
    const wanted = String(target || "").split("#")[0].trim();
    if (!wanted) {
      return "";
    }
    const direct = documents.find((entry) => entry.id === wanted);
    if (direct) {
      return direct.id;
    }
    // Documents link each other relatively ("./knowledge-base.md",
    // "../README.md"), so fall back to matching the file name.
    const fileName = wanted.split("/").filter(Boolean).pop();
    const byName = documents.find((entry) => entry.id.endsWith(`/${fileName}`) || entry.id === fileName);
    return byName ? byName.id : "";
  }

  async function showDocument(documentId, anchor = "") {
    const wanted = String(documentId || "").trim();
    if (!wanted) {
      return;
    }

    activeId = wanted;
    renderList();
    renderPager();

    const entry = documents.find((item) => item.id === wanted);
    documentTitle.textContent = entry ? entry.title : wanted;

    if (!markdownCache.has(wanted)) {
      setStatus("Dokument wird geladen …");
      content.innerHTML = "";
      try {
        const payload = await fetchJson(`/api/docs?id=${encodeURIComponent(wanted)}`);
        markdownCache.set(wanted, String(payload?.markdown || ""));
      } catch (_error) {
        setStatus("Dokument konnte nicht geladen werden.");
        return;
      }
      // A different document may have been selected while this one loaded.
      if (activeId !== wanted) {
        return;
      }
    }

    setStatus("");
    content.innerHTML = renderMarkdown(markdownCache.get(wanted));
    content.scrollTop = 0;
    if (anchor) {
      scrollToAnchor(anchor);
    }
  }

  function scrollToAnchor(anchor) {
    const wanted = String(anchor || "").replace(/^#/, "").toLowerCase();
    if (!wanted) {
      return;
    }
    const headings = Array.from(content.querySelectorAll("[data-md-heading]"));
    const target = headings.find((heading) => {
      const slug = String(heading.dataset.mdHeading || "")
        .toLowerCase()
        .replace(/[^a-z0-9äöüß\s-]/g, "")
        .trim()
        .replace(/\s+/g, "-");
      return slug === wanted;
    });
    if (target) {
      content.scrollTop = target.offsetTop - content.offsetTop;
    }
  }

  function step(offset) {
    const index = activeIndex();
    const nextIndex = index + offset;
    if (index < 0 || nextIndex < 0 || nextIndex >= documents.length) {
      return;
    }
    showDocument(documents[nextIndex].id);
  }

  async function open() {
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    closeButton.focus();

    try {
      await loadIndex();
    } catch (_error) {
      setStatus("Dokumentation ist nicht erreichbar.");
      return;
    }

    if (documents.length === 0) {
      setStatus("Keine Dokumentation gefunden.");
      return;
    }

    renderList();
    await showDocument(activeId || documents[0].id);
  }

  function close() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  }

  function handleDocumentKeydown(event) {
    if (!isOpen()) {
      return false;
    }
    if (event.key === "Escape") {
      close();
      return true;
    }
    if (event.key === "ArrowLeft" && !prevButton.disabled) {
      step(-1);
      return true;
    }
    if (event.key === "ArrowRight" && !nextButton.disabled) {
      step(1);
      return true;
    }
    return false;
  }

  function attachEventHandlers() {
    if (listenersBound) {
      return;
    }
    listenersBound = true;

    closeButton.addEventListener("click", close);
    prevButton.addEventListener("click", () => step(-1));
    nextButton.addEventListener("click", () => step(1));

    modal.addEventListener("click", (event) => {
      if (event.target && event.target.dataset && event.target.dataset.closeDocs) {
        close();
      }
    });

    list.addEventListener("click", (event) => {
      const button = event.target.closest("[data-doc-id]");
      if (button) {
        showDocument(button.dataset.docId);
      }
    });

    content.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (!link) {
        return;
      }
      event.preventDefault();

      const docTarget = link.dataset.docLink;
      if (docTarget) {
        const resolved = resolveDocumentId(docTarget);
        const anchor = docTarget.includes("#") ? docTarget.split("#")[1] : "";
        if (resolved) {
          showDocument(resolved, anchor);
        }
        return;
      }

      const href = link.getAttribute("href") || "";
      if (href.startsWith("#")) {
        scrollToAnchor(href);
      }
    });
  }

  return {
    attachEventHandlers,
    handleDocumentKeydown,
    isOpen,
    open,
    close,
  };
}
