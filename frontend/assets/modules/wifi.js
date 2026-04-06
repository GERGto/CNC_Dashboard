export function createWifiController({
  apiBase,
  state,
  elements,
  keyboardController,
  onSetWifiConnected,
  onBroadcastWifi,
  onReturnFocus,
  connectTimeoutMs = 15000,
  feedbackMs = 2000,
}) {
  const {
    btn,
    configModal,
    modalClose,
    ssidSelect,
    scanBtn,
    passwordInput,
    autoConnectInput,
    saveBtn,
    connectBtn,
    disconnectBtn,
    configMsg,
    connectFeedbackModal,
    feedbackSpinner,
    feedbackSuccess,
    feedbackError,
    connectFeedbackText,
  } = elements;

  let connectInFlight = false;
  let listenersBound = false;

  function setConfigMessage(message, type = "info") {
    configMsg.textContent = String(message || "");
    configMsg.classList.toggle("is-error", type === "error");
    configMsg.classList.toggle("is-ok", type === "ok");
  }

  function waitFor(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function setControlsDisabled(disabled) {
    const isDisabled = !!disabled;
    ssidSelect.disabled = isDisabled;
    scanBtn.disabled = isDisabled;
    passwordInput.disabled = isDisabled;
    autoConnectInput.disabled = isDisabled;
    saveBtn.disabled = isDisabled;
    connectBtn.disabled = isDisabled;
    disconnectBtn.disabled = isDisabled;
    modalClose.disabled = isDisabled;
    if (isDisabled && keyboardController.isOpen()) {
      keyboardController.closeImmediate();
    }
  }

  function openConnectFeedbackLoading(loadingText = "WLAN wird verbunden ...") {
    connectFeedbackModal.classList.add("is-open");
    connectFeedbackModal.setAttribute("aria-hidden", "false");
    feedbackSpinner.hidden = false;
    feedbackSuccess.hidden = true;
    feedbackError.hidden = true;
    connectFeedbackText.textContent = String(loadingText || "");
  }

  function closeConnectFeedback() {
    connectFeedbackModal.classList.remove("is-open");
    connectFeedbackModal.setAttribute("aria-hidden", "true");
  }

  async function showConnectFeedbackResult(
    ok,
    successText = "WLAN verbunden",
    errorText = "WLAN-Verbindung fehlgeschlagen"
  ) {
    feedbackSpinner.hidden = true;
    feedbackSuccess.hidden = !ok;
    feedbackError.hidden = ok;
    connectFeedbackText.textContent = ok ? String(successText || "") : String(errorText || "");
    await waitFor(feedbackMs);
    closeConnectFeedback();
  }

  function readPayload() {
    return {
      ssid: String(ssidSelect.value || "").trim(),
      password: String(passwordInput.value || ""),
      autoConnect: !!autoConnectInput.checked,
    };
  }

  function setSsidOptions(networks, preferredSsid = "") {
    const list = Array.isArray(networks) ? networks : [];
    const selectedBefore = String(ssidSelect.value || "").trim();
    const preferred = String(preferredSsid || "").trim();
    const merged = [];

    for (const raw of list) {
      const ssid = String(raw || "").trim();
      if (!ssid || merged.includes(ssid)) continue;
      merged.push(ssid);
    }
    if (preferred && !merged.includes(preferred)) {
      merged.push(preferred);
    }

    ssidSelect.innerHTML = "";
    if (merged.length === 0) {
      const emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = "Keine Netzwerke gefunden";
      ssidSelect.appendChild(emptyOption);
      ssidSelect.value = "";
      return;
    }

    for (const ssid of merged) {
      const option = document.createElement("option");
      option.value = ssid;
      option.textContent = ssid;
      ssidSelect.appendChild(option);
    }

    if (preferred && merged.includes(preferred)) {
      ssidSelect.value = preferred;
    } else if (selectedBefore && merged.includes(selectedBefore)) {
      ssidSelect.value = selectedBefore;
    } else {
      ssidSelect.value = merged[0];
    }
  }

  function loadNetworks(preferredSsid = "") {
    return fetch(`${apiBase}/api/wifi/networks`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const networks = data && Array.isArray(data.networks) ? data.networks : [];
        setSsidOptions(networks, preferredSsid);
      })
      .catch(() => {
        setSsidOptions([], preferredSsid);
        setConfigMessage("WLAN-Netzwerke konnten nicht geladen werden.", "error");
      });
  }

  function toBooleanLike(value) {
    if (typeof value === "boolean") return value;
    if (typeof value === "number" && (value === 0 || value === 1)) {
      return Boolean(value);
    }
    return null;
  }

  function applySettings(data, options = {}) {
    if (!data || typeof data !== "object") return state.wifiSsid;
    const updateForm = !!options.updateForm;
    const fallbackConnected = !!options.fallbackConnected;
    const broadcast = options.broadcast !== false;
    const showIssue = options.showIssue === true;
    const hasWifiIpAddress = typeof data.wifiIpAddress === "string";

    const currentSsid = typeof data.wifiSsid === "string" ? data.wifiSsid : state.wifiSsid;
    state.wifiSsid = String(currentSsid || "").trim();
    state.wifiIssue = typeof data.wifiIssue === "string" ? data.wifiIssue.trim() : "";
    if (hasWifiIpAddress) {
      state.wifiIpAddress = data.wifiIpAddress.trim();
    }

    if (updateForm) {
      if (typeof data.wifiPassword === "string") {
        passwordInput.value = data.wifiPassword;
      }
      const autoConnect = toBooleanLike(data.wifiAutoConnect);
      if (autoConnect !== null) {
        autoConnectInput.checked = autoConnect;
      }
    }

    const connected = toBooleanLike(data.wifiConnected);
    if (connected !== null) {
      onSetWifiConnected(connected, currentSsid);
      if (!connected && !hasWifiIpAddress) {
        state.wifiIpAddress = "";
      }
    } else if (fallbackConnected) {
      onSetWifiConnected(state.wifiConnected, currentSsid);
    }

    if (connected) {
      state.wifiIssue = "";
    }

    if (broadcast) {
      onBroadcastWifi();
    }

    if (showIssue) {
      const issue = typeof data.wifiIssue === "string" ? data.wifiIssue.trim() : "";
      if (issue && connected === false) {
        setConfigMessage(issue, "error");
      }
    }

    return String(currentSsid || "").trim();
  }

  function openPasswordKeyboard() {
    if (connectInFlight || passwordInput.disabled) {
      return;
    }
    keyboardController.open({
      title: "WLAN-Passwort",
      placeholder: "Passwort eingeben",
      value: passwordInput.value,
      onSubmit: (nextValue) => {
        passwordInput.value = nextValue;
      },
      returnFocusEl: passwordInput,
    });
  }

  function openConfigModal() {
    configModal.classList.add("is-open");
    configModal.setAttribute("aria-hidden", "false");
    setConfigMessage("");
    fetch(`${apiBase}/api/settings`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const currentSsid = applySettings(data, {
          updateForm: true,
          fallbackConnected: true,
          broadcast: true,
          showIssue: true,
        });
        return loadNetworks(currentSsid);
      })
      .catch(() => {
        loadNetworks(state.wifiSsid);
        setConfigMessage("WLAN-Einstellungen konnten nicht geladen werden.", "error");
      })
      .finally(() => {
        ssidSelect.focus();
      });
  }

  function closeConfigModal(force = false) {
    if (connectInFlight && !force) {
      return false;
    }
    if (keyboardController.isOpen()) {
      keyboardController.closeImmediate();
    }
    configModal.classList.remove("is-open");
    configModal.setAttribute("aria-hidden", "true");
    if (typeof onReturnFocus === "function") {
      onReturnFocus();
    } else if (btn && typeof btn.focus === "function") {
      btn.focus();
    }
    return true;
  }

  function saveConfig() {
    const payload = readPayload();
    fetch(`${apiBase}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        wifiSsid: payload.ssid,
        wifiPassword: payload.password,
        wifiAutoConnect: payload.autoConnect,
      }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data || typeof data !== "object") {
          setConfigMessage("WLAN-Einstellungen konnten nicht gespeichert werden.", "error");
          return;
        }
        state.wifiSsid = payload.ssid;
        setConfigMessage("WLAN-Einstellungen gespeichert.", "ok");
        onBroadcastWifi();
      })
      .catch(() => {
        setConfigMessage("WLAN-Einstellungen konnten nicht gespeichert werden.", "error");
      });
  }

  async function connectWifi() {
    if (connectInFlight) {
      return;
    }

    const payload = readPayload();
    if (!payload.ssid) {
      setConfigMessage("Bitte WLAN auswählen.", "error");
      return;
    }

    connectInFlight = true;
    setControlsDisabled(true);
    setConfigMessage("");
    openConnectFeedbackLoading("WLAN wird verbunden ...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), connectTimeoutMs);

    try {
      const res = await fetch(`${apiBase}/api/wifi/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = res.ok ? await res.json() : null;
      if (!data || !data.ok) {
        const errorMessage = data && typeof data.message === "string" && data.message.trim()
          ? data.message.trim()
          : "WLAN-Verbindung fehlgeschlagen.";
        setConfigMessage(errorMessage, "error");
        await showConnectFeedbackResult(false, "WLAN verbunden", errorMessage);
        return;
      }

      const connected = !!data.connected;
      const ssid = String(data.ssid || payload.ssid || "").trim();
      state.wifiIssue = "";
      state.wifiIpAddress = "";
      onSetWifiConnected(connected, ssid);
      onBroadcastWifi();
      await showConnectFeedbackResult(true, "WLAN verbunden", "WLAN-Verbindung fehlgeschlagen");
      closeConfigModal(true);
    } catch (_err) {
      setConfigMessage("WLAN-Verbindung fehlgeschlagen.", "error");
      await showConnectFeedbackResult(false, "WLAN verbunden", "WLAN-Verbindung fehlgeschlagen");
    } finally {
      clearTimeout(timeoutId);
      connectInFlight = false;
      setControlsDisabled(false);
      closeConnectFeedback();
    }
  }

  async function disconnectWifi() {
    if (connectInFlight) {
      return;
    }

    connectInFlight = true;
    setControlsDisabled(true);
    setConfigMessage("");
    openConnectFeedbackLoading("WLAN wird getrennt ...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), connectTimeoutMs);

    try {
      const res = await fetch(`${apiBase}/api/wifi/disconnect`, {
        method: "POST",
        signal: controller.signal,
      });
      const data = res.ok ? await res.json() : null;
      if (!data || !data.ok) {
        setConfigMessage("WLAN konnte nicht getrennt werden.", "error");
        await showConnectFeedbackResult(false, "WLAN getrennt", "WLAN konnte nicht getrennt werden.");
        return;
      }

      const ssid = String(data.ssid || state.wifiSsid || "").trim();
      state.wifiIssue = "";
      state.wifiIpAddress = "";
      onSetWifiConnected(false, ssid);
      onBroadcastWifi();
      await showConnectFeedbackResult(true, "WLAN getrennt", "WLAN konnte nicht getrennt werden.");
      closeConfigModal(true);
    } catch (_err) {
      setConfigMessage("WLAN konnte nicht getrennt werden.", "error");
      await showConnectFeedbackResult(false, "WLAN getrennt", "WLAN konnte nicht getrennt werden.");
    } finally {
      clearTimeout(timeoutId);
      connectInFlight = false;
      setControlsDisabled(false);
      closeConnectFeedback();
    }
  }

  function attachEventHandlers() {
    if (listenersBound) return;
    listenersBound = true;

    modalClose.addEventListener("click", () => closeConfigModal());
    configModal.addEventListener("click", (ev) => {
      if (ev.target && ev.target.dataset && ev.target.dataset.close) {
        closeConfigModal();
      }
    });
    passwordInput.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      openPasswordKeyboard();
    });
    scanBtn.addEventListener("click", () => loadNetworks(ssidSelect.value));
    saveBtn.addEventListener("click", saveConfig);
    connectBtn.addEventListener("click", connectWifi);
    disconnectBtn.addEventListener("click", disconnectWifi);
  }

  return {
    applySettings,
    loadNetworks,
    openConfigModal,
    closeConfigModal,
    saveConfig,
    connectWifi,
    disconnectWifi,
    openPasswordKeyboard,
    isConnectInFlight: () => connectInFlight,
    setConfigMessage,
    attachEventHandlers,
  };
}
