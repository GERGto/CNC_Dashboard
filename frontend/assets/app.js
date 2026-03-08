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

const state = {
  activePage: "home",
  machineStatus: "IDLE", // IDLE | RUNNING | ERROR
  wifiConnected: true,
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

const frames = new Map();
let uiSettingsSaveTimer = null;
let runtimeSaveTimer = null;
let spindleRuntimeRawSec = 0;
let lastAxesTimestampMs = null;

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

function setWifiConnected(isConnected){
  state.wifiConnected = !!isConnected;
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
    queueRuntimeSave();
  }
}

function loadUiSettings(){
  fetch(`${API_BASE}/api/settings`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
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
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && shutdownModal.classList.contains("is-open")){
    closeShutdownModal();
  }
  if (ev.key === "Escape" && lightModal.classList.contains("is-open")){
    closeLightModal();
  }
  if (ev.key === "Escape" && fanModal.classList.contains("is-open")){
    closeFanModal();
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
    case "setWifi":    setWifiConnected(!!msg.connected); break;
    case "setLight":   setLightOn(!!msg.on); break;
    case "toggleLight":toggleLight(); break;
    case "setFan":     setFanOn(!!msg.on); break;
    case "toggleFan":  toggleFan(); break;
    case "setFanSpeed":updateFanSpeed(msg.value); break;
    case "setFanAuto": setFanAuto(!!msg.enabled); break;
    case "setSpindleRuntime": setSpindleRuntimeSec(msg.seconds, true); break;
    case "navigate":   if (typeof msg.page === "string") showPage(msg.page); break;
    default: break;
  }
});

// initiale Zustände an alle Frames
broadcastToFrames({
  type: "init",
  machineStatus: state.machineStatus,
  wifiConnected: state.wifiConnected,
  lightOn: state.lightOn,
  fanOn: state.fanOn,
  fanSpeed: state.fanSpeed,
  fanAuto: state.fanAuto,
  spindleRuntimeSec: state.spindleRuntimeSec
});

loadUiSettings();
startAxesStream();
