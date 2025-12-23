// -----------------------------
// Konfiguration
// -----------------------------
const PAGES = [
  { id: "home",        title: "Dashboard",      src: "pages/home.html" },
  { id: "errors",      title: "Fehler",         src: "pages/errors.html" },
  { id: "maintenance", title: "Wartung",        src: "pages/maintenance.html" },
  { id: "system",      title: "Systemkonfiguration", src: "pages/system.html" },
];

const API_BASE = "http://localhost:8080";

const state = {
  activePage: "home",
  machineStatus: "IDLE", // IDLE | RUNNING | ERROR
  wifiConnected: true,
  lightOn: true,
  lightBrightness: 75,
};

const ICONS = {
  wifiOn: "assets/svg/wifi-on.svg",
  wifiOff: "assets/svg/wifi-off.svg",
  bulbOn: "assets/svg/bulb-on.svg",
  bulbOff: "assets/svg/bulb-off.svg",
};

const mainEl = document.querySelector(".main");
const clockEl = document.getElementById("clock");
const statusEl = document.getElementById("machineStatus");

const wifiBtn = document.getElementById("wifiBtn");
const lightBtn = document.getElementById("lightBtn");
const shutdownBtn = document.getElementById("shutdownBtn");

const wifiImg = document.getElementById("wifiImg");
const lightImg = document.getElementById("lightImg");
const shutdownModal = document.getElementById("shutdownModal");
const shutdownCancel = document.getElementById("shutdownCancel");
const shutdownConfirm = document.getElementById("shutdownConfirm");
const lightModal = document.getElementById("lightModal");
const lightClose = document.getElementById("lightClose");
const lightSlider = document.getElementById("lightSlider");
const lightValue = document.getElementById("lightValue");

const frames = new Map();

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
}

function openLightModal(){
  updateLightBrightness(state.lightBrightness);
  lightModal.classList.add("is-open");
  lightModal.setAttribute("aria-hidden", "false");
  lightSlider.focus();
}

function closeLightModal(){
  lightModal.classList.remove("is-open");
  lightModal.setAttribute("aria-hidden", "true");
  lightBtn.focus();
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

// Demo: WiFi per Klick toggeln (für Test). In Produktion ersetzen durch echten Status.
wifiBtn.addEventListener("click", () => setWifiConnected(!state.wifiConnected));
let lightPressTimer = null;
let lightLongPress = false;

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
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && shutdownModal.classList.contains("is-open")){
    closeShutdownModal();
  }
  if (ev.key === "Escape" && lightModal.classList.contains("is-open")){
    closeLightModal();
  }
});

// Initial
setMachineStatus(state.machineStatus);
setWifiConnected(state.wifiConnected);
setLightOn(state.lightOn);

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
    const es = new EventSource(`${API_BASE}/api/axes/stream`);
    es.addEventListener("axes", (ev) => {
      try{
        const data = JSON.parse(ev.data || "{}");
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
    case "navigate":   if (typeof msg.page === "string") showPage(msg.page); break;
    default: break;
  }
});

// initiale Zustände an alle Frames
broadcastToFrames({
  type: "init",
  machineStatus: state.machineStatus,
  wifiConnected: state.wifiConnected,
  lightOn: state.lightOn
});

startAxesStream();
