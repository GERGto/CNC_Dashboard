const KEYBOARD_ROWS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "ß", "acute", "backspace"],
  ["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ü", "plus", "at"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "hash", "lbracket"],
  ["shift", "y", "x", "c", "v", "b", "n", "m", "comma", "dot", "minus", "rbracket", "clear"],
  ["space"],
];

const KEYBOARD_CHAR_PAIRS = {
  "1": ["1", "!"],
  "2": ["2", "\""],
  "3": ["3", "§"],
  "4": ["4", "$"],
  "5": ["5", "%"],
  "6": ["6", "&"],
  "7": ["7", "/"],
  "8": ["8", "("],
  "9": ["9", ")"],
  "0": ["0", "="],
  "ß": ["ß", "?"],
  "acute": ["´", "`"],
  "plus": ["+", "*"],
  "hash": ["#", "'"],
  "comma": [",", ";"],
  "dot": [".", ":"],
  "minus": ["-", "_"],
  "at": ["@", "\\"],
  "lbracket": ["[", "{"],
  "rbracket": ["]", "}"],
};

export function createKeyboardController({
  modalEl,
  titleEl,
  displayInputEl,
  keysEl,
  cancelBtn,
  okBtn,
}) {
  let value = "";
  let shift = false;
  let context = null;
  let listenersBound = false;

  function isOpen() {
    return modalEl.classList.contains("is-open");
  }

  function isLetter(key) {
    return /^[a-zäöü]$/i.test(String(key || ""));
  }

  function keyLabel(key) {
    switch (key) {
      case "backspace":
        return "⌫";
      case "shift":
        return "Umschalt";
      case "clear":
        return "Löschen";
      case "space":
        return "Leerzeichen";
      default: {
        const pair = KEYBOARD_CHAR_PAIRS[key];
        if (pair) {
          return shift ? pair[1] : pair[0];
        }
        if (shift && isLetter(key)) {
          return String(key).toLocaleUpperCase("de-DE");
        }
        return String(key);
      }
    }
  }

  function renderDisplay() {
    const masked = !!(context && context.masked);
    displayInputEl.value = masked ? "•".repeat(value.length) : value;
  }

  function render() {
    keysEl.innerHTML = "";
    for (const row of KEYBOARD_ROWS) {
      const rowEl = document.createElement("div");
      rowEl.className = "keyboard__row";
      for (const key of row) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "keyboard__key";
        btn.dataset.key = key;
        if (key === "space") {
          btn.classList.add("keyboard__key--space");
        } else if (key === "shift" || key === "backspace" || key === "clear") {
          btn.classList.add("keyboard__key--wide");
        }
        if (key === "shift" && shift) {
          btn.classList.add("keyboard__key--active");
        }
        btn.textContent = keyLabel(key);
        rowEl.appendChild(btn);
      }
      keysEl.appendChild(rowEl);
    }
  }

  function closeImmediate() {
    modalEl.classList.remove("is-open");
    modalEl.setAttribute("aria-hidden", "true");
    shift = false;
    value = "";
    context = null;
  }

  function finish(submitted) {
    const current = context;
    const currentValue = value;
    closeImmediate();
    if (!current) return;

    if (submitted) {
      if (typeof current.onSubmit === "function") {
        current.onSubmit(currentValue);
      }
    } else if (typeof current.onCancel === "function") {
      current.onCancel();
    }

    if (current.sourceWindow && typeof current.sourceWindow.postMessage === "function") {
      current.sourceWindow.postMessage(
        {
          type: "keyboardResult",
          requestId: current.requestId ?? null,
          value: currentValue,
          canceled: !submitted,
        },
        current.responseOrigin || location.origin
      );
    }

    if (current.returnFocusEl && typeof current.returnFocusEl.focus === "function") {
      current.returnFocusEl.focus();
    }
  }

  function applyCharacter(rawKey) {
    let next = String(rawKey || "");
    if (!next) return;

    const pair = KEYBOARD_CHAR_PAIRS[next];
    if (pair) {
      next = shift ? pair[1] : pair[0];
    } else if (isLetter(next)) {
      next = shift ? next.toLocaleUpperCase("de-DE") : next.toLocaleLowerCase("de-DE");
    }

    const rawMaxLength = context ? context.maxLength : null;
    const maxLength =
      typeof rawMaxLength === "number" && Number.isFinite(rawMaxLength)
        ? Math.max(1, Math.floor(rawMaxLength))
        : null;
    if (maxLength !== null && value.length >= maxLength) {
      return;
    }
    value += next;
  }

  function handleKey(rawKey) {
    const key = String(rawKey || "");
    if (!key) return;

    if (key === "shift") {
      shift = !shift;
      render();
      return;
    }
    if (key === "backspace") {
      value = value.slice(0, -1);
      renderDisplay();
      return;
    }
    if (key === "clear") {
      value = "";
      renderDisplay();
      return;
    }
    if (key === "space") {
      applyCharacter(" ");
      if (shift) {
        shift = false;
        render();
      }
      renderDisplay();
      return;
    }

    applyCharacter(key);
    if (shift) {
      shift = false;
      render();
    }
    renderDisplay();
  }

  function open(options = {}) {
    if (isOpen()) {
      closeImmediate();
    }

    const title =
      typeof options.title === "string" && options.title.trim() ? options.title.trim() : "Eingabe";
    const placeholder = typeof options.placeholder === "string" ? options.placeholder : "";
    context = {
      masked: !!options.masked,
      maxLength: options.maxLength,
      onSubmit: options.onSubmit,
      onCancel: options.onCancel,
      sourceWindow: options.sourceWindow || null,
      requestId: options.requestId,
      responseOrigin: options.responseOrigin || location.origin,
      returnFocusEl: options.returnFocusEl || null,
    };
    titleEl.textContent = title;
    displayInputEl.placeholder = placeholder;
    value = String(options.value || "");
    shift = false;
    render();
    renderDisplay();

    modalEl.classList.add("is-open");
    modalEl.setAttribute("aria-hidden", "false");
    okBtn.focus();
  }

  function handleDocumentKeydown(ev) {
    if (!isOpen()) return false;

    if (ev.key === "Escape") {
      finish(false);
      return true;
    }
    if (ev.key === "Enter") {
      finish(true);
      return true;
    }
    if (ev.key === "Backspace") {
      ev.preventDefault();
      handleKey("backspace");
      return true;
    }
    if (ev.key === " ") {
      ev.preventDefault();
      handleKey("space");
      return true;
    }
    if (ev.key.length === 1) {
      handleKey(ev.key);
      return true;
    }

    return false;
  }

  function attachEventHandlers() {
    if (listenersBound) return;
    listenersBound = true;

    cancelBtn.addEventListener("click", () => finish(false));
    okBtn.addEventListener("click", () => finish(true));
    modalEl.addEventListener("click", (ev) => {
      if (ev.target && ev.target.dataset && ev.target.dataset.close) {
        finish(false);
      }
    });
    keysEl.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".keyboard__key");
      if (!btn) return;
      handleKey(btn.dataset.key);
    });
  }

  return {
    isOpen,
    open,
    closeImmediate,
    finish,
    handleKey,
    handleDocumentKeydown,
    attachEventHandlers,
  };
}
