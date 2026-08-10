// Small Markdown renderer for the built-in system guide. Everything is escaped
// before any markup is produced, so document text can never inject HTML.

const HTML_ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value) {
  return String(value === null || value === undefined ? "" : value).replace(
    /[&<>"']/g,
    (character) => HTML_ESCAPES[character]
  );
}

// Set for the duration of one renderMarkdown() call. Rendering is synchronous,
// so a module-level slot is enough and keeps the inline helpers simple.
let activeOptions = {};

function isExternalTarget(target) {
  return /^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith("//");
}

// Images are only rendered when the caller supplies a resolver, because only it
// knows which document the relative path belongs to.
function renderImage(escapedAlt, escapedSource) {
  const resolve = activeOptions.resolveAsset;
  if (typeof resolve !== "function") {
    return escapedAlt;
  }
  const source = escapedSource.replace(/&amp;/g, "&");
  const url = resolve(source);
  if (!url) {
    return escapedAlt;
  }
  return `<img class="md__image" src="${escapeHtml(url)}" alt="${escapedAlt}" loading="lazy" />`;
}

// Documentation links stay inside the modal. External addresses are printed
// instead of linked: the kiosk has no browser chrome, so a navigation away from
// the dashboard would be a one-way trip.
function renderLink(label, target) {
  const cleanTarget = target.trim();
  const text = label.trim() || cleanTarget;

  if (cleanTarget.startsWith("#")) {
    return `<a class="md__link" href="${escapeHtml(cleanTarget)}">${text}</a>`;
  }

  if (!isExternalTarget(cleanTarget) && /\.md(#.*)?$/i.test(cleanTarget)) {
    return `<a class="md__link" href="#" data-doc-link="${escapeHtml(cleanTarget)}">${text}</a>`;
  }

  if (text === cleanTarget) {
    return `<span class="md__url">${escapeHtml(cleanTarget)}</span>`;
  }
  return `${text} <span class="md__url">${escapeHtml(cleanTarget)}</span>`;
}

function renderInlineSegment(escapedText) {
  return escapedText
    // Images first: the link pattern would otherwise match their "[alt](src)"
    // part and leave a stray exclamation mark behind.
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_match, alt, source) => renderImage(alt, source))
    .replace(/\[([^\]]*)\]\(([^)\s]+)\)/g, (_match, label, target) => renderLink(label, target))
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])_([^_]+)_(?=$|[\s).,;:!?])/g, "$1<em>$2</em>")
    .replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>");
}

export function renderInline(rawText) {
  const escaped = escapeHtml(rawText);
  let html = "";
  let index = 0;

  // Code spans are emitted verbatim so their content is never treated as markup.
  const pattern = /`([^`]+)`/g;
  let match = pattern.exec(escaped);
  while (match) {
    html += renderInlineSegment(escaped.slice(index, match.index));
    html += `<code class="md__code">${match[1]}</code>`;
    index = match.index + match[0].length;
    match = pattern.exec(escaped);
  }
  html += renderInlineSegment(escaped.slice(index));
  return html;
}

function isTableSeparator(line) {
  return /^\|?[\s:-]*-[\s|:-]*\|?$/.test(line.trim()) && line.includes("-");
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function listItemMatch(line) {
  const unordered = /^(\s*)[-*+]\s+(.*)$/.exec(line);
  if (unordered) {
    return { indent: unordered[1].length, ordered: false, text: unordered[2] };
  }
  const ordered = /^(\s*)\d+[.)]\s+(.*)$/.exec(line);
  if (ordered) {
    return { indent: ordered[1].length, ordered: true, text: ordered[2] };
  }
  return null;
}

function renderList(lines, startIndex, baseIndent) {
  const first = listItemMatch(lines[startIndex]);
  const tag = first.ordered ? "ol" : "ul";
  let html = `<${tag} class="md__list">`;
  let index = startIndex;

  while (index < lines.length) {
    const item = listItemMatch(lines[index]);
    if (!item || item.indent < baseIndent) {
      break;
    }

    if (item.indent > baseIndent) {
      const nested = renderList(lines, index, item.indent);
      html = html.replace(/<\/li>$/, `${nested.html}</li>`);
      index = nested.nextIndex;
      continue;
    }

    html += `<li>${renderInline(item.text)}</li>`;
    index += 1;
  }

  return { html: `${html}</${tag}>`, nextIndex: index };
}

export function renderMarkdown(markdown, options = {}) {
  activeOptions = options && typeof options === "object" ? options : {};
  const lines = String(markdown || "").replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let paragraph = [];

  function flushParagraph() {
    if (paragraph.length === 0) {
      return;
    }
    html.push(`<p class="md__paragraph">${renderInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      flushParagraph();
      const language = trimmed.slice(3).trim();
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      html.push(
        `<pre class="md__pre" data-language="${escapeHtml(language)}"><code>${escapeHtml(
          code.join("\n")
        )}</code></pre>`
      );
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      index += 1;
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      const level = Math.min(6, heading[1].length);
      html.push(
        `<h${level} class="md__heading md__heading--${level}" data-md-heading="${escapeHtml(
          heading[2]
        )}">${renderInline(heading[2])}</h${level}>`
      );
      index += 1;
      continue;
    }

    if (/^([-*_])\1{2,}$/.test(trimmed.replace(/\s+/g, ""))) {
      flushParagraph();
      html.push('<hr class="md__rule" />');
      index += 1;
      continue;
    }

    if (trimmed.startsWith("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      flushParagraph();
      const header = splitTableRow(trimmed);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      const headHtml = header.map((cell) => `<th>${renderInline(cell)}</th>`).join("");
      const bodyHtml = rows
        .map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`)
        .join("");
      html.push(
        `<div class="md__table-scroll"><table class="md__table"><thead><tr>${headHtml}</tr></thead>` +
          `<tbody>${bodyHtml}</tbody></table></div>`
      );
      continue;
    }

    if (trimmed.startsWith(">")) {
      flushParagraph();
      const quote = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote class="md__quote">${renderInline(quote.join(" "))}</blockquote>`);
      continue;
    }

    const item = listItemMatch(line);
    if (item) {
      flushParagraph();
      const list = renderList(lines, index, item.indent);
      html.push(list.html);
      index = list.nextIndex;
      continue;
    }

    paragraph.push(trimmed);
    index += 1;
  }

  flushParagraph();
  activeOptions = {};
  return html.join("\n");
}
