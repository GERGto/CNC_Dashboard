// -----------------------------
// Konfiguration
// -----------------------------
const PAGES = [
  { id: "home",        title: "Dashboard",      src: "pages/home.html" },
  { id: "maintenance", title: "Wartung",        src: "pages/maintenance.html" },
  { id: "system",      title: "Systemkonfiguration", src: "pages/system.html" },
];

const API_BASE = "http://localhost:8080";
const AXES_INTERVAL_MS = 250;
const SPINDLE_RUNNING_THRESHOLD = 5;
const RUNTIME_SAVE_INTERVAL_MS = 5000;
const MAINTENANCE_REFRESH_MS = 60000;
const WIFI_CONNECT_TIMEOUT_MS = 15000;
const WIFI_CONNECT_FEEDBACK_MS = 2000;

const state = {
  activePage: "home",
  machineStatus: "IDLE", // IDLE | RUNNING | ERROR
  wifiConnected: true,
  wifiSsid: "",
  lightOn: true,
  lightBrightness: 75,
  fanOn: true,
  fanSpeed: 40,
  fanAuto: false,
  spindleRuntimeSec: 0,
};

const ICONS = {
  wifiOn: "assets/svg/wifi-on.svg",
  wifiOff: "assets/svg/wifi-off.svg",
  bulbOn: "assets/svg/bulb-on.svg",
  bulbOff: "assets/svg/bulb-off.svg",
  fanOn: "assets/svg/fan-on.svg",
  fanOff: "assets/svg/fan-off.svg",
};

const mainEl = document.querySelector(".main");
const clockEl = document.getElementById("clock");
const statusEl = document.getElementById("machineStatus");

const wifiBtn = document.getElementById("wifiBtn");
const lightBtn = document.getElementById("lightBtn");
const fanBtn = document.getElementById("fanBtn");
const shutdownBtn = document.getElementById("shutdownBtn");

const wifiImg = document.getElementById("wifiImg");
const lightImg = document.getElementById("lightImg");
const fanImg = document.getElementById("fanImg");
const shutdownModal = document.getElementById("shutdownModal");
const shutdownCancel = document.getElementById("shutdownCancel");
const shutdownConfirm = document.getElementById("shutdownConfirm");
const lightModal = document.getElementById("lightModal");
const lightClose = document.getElementById("lightClose");
const lightSlider = document.getElementById("lightSlider");
const lightValue = document.getElementById("lightValue");
const fanModal = document.getElementById("fanModal");
const fanClose = document.getElementById("fanClose");
const fanSlider = document.getElementById("fanSlider");
const fanValue = document.getElementById("fanValue");
const fanAutoInput = document.getElementById("fanAuto");
const wifiConfigModal = document.getElementById("wifiConfigModal");
const wifiModalClose = document.getElementById("wifiModalClose");
const wifiSsidSelect = document.getElementById("wifiSsidSelect");
const wifiScanBtn = document.getElementById("wifiScanBtn");
const wifiPasswordInput = document.getElementById("wifiPasswordInput");
const wifiAutoConnectInput = document.getElementById("wifiAutoConnectInput");
const wifiSaveBtn = document.getElementById("wifiSaveBtn");
const wifiConnectBtn = document.getElementById("wifiConnectBtn");
const wifiDisconnectBtn = document.getElementById("wifiDisconnectBtn");
const wifiConfigMsg = document.getElementById("wifiConfigMsg");
const wifiConnectFeedbackModal = document.getElementById("wifiConnectFeedbackModal");
const wifiFeedbackSpinner = document.getElementById("wifiFeedbackSpinner");
const wifiFeedbackSuccess = document.getElementById("wifiFeedbackSuccess");
const wifiFeedbackError = document.getElementById("wifiFeedbackError");
const wifiConnectFeedbackText = document.getElementById("wifiConnectFeedbackText");
const keyboardModal = document.getElementById("keyboardModal");
const keyboardTitle = document.getElementById("keyboardTitle");
const keyboardDisplayInput = document.getElementById("keyboardDisplayInput");
const keyboardKeys = document.getElementById("keyboardKeys");
const keyboardCancelBtn = document.getElementById("keyboardCancelBtn");
const keyboardOkBtn = document.getElementById("keyboardOkBtn");
const graphModal = document.getElementById("graphModal");
const graphClose = document.getElementById("graphClose");
const graphWindowSlider = document.getElementById("graphWindowSlider");
const graphWindowValue = document.getElementById("graphWindowValue");
const maintenanceTaskModal = document.getElementById("maintenanceTaskModal");
const maintenanceTaskTitle = document.getElementById("maintenanceTaskTitle");
const maintenanceDetailInterval = document.getElementById("maintenanceDetailInterval");
const maintenanceDetailEffort = document.getElementById("maintenanceDetailEffort");
const maintenanceDetailStatus = document.getElementById("maintenanceDetailStatus");
const maintenanceDetailLastDone = document.getElementById("maintenanceDetailLastDone");
const maintenanceDetailSinceDone = document.getElementById("maintenanceDetailSinceDone");
const maintenanceDetailDescription = document.getElementById("maintenanceDetailDescription");
const maintenanceDetailGuideInfo = document.getElementById("maintenanceDetailGuideInfo");
const maintenanceTabOverview = document.getElementById("maintenanceTabOverview");
const maintenanceTabGuide = document.getElementById("maintenanceTabGuide");
const maintenancePanelOverview = document.getElementById("maintenancePanelOverview");
const maintenancePanelGuide = document.getElementById("maintenancePanelGuide");
const maintenanceGuideContent = document.getElementById("maintenanceGuideContent");
const maintenanceGuideEmpty = document.getElementById("maintenanceGuideEmpty");
const maintenanceGuideStepMeta = document.getElementById("maintenanceGuideStepMeta");
const maintenanceGuideStepText = document.getElementById("maintenanceGuideStepText");
const maintenanceGuideStepImage = document.getElementById("maintenanceGuideStepImage");
const maintenanceTaskClose = document.getElementById("maintenanceTaskClose");
const maintenanceGuidePrev = document.getElementById("maintenanceGuidePrev");
const maintenanceGuideNext = document.getElementById("maintenanceGuideNext");
const maintenanceTaskDone = document.getElementById("maintenanceTaskDone");
const maintenanceDueDot = document.getElementById("maintenanceDueDot");

const frames = new Map();
let uiSettingsSaveTimer = null;
let runtimeSaveTimer = null;
let spindleRuntimeRawSec = 0;
let lastAxesTimestampMs = null;
let graphWindowSec = 60;
let maintenanceModalTaskId = null;
let maintenanceModalTab = "overview";
let maintenanceModalSteps = [];
let maintenanceModalStepIndex = 0;
let maintenanceTasksCache = [];
let wifiConnectInFlight = false;
let keyboardValue = "";
let keyboardShift = false;
let keyboardContext = null;

const KEYBOARD_ROWS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "ß", "acute", "backspace"],
  ["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ü", "plus", "at"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "hash", "lbracket"],
  ["shift", "y", "x", "c", "v", "b", "n", "m", "comma", "dot", "minus", "rbracket", "clear"],
  ["space"]
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

// -----------------------------
// Uhr
// -----------------------------
function updateClock(){
  const d = new Date();
  const hh = String(d.getHours()).padStart(2,"0");
  const mm = String(d.getMinutes()).padStart(2,"0");
  clockEl.textContent = `${hh}:${mm}`;
}
updateClock();
setInterval(updateClock, 1000);

// -----------------------------
// Status / Icons
// -----------------------------
function setMachineStatus(newStatus){
  const s = String(newStatus || "").toUpperCase();
  state.machineStatus = s || "IDLE";
  statusEl.textContent = state.machineStatus;

  statusEl.style.letterSpacing = (state.machineStatus === "ERROR") ? "0.8px" : "0.2px";

  const statusBar = document.querySelector(".statusbar");
  if (statusBar){
    statusBar.classList.toggle("is-running", state.machineStatus === "RUNNING");
    statusBar.classList.toggle("is-error", state.machineStatus === "ERROR");
  }
}

function setWifiConnected(isConnected, ssid = null){
  state.wifiConnected = !!isConnected;
  if (typeof ssid === "string"){
    state.wifiSsid = ssid.trim();
  }
  wifiImg.src = state.wifiConnected ? ICONS.wifiOn : ICONS.wifiOff;
  wifiBtn.setAttribute("aria-label", state.wifiConnected ? "WLAN verbunden" : "WLAN getrennt");
}

function setLightOn(isOn){
  state.lightOn = !!isOn;
  lightImg.src = state.lightOn ? ICONS.bulbOn : ICONS.bulbOff;
  lightBtn.setAttribute("aria-label", state.lightOn ? "Maschinenlicht an" : "Maschinenlicht aus");
}

function toggleLight(){
  // Hier: echtes Kommando ans Backend (fetch/WebSocket) einbauen
  setLightOn(!state.lightOn);
  broadcastToFrames({ type: "light", on: state.lightOn });
}

function updateLightBrightness(value){
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  state.lightBrightness = v;
  lightSlider.value = String(v);
  lightValue.textContent = `${v}%`;
  broadcastToFrames({ type: "lightBrightness", value: v });
  queueUiSettingsSave();
}

function setFanOn(isOn){
  state.fanOn = !!isOn;
  fanImg.src = state.fanOn ? ICONS.fanOn : ICONS.fanOff;
  fanBtn.setAttribute("aria-label", state.fanOn ? "Lüfter an" : "Lüfter aus");
}

function toggleFan(){
  setFanOn(!state.fanOn);
  broadcastToFrames({ type: "fan", on: state.fanOn });
}

function updateFanSpeed(value){
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  state.fanSpeed = v;
  fanSlider.value = String(v);
  fanValue.textContent = `${v}%`;
  broadcastToFrames({ type: "fanSpeed", value: v });
  queueUiSettingsSave();
}

function setFanAuto(isAuto, persist = false){
  state.fanAuto = !!isAuto;
  fanAutoInput.checked = state.fanAuto;
  broadcastToFrames({ type: "fanAuto", enabled: state.fanAuto });
  if (persist) queueUiSettingsSave();
}

function openLightModal(){
  lightSlider.value = String(state.lightBrightness);
  lightValue.textContent = `${state.lightBrightness}%`;
  lightModal.classList.add("is-open");
  lightModal.setAttribute("aria-hidden", "false");
  lightSlider.focus();
}

function closeLightModal(){
  lightModal.classList.remove("is-open");
  lightModal.setAttribute("aria-hidden", "true");
  lightBtn.focus();
}

function openFanModal(){
  fanSlider.value = String(state.fanSpeed);
  fanValue.textContent = `${state.fanSpeed}%`;
  setFanAuto(state.fanAuto);
  fanModal.classList.add("is-open");
  fanModal.setAttribute("aria-hidden", "false");
  fanSlider.focus();
}

function updateGraphWindowModal(seconds, emitToHome = false){
  const s = Math.max(10, Math.min(120, Number(seconds) || 60));
  graphWindowSec = s;
  graphWindowSlider.value = String(s);
  graphWindowValue.textContent = `${s}s`;
  if (emitToHome){
    postToFrame("home", { type: "setGraphWindow", seconds: s });
  }
}

function openGraphModal(seconds){
  updateGraphWindowModal(seconds ?? graphWindowSec, false);
  graphModal.classList.add("is-open");
  graphModal.setAttribute("aria-hidden", "false");
  graphWindowSlider.focus();
}

function closeGraphModal(){
  graphModal.classList.remove("is-open");
  graphModal.setAttribute("aria-hidden", "true");
}

function isKeyboardOpen(){
  return keyboardModal.classList.contains("is-open");
}

function isKeyboardLetter(key){
  return /^[a-zäöü]$/i.test(String(key || ""));
}

function keyboardKeyLabel(key){
  switch (key){
    case "backspace": return "⌫";
    case "shift": return "Umschalt";
    case "clear": return "Löschen";
    case "space": return "Leerzeichen";
    default: {
      const pair = KEYBOARD_CHAR_PAIRS[key];
      if (pair){
        return keyboardShift ? pair[1] : pair[0];
      }
      if (keyboardShift && isKeyboardLetter(key)){
        return String(key).toLocaleUpperCase("de-DE");
      }
      return String(key);
    }
  }
}

function renderKeyboardDisplay(){
  const masked = !!(keyboardContext && keyboardContext.masked);
  keyboardDisplayInput.value = masked ? "•".repeat(keyboardValue.length) : keyboardValue;
}

function renderKeyboard(){
  keyboardKeys.innerHTML = "";
  for (const row of KEYBOARD_ROWS){
    const rowEl = document.createElement("div");
    rowEl.className = "keyboard__row";
    for (const key of row){
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "keyboard__key";
      btn.dataset.key = key;
      if (key === "space"){
        btn.classList.add("keyboard__key--space");
      } else if (key === "shift" || key === "backspace" || key === "clear"){
        btn.classList.add("keyboard__key--wide");
      }
      if (key === "shift" && keyboardShift){
        btn.classList.add("keyboard__key--active");
      }
      btn.textContent = keyboardKeyLabel(key);
      rowEl.appendChild(btn);
    }
    keyboardKeys.appendChild(rowEl);
  }
}

function closeKeyboardModalImmediate(){
  keyboardModal.classList.remove("is-open");
  keyboardModal.setAttribute("aria-hidden", "true");
  keyboardShift = false;
  keyboardValue = "";
  keyboardContext = null;
}

function finishKeyboardModal(submitted){
  const ctx = keyboardContext;
  const value = keyboardValue;
  closeKeyboardModalImmediate();
  if (!ctx) return;

  if (submitted){
    if (typeof ctx.onSubmit === "function"){
      ctx.onSubmit(value);
    }
  } else if (typeof ctx.onCancel === "function"){
    ctx.onCancel();
  }

  if (ctx.sourceWindow && typeof ctx.sourceWindow.postMessage === "function"){
    ctx.sourceWindow.postMessage({
      type: "keyboardResult",
      requestId: ctx.requestId ?? null,
      value,
      canceled: !submitted,
    }, ctx.responseOrigin || location.origin);
  }

  if (ctx.returnFocusEl && typeof ctx.returnFocusEl.focus === "function"){
    ctx.returnFocusEl.focus();
  }
}

function applyKeyboardCharacter(rawKey){
  let key = String(rawKey || "");
  if (!key) return;

  const pair = KEYBOARD_CHAR_PAIRS[key];
  if (pair){
    key = keyboardShift ? pair[1] : pair[0];
  } else if (isKeyboardLetter(key)){
    key = keyboardShift ? key.toLocaleUpperCase("de-DE") : key.toLocaleLowerCase("de-DE");
  }

  const rawMaxLength = keyboardContext ? keyboardContext.maxLength : null;
  const maxLength = (typeof rawMaxLength === "number" && Number.isFinite(rawMaxLength))
    ? Math.max(1, Math.floor(rawMaxLength))
    : null;
  if (maxLength !== null && keyboardValue.length >= maxLength){
    return;
  }
  keyboardValue += key;
}

function handleKeyboardKey(rawKey){
  const key = String(rawKey || "");
  if (!key) return;

  if (key === "shift"){
    keyboardShift = !keyboardShift;
    renderKeyboard();
    return;
  }
  if (key === "backspace"){
    keyboardValue = keyboardValue.slice(0, -1);
    renderKeyboardDisplay();
    return;
  }
  if (key === "clear"){
    keyboardValue = "";
    renderKeyboardDisplay();
    return;
  }
  if (key === "space"){
    applyKeyboardCharacter(" ");
    if (keyboardShift){
      keyboardShift = false;
      renderKeyboard();
    }
    renderKeyboardDisplay();
    return;
  }

  applyKeyboardCharacter(key);
  if (keyboardShift){
    keyboardShift = false;
    renderKeyboard();
  }
  renderKeyboardDisplay();
}

function openKeyboardModal(options = {}){
  if (isKeyboardOpen()){
    closeKeyboardModalImmediate();
  }

  const title = typeof options.title === "string" && options.title.trim() ? options.title.trim() : "Eingabe";
  const placeholder = typeof options.placeholder === "string" ? options.placeholder : "";
  keyboardContext = {
    masked: !!options.masked,
    maxLength: options.maxLength,
    onSubmit: options.onSubmit,
    onCancel: options.onCancel,
    sourceWindow: options.sourceWindow || null,
    requestId: options.requestId,
    responseOrigin: options.responseOrigin || location.origin,
    returnFocusEl: options.returnFocusEl || null,
  };
  keyboardTitle.textContent = title;
  keyboardDisplayInput.placeholder = placeholder;
  keyboardValue = String(options.value || "");
  keyboardShift = false;
  renderKeyboard();
  renderKeyboardDisplay();

  keyboardModal.classList.add("is-open");
  keyboardModal.setAttribute("aria-hidden", "false");
  keyboardOkBtn.focus();
}

function openWifiPasswordKeyboard(){
  if (wifiConnectInFlight || wifiPasswordInput.disabled){
    return;
  }
  openKeyboardModal({
    title: "WLAN-Passwort",
    placeholder: "Passwort eingeben",
    value: wifiPasswordInput.value,
    onSubmit: (value) => {
      wifiPasswordInput.value = value;
    },
    returnFocusEl: wifiPasswordInput,
  });
}

function setWifiConfigMessage(message, type = "info"){
  wifiConfigMsg.textContent = String(message || "");
  wifiConfigMsg.classList.toggle("is-error", type === "error");
  wifiConfigMsg.classList.toggle("is-ok", type === "ok");
}

function waitFor(ms){
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setWifiConfigControlsDisabled(disabled){
  const isDisabled = !!disabled;
  wifiSsidSelect.disabled = isDisabled;
  wifiScanBtn.disabled = isDisabled;
  wifiPasswordInput.disabled = isDisabled;
  wifiAutoConnectInput.disabled = isDisabled;
  wifiSaveBtn.disabled = isDisabled;
  wifiConnectBtn.disabled = isDisabled;
  wifiDisconnectBtn.disabled = isDisabled;
  wifiModalClose.disabled = isDisabled;
  if (isDisabled && isKeyboardOpen()){
    closeKeyboardModalImmediate();
  }
}

function openWifiConnectFeedbackLoading(loadingText = "WLAN wird verbunden ..."){
  wifiConnectFeedbackModal.classList.add("is-open");
  wifiConnectFeedbackModal.setAttribute("aria-hidden", "false");
  wifiFeedbackSpinner.hidden = false;
  wifiFeedbackSuccess.hidden = true;
  wifiFeedbackError.hidden = true;
  wifiConnectFeedbackText.textContent = String(loadingText || "");
}

function closeWifiConnectFeedback(){
  wifiConnectFeedbackModal.classList.remove("is-open");
  wifiConnectFeedbackModal.setAttribute("aria-hidden", "true");
}

async function showWifiConnectFeedbackResult(ok, successText = "WLAN verbunden", errorText = "WLAN-Verbindung fehlgeschlagen"){
  wifiFeedbackSpinner.hidden = true;
  wifiFeedbackSuccess.hidden = !ok;
  wifiFeedbackError.hidden = ok;
  wifiConnectFeedbackText.textContent = ok ? String(successText || "") : String(errorText || "");
  await waitFor(WIFI_CONNECT_FEEDBACK_MS);
  closeWifiConnectFeedback();
}

function readWifiPayload(){
  return {
    ssid: String(wifiSsidSelect.value || "").trim(),
    password: String(wifiPasswordInput.value || ""),
    autoConnect: !!wifiAutoConnectInput.checked,
  };
}

function setWifiSsidOptions(networks, preferredSsid = ""){
  const list = Array.isArray(networks) ? networks : [];
  const selectedBefore = String(wifiSsidSelect.value || "").trim();
  const preferred = String(preferredSsid || "").trim();
  const merged = [];

  for (const raw of list){
    const ssid = String(raw || "").trim();
    if (!ssid || merged.includes(ssid)) continue;
    merged.push(ssid);
  }
  if (preferred && !merged.includes(preferred)){
    merged.push(preferred);
  }

  wifiSsidSelect.innerHTML = "";
  if (merged.length === 0){
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "Keine Netzwerke gefunden";
    wifiSsidSelect.appendChild(emptyOption);
    wifiSsidSelect.value = "";
    return;
  }

  for (const ssid of merged){
    const option = document.createElement("option");
    option.value = ssid;
    option.textContent = ssid;
    wifiSsidSelect.appendChild(option);
  }

  if (preferred && merged.includes(preferred)){
    wifiSsidSelect.value = preferred;
  } else if (selectedBefore && merged.includes(selectedBefore)){
    wifiSsidSelect.value = selectedBefore;
  } else {
    wifiSsidSelect.value = merged[0];
  }
}

function loadWifiNetworks(preferredSsid = ""){
  fetch(`${API_BASE}/api/wifi/networks`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      const networks = data && Array.isArray(data.networks) ? data.networks : [];
      setWifiSsidOptions(networks, preferredSsid);
    })
    .catch(() => {
      setWifiSsidOptions([], preferredSsid);
      setWifiConfigMessage("WLAN-Netzwerke konnten nicht geladen werden.", "error");
    });
}

function openWifiConfigModal(){
  wifiConfigModal.classList.add("is-open");
  wifiConfigModal.setAttribute("aria-hidden", "false");
  setWifiConfigMessage("");
  fetch(`${API_BASE}/api/settings`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      const currentSsid = typeof data.wifiSsid === "string" ? data.wifiSsid : state.wifiSsid;
      if (typeof data.wifiPassword === "string"){
        wifiPasswordInput.value = data.wifiPassword;
      }
      if (typeof data.wifiAutoConnect === "boolean"){
        wifiAutoConnectInput.checked = data.wifiAutoConnect;
      } else if (typeof data.wifiAutoConnect === "number" && (data.wifiAutoConnect === 0 || data.wifiAutoConnect === 1)){
        wifiAutoConnectInput.checked = Boolean(data.wifiAutoConnect);
      }
      if (typeof data.wifiConnected === "boolean"){
        setWifiConnected(data.wifiConnected, currentSsid);
      } else if (typeof data.wifiConnected === "number" && (data.wifiConnected === 0 || data.wifiConnected === 1)){
        setWifiConnected(Boolean(data.wifiConnected), currentSsid);
      } else {
        setWifiConnected(state.wifiConnected, currentSsid);
      }
      loadWifiNetworks(currentSsid);
      broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
    })
    .catch(() => {
      loadWifiNetworks(state.wifiSsid);
      setWifiConfigMessage("WLAN-Einstellungen konnten nicht geladen werden.", "error");
    })
    .finally(() => {
      wifiSsidSelect.focus();
    });
}

function closeWifiConfigModal(force = false){
  if (wifiConnectInFlight && !force){
    return;
  }
  if (isKeyboardOpen()){
    closeKeyboardModalImmediate();
  }
  wifiConfigModal.classList.remove("is-open");
  wifiConfigModal.setAttribute("aria-hidden", "true");
  wifiBtn.focus();
}

function saveWifiConfig(){
  const payload = readWifiPayload();
  fetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      wifiSsid: payload.ssid,
      wifiPassword: payload.password,
      wifiAutoConnect: payload.autoConnect,
    }),
  })
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object"){
        setWifiConfigMessage("WLAN-Einstellungen konnten nicht gespeichert werden.", "error");
        return;
      }
      state.wifiSsid = payload.ssid;
      setWifiConfigMessage("WLAN-Einstellungen gespeichert.", "ok");
      broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
    })
    .catch(() => {
      setWifiConfigMessage("WLAN-Einstellungen konnten nicht gespeichert werden.", "error");
    });
}

async function connectWifi(){
  if (wifiConnectInFlight){
    return;
  }
  const payload = readWifiPayload();
  if (!payload.ssid){
    setWifiConfigMessage("Bitte WLAN auswählen.", "error");
    return;
  }

  wifiConnectInFlight = true;
  setWifiConfigControlsDisabled(true);
  setWifiConfigMessage("");
  openWifiConnectFeedbackLoading("WLAN wird verbunden ...");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), WIFI_CONNECT_TIMEOUT_MS);

  try{
    const res = await fetch(`${API_BASE}/api/wifi/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = res.ok ? await res.json() : null;
    if (!data || !data.ok){
      setWifiConfigMessage("WLAN-Verbindung fehlgeschlagen.", "error");
      await showWifiConnectFeedbackResult(false, "WLAN verbunden", "WLAN-Verbindung fehlgeschlagen");
      return;
    }

    const connected = !!data.connected;
    const ssid = String(data.ssid || payload.ssid || "").trim();
    setWifiConnected(connected, ssid);
    broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
    await showWifiConnectFeedbackResult(true, "WLAN verbunden", "WLAN-Verbindung fehlgeschlagen");
    closeWifiConfigModal(true);
  } catch (_err){
    setWifiConfigMessage("WLAN-Verbindung fehlgeschlagen.", "error");
    await showWifiConnectFeedbackResult(false, "WLAN verbunden", "WLAN-Verbindung fehlgeschlagen");
  } finally {
    clearTimeout(timeoutId);
    wifiConnectInFlight = false;
    setWifiConfigControlsDisabled(false);
    closeWifiConnectFeedback();
  }
}

async function disconnectWifi(){
  if (wifiConnectInFlight){
    return;
  }

  wifiConnectInFlight = true;
  setWifiConfigControlsDisabled(true);
  setWifiConfigMessage("");
  openWifiConnectFeedbackLoading("WLAN wird getrennt ...");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), WIFI_CONNECT_TIMEOUT_MS);

  try{
    const res = await fetch(`${API_BASE}/api/wifi/disconnect`, {
      method: "POST",
      signal: controller.signal,
    });
    const data = res.ok ? await res.json() : null;
    if (!data || !data.ok){
      setWifiConfigMessage("WLAN konnte nicht getrennt werden.", "error");
      await showWifiConnectFeedbackResult(false, "WLAN getrennt", "WLAN konnte nicht getrennt werden.");
      return;
    }
    const ssid = String(data.ssid || state.wifiSsid || "").trim();
    setWifiConnected(false, ssid);
    broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
    await showWifiConnectFeedbackResult(true, "WLAN getrennt", "WLAN konnte nicht getrennt werden.");
    closeWifiConfigModal(true);
  } catch (_err){
    setWifiConfigMessage("WLAN konnte nicht getrennt werden.", "error");
    await showWifiConnectFeedbackResult(false, "WLAN getrennt", "WLAN konnte nicht getrennt werden.");
  } finally {
    clearTimeout(timeoutId);
    wifiConnectInFlight = false;
    setWifiConfigControlsDisabled(false);
    closeWifiConnectFeedback();
  }
}

function toNumber(value, fallback = 0){
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function addMonths(date, months){
  const d = new Date(date.getTime());
  d.setMonth(d.getMonth() + months);
  return d;
}

function normalizeMaintenanceTask(task){
  if (!task || typeof task !== "object") return null;
  const id = String(task.id || "").trim();
  if (!id) return null;

  const rawIntervalType = String(task.intervalType || "").trim();
  const rawIntervalValue = task.intervalValue;
  let intervalType = "runtimeHours";
  if (rawIntervalType === "calendarMonths"){
    intervalType = "calendarMonths";
  }
  if (rawIntervalType === "none" || (typeof rawIntervalValue === "string" && rawIntervalValue.trim() === "-")){
    intervalType = "none";
  }

  return {
    id,
    intervalType,
    intervalValue: intervalType === "none"
      ? "-"
      : Math.max(1, Math.floor(toNumber(rawIntervalValue, 1))),
    lastCompletedAt: task.lastCompletedAt ? String(task.lastCompletedAt) : null,
    spindleRuntimeSecAtCompletion: Math.max(0, Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0))),
  };
}

function hasAutomaticInterval(task){
  if (!task || typeof task !== "object") return false;
  const intervalType = String(task.intervalType || "").trim();
  const intervalValue = task.intervalValue;
  if (intervalType === "none") return false;
  if (typeof intervalValue === "string" && intervalValue.trim() === "-") return false;
  return intervalType === "runtimeHours" || intervalType === "calendarMonths";
}

function isMaintenanceTaskDue(task){
  if (!task || typeof task !== "object") return false;
  if (!hasAutomaticInterval(task)) return false;
  if (!task.lastCompletedAt) return true;

  const intervalType = String(task.intervalType || "");
  const intervalValue = Math.max(1, Math.floor(toNumber(task.intervalValue, 1)));

  if (intervalType === "runtimeHours"){
    const lastSec = Math.max(0, Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0)));
    const elapsedSec = Math.max(0, state.spindleRuntimeSec - lastSec);
    return elapsedSec >= (intervalValue * 3600);
  }

  if (intervalType === "calendarMonths"){
    const lastDone = new Date(task.lastCompletedAt);
    if (Number.isNaN(lastDone.getTime())) return true;
    return Date.now() >= addMonths(lastDone, intervalValue).getTime();
  }

  return false;
}

function updateMaintenanceDueIndicator(){
  if (!maintenanceDueDot) return;
  const hasDueTask = maintenanceTasksCache.some((task) => isMaintenanceTaskDue(task));
  maintenanceDueDot.hidden = !hasDueTask;
}

function setMaintenanceTasks(tasks){
  const list = Array.isArray(tasks) ? tasks : [];
  maintenanceTasksCache = list.map(normalizeMaintenanceTask).filter(Boolean);
  updateMaintenanceDueIndicator();
}

function upsertMaintenanceTask(task){
  const normalized = normalizeMaintenanceTask(task);
  if (!normalized) return;
  const idx = maintenanceTasksCache.findIndex((item) => item.id === normalized.id);
  if (idx >= 0){
    maintenanceTasksCache[idx] = normalized;
  } else {
    maintenanceTasksCache.push(normalized);
  }
  updateMaintenanceDueIndicator();
}

function loadMaintenanceTasks(){
  fetch(`${API_BASE}/api/maintenance/tasks`)
    .then((res) => res.ok ? res.json() : null)
    .then((payload) => {
      const tasks = payload && Array.isArray(payload.tasks) ? payload.tasks : [];
      setMaintenanceTasks(tasks);
    })
    .catch(() => {});
}

function normalizeMaintenanceSteps(rawSteps){
  if (!Array.isArray(rawSteps)){
    return [];
  }
  const steps = [];
  for (const step of rawSteps){
    if (!step || typeof step !== "object") continue;
    const instruction = String(step.instruction || step.text || step.title || "").trim();
    const image = String(step.image || "").trim();
    const imageAlt = String(step.imageAlt || "Arbeitsschritt").trim();
    if (!instruction) continue;
    steps.push({ instruction, image, imageAlt });
  }
  return steps;
}

function renderMaintenanceGuideStep(){
  const count = maintenanceModalSteps.length;
  if (count === 0){
    maintenanceGuideContent.hidden = true;
    maintenanceGuideEmpty.hidden = false;
    maintenanceGuidePrev.disabled = true;
    maintenanceGuideNext.disabled = true;
    return;
  }

  maintenanceGuideContent.hidden = false;
  maintenanceGuideEmpty.hidden = true;

  if (maintenanceModalStepIndex < 0){
    maintenanceModalStepIndex = 0;
  }
  if (maintenanceModalStepIndex > count - 1){
    maintenanceModalStepIndex = count - 1;
  }

  const step = maintenanceModalSteps[maintenanceModalStepIndex];
  maintenanceGuideStepMeta.textContent = `Schritt ${maintenanceModalStepIndex + 1} / ${count}`;
  maintenanceGuideStepText.textContent = step.instruction || "-";

  if (step.image){
    maintenanceGuideStepImage.src = step.image;
    maintenanceGuideStepImage.alt = step.imageAlt || "Arbeitsschritt";
    maintenanceGuideStepImage.hidden = false;
  } else {
    maintenanceGuideStepImage.src = "";
    maintenanceGuideStepImage.alt = "";
    maintenanceGuideStepImage.hidden = true;
  }

  maintenanceGuidePrev.disabled = maintenanceModalStepIndex <= 0;
  maintenanceGuideNext.disabled = maintenanceModalStepIndex >= (count - 1);
}

function setMaintenanceTab(tab){
  maintenanceModalTab = (tab === "guide") ? "guide" : "overview";
  const isGuide = maintenanceModalTab === "guide";

  maintenanceTabOverview.classList.toggle("is-active", !isGuide);
  maintenanceTabOverview.setAttribute("aria-selected", isGuide ? "false" : "true");
  maintenanceTabOverview.setAttribute("tabindex", isGuide ? "-1" : "0");

  maintenanceTabGuide.classList.toggle("is-active", isGuide);
  maintenanceTabGuide.setAttribute("aria-selected", isGuide ? "true" : "false");
  maintenanceTabGuide.setAttribute("tabindex", isGuide ? "0" : "-1");

  maintenancePanelOverview.classList.toggle("is-active", !isGuide);
  maintenancePanelOverview.setAttribute("aria-hidden", isGuide ? "true" : "false");

  maintenancePanelGuide.classList.toggle("is-active", isGuide);
  maintenancePanelGuide.setAttribute("aria-hidden", isGuide ? "false" : "true");

  maintenanceGuidePrev.hidden = !isGuide;
  maintenanceGuideNext.hidden = !isGuide;

  if (isGuide){
    renderMaintenanceGuideStep();
    if (!maintenanceGuideNext.disabled){
      maintenanceGuideNext.focus();
    } else if (!maintenanceGuidePrev.disabled){
      maintenanceGuidePrev.focus();
    } else {
      maintenanceTaskDone.focus();
    }
    return;
  }
  maintenanceTaskDone.focus();
}

function openMaintenanceTaskModal(payload){
  const data = (payload && typeof payload === "object") ? payload : {};
  maintenanceModalTaskId = data.taskId ? String(data.taskId) : null;
  maintenanceTaskTitle.textContent = String(data.title || "Wartungsaufgabe");
  maintenanceDetailInterval.textContent = String(data.intervalText || "-");
  maintenanceDetailEffort.textContent = String(data.effortText || "-");
  maintenanceDetailStatus.textContent = String(data.statusText || "-");
  maintenanceDetailStatus.classList.toggle("is-due", !!data.due);
  maintenanceDetailLastDone.textContent = String(data.lastDoneText || "-");
  maintenanceDetailSinceDone.textContent = String(data.sinceDoneText || "-");
  maintenanceDetailDescription.textContent = String(data.description || "-");
  maintenanceModalSteps = normalizeMaintenanceSteps(data.steps);
  maintenanceModalStepIndex = 0;
  maintenanceDetailGuideInfo.textContent = maintenanceModalSteps.length > 0
    ? `${maintenanceModalSteps.length} Schritte`
    : "Keine Anleitung hinterlegt";

  maintenanceTaskDone.disabled = !maintenanceModalTaskId;
  maintenanceTaskModal.classList.add("is-open");
  maintenanceTaskModal.setAttribute("aria-hidden", "false");
  setMaintenanceTab("overview");
}

function closeMaintenanceTaskModal(){
  maintenanceModalTaskId = null;
  maintenanceModalSteps = [];
  maintenanceModalStepIndex = 0;
  maintenanceModalTab = "overview";
  maintenanceTaskModal.classList.remove("is-open");
  maintenanceTaskModal.setAttribute("aria-hidden", "true");
}

function completeMaintenanceTask(){
  if (!maintenanceModalTaskId) return;
  maintenanceTaskDone.disabled = true;
  fetch(`${API_BASE}/api/maintenance/tasks/${encodeURIComponent(maintenanceModalTaskId)}/complete`, { method: "POST" })
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || !data.task) return;
      upsertMaintenanceTask(data.task);
      broadcastToFrames({ type: "maintenanceTaskCompleted", task: data.task });
      closeMaintenanceTaskModal();
    })
    .catch(() => {})
    .finally(() => {
      maintenanceTaskDone.disabled = false;
    });
}

function queueUiSettingsSave(){
  if (uiSettingsSaveTimer) clearTimeout(uiSettingsSaveTimer);
  uiSettingsSaveTimer = setTimeout(() => {
    persistUiSettings();
  }, 250);
}

function queueRuntimeSave(){
  if (runtimeSaveTimer) return;
  runtimeSaveTimer = setTimeout(() => {
    runtimeSaveTimer = null;
    persistUiSettings();
  }, RUNTIME_SAVE_INTERVAL_MS);
}

function persistUiSettings(){
  fetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lightBrightness: state.lightBrightness,
      fanSpeed: state.fanSpeed,
      fanAuto: state.fanAuto,
      spindleRuntimeSec: state.spindleRuntimeSec
    })
  }).catch(() => {});
}

function setSpindleRuntimeSec(value, persist = false){
  const v = Math.max(0, Math.floor(Number(value) || 0));
  spindleRuntimeRawSec = v;
  state.spindleRuntimeSec = v;
  broadcastToFrames({ type: "spindleRuntime", seconds: v });
  updateMaintenanceDueIndicator();
  if (persist){
    queueRuntimeSave();
  }
}

function updateSpindleRuntimeFromAxes(data){
  const nowMs = Math.max(0, Number(data && data.timestamp) || Date.now());
  if (lastAxesTimestampMs === null){
    lastAxesTimestampMs = nowMs;
    return;
  }

  let deltaSec = (nowMs - lastAxesTimestampMs) / 1000;
  lastAxesTimestampMs = nowMs;
  if (!Number.isFinite(deltaSec) || deltaSec <= 0){
    return;
  }
  if (deltaSec > 10){
    deltaSec = 0;
  }
  if (deltaSec <= 0){
    return;
  }

  const axes = (data && typeof data.axes === "object") ? data.axes : null;
  const spindleLoad = Number(axes && axes.spindle);
  if (!Number.isFinite(spindleLoad) || spindleLoad <= SPINDLE_RUNNING_THRESHOLD){
    return;
  }

  spindleRuntimeRawSec += deltaSec;
  const rounded = Math.floor(spindleRuntimeRawSec);
  if (rounded !== state.spindleRuntimeSec){
    state.spindleRuntimeSec = rounded;
    broadcastToFrames({ type: "spindleRuntime", seconds: rounded });
    updateMaintenanceDueIndicator();
    queueRuntimeSave();
  }
}

function loadUiSettings(){
  fetch(`${API_BASE}/api/settings`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      const wifiSsid = typeof data.wifiSsid === "string" ? data.wifiSsid : state.wifiSsid;
      state.wifiSsid = String(wifiSsid || "").trim();
      if (typeof data.wifiConnected === "boolean"){
        setWifiConnected(data.wifiConnected, wifiSsid);
        broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
      } else if (typeof data.wifiConnected === "number" && (data.wifiConnected === 0 || data.wifiConnected === 1)){
        setWifiConnected(Boolean(data.wifiConnected), wifiSsid);
        broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
      }
      if (typeof data.lightBrightness === "number"){
        const v = Math.max(0, Math.min(100, data.lightBrightness));
        state.lightBrightness = v;
        lightSlider.value = String(v);
        lightValue.textContent = `${v}%`;
        broadcastToFrames({ type: "lightBrightness", value: v });
      }
      if (typeof data.fanSpeed === "number"){
        const v = Math.max(0, Math.min(100, data.fanSpeed));
        state.fanSpeed = v;
        fanSlider.value = String(v);
        fanValue.textContent = `${v}%`;
        broadcastToFrames({ type: "fanSpeed", value: v });
      }
      if (typeof data.fanAuto === "boolean"){
        setFanAuto(data.fanAuto);
      } else if (typeof data.fanAuto === "number" && (data.fanAuto === 0 || data.fanAuto === 1)){
        setFanAuto(Boolean(data.fanAuto));
      }
      if (typeof data.spindleRuntimeSec === "number"){
        setSpindleRuntimeSec(data.spindleRuntimeSec);
      }
      if (typeof data.graphWindowSec === "number"){
        updateGraphWindowModal(data.graphWindowSec, false);
      }
    })
    .catch(() => {});
}

function closeFanModal(){
  fanModal.classList.remove("is-open");
  fanModal.setAttribute("aria-hidden", "true");
  fanBtn.focus();
}

function openShutdownModal(){
  shutdownModal.classList.add("is-open");
  shutdownModal.setAttribute("aria-hidden", "false");
  shutdownConfirm.focus();
}

function closeShutdownModal(){
  shutdownModal.classList.remove("is-open");
  shutdownModal.setAttribute("aria-hidden", "true");
  shutdownBtn.focus();
}

function confirmShutdown(){
  fetch(`${API_BASE}/api/shutdown`, { method: "POST" }).catch(() => {});
  closeShutdownModal();
}

let lightPressTimer = null;
let lightLongPress = false;
let fanPressTimer = null;
let fanLongPress = false;
let wifiPressTimer = null;
let wifiLongPress = false;

wifiBtn.addEventListener("pointerdown", (ev) => {
  if (ev.pointerType === "mouse" && ev.button !== 0) return;
  wifiLongPress = false;
  wifiPressTimer = setTimeout(() => {
    wifiLongPress = true;
    openSystemWifiConfig();
  }, 600);
});

const clearWifiPress = () => {
  if (wifiPressTimer) clearTimeout(wifiPressTimer);
  wifiPressTimer = null;
};

wifiBtn.addEventListener("pointerup", clearWifiPress);
wifiBtn.addEventListener("pointerleave", clearWifiPress);
wifiBtn.addEventListener("pointercancel", clearWifiPress);
wifiBtn.addEventListener("click", () => {
  if (wifiLongPress){
    wifiLongPress = false;
  }
});

lightBtn.addEventListener("pointerdown", (ev) => {
  if (ev.pointerType === "mouse" && ev.button !== 0) return;
  lightLongPress = false;
  lightPressTimer = setTimeout(() => {
    lightLongPress = true;
    openLightModal();
  }, 600);
});

const clearLightPress = () => {
  if (lightPressTimer) clearTimeout(lightPressTimer);
  lightPressTimer = null;
};

lightBtn.addEventListener("pointerup", clearLightPress);
lightBtn.addEventListener("pointerleave", clearLightPress);
lightBtn.addEventListener("pointercancel", clearLightPress);
lightBtn.addEventListener("click", () => {
  if (lightLongPress){
    lightLongPress = false;
    return;
  }
  toggleLight();
});

fanBtn.addEventListener("pointerdown", (ev) => {
  if (ev.pointerType === "mouse" && ev.button !== 0) return;
  fanLongPress = false;
  fanPressTimer = setTimeout(() => {
    fanLongPress = true;
    openFanModal();
  }, 600);
});

const clearFanPress = () => {
  if (fanPressTimer) clearTimeout(fanPressTimer);
  fanPressTimer = null;
};

fanBtn.addEventListener("pointerup", clearFanPress);
fanBtn.addEventListener("pointerleave", clearFanPress);
fanBtn.addEventListener("pointercancel", clearFanPress);
fanBtn.addEventListener("click", () => {
  if (fanLongPress){
    fanLongPress = false;
    return;
  }
  toggleFan();
});
shutdownBtn.addEventListener("click", openShutdownModal);
shutdownCancel.addEventListener("click", closeShutdownModal);
shutdownConfirm.addEventListener("click", confirmShutdown);
shutdownModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeShutdownModal();
  }
});
lightClose.addEventListener("click", closeLightModal);
lightModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeLightModal();
  }
});
lightSlider.addEventListener("input", (ev) => updateLightBrightness(ev.target.value));
fanClose.addEventListener("click", closeFanModal);
fanModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeFanModal();
  }
});
fanSlider.addEventListener("input", (ev) => updateFanSpeed(ev.target.value));
fanAutoInput.addEventListener("change", (ev) => setFanAuto(ev.target.checked, true));
wifiModalClose.addEventListener("click", closeWifiConfigModal);
wifiConfigModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeWifiConfigModal();
  }
});
wifiPasswordInput.addEventListener("pointerdown", (ev) => {
  ev.preventDefault();
  openWifiPasswordKeyboard();
});
wifiScanBtn.addEventListener("click", () => loadWifiNetworks(wifiSsidSelect.value));
wifiSaveBtn.addEventListener("click", saveWifiConfig);
wifiConnectBtn.addEventListener("click", connectWifi);
wifiDisconnectBtn.addEventListener("click", disconnectWifi);
keyboardCancelBtn.addEventListener("click", () => finishKeyboardModal(false));
keyboardOkBtn.addEventListener("click", () => finishKeyboardModal(true));
keyboardModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    finishKeyboardModal(false);
  }
});
keyboardKeys.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".keyboard__key");
  if (!btn) return;
  handleKeyboardKey(btn.dataset.key);
});
graphClose.addEventListener("click", closeGraphModal);
graphModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeGraphModal();
  }
});
graphWindowSlider.addEventListener("input", (ev) => updateGraphWindowModal(ev.target.value, true));
maintenanceTaskClose.addEventListener("click", closeMaintenanceTaskModal);
maintenanceTabOverview.addEventListener("click", () => setMaintenanceTab("overview"));
maintenanceTabGuide.addEventListener("click", () => setMaintenanceTab("guide"));
maintenanceGuidePrev.addEventListener("click", () => {
  if (maintenanceModalStepIndex <= 0) return;
  maintenanceModalStepIndex -= 1;
  renderMaintenanceGuideStep();
});
maintenanceGuideNext.addEventListener("click", () => {
  if (maintenanceModalStepIndex >= maintenanceModalSteps.length - 1) return;
  maintenanceModalStepIndex += 1;
  renderMaintenanceGuideStep();
});
maintenanceTaskDone.addEventListener("click", completeMaintenanceTask);
maintenanceTaskModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeMaintenanceTaskModal();
  }
});
window.addEventListener("keydown", (ev) => {
  if (isKeyboardOpen()){
    if (ev.key === "Escape"){
      finishKeyboardModal(false);
      return;
    }
    if (ev.key === "Enter"){
      finishKeyboardModal(true);
      return;
    }
    if (ev.key === "Backspace"){
      ev.preventDefault();
      handleKeyboardKey("backspace");
      return;
    }
    if (ev.key === " "){
      ev.preventDefault();
      handleKeyboardKey("space");
      return;
    }
    if (ev.key.length === 1){
      handleKeyboardKey(ev.key);
      return;
    }
  }

  if (ev.key === "Escape" && shutdownModal.classList.contains("is-open")){
    closeShutdownModal();
  }
  if (ev.key === "Escape" && lightModal.classList.contains("is-open")){
    closeLightModal();
  }
  if (ev.key === "Escape" && fanModal.classList.contains("is-open")){
    closeFanModal();
  }
  if (ev.key === "Escape" && wifiConfigModal.classList.contains("is-open")){
    closeWifiConfigModal();
  }
  if (ev.key === "Escape" && graphModal.classList.contains("is-open")){
    closeGraphModal();
  }
  if (ev.key === "Escape" && maintenanceTaskModal.classList.contains("is-open")){
    closeMaintenanceTaskModal();
  }
  if (maintenanceTaskModal.classList.contains("is-open") && maintenanceModalTab === "guide"){
    if (ev.key === "ArrowLeft" && !maintenanceGuidePrev.disabled){
      maintenanceGuidePrev.click();
    }
    if (ev.key === "ArrowRight" && !maintenanceGuideNext.disabled){
      maintenanceGuideNext.click();
    }
  }
});

// Initial
setMachineStatus(state.machineStatus);
setWifiConnected(state.wifiConnected);
setLightOn(state.lightOn);
setFanOn(state.fanOn);
setFanAuto(state.fanAuto);

// -----------------------------
// iFrames erstellen & vorladen
// -----------------------------
function createFrames(){
  for (const p of PAGES){
    const f = document.createElement("iframe");
    f.className = "viewframe";
    f.dataset.page = p.id;
    f.src = p.src;
    f.loading = "eager"; // alles beim Start laden
    f.setAttribute("title", p.title);
    mainEl.appendChild(f);
    frames.set(p.id, f);
  }
}

function showPage(pageId){
  if (!frames.has(pageId)) return;
  state.activePage = pageId;

  for (const [id, frame] of frames.entries()){
    frame.classList.toggle("active", id === pageId);
  }

  for (const btn of document.querySelectorAll(".navbtn")){
    btn.classList.toggle("active", btn.dataset.page === pageId);
  }

  postToFrame(pageId, { type: "pageShown", id: pageId });
}

function openSystemWifiConfig(){
  const message = { type: "openWifiConfig", openModal: false };
  showPage("system");
  openWifiConfigModal();
  postToFrame("system", message);
  setTimeout(() => postToFrame("system", message), 150);
  setTimeout(() => postToFrame("system", message), 500);
}

document.querySelector(".nav").addEventListener("click", (ev) => {
  const btn = ev.target.closest(".navbtn");
  if (!btn) return;
  showPage(btn.dataset.page);
});

createFrames();
showPage(state.activePage);

// -----------------------------
// Kommunikation Shell <-> iFrames (optional)
// -----------------------------
function postToFrame(pageId, message){
  const f = frames.get(pageId);
  if (!f || !f.contentWindow) return;
  f.contentWindow.postMessage(message, location.origin);
}

function broadcastToFrames(message){
  for (const id of frames.keys()){
    postToFrame(id, message);
  }
}

function startAxesStream(){
  if (!("EventSource" in window)) return;

  const connect = () => {
    const es = new EventSource(`${API_BASE}/api/axes/stream?intervalMs=${AXES_INTERVAL_MS}`);
    es.addEventListener("axes", (ev) => {
      try{
        const data = JSON.parse(ev.data || "{}");
        updateSpindleRuntimeFromAxes(data);
        broadcastToFrames({ type: "axes", ...data });
      }catch (_err){
        // Ignore malformed payloads in dev.
      }
    });
    es.onerror = () => {
      es.close();
      setTimeout(connect, 1000);
    };
  };

  connect();
}

window.addEventListener("message", (ev) => {
  if (ev.origin !== location.origin) return;
  const msg = ev.data || {};
  if (typeof msg !== "object") return;

  switch (msg.type){
    case "setStatus":  setMachineStatus(msg.status); break;
    case "setWifi":
      setWifiConnected(!!msg.connected, typeof msg.ssid === "string" ? msg.ssid : state.wifiSsid);
      broadcastToFrames({ type: "wifi", connected: state.wifiConnected, ssid: state.wifiSsid });
      break;
    case "openWifiConfigModal": openWifiConfigModal(); break;
    case "openKeyboard":
      openKeyboardModal({
        title: typeof msg.title === "string" ? msg.title : "Eingabe",
        placeholder: typeof msg.placeholder === "string" ? msg.placeholder : "",
        value: typeof msg.value === "string" ? msg.value : "",
        masked: !!msg.masked,
        maxLength: Number.isFinite(Number(msg.maxLength)) ? Math.max(1, Math.floor(Number(msg.maxLength))) : null,
        sourceWindow: ev.source && typeof ev.source.postMessage === "function" ? ev.source : null,
        requestId: msg.requestId ?? null,
        responseOrigin: ev.origin,
      });
      break;
    case "setLight":   setLightOn(!!msg.on); break;
    case "toggleLight":toggleLight(); break;
    case "setFan":     setFanOn(!!msg.on); break;
    case "toggleFan":  toggleFan(); break;
    case "setFanSpeed":updateFanSpeed(msg.value); break;
    case "setFanAuto": setFanAuto(!!msg.enabled); break;
    case "setSpindleRuntime": setSpindleRuntimeSec(msg.seconds, true); break;
    case "openGraphSettingsModal": openGraphModal(msg.seconds); break;
    case "openMaintenanceTaskModal": openMaintenanceTaskModal(msg); break;
    case "navigate":   if (typeof msg.page === "string") showPage(msg.page); break;
    default: break;
  }
});

// initiale Zustände an alle Frames
broadcastToFrames({
  type: "init",
  machineStatus: state.machineStatus,
  wifiConnected: state.wifiConnected,
  wifiSsid: state.wifiSsid,
  lightOn: state.lightOn,
  fanOn: state.fanOn,
  fanSpeed: state.fanSpeed,
  fanAuto: state.fanAuto,
  spindleRuntimeSec: state.spindleRuntimeSec
});

loadUiSettings();
loadMaintenanceTasks();
setInterval(loadMaintenanceTasks, MAINTENANCE_REFRESH_MS);
startAxesStream();
