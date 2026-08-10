const AXIS_KEYS = ["x", "y", "z", "spindle"];
const AXIS_WARN = {
  x: 80,
  y: 80,
  z: 80,
  spindle: 75,
};
const STATIC_REFRESH_MS = 1500;
const CAMERA_RECONNECT_DELAY_MS = 1500;

const ICONS = {
  rec: `
    <svg viewBox="0 0 24 24" fill="currentColor">
      <circle cx="12" cy="12" r="8"></circle>
    </svg>
  `,
  stop: `
    <svg viewBox="0 0 24 24" fill="currentColor">
      <rect x="4" y="4" width="16" height="16" rx="2"></rect>
    </svg>
  `,
  file: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
    </svg>
  `,
  download: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
      <path d="M7 10l5 5 5-5"></path>
      <path d="M12 15V3"></path>
    </svg>
  `,
  trash: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M3 6h18"></path>
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
    </svg>
  `,
  check: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
  `,
};

const dom = {
  headerStatusDot: document.getElementById("headerStatusDot"),
  ledStrip: document.getElementById("ledStrip"),
  ledStripLabel: document.getElementById("ledStripLabel"),
  lightToggleBtn: document.getElementById("lightToggleBtn"),
  spindleFanToggleBtn: document.getElementById("spindleFanToggleBtn"),
  enclosureFanToggleBtn: document.getElementById("enclosureFanToggleBtn"),
  recordToggleBtn: document.getElementById("recordToggleBtn"),
  recordToggleIcon: document.getElementById("recordToggleIcon"),
  recordToggleLabel: document.getElementById("recordToggleLabel"),
  cameraFeed: document.getElementById("cameraFeed"),
  cameraPlaceholder: document.getElementById("cameraPlaceholder"),
  cameraPlaceholderTitle: document.getElementById("cameraPlaceholderTitle"),
  cameraPlaceholderText: document.getElementById("cameraPlaceholderText"),
  recordingBadge: document.getElementById("recordingBadge"),
  recordingBadgeLabel: document.getElementById("recordingBadgeLabel"),
  estopOverlay: document.getElementById("estopOverlay"),
  axisValueX: document.getElementById("axisValueX"),
  axisValueY: document.getElementById("axisValueY"),
  axisValueZ: document.getElementById("axisValueZ"),
  axisValueSpindle: document.getElementById("axisValueSpindle"),
  axisBarX: document.getElementById("axisBarX"),
  axisBarY: document.getElementById("axisBarY"),
  axisBarZ: document.getElementById("axisBarZ"),
  axisBarSpindle: document.getElementById("axisBarSpindle"),
  loadMeterX: document.getElementById("loadMeterX"),
  loadMeterY: document.getElementById("loadMeterY"),
  loadMeterZ: document.getElementById("loadMeterZ"),
  loadMeterSpindle: document.getElementById("loadMeterSpindle"),
  estopToggleBtn: document.getElementById("estopToggleBtn"),
  estopToggleLabel: document.getElementById("estopToggleLabel"),
  filesTabBtn: document.getElementById("filesTabBtn"),
  maintenanceTabBtn: document.getElementById("maintenanceTabBtn"),
  filesCountBadge: document.getElementById("filesCountBadge"),
  maintenanceCountBadge: document.getElementById("maintenanceCountBadge"),
  filesPanel: document.getElementById("filesPanel"),
  maintenancePanel: document.getElementById("maintenancePanel"),
  fileDropZone: document.getElementById("fileDropZone"),
  fileInput: document.getElementById("fileInput"),
  fileList: document.getElementById("fileList"),
  fileEmptyState: document.getElementById("fileEmptyState"),
  taskList: document.getElementById("taskList"),
  taskEmptyState: document.getElementById("taskEmptyState"),
  toast: document.getElementById("toast"),
};

const axisValueEls = {
  x: dom.axisValueX,
  y: dom.axisValueY,
  z: dom.axisValueZ,
  spindle: dom.axisValueSpindle,
};

const axisBarEls = {
  x: dom.axisBarX,
  y: dom.axisBarY,
  z: dom.axisBarZ,
  spindle: dom.axisBarSpindle,
};

const axisMeterEls = {
  x: dom.loadMeterX,
  y: dom.loadMeterY,
  z: dom.loadMeterZ,
  spindle: dom.loadMeterSpindle,
};

const state = {
  apiBase: createApiBase(),
  cameraStreamBase: createCameraStreamBase(),
  machineStatus: "IDLE",
  maintenanceDue: false,
  warmupDue: false,
  dueTaskIds: [],
  tasks: [],
  lightOn: false,
  spindleFanOn: false,
  enclosureFanOn: false,
  enclosureFanAvailable: false,
  eStopEngaged: false,
  hardwareEStopEngaged: false,
  eStopResetLocked: false,
  hardwareEStopInputIds: [],
  cameraTransport: "",
  cameraWhepUrl: "",
  cameraAvailable: false,
  cameraDevicePath: "",
  cameraError: "",
  cameraLoaded: false,
  axes: { x: 0, y: 0, z: 0, spindle: 0 },
  spindleRunning: false,
  spindleRuntimeSec: 0,
  backendStartCount: 0,
  activeTab: "files",
  files: [],
  programs: [],
  programController: { enabled: false, configured: false, issue: "" },
  allowedProgramExtensions: [".gcode", ".nc", ".tap", ".ngc"],
  uploadBusy: false,
  cameraReaderSupported:
    typeof window.MediaMTXWebRTCReader === "function" && typeof window.RTCPeerConnection !== "undefined",
  recordingSupported: false,
  recordingActive: false,
  recordingSeconds: 0,
  recordingBusy: false,
  recordingError: "",
  recordings: [],
  pollingBusy: false,
};

// The recording itself runs on the Pi; the browser only drives start/stop and
// keeps a local seconds counter between status polls.
const recording = {
  timer: null,
};

const completingTaskIds = new Set();
const completedTaskIds = new Set();
let axesSource = null;
let toastTimer = null;
let cameraReader = null;
let cameraReaderUrl = "";
let cameraReconnectTimer = null;
let cameraConnectionToken = 0;

function shouldEnsureCameraStream() {
  return !document.hidden || state.recordingActive;
}

function createApiBase() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("apiBase");
  if (fromQuery) {
    try {
      return new URL(fromQuery).origin;
    } catch (_error) {
      // Fall through to host-based default.
    }
  }

  const backendPort = params.get("backendPort");
  if (backendPort) {
    const apiUrl = new URL(window.location.origin);
    apiUrl.port = backendPort;
    apiUrl.pathname = "";
    apiUrl.search = "";
    apiUrl.hash = "";
    return apiUrl.origin;
  }

  return window.location.origin;
}

function createCameraStreamBase() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("cameraStreamBase");
  if (fromQuery) {
    try {
      return new URL(fromQuery).origin;
    } catch (_error) {
      // Fall through to host-based default.
    }
  }

  const streamPort = params.get("cameraWebrtcPort");
  if (streamPort) {
    const streamUrl = new URL(window.location.origin);
    streamUrl.port = streamPort;
    streamUrl.pathname = "";
    streamUrl.search = "";
    streamUrl.hash = "";
    return streamUrl.origin;
  }

  return window.location.origin;
}

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function formatRecordingTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function formatDate(date) {
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatFileNameTimestamp(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day}_${hours}-${minutes}-${seconds}`;
}

function formatFileSize(bytes) {
  const numeric = Math.max(0, Number(bytes) || 0);
  if (numeric >= 1024 * 1024) {
    return `${(numeric / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(numeric / 1024))} KB`;
}

function addMonths(date, months) {
  const result = new Date(date.getTime());
  const originalDay = result.getDate();
  result.setDate(1);
  result.setMonth(result.getMonth() + months);
  const maxDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
  result.setDate(Math.min(originalDay, maxDay));
  return result;
}

function showToast(message, isError = false) {
  dom.toast.textContent = message;
  dom.toast.hidden = false;
  dom.toast.classList.toggle("is-error", isError);
  if (toastTimer) {
    window.clearTimeout(toastTimer);
  }
  toastTimer = window.setTimeout(() => {
    dom.toast.hidden = true;
  }, 2600);
}

function clearCameraReconnectTimer() {
  if (!cameraReconnectTimer) {
    return;
  }
  window.clearTimeout(cameraReconnectTimer);
  cameraReconnectTimer = null;
}

function stopCameraReader(clearVideo = true) {
  cameraConnectionToken += 1;
  clearCameraReconnectTimer();
  cameraReaderUrl = "";

  if (cameraReader) {
    try {
      cameraReader.close();
    } catch (_error) {
      // Ignore cleanup issues while replacing the stream.
    }
    cameraReader = null;
  }

  if (clearVideo) {
    try {
      dom.cameraFeed.pause();
    } catch (_error) {
      // Ignore browsers that reject pause() during unload.
    }
    dom.cameraFeed.srcObject = null;
  }
}

function scheduleCameraReconnect() {
  if (cameraReconnectTimer || !state.cameraAvailable || !state.cameraWhepUrl) {
    return;
  }

  cameraReconnectTimer = window.setTimeout(() => {
    cameraReconnectTimer = null;
    ensureCameraReader();
  }, CAMERA_RECONNECT_DELAY_MS);
}

function attachCameraStream(stream) {
  if (!stream) {
    return;
  }

  dom.cameraFeed.srcObject = stream;
  const playPromise = dom.cameraFeed.play();
  if (playPromise && typeof playPromise.catch === "function") {
    playPromise.catch(() => {
      // Autoplay can briefly race while the page becomes visible.
    });
  }
  state.cameraLoaded = true;
  state.cameraError = "";
  renderCamera();
}

function ensureCameraReader() {
  if (!shouldEnsureCameraStream()) {
    stopCameraReader(true);
    state.cameraLoaded = false;
    return;
  }

  const whepUrl = state.cameraAvailable ? state.cameraWhepUrl.trim() : "";
  if (!whepUrl) {
    stopCameraReader(true);
    return;
  }

  if (!state.cameraReaderSupported) {
    state.cameraLoaded = false;
    state.cameraError = "WebRTC wird in diesem Browser nicht unterstuetzt.";
    return;
  }

  if (cameraReconnectTimer) {
    return;
  }

  if (cameraReader && cameraReaderUrl === whepUrl) {
    return;
  }

  stopCameraReader(false);
  state.cameraLoaded = false;
  cameraReaderUrl = whepUrl;
  const connectionToken = cameraConnectionToken;

  cameraReader = new window.MediaMTXWebRTCReader({
    url: whepUrl,
    onTrack: (event) => {
      if (connectionToken !== cameraConnectionToken || cameraReaderUrl !== whepUrl) {
        return;
      }
      attachCameraStream(event?.streams?.[0]);
    },
    onError: (message) => {
      if (connectionToken !== cameraConnectionToken || cameraReaderUrl !== whepUrl) {
        return;
      }
      // The recording runs on the Pi and survives a broken browser stream.
      state.cameraLoaded = false;
      state.cameraError = message
        ? `MediaMTX/WebRTC-Verbindung unterbrochen: ${message}`
        : "MediaMTX/WebRTC-Verbindung unterbrochen.";
      stopCameraReader(false);
      scheduleCameraReconnect();
      renderCamera();
    },
  });
}

function getSpindleActive() {
  return state.spindleRunning;
}

function getCurrentTone() {
  if (state.eStopEngaged) {
    return "estop";
  }
  if (state.maintenanceDue) {
    return "maintenance";
  }
  if (getSpindleActive()) {
    return "spindle";
  }
  return "idle";
}

function renderStatusStrip() {
  const tone = getCurrentTone();
  const labels = {
    idle: "IDLE",
    spindle: "SPINDEL",
    maintenance: "WARTUNG FÄLLIG",
    estop: "E-STOP AKTIV",
  };

  if (dom.ledStrip) {
    dom.ledStrip.dataset.tone = tone;
  }
  if (dom.ledStripLabel) {
    dom.ledStripLabel.textContent = labels[tone] || "IDLE";
  }

  dom.headerStatusDot.classList.remove("is-spindle", "is-maintenance", "is-estop");
  if (tone === "spindle") {
    dom.headerStatusDot.classList.add("is-spindle");
  } else if (tone === "maintenance") {
    dom.headerStatusDot.classList.add("is-maintenance");
  } else if (tone === "estop") {
    dom.headerStatusDot.classList.add("is-estop");
  }
}

function renderToolbar() {
  dom.lightToggleBtn.classList.toggle("is-light-active", state.lightOn);
  dom.spindleFanToggleBtn.classList.toggle("is-fan-active", state.spindleFanOn);
  dom.enclosureFanToggleBtn.classList.toggle("is-fan-active", state.enclosureFanOn);
  dom.enclosureFanToggleBtn.classList.toggle("is-disabled", !state.enclosureFanAvailable);
  dom.enclosureFanToggleBtn.disabled = !state.enclosureFanAvailable;
  dom.enclosureFanToggleBtn.title = state.enclosureFanAvailable
    ? "Gehäuse-Lüfter schalten"
    : "Gehäuse-Lüfter ist aktuell nicht konfiguriert";

  const recordingReady = state.recordingSupported && !state.recordingBusy;
  dom.recordToggleBtn.classList.toggle("is-recording", state.recordingActive);
  dom.recordToggleBtn.classList.toggle("is-disabled", !recordingReady);
  dom.recordToggleBtn.disabled = !recordingReady;
  dom.recordToggleBtn.title = state.recordingSupported
    ? state.recordingError || "MP4-Aufnahme des Livebilds auf dem Pi"
    : "Aufnahme steht auf diesem System nicht zur Verfuegung";

  dom.recordToggleIcon.innerHTML = state.recordingActive ? ICONS.stop : ICONS.rec;
  dom.recordToggleLabel.textContent = state.recordingActive
    ? `REC ${formatRecordingTime(state.recordingSeconds)}`
    : "Aufnahme";

  dom.estopToggleBtn.classList.toggle("is-active", state.eStopEngaged);
  dom.estopToggleBtn.classList.toggle("is-disabled", state.eStopResetLocked);
  dom.estopToggleBtn.disabled = state.eStopResetLocked;
  dom.estopToggleBtn.title = state.eStopResetLocked
    ? "Hardware-E-Stop aktiv. Nur mechanisch am Taster loesbar."
    : state.eStopEngaged
      ? "E-Stop zuruecksetzen"
      : "E-Stop ausloesen";
  dom.estopToggleLabel.textContent = state.eStopResetLocked
    ? "MECH. LOESEN"
    : state.eStopEngaged
      ? "RESET"
      : "E-STOP";
}

function renderCamera() {
  if (!shouldEnsureCameraStream()) {
    stopCameraReader(true);
    state.cameraLoaded = false;
    dom.cameraFeed.hidden = true;
    dom.cameraPlaceholder.hidden = false;
    dom.cameraPlaceholderTitle.textContent = "Kamera-Feed pausiert";
    dom.cameraPlaceholderText.textContent = "Der Stream startet wieder, sobald die Seite sichtbar ist.";
    dom.recordingBadge.hidden = !state.recordingActive;
    dom.recordingBadgeLabel.textContent = `REC ${formatRecordingTime(state.recordingSeconds)}`;
    dom.estopOverlay.hidden = !state.eStopEngaged;
    return;
  }

  const whepUrl = state.cameraAvailable ? state.cameraWhepUrl.trim() : "";
  if (!whepUrl) {
    stopCameraReader(true);
    state.cameraLoaded = false;
    dom.cameraFeed.hidden = true;
    dom.cameraPlaceholder.hidden = false;
    dom.cameraPlaceholderTitle.textContent = "Kamera-Feed";
    dom.cameraPlaceholderText.textContent = state.cameraError
      ? state.cameraError
      : "Der MediaMTX-WebRTC-Stream der USB-Kamera wird automatisch eingebunden.";
  } else {
    ensureCameraReader();
    dom.cameraPlaceholder.hidden = state.cameraLoaded;
    dom.cameraFeed.hidden = !state.cameraLoaded;
    if (!state.cameraLoaded) {
      dom.cameraPlaceholderTitle.textContent = state.cameraError ? "Stream nicht erreichbar" : "Verbinde Kamera";
      dom.cameraPlaceholderText.textContent = state.cameraError
        ? state.cameraError
          : state.cameraDevicePath
          ? `MediaMTX/WebRTC verbindet ${state.cameraDevicePath}.`
          : "MediaMTX/WebRTC-Stream wird geladen.";
    }
  }

  dom.recordingBadge.hidden = !state.recordingActive;
  dom.recordingBadgeLabel.textContent = `REC ${formatRecordingTime(state.recordingSeconds)}`;
  dom.estopOverlay.hidden = !state.eStopEngaged;
}

function renderLoads() {
  AXIS_KEYS.forEach((axis) => {
    const value = clampPercent(state.axes[axis]);
    if (axisValueEls[axis]) {
      axisValueEls[axis].textContent = `${value}%`;
    }
    if (axisBarEls[axis]) {
      axisBarEls[axis].style.width = `${value}%`;
    }
    if (axisMeterEls[axis]) {
      axisMeterEls[axis].classList.toggle("is-warn", value >= AXIS_WARN[axis]);
    }
  });
}

function setActiveTab(tabName) {
  state.activeTab = tabName === "maintenance" ? "maintenance" : "files";
  renderTabs();
}

function renderTabs() {
  dom.filesCountBadge.textContent = String(state.files.length);
  dom.maintenanceCountBadge.textContent = String(state.dueTaskIds.length);

  const filesActive = state.activeTab === "files";
  dom.filesTabBtn.classList.toggle("is-active", filesActive);
  dom.maintenanceTabBtn.classList.toggle("is-active", !filesActive);
  dom.filesPanel.hidden = !filesActive;
  dom.maintenancePanel.hidden = filesActive;
}

// Recordings and CNC programs both live on the Pi, so the list is composed
// from the two latest snapshots instead of being mutated in place.
function rebuildFileList() {
  const recordingFiles = state.recordings.map((entry) => {
    const name = String(entry?.name || "aufnahme.mp4");
    const createdAt = new Date(String(entry?.createdAt || ""));
    return {
      id: `recording:${name}`,
      name,
      sizeLabel: formatFileSize(entry?.sizeBytes),
      dateLabel: Number.isNaN(createdAt.getTime()) ? "-" : formatDate(createdAt),
      downloadUrl: `${state.apiBase}${String(entry?.downloadPath || "")}`,
      source: "recording",
      transferState: "recording",
      transferMessage: "Kamera-Aufnahme auf dem Pi",
    };
  });

  const programFiles = state.programs.map((program) => {
    const name = String(program?.name || "programm.nc");
    const modifiedAt = new Date(String(program?.modifiedAt || ""));
    return {
      id: `program:${name}`,
      name,
      sizeLabel: formatFileSize(program?.sizeBytes),
      dateLabel: Number.isNaN(modifiedAt.getTime()) ? "-" : formatDate(modifiedAt),
      downloadUrl: `${state.apiBase}/api/programs/${encodeURIComponent(name)}/download`,
      source: "server",
      transferState: String(program?.transferState || "pending"),
      transferMessage: String(program?.transferMessage || ""),
    };
  });

  state.files = [...recordingFiles, ...programFiles];
}

function applyProgramsSnapshot(snapshot) {
  const payload = snapshot && typeof snapshot === "object" ? snapshot : {};
  state.programs = Array.isArray(payload.programs) ? payload.programs : [];
  rebuildFileList();
  state.programController = payload.controller && typeof payload.controller === "object"
    ? payload.controller
    : { enabled: false, configured: false, issue: "" };
  state.allowedProgramExtensions = Array.isArray(payload.allowedExtensions)
    ? payload.allowedExtensions.map((value) => String(value).toLowerCase())
    : state.allowedProgramExtensions;
}

function getTransferStateView(file) {
  const stateId = String(file?.transferState || "");
  const views = {
    transferred: { label: "Am CNC-Controller", className: "is-success" },
    transferring: { label: "Wird übertragen", className: "is-working" },
    failed: { label: "Übertragung fehlgeschlagen", className: "is-error" },
    waitingForController: { label: "Lokal bereit · Controller fehlt", className: "is-waiting" },
    pending: { label: "Lokal bereit", className: "is-pending" },
    recording: { label: "Kamera-Aufnahme", className: "is-success" },
  };
  return views[stateId] || views.pending;
}

function triggerDownload(url, fileName) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

function renderFiles() {
  dom.fileList.innerHTML = "";
  dom.fileEmptyState.hidden = state.files.length > 0;

  state.files.forEach((file) => {
    const row = document.createElement("div");
    row.className = "file-row";

    const icon = document.createElement("div");
    icon.className = "file-row__icon";
    icon.innerHTML = ICONS.file;

    const body = document.createElement("div");
    body.className = "file-row__body";

    const name = document.createElement("div");
    name.className = "file-row__name";
    name.textContent = file.name;

    const meta = document.createElement("div");
    meta.className = "file-row__meta";
    meta.textContent = `${file.sizeLabel} - ${file.dateLabel}`;

    const transferView = getTransferStateView(file);
    const transferState = document.createElement("span");
    transferState.className = `file-row__transfer ${transferView.className}`;
    transferState.textContent = transferView.label;
    transferState.title = file.transferMessage || transferView.label;

    body.appendChild(name);
    body.appendChild(meta);
    body.appendChild(transferState);

    const actions = document.createElement("div");
    actions.className = "file-row__actions";

    if (file.downloadUrl) {
      const downloadBtn = document.createElement("button");
      downloadBtn.className = "row-icon-btn";
      downloadBtn.type = "button";
      downloadBtn.title = "Herunterladen";
      downloadBtn.innerHTML = `<span class="file-row__action-icon">${ICONS.download}</span>`;
      downloadBtn.addEventListener("click", () => {
        triggerDownload(file.downloadUrl, file.name);
      });
      actions.appendChild(downloadBtn);
    }

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "row-icon-btn row-icon-btn--danger";
    deleteBtn.type = "button";
    deleteBtn.title = "Loeschen";
    deleteBtn.innerHTML = `<span class="file-row__action-icon">${ICONS.trash}</span>`;
    deleteBtn.addEventListener("click", () => {
      void deleteFile(file);
    });
    actions.appendChild(deleteBtn);

    row.appendChild(icon);
    row.appendChild(body);
    row.appendChild(actions);
    dom.fileList.appendChild(row);
  });
}

function getTaskDueDetails(task) {
  const taskId = String(task?.id || "");
  const overdue = state.dueTaskIds.includes(taskId);
  if (overdue) {
    return {
      label: "Ueberfaellig",
      priority: "high",
      overdue: true,
    };
  }

  const intervalType = String(task?.intervalType || "").trim();
  const intervalValue = Number(task?.intervalValue);
  if (intervalType === "runtimeHours" && Number.isFinite(intervalValue)) {
    const completionSec = Math.max(0, Number(task?.spindleRuntimeSecAtCompletion) || 0);
    const elapsedSec = Math.max(0, state.spindleRuntimeSec - completionSec);
    const remainingHours = intervalValue - elapsedSec / 3600;
    if (remainingHours <= 1) {
      return { label: "Heute", priority: "high", overdue: false };
    }
    if (remainingHours <= 8) {
      return { label: `In ${remainingHours.toFixed(1)} h`, priority: "medium", overdue: false };
    }
    return { label: `In ${Math.ceil(remainingHours)} h`, priority: "low", overdue: false };
  }

  if (intervalType === "backendStarts" && Number.isFinite(intervalValue)) {
    const completionCount = Math.max(0, Number(task?.backendStartCountAtCompletion) || 0);
    const remainingStarts = intervalValue - Math.max(0, state.backendStartCount - completionCount);
    if (remainingStarts <= 1) {
      return { label: "Beim nächsten Start", priority: "medium", overdue: false };
    }
    return { label: `In ${Math.ceil(remainingStarts)} Starts`, priority: "low", overdue: false };
  }

  if (intervalType === "calendarMonths" && Number.isFinite(intervalValue)) {
    const lastCompletedAt = String(task?.lastCompletedAt || "").trim();
    if (lastCompletedAt) {
      const completedAt = new Date(lastCompletedAt);
      if (!Number.isNaN(completedAt.getTime())) {
        const dueAt = addMonths(completedAt, intervalValue);
        const diffDays = Math.ceil((dueAt.getTime() - Date.now()) / 86_400_000);
        if (diffDays <= 1) {
          return { label: diffDays <= 0 ? "Heute" : "Morgen", priority: "medium", overdue: false };
        }
        if (diffDays <= 7) {
          return { label: `In ${diffDays} Tagen`, priority: "medium", overdue: false };
        }
        return { label: formatDate(dueAt), priority: "low", overdue: false };
      }
    }
  }

  return { label: "Manuell", priority: "low", overdue: false };
}

function compareTaskPriority(left, right) {
  const order = { high: 0, medium: 1, low: 2 };
  return (order[left] ?? 99) - (order[right] ?? 99);
}

function renderTasks() {
  dom.taskList.innerHTML = "";
  dom.taskEmptyState.hidden = state.tasks.length > 0;

  const taskView = state.tasks
    .map((task) => {
      const due = getTaskDueDetails(task);
      return {
        task,
        due,
        isWorking: completingTaskIds.has(String(task?.id || "")),
      };
    })
    .sort((left, right) => {
      if (left.due.overdue !== right.due.overdue) {
        return left.due.overdue ? -1 : 1;
      }
      const priorityDiff = compareTaskPriority(left.due.priority, right.due.priority);
      if (priorityDiff !== 0) {
        return priorityDiff;
      }
      return String(left.task?.title || "").localeCompare(String(right.task?.title || ""), "de");
    });

  taskView.forEach(({ task, due, isWorking }) => {
    const taskId = String(task?.id || "");
    const isDone = completedTaskIds.has(taskId);
    const row = document.createElement("div");
    row.className = "task-row";
    if (due.overdue) {
      row.classList.add("is-overdue");
    }
    if (isDone) {
      row.classList.add("is-done");
    }

    const checkBtn = document.createElement("button");
    checkBtn.className = "task-check";
    if (isDone) {
      checkBtn.classList.add("is-done");
    }
    if (isWorking) {
      checkBtn.classList.add("is-working");
    }
    checkBtn.type = "button";
    checkBtn.title = "Wartung als erledigt markieren";
    if (isDone || isWorking) {
      checkBtn.innerHTML = `<span class="task-row__check-icon">${ICONS.check}</span>`;
    }
    checkBtn.addEventListener("click", () => {
      void completeMaintenanceTask(taskId);
    });

    const body = document.createElement("div");
    body.className = "task-row__body";

    const title = document.createElement("div");
    title.className = "task-row__title";
    title.textContent = String(task?.title || task?.id || "Aufgabe");

    const meta = document.createElement("div");
    meta.className = "task-row__meta";

    const priority = document.createElement("span");
    priority.className = `priority-pill is-${due.priority}`;
    priority.textContent = due.priority === "high" ? "Hoch" : due.priority === "medium" ? "Mittel" : "Niedrig";

    const dueText = document.createElement("span");
    dueText.className = "task-row__due";
    if (due.overdue) {
      dueText.classList.add("is-overdue");
    }
    dueText.textContent = due.label;

    meta.appendChild(priority);
    meta.appendChild(dueText);

    body.appendChild(title);
    body.appendChild(meta);

    row.appendChild(checkBtn);
    row.appendChild(body);
    dom.taskList.appendChild(row);
  });
}

function renderAll() {
  renderStatusStrip();
  renderToolbar();
  renderCamera();
  renderLoads();
  renderTabs();
  renderFiles();
  renderTasks();
}

function applyHardwareSnapshot(snapshot) {
  const relayBoard = snapshot?.actuators?.relayBoard;
  const channels = relayBoard && typeof relayBoard === "object" ? relayBoard.channels : null;
  if (channels && typeof channels === "object") {
    state.lightOn = !!channels.light?.on;
    state.spindleFanOn = !!channels.fan?.on;
    state.enclosureFanOn = !!(channels.enclosureFan?.on ?? channels.relay3?.on);
    state.enclosureFanAvailable = !!(channels.enclosureFan?.available ?? channels.relay3?.available);
    state.eStopEngaged = !!(channels.eStop?.engaged ?? channels.eStop?.on);
    state.hardwareEStopEngaged = !!channels.eStop?.hardwareInputEngaged;
    state.eStopResetLocked = !!channels.eStop?.resetLocked;
    state.hardwareEStopInputIds = Array.isArray(channels.eStop?.triggeredInputIds)
      ? channels.eStop.triggeredInputIds.map((inputId) => String(inputId))
      : [];
  } else {
    state.enclosureFanAvailable = false;
    state.enclosureFanOn = false;
    state.hardwareEStopEngaged = false;
    state.eStopResetLocked = false;
    state.hardwareEStopInputIds = [];
  }
}

function applyMachineStatus(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return;
  }
  state.machineStatus = String(snapshot.effectiveStatus || "IDLE").toUpperCase();
  state.maintenanceDue = !!snapshot.maintenanceDue;
  state.warmupDue = !!snapshot.warmupDue;
  state.dueTaskIds = Array.isArray(snapshot.maintenanceDueTaskIds)
    ? snapshot.maintenanceDueTaskIds.map((taskId) => String(taskId))
    : [];
  state.spindleRuntimeSec = Math.max(0, Math.floor(Number(snapshot.spindleRuntimeSec) || 0));
  state.backendStartCount = Math.max(0, Math.floor(Number(snapshot.backendStartCount) || 0));
  if (snapshot.spindleRunning !== undefined) {
    state.spindleRunning = !!snapshot.spindleRunning;
  }
  if (snapshot.eStopEngaged !== undefined) {
    state.eStopEngaged = !!snapshot.eStopEngaged;
  }
  if (snapshot.hardwareEStopEngaged !== undefined) {
    state.hardwareEStopEngaged = !!snapshot.hardwareEStopEngaged;
  }
  if (snapshot.eStopResetLocked !== undefined) {
    state.eStopResetLocked = !!snapshot.eStopResetLocked;
  }
  state.hardwareEStopInputIds = Array.isArray(snapshot.hardwareEStopInputIds)
    ? snapshot.hardwareEStopInputIds.map((inputId) => String(inputId))
    : state.hardwareEStopInputIds;
}

function applyTasks(tasksPayload) {
  state.tasks = (Array.isArray(tasksPayload) ? tasksPayload : [])
    .filter((t) => String(t?.id || "").trim() !== "spindle-warmup");
}

function buildCameraWhepUrl(snapshot) {
  const baseUrl = new URL(state.cameraStreamBase || window.location.origin);
  const webrtcPort = Number(snapshot?.webrtcPort || 0);
  if (Number.isFinite(webrtcPort) && webrtcPort > 0) {
    baseUrl.port = String(webrtcPort);
  }
  baseUrl.search = "";
  baseUrl.hash = "";

  const rawWhepPath = String(snapshot?.whepPath || snapshot?.whepUrl || "").trim();
  if (rawWhepPath) {
    return new URL(rawWhepPath, baseUrl).toString();
  }

  const streamPath = String(snapshot?.streamPath || "camera").trim().replace(/^\/+|\/+$/g, "");
  if (!streamPath) {
    return "";
  }

  const encodedPath = streamPath
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  baseUrl.pathname = `/${encodedPath}/whep`;
  return baseUrl.toString();
}

function applyCameraStatus(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return;
  }
  state.cameraTransport = String(snapshot.transport || "").trim();
  state.cameraAvailable = !!snapshot.available;
  state.cameraDevicePath = String(snapshot.devicePath || "").trim();
  state.cameraError = String(snapshot.error || "").trim();

  const nextWhepUrl =
    state.cameraAvailable && state.cameraTransport === "webrtc"
      ? buildCameraWhepUrl(snapshot)
      : "";

  if (nextWhepUrl !== state.cameraWhepUrl) {
    state.cameraWhepUrl = nextWhepUrl;
    state.cameraLoaded = false;
    stopCameraReader(!nextWhepUrl);
  }

  if (!state.cameraWhepUrl && state.recordingActive) {
    stopRecording(false);
  }
}

async function fetchJson(path) {
  const response = await fetch(`${state.apiBase}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function refreshStaticData() {
  if (state.pollingBusy) {
    return;
  }
  state.pollingBusy = true;
  try {
    const cameraStatusPath = shouldEnsureCameraStream() ? "/api/camera/status?ensure=1" : "/api/camera/status";
    const [hardware, machineStatus, maintenanceTasks, cameraStatus, programsSnapshot, recordingStatus] =
      await Promise.all([
        fetchJson("/api/hardware?refresh=1"),
        fetchJson("/api/machine/status"),
        fetchJson("/api/maintenance/tasks"),
        fetchJson(cameraStatusPath),
        fetchJson("/api/programs"),
        fetchJson("/api/camera/recording"),
      ]);

    applyHardwareSnapshot(hardware);
    applyMachineStatus(machineStatus);
    applyTasks(maintenanceTasks?.tasks);
    applyCameraStatus(cameraStatus);
    applyRecordingStatus(recordingStatus);
    applyProgramsSnapshot(programsSnapshot);
    renderAll();
  } catch (_error) {
    showToast("Backend momentan nicht erreichbar.", true);
  } finally {
    state.pollingBusy = false;
  }
}

function pushAxesPayload(payload) {
  const axes = payload?.axes && typeof payload.axes === "object" ? payload.axes : payload;
  AXIS_KEYS.forEach((axis) => {
    state.axes[axis] = clampPercent(axes?.[axis]);
  });
  renderStatusStrip();
  renderLoads();
}

function connectAxesStream() {
  if (!("EventSource" in window)) {
    showToast("EventSource wird im Browser nicht unterstuetzt.", true);
    return;
  }

  if (axesSource) {
    axesSource.close();
  }

  axesSource = new EventSource(`${state.apiBase}/api/axes/stream?intervalMs=500`);
  axesSource.addEventListener("axes", (event) => {
    try {
      pushAxesPayload(JSON.parse(event.data || "{}"));
    } catch (_error) {
      // Ignore malformed SSE payloads.
    }
  });

  axesSource.onerror = () => {
    if (axesSource) {
      axesSource.close();
      axesSource = null;
    }
    window.setTimeout(connectAxesStream, 1500);
  };
}

async function postJson(path, body) {
  const response = await fetch(`${state.apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function postRelay(path, body, successMessage) {
  try {
    const payload = await postJson(path, body);
    if (payload?.relayBoard) {
      applyHardwareSnapshot({ actuators: { relayBoard: payload.relayBoard } });
      renderAll();
    }
    showToast(successMessage);
    void refreshStaticData();
  } catch (error) {
    const message = error instanceof Error && error.message ? error.message : "Aktion fehlgeschlagen.";
    showToast(message, true);
  }
}

async function completeMaintenanceTask(taskId) {
  const normalizedTaskId = String(taskId || "").trim();
  if (!normalizedTaskId || completingTaskIds.has(normalizedTaskId)) {
    return;
  }

  completingTaskIds.add(normalizedTaskId);
  renderTasks();
  try {
    await postJson(`/api/maintenance/tasks/${encodeURIComponent(normalizedTaskId)}/complete`, {});
    completedTaskIds.add(normalizedTaskId);
    renderTasks();
    showToast("Wartungsaufgabe abgeschlossen.");
    await refreshStaticData();
  } catch (error) {
    completedTaskIds.delete(normalizedTaskId);
    const message = error instanceof Error && error.message ? error.message : "Aufgabe konnte nicht abgeschlossen werden.";
    showToast(message, true);
  } finally {
    completingTaskIds.delete(normalizedTaskId);
    renderTasks();
  }
}

async function deleteFile(file) {
  const deletePath =
    file?.source === "recording"
      ? `/api/camera/recordings/${encodeURIComponent(file.name)}`
      : `/api/programs/${encodeURIComponent(file?.name || "")}`;

  try {
    const response = await fetch(`${state.apiBase}${deletePath}`, { method: "DELETE" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.error || `HTTP ${response.status}`);
    }
    showToast(`Gelöscht: ${file.name}`);
    await refreshStaticData();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Datei konnte nicht gelöscht werden.", true);
  }
}

async function uploadProgramFiles(fileList) {
  const incomingFiles = Array.from(fileList || []);
  if (!incomingFiles.length || state.uploadBusy) {
    return;
  }
  const invalidFile = incomingFiles.find((file) => {
    const lowerName = String(file?.name || "").toLowerCase();
    return !state.allowedProgramExtensions.some((extension) => lowerName.endsWith(extension));
  });
  if (invalidFile) {
    showToast(`Nicht unterstütztes Dateiformat: ${invalidFile.name}`, true);
    return;
  }

  state.uploadBusy = true;
  dom.fileDropZone.classList.add("is-uploading");
  try {
    let uploadedCount = 0;
    for (const file of incomingFiles) {
      showToast(`Upload: ${file.name}`);
      const response = await fetch(
        `${state.apiBase}/api/programs/upload?name=${encodeURIComponent(file.name)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: file,
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.error || `Upload fehlgeschlagen: HTTP ${response.status}`);
      }
      uploadedCount += 1;
    }
    setActiveTab("files");
    await refreshStaticData();
    showToast(`${uploadedCount} Programmdatei(en) auf dem Pi gespeichert.`);
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Upload fehlgeschlagen.", true);
  } finally {
    state.uploadBusy = false;
    dom.fileDropZone.classList.remove("is-uploading");
  }
}

function stopRecordingTicker() {
  if (recording.timer) {
    window.clearInterval(recording.timer);
    recording.timer = null;
  }
}

function startRecordingTicker() {
  stopRecordingTicker();
  recording.timer = window.setInterval(() => {
    state.recordingSeconds += 1;
    renderToolbar();
    renderCamera();
  }, 1000);
}

function applyRecordingStatus(status) {
  const payload = status && typeof status === "object" ? status : {};
  const wasActive = state.recordingActive;

  state.recordingSupported = !!payload.available;
  state.recordingActive = !!payload.active;
  state.recordingSeconds = Math.max(0, Math.round(Number(payload.elapsedSec) || 0));
  state.recordingError = String(payload.error || "").trim();
  state.recordings = Array.isArray(payload.recordings) ? payload.recordings : [];
  rebuildFileList();

  if (state.recordingActive && !recording.timer) {
    startRecordingTicker();
  }
  if (!state.recordingActive) {
    stopRecordingTicker();
  }
  if (wasActive && !state.recordingActive && state.recordingError) {
    showToast(state.recordingError, true);
  }
}

async function postRecording(path) {
  const response = await fetch(`${state.apiBase}${path}`, { method: "POST", cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function startRecording() {
  if (state.recordingBusy) {
    return;
  }
  state.recordingBusy = true;
  renderToolbar();
  try {
    const payload = await postRecording("/api/camera/recording/start");
    applyRecordingStatus(payload.status);
    showToast("Aufnahme gestartet.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Aufnahme konnte nicht gestartet werden.", true);
  } finally {
    state.recordingBusy = false;
    renderToolbar();
    renderCamera();
    renderFiles();
    renderTabs();
  }
}

async function stopRecording() {
  if (state.recordingBusy) {
    return;
  }
  state.recordingBusy = true;
  renderToolbar();
  try {
    const payload = await postRecording("/api/camera/recording/stop");
    applyRecordingStatus(payload.status);

    const finished = payload.recording;
    if (finished && finished.name) {
      const downloadUrl = `${state.apiBase}${finished.downloadPath}`;
      triggerDownload(downloadUrl, finished.name);
      showToast(`Aufnahme gespeichert: ${finished.name}`);
      setActiveTab("files");
    }
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Aufnahme konnte nicht gestoppt werden.", true);
  } finally {
    state.recordingBusy = false;
    stopRecordingTicker();
    renderToolbar();
    renderCamera();
    renderFiles();
    renderTabs();
  }
}

function toggleRecording() {
  if (state.recordingActive) {
    void stopRecording();
  } else {
    void startRecording();
  }
}

function attachEvents() {
  dom.cameraFeed.addEventListener("playing", () => {
    if (!state.cameraAvailable) {
      return;
    }
    state.cameraLoaded = true;
    state.cameraError = "";
    renderCamera();
  });

  dom.cameraFeed.addEventListener("stalled", () => {
    if (!state.cameraAvailable || !state.cameraWhepUrl) {
      return;
    }
    state.cameraLoaded = false;
    state.cameraError = "MediaMTX/WebRTC-Stream puffert neu.";
    renderCamera();
  });

  dom.filesTabBtn.addEventListener("click", () => setActiveTab("files"));
  dom.maintenanceTabBtn.addEventListener("click", () => setActiveTab("maintenance"));

  dom.lightToggleBtn.addEventListener("click", () => {
    void postRelay("/api/hardware/light", { on: !state.lightOn }, state.lightOn ? "Licht ausgeschaltet." : "Licht eingeschaltet.");
  });

  dom.spindleFanToggleBtn.addEventListener("click", () => {
    void postRelay(
      "/api/hardware/fan",
      { on: !state.spindleFanOn },
      state.spindleFanOn ? "Spindel-Lüfter ausgeschaltet." : "Spindel-Lüfter eingeschaltet."
    );
  });

  dom.enclosureFanToggleBtn.addEventListener("click", () => {
    if (!state.enclosureFanAvailable) {
      showToast("Gehäuse-Lüfter ist aktuell nicht konfiguriert.", true);
      return;
    }
    void postRelay(
      "/api/hardware/enclosure-fan",
      { on: !state.enclosureFanOn },
      state.enclosureFanOn ? "Gehäuse-Lüfter ausgeschaltet." : "Gehäuse-Lüfter eingeschaltet."
    );
  });

  dom.estopToggleBtn.addEventListener("click", () => {
    const engage = !state.eStopEngaged;
    void postRelay(
      "/api/hardware/e-stop",
      { engaged: engage },
      engage ? "E-Stop wurde ausgeloest." : "E-Stop wurde zurueckgesetzt."
    );
  });

  dom.recordToggleBtn.addEventListener("click", toggleRecording);

  dom.fileDropZone.addEventListener("click", () => {
    dom.fileInput.click();
  });

  dom.fileDropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      dom.fileInput.click();
    }
  });

  dom.fileDropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dom.fileDropZone.classList.add("is-dragover");
  });

  dom.fileDropZone.addEventListener("dragleave", () => {
    dom.fileDropZone.classList.remove("is-dragover");
  });

  dom.fileDropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dom.fileDropZone.classList.remove("is-dragover");
    void uploadProgramFiles(event.dataTransfer?.files || []);
  });

  dom.fileInput.addEventListener("change", () => {
    void uploadProgramFiles(dom.fileInput.files || []);
    dom.fileInput.value = "";
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopCameraReader(true);
      state.cameraLoaded = false;
      renderCamera();
      return;
    }
    void refreshStaticData();
  });

  window.addEventListener("beforeunload", () => {
    if (axesSource) {
      axesSource.close();
      axesSource = null;
    }
    stopCameraReader(true);
    stopRecordingTicker();
  });
}

function startPolling() {
  window.setInterval(() => {
    void refreshStaticData();
  }, STATIC_REFRESH_MS);
}

function boot() {
  attachEvents();
  renderAll();
  void refreshStaticData();
  connectAxesStream();
  startPolling();
}

boot();
