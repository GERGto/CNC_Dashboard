import { createStatusbarController } from "./modules/statusbar.js?v=20260406-02";
import { createWifiEastereggController } from "./modules/wifiEasteregg.js";
import { createKeyboardController } from "./modules/keyboard.js";
import { createWifiController } from "./modules/wifi.js";
import { createMaintenanceController } from "./modules/maintenance.js";

// -----------------------------
// Konfiguration
// -----------------------------
const PAGES = [
  { id: "home",        title: "Dashboard",      src: "pages/home.html" },
  { id: "maintenance", title: "Wartung",        src: "pages/maintenance.html" },
  { id: "system",      title: "Systemkonfiguration", src: "pages/system.html" },
];

function createApiBase(){
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("apiBase");
  if (fromQuery){
    try{
      return new URL(fromQuery).origin;
    }catch (_error){
      // Ignore invalid override and fall back to host-based resolution.
    }
  }

  const base = new URL(window.location.href);
  base.port = params.get("backendPort") || "8080";
  base.pathname = "";
  base.search = "";
  base.hash = "";
  return base.origin;
}

const API_BASE = createApiBase();
const AXES_INTERVAL_MS = 250;
const RUNTIME_SAVE_INTERVAL_MS = 5000;
const MAINTENANCE_REFRESH_MS = 60000;
const WIFI_STATUS_REFRESH_MS = 10000;
const MACHINE_STATUS_REFRESH_MS = 1500;
const HARDWARE_REFRESH_MS = 1500;
const SHUTDOWN_RECOVERY_MS = 15000;
const PAGE_LOAD_TOKEN = String(Date.now());

const state = {
  activePage: "home",
  machineStatus: "IDLE", // IDLE | RUNNING | ERROR
  maintenanceDue: false,
  eStopEngaged: false,
  spindleRunning: false,
  wifiConnected: false,
  wifiSsid: "",
  wifiIssue: "",
  wifiIpAddress: "",
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
const navEl = document.querySelector(".nav");
const clockEl = document.getElementById("clock");
const statusEl = document.getElementById("machineStatus");
const statusBarEl = document.querySelector(".statusbar");

const wifiBtn = document.getElementById("wifiBtn");
const lightBtn = document.getElementById("lightBtn");
const fanBtn = document.getElementById("fanBtn");
const shutdownBtn = document.getElementById("shutdownBtn");

const wifiImg = document.getElementById("wifiImg");
const lightImg = document.getElementById("lightImg");
const fanImg = document.getElementById("fanImg");
const wifiEastereggOverlay = document.getElementById("wifiEastereggOverlay");
const wifiEastereggGif = document.getElementById("wifiEastereggGif");
const shutdownModal = document.getElementById("shutdownModal");
const shutdownMessage = shutdownModal.querySelector(".modal__text");
const shutdownError = document.getElementById("shutdownError");
const shutdownCancel = document.getElementById("shutdownCancel");
const shutdownConfirm = document.getElementById("shutdownConfirm");
const shutdownScreen = document.getElementById("shutdownScreen");
const startupNoticeModal = document.getElementById("startupNoticeModal");
const startupNoticeClose = document.getElementById("startupNoticeClose");
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
const frameStates = new Map();
let uiSettingsSaveTimer = null;
let machineStatusSyncTimer = null;
let spindleRuntimeRawSec = 0;
let graphWindowSec = 60;
let navSuppressClickUntilMs = 0;
let shutdownRecoveryTimer = null;
let shutdownInProgress = false;
let lightRequestInFlight = false;
let fanRequestInFlight = false;

const statusbarController = createStatusbarController({
  state,
  statusEl,
  statusBarEl,
});
const wifiEastereggController = createWifiEastereggController({
  overlayEl: wifiEastereggOverlay,
  imageEl: wifiEastereggGif,
  tapTarget: 5,
  tapWindowMs: 1600,
  durationMs: 12000,
});
const keyboardController = createKeyboardController({
  modalEl: keyboardModal,
  titleEl: keyboardTitle,
  displayInputEl: keyboardDisplayInput,
  keysEl: keyboardKeys,
  cancelBtn: keyboardCancelBtn,
  okBtn: keyboardOkBtn,
});
const wifiController = createWifiController({
  apiBase: API_BASE,
  state,
  keyboardController,
  connectTimeoutMs: 30000,
  feedbackMs: 2000,
  onSetWifiConnected: setWifiConnected,
  onBroadcastWifi: broadcastWifiState,
  onReturnFocus: () => wifiBtn.focus(),
  elements: {
    btn: wifiBtn,
    configModal: wifiConfigModal,
    modalClose: wifiModalClose,
    ssidSelect: wifiSsidSelect,
    scanBtn: wifiScanBtn,
    passwordInput: wifiPasswordInput,
    autoConnectInput: wifiAutoConnectInput,
    saveBtn: wifiSaveBtn,
    connectBtn: wifiConnectBtn,
    disconnectBtn: wifiDisconnectBtn,
    configMsg: wifiConfigMsg,
    connectFeedbackModal: wifiConnectFeedbackModal,
    feedbackSpinner: wifiFeedbackSpinner,
    feedbackSuccess: wifiFeedbackSuccess,
    feedbackError: wifiFeedbackError,
    connectFeedbackText: wifiConnectFeedbackText,
  },
});
const maintenanceController = createMaintenanceController({
  apiBase: API_BASE,
  state,
  onSetMaintenanceDue: setMaintenanceDue,
  onTaskCompleted: (task) => {
    broadcastToFrames({ type: "maintenanceTaskCompleted", task });
  },
  elements: {
    taskModal: maintenanceTaskModal,
    taskTitle: maintenanceTaskTitle,
    detailInterval: maintenanceDetailInterval,
    detailEffort: maintenanceDetailEffort,
    detailStatus: maintenanceDetailStatus,
    detailLastDone: maintenanceDetailLastDone,
    detailSinceDone: maintenanceDetailSinceDone,
    detailDescription: maintenanceDetailDescription,
    detailGuideInfo: maintenanceDetailGuideInfo,
    tabOverview: maintenanceTabOverview,
    tabGuide: maintenanceTabGuide,
    panelOverview: maintenancePanelOverview,
    panelGuide: maintenancePanelGuide,
    guideContent: maintenanceGuideContent,
    guideEmpty: maintenanceGuideEmpty,
    guideStepMeta: maintenanceGuideStepMeta,
    guideStepText: maintenanceGuideStepText,
    guideStepImage: maintenanceGuideStepImage,
    taskClose: maintenanceTaskClose,
    guidePrev: maintenanceGuidePrev,
    guideNext: maintenanceGuideNext,
    taskDone: maintenanceTaskDone,
    dueDot: maintenanceDueDot,
  },
});

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
  statusbarController.setMachineStatus(newStatus);
  queueMachineStatusSync();
}

function setMaintenanceDue(isDue){
  statusbarController.setMaintenanceDue(isDue);
}

function applyMachineStatusSnapshot(snapshot){
  if (!snapshot || typeof snapshot !== "object") return;

  if (typeof snapshot.effectiveStatus === "string"){
    const nextStatus = String(snapshot.effectiveStatus || "").trim().toUpperCase();
    state.machineStatus = nextStatus || "IDLE";
  }
  if (snapshot.maintenanceDue !== undefined){
    state.maintenanceDue = !!snapshot.maintenanceDue;
    if (maintenanceDueDot) {
      maintenanceDueDot.hidden = !state.maintenanceDue;
    }
  }
  if (snapshot.eStopEngaged !== undefined){
    state.eStopEngaged = !!snapshot.eStopEngaged;
  }
  if (snapshot.spindleRunning !== undefined){
    state.spindleRunning = !!snapshot.spindleRunning;
  }
  if (snapshot.spindleRuntimeSec !== undefined){
    const nextRuntimeSec = Math.max(0, Math.floor(Number(snapshot.spindleRuntimeSec) || 0));
    if (nextRuntimeSec !== state.spindleRuntimeSec){
      setSpindleRuntimeSec(nextRuntimeSec, false);
    }
  }

  statusbarController.applyStatusbarState();
}

function setWifiConnected(isConnected, ssid = null){
  state.wifiConnected = !!isConnected;
  if (typeof ssid === "string"){
    state.wifiSsid = ssid.trim();
  }
  wifiImg.src = state.wifiConnected ? ICONS.wifiOn : ICONS.wifiOff;
  wifiBtn.setAttribute("aria-label", state.wifiConnected ? "WLAN verbunden" : "WLAN getrennt");
}

function broadcastWifiState(){
  broadcastToFrames({
    type: "wifi",
    connected: state.wifiConnected,
    ssid: state.wifiSsid,
    issue: state.wifiIssue,
    wifiIpAddress: state.wifiIpAddress,
  });
}

function setLightOn(isOn, broadcast = false){
  state.lightOn = !!isOn;
  lightImg.src = state.lightOn ? ICONS.bulbOn : ICONS.bulbOff;
  lightBtn.setAttribute("aria-label", state.lightOn ? "Maschinenlicht an" : "Maschinenlicht aus");
  if (broadcast){
    broadcastToFrames({ type: "light", on: state.lightOn });
  }
}

function toggleLight(){
  void setLightPower(!state.lightOn);
}

function updateLightBrightness(value){
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  state.lightBrightness = v;
  lightSlider.value = String(v);
  lightValue.textContent = `${v}%`;
  broadcastToFrames({ type: "lightBrightness", value: v });
  queueUiSettingsSave();
}

function setFanOn(isOn, broadcast = false){
  state.fanOn = !!isOn;
  fanImg.src = state.fanOn ? ICONS.fanOn : ICONS.fanOff;
  fanBtn.setAttribute("aria-label", state.fanOn ? "Luefter an" : "Luefter aus");
  if (broadcast){
    broadcastToFrames({ type: "fan", on: state.fanOn });
  }
}

function toggleFan(){
  void setFanPower(!state.fanOn);
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

function showWifiEasteregg(){
  wifiEastereggController.show();
}

function hideWifiEasteregg(){
  wifiEastereggController.hide();
}

function registerWifiRapidTap(){
  wifiEastereggController.registerRapidTap();
}

function buildFrameSrc(page){
  const separator = page.src.includes("?") ? "&" : "?";
  return `${page.src}${separator}v=${encodeURIComponent(PAGE_LOAD_TOKEN)}`;
}

function buildInitMessage(){
  return {
    type: "init",
    machineStatus: state.machineStatus,
    eStopEngaged: state.eStopEngaged,
    wifiConnected: state.wifiConnected,
    wifiSsid: state.wifiSsid,
    wifiIssue: state.wifiIssue,
    wifiIpAddress: state.wifiIpAddress,
    lightOn: state.lightOn,
    fanOn: state.fanOn,
    fanSpeed: state.fanSpeed,
    fanAuto: state.fanAuto,
    spindleRuntimeSec: state.spindleRuntimeSec,
    spindleRunning: state.spindleRunning
  };
}

function openKeyboardModal(options = {}){
  keyboardController.open(options);
}

function openWifiConfigModal(){
  wifiController.openConfigModal();
}

function closeWifiConfigModal(force = false){
  wifiController.closeConfigModal(force);
}

function loadMaintenanceTasks(){
  return maintenanceController.loadTasks();
}

function openMaintenanceTaskModal(payload){
  maintenanceController.openTaskModal(payload);
}

function queueUiSettingsSave(){
  if (uiSettingsSaveTimer) clearTimeout(uiSettingsSaveTimer);
  uiSettingsSaveTimer = setTimeout(() => {
    persistUiSettings();
  }, 250);
}

function queueMachineStatusSync(){
  if (machineStatusSyncTimer) clearTimeout(machineStatusSyncTimer);
  machineStatusSyncTimer = setTimeout(() => {
    machineStatusSyncTimer = null;
    fetch(`${API_BASE}/api/machine/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: state.machineStatus,
        source: "frontend",
      }),
    }).catch(() => {});
  }, 100);
}

function persistUiSettings(){
  fetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lightBrightness: state.lightBrightness,
      fanSpeed: state.fanSpeed,
      fanAuto: state.fanAuto
    })
  }).catch(() => {});
}

function persistSpindleRuntime(){
  fetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      spindleRuntimeSec: state.spindleRuntimeSec
    })
  }).catch(() => {});
}

function applyRelayBoardSnapshot(relayBoard){
  const channels = relayBoard && typeof relayBoard === "object" ? relayBoard.channels : null;
  if (!channels || typeof channels !== "object") return;

  if (channels.light && typeof channels.light.on === "boolean"){
    setLightOn(channels.light.on, true);
  }
  if (channels.fan && typeof channels.fan.on === "boolean"){
    setFanOn(channels.fan.on, true);
  }
  if (channels.eStop){
    state.eStopEngaged = !!(channels.eStop.engaged ?? channels.eStop.on);
    statusbarController.applyStatusbarState();
  }
}

function applyHardwareSnapshot(data){
  const relayBoard = data && data.actuators && data.actuators.relayBoard;
  if (relayBoard && typeof relayBoard === "object" && (relayBoard.available || relayBoard.status === "ok")){
    applyRelayBoardSnapshot(relayBoard);
  }
}

async function postRelayOutput(endpoint, payload){
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false){
    throw new Error(typeof data?.error === "string" ? data.error : `Hardware request failed (${response.status})`);
  }
  return data;
}

async function setLightPower(isOn){
  if (lightRequestInFlight) return;
  lightRequestInFlight = true;
  try {
    const data = await postRelayOutput("/api/hardware/light", { on: !!isOn });
    if (data && data.relayBoard){
      applyRelayBoardSnapshot(data.relayBoard);
    } else if (data && data.channel && typeof data.channel.on === "boolean"){
      setLightOn(data.channel.on, true);
    }
  } catch (error){
    console.error("Light relay request failed:", error);
  } finally {
    lightRequestInFlight = false;
  }
}

async function setFanPower(isOn){
  if (fanRequestInFlight) return;
  fanRequestInFlight = true;
  try {
    const data = await postRelayOutput("/api/hardware/fan", { on: !!isOn });
    if (data && data.relayBoard){
      applyRelayBoardSnapshot(data.relayBoard);
    } else if (data && data.channel && typeof data.channel.on === "boolean"){
      setFanOn(data.channel.on, true);
    }
  } catch (error){
    console.error("Fan relay request failed:", error);
  } finally {
    fanRequestInFlight = false;
  }
}

function setSpindleRuntimeSec(value, persist = false){
  const v = Math.max(0, Math.floor(Number(value) || 0));
  spindleRuntimeRawSec = v;
  state.spindleRuntimeSec = v;
  broadcastToFrames({ type: "spindleRuntime", seconds: v });
  maintenanceController.onSpindleRuntimeChanged();
  if (persist){
    window.setTimeout(persistSpindleRuntime, RUNTIME_SAVE_INTERVAL_MS);
  }
}

function loadUiSettings(){
  fetch(`${API_BASE}/api/settings`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      wifiController.applySettings(data, {
        updateForm: false,
        fallbackConnected: false,
        broadcast: true,
      });
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

function loadWifiStatus(){
  fetch(`${API_BASE}/api/wifi/status`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      wifiController.applySettings(data, {
        updateForm: false,
        fallbackConnected: true,
        broadcast: true,
      });
    })
    .catch(() => {});
}

function loadHardwareState(){
  fetch(`${API_BASE}/api/hardware`, { cache: "no-store" })
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      applyHardwareSnapshot(data);
    })
    .catch(() => {});
}

function loadMachineStatus(){
  fetch(`${API_BASE}/api/machine/status`, { cache: "no-store" })
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      applyMachineStatusSnapshot(data);
    })
    .catch(() => {});
}

function closeFanModal(){
  fanModal.classList.remove("is-open");
  fanModal.setAttribute("aria-hidden", "true");
  fanBtn.focus();
}

function setShutdownError(message = ""){
  const hasMessage = Boolean(message);
  shutdownError.textContent = hasMessage ? message : "";
  shutdownError.hidden = !hasMessage;
  shutdownMessage.hidden = false;
}

function showShutdownScreen(){
  document.body.classList.add("is-shutting-down");
  shutdownScreen.classList.add("is-active");
}

function hideShutdownScreen(){
  shutdownScreen.classList.remove("is-active");
  document.body.classList.remove("is-shutting-down");
}

function clearShutdownRecoveryTimer(){
  if (shutdownRecoveryTimer !== null){
    clearTimeout(shutdownRecoveryTimer);
    shutdownRecoveryTimer = null;
  }
}

function scheduleShutdownRecovery(){
  clearShutdownRecoveryTimer();
  shutdownRecoveryTimer = window.setTimeout(() => {
    shutdownInProgress = false;
    hideShutdownScreen();
    setShutdownError("Herunterfahren wurde angefordert, aber das System ist noch aktiv.");
    openShutdownModal({ preserveError: true });
  }, SHUTDOWN_RECOVERY_MS);
}

function queueShutdownRequest(){
  requestAnimationFrame(() => {
    window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/shutdown`, {
          method: "POST",
          keepalive: true,
          cache: "no-store",
        });
        const payload = await response.json().catch(() => null);

        if (!response.ok || payload?.ok === false){
          const detail = payload?.message ? `: ${payload.message}` : "";
          throw new Error(`Herunterfahren konnte nicht gestartet werden${detail}`);
        }

        scheduleShutdownRecovery();
      } catch (error){
        shutdownInProgress = false;
        hideShutdownScreen();
        setShutdownError(
          error instanceof Error && error.message
            ? error.message
            : "Herunterfahren konnte nicht gestartet werden."
        );
        openShutdownModal({ preserveError: true });
      }
    }, 0);
  });
}

function openShutdownModal({ preserveError = false } = {}){
  if (shutdownInProgress) return;
  if (!preserveError){
    setShutdownError("");
  }
  shutdownModal.classList.add("is-open");
  shutdownModal.setAttribute("aria-hidden", "false");
  shutdownConfirm.focus();
}

function closeShutdownModal({ restoreFocus = true } = {}){
  shutdownModal.classList.remove("is-open");
  shutdownModal.setAttribute("aria-hidden", "true");
  if (restoreFocus){
    shutdownBtn.focus();
  }
}

function openStartupNoticeModal(){
  startupNoticeModal.classList.add("is-open");
  startupNoticeModal.setAttribute("aria-hidden", "false");
  startupNoticeClose.focus();
}

function closeStartupNoticeModal(){
  startupNoticeModal.classList.remove("is-open");
  startupNoticeModal.setAttribute("aria-hidden", "true");
}

function confirmShutdown(){
  if (shutdownInProgress) return;

  shutdownInProgress = true;
  clearShutdownRecoveryTimer();
  setShutdownError("");
  closeShutdownModal({ restoreFocus: false });
  showShutdownScreen();
  shutdownScreen.getBoundingClientRect();
  queueShutdownRequest();
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
    return;
  }
  registerWifiRapidTap();
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
startupNoticeClose.addEventListener("click", closeStartupNoticeModal);
startupNoticeModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeStartupNoticeModal();
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
wifiController.attachEventHandlers();
keyboardController.attachEventHandlers();
graphClose.addEventListener("click", closeGraphModal);
graphModal.addEventListener("click", (ev) => {
  if (ev.target && ev.target.dataset && ev.target.dataset.close){
    closeGraphModal();
  }
});
graphWindowSlider.addEventListener("input", (ev) => updateGraphWindowModal(ev.target.value, true));
maintenanceController.attachEventHandlers();
window.addEventListener("keydown", (ev) => {
  if (keyboardController.handleDocumentKeydown(ev)){
    return;
  }
  if (maintenanceController.handleDocumentKeydown(ev)){
    return;
  }

  if (ev.key === "Escape" && shutdownModal.classList.contains("is-open")){
    closeShutdownModal();
  }
  if (ev.key === "Escape" && startupNoticeModal.classList.contains("is-open")){
    closeStartupNoticeModal();
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
    const frameState = {
      src: buildFrameSrc(p),
      loadRequested: false,
      loaded: false,
      pendingMessages: [],
    };
    f.loading = p.id === state.activePage ? "eager" : "lazy";
    f.setAttribute("title", p.title);
    f.addEventListener("load", () => {
      frameState.loaded = true;
      flushQueuedFrameMessages(p.id);
    });
    mainEl.appendChild(f);
    frames.set(p.id, f);
    frameStates.set(p.id, frameState);
    if (p.id === state.activePage){
      ensureFrameLoaded(p.id);
    }
  }
}

function showPage(pageId){
  if (!frames.has(pageId)) return;
  const previousPageId = state.activePage;
  state.activePage = pageId;
  ensureFrameLoaded(pageId);

  for (const [id, frame] of frames.entries()){
    frame.classList.toggle("active", id === pageId);
  }

  for (const btn of document.querySelectorAll(".navbtn")){
    btn.classList.toggle("active", btn.dataset.page === pageId);
  }

  if (previousPageId && previousPageId !== pageId){
    postToFrame(previousPageId, { type: "pageHidden", id: previousPageId });
  }
  postToFrame(pageId, { type: "pageShown", id: pageId });
}

function openSystemWifiConfig(){
  const message = { type: "openWifiConfig", openModal: false };
  showPage("system");
  openWifiConfigModal();
  postToFrame("system", message);
}

function activateNavButton(btn){
  if (!btn) return;
  showPage(btn.dataset.page);
}

navEl.addEventListener("pointerdown", (ev) => {
  const btn = ev.target.closest(".navbtn");
  if (!btn) return;
  if (ev.pointerType === "mouse"){
    return;
  }
  navSuppressClickUntilMs = performance.now() + 700;
  ev.preventDefault();
  activateNavButton(btn);
});

navEl.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".navbtn");
  if (!btn) return;
  if (performance.now() < navSuppressClickUntilMs){
    return;
  }
  activateNavButton(btn);
});

createFrames();
showPage(state.activePage);
openStartupNoticeModal();
window.addEventListener("load", () => {
  const deferredPageIds = PAGES
    .map((page) => page.id)
    .filter((pageId) => pageId !== state.activePage);
  deferredPageIds.forEach((pageId, index) => {
    window.setTimeout(() => {
      ensureFrameLoaded(pageId);
    }, 800 + (index * 400));
  });
}, { once: true });

// -----------------------------
// Kommunikation Shell <-> iFrames (optional)
// -----------------------------
function ensureFrameLoaded(pageId){
  const f = frames.get(pageId);
  const frameState = frameStates.get(pageId);
  if (!f || !frameState || frameState.loadRequested){
    return;
  }
  frameState.loadRequested = true;
  f.src = frameState.src;
}

function flushQueuedFrameMessages(pageId){
  const f = frames.get(pageId);
  const frameState = frameStates.get(pageId);
  if (!f || !frameState || !frameState.loaded || !f.contentWindow){
    return;
  }
  f.contentWindow.postMessage(buildInitMessage(), location.origin);
  for (const message of frameState.pendingMessages){
    f.contentWindow.postMessage(message, location.origin);
  }
  frameState.pendingMessages = [];
}

function postToFrame(pageId, message){
  const f = frames.get(pageId);
  const frameState = frameStates.get(pageId);
  if (!f || !frameState) return;
  if (!frameState.loaded || !f.contentWindow){
    frameState.pendingMessages.push(message);
    ensureFrameLoaded(pageId);
    return;
  }
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
      broadcastWifiState();
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
    case "setLight":   void setLightPower(!!msg.on); break;
    case "toggleLight":toggleLight(); break;
    case "setFan":     void setFanPower(!!msg.on); break;
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

loadUiSettings();
loadWifiStatus();
loadHardwareState();
loadMachineStatus();
loadMaintenanceTasks();
setInterval(loadWifiStatus, WIFI_STATUS_REFRESH_MS);
setInterval(loadHardwareState, HARDWARE_REFRESH_MS);
setInterval(loadMachineStatus, MACHINE_STATUS_REFRESH_MS);
setInterval(loadMaintenanceTasks, MAINTENANCE_REFRESH_MS);
startAxesStream();
