import { createApiBase, onParentMessage, postToParent } from "../assets/modules/pageBridge.js?v=20260811-02";

const API_BASE = createApiBase();
const PAGE_SIZE = 4;
const WARMUP_VALIDITY_MS = 2 * 60 * 60 * 1000;

const taskTableBody = document.getElementById("taskTableBody");
const prevPageBtn = document.getElementById("prevPageBtn");
const nextPageBtn = document.getElementById("nextPageBtn");
const pageIndicator = document.getElementById("pageIndicator");
const layoutEl = document.querySelector(".layout");

let swipeStartX = null;
let swipeStartY = null;

const state = {
  tasks: [],
  page: 0,
  spindleRuntimeSec: 0,
  backendStartCount: 0,
  spindleRunning: false,
};

function toNumber(value, fallback = 0){
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function getHoursText(seconds, decimals = 1){
  const h = Math.max(0, toNumber(seconds, 0)) / 3600;
  return `${h.toLocaleString("de-DE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} h`;
}

function formatDateTime(isoString){
  if (!isoString) return "Noch nie";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return "Noch nie";
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function addMonths(date, months){
  const d = new Date(date.getTime());
  d.setMonth(d.getMonth() + months);
  return d;
}

function formatDurationMs(ms){
  const totalMinutes = Math.max(1, Math.round(Math.max(0, toNumber(ms, 0)) / 60000));
  if (totalMinutes < 60){
    return `${totalMinutes} min`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (minutes === 0){
    return `${hours} h`;
  }
  return `${hours} h ${minutes} min`;
}

function getWarmupDueAtMs(task){
  const lastCompletedAt = String(task?.lastCompletedAt || "").trim();
  if (!lastCompletedAt){
    return null;
  }
  const completedAt = new Date(lastCompletedAt);
  if (Number.isNaN(completedAt.getTime())){
    return null;
  }
  return completedAt.getTime() + WARMUP_VALIDITY_MS;
}

function hasAutomaticInterval(task){
  if (!task || typeof task !== "object") return false;
  const intervalType = String(task.intervalType || "").trim();
  const rawIntervalValue = task.intervalValue;
  if (intervalType === "none") return false;
  if (typeof rawIntervalValue === "string" && rawIntervalValue.trim() === "-") return false;
  return intervalType === "runtimeHours" || intervalType === "calendarMonths" || intervalType === "backendStarts";
}

function isWarmupTask(task){
  return !!task && String(task.id || "").trim() === "spindle-warmup";
}

function isTaskDue(task){
  if (!task || typeof task !== "object") return false;
  if (!hasAutomaticInterval(task)) return false;
  if (!task.lastCompletedAt) return true;

  if (isWarmupTask(task)){
    const dueAtMs = getWarmupDueAtMs(task);
    if (dueAtMs === null) return true;
    return Date.now() >= dueAtMs;
  }

  const intervalType = String(task.intervalType || "");
  const intervalValue = Math.max(1, Math.floor(toNumber(task.intervalValue, 1)));

  if (intervalType === "runtimeHours"){
    const lastSec = Math.max(0, Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0)));
    const elapsedSec = Math.max(0, state.spindleRuntimeSec - lastSec);
    return elapsedSec >= (intervalValue * 3600);
  }

  if (intervalType === "backendStarts"){
    const lastStartCount = Math.max(0, Math.floor(toNumber(task.backendStartCountAtCompletion, 0)));
    const elapsedStarts = Math.max(0, state.backendStartCount - lastStartCount);
    return elapsedStarts >= intervalValue;
  }

  if (intervalType === "calendarMonths"){
    const lastDone = new Date(task.lastCompletedAt);
    if (Number.isNaN(lastDone.getTime())) return true;
    return Date.now() >= addMonths(lastDone, intervalValue).getTime();
  }

  return true;
}

function formatInterval(task){
  if (!hasAutomaticInterval(task)){
    return "-";
  }
  const intervalValue = Math.max(1, Math.floor(toNumber(task.intervalValue, 1)));
  if (isWarmupTask(task)){
    return "2 h gültig";
  }
  if (isWarmupTask(task) && false){
    return "2h gültig";
  }
  if (task.intervalType === "runtimeHours"){
    return `Alle ${intervalValue}h`;
  }
  if (task.intervalType === "backendStarts"){
    return intervalValue <= 1 ? "Nach jedem Einschalten" : `Alle ${intervalValue} Starts`;
  }
  if (task.intervalType === "calendarMonths"){
    return `Alle ${intervalValue} Monate`;
  }
  return `Alle ${intervalValue}`;
}

function getSortedTasks(){
  return state.tasks
    .slice()
    .sort((a, b) => {
      const dueDiff = Number(isTaskDue(b)) - Number(isTaskDue(a));
      if (dueDiff !== 0) return dueDiff;
      return String(a.title || "").localeCompare(String(b.title || ""), "de");
    });
}

function findTask(taskId){
  return state.tasks.find((t) => String(t.id) === String(taskId)) || null;
}

function normalizeTaskSteps(rawSteps){
  if (!Array.isArray(rawSteps)){
    return [];
  }
  const steps = [];
  for (const step of rawSteps){
    if (!step || typeof step !== "object") continue;
    const instruction = String(step.instruction || step.text || step.title || "").trim();
    if (!instruction) continue;
    const image = String(step.image || "").trim();
    const imageAlt = String(step.imageAlt || "").trim();
    const item = { instruction };
    if (image){
      item.image = image;
    }
    if (imageAlt){
      item.imageAlt = imageAlt;
    }
    steps.push(item);
  }
  return steps;
}

function buildTaskModalPayload(task){
  const autoDue = hasAutomaticInterval(task);
  const due = autoDue && isTaskDue(task);
  const lastRuntimeSec = Math.max(0, Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0)));
  const runtimeSinceSec = task.lastCompletedAt ? Math.max(0, state.spindleRuntimeSec - lastRuntimeSec) : 0;
  const lastBackendStartCount = Math.max(0, Math.floor(toNumber(task.backendStartCountAtCompletion, 0)));
  const startsSinceCompletion = task.lastCompletedAt ? Math.max(0, state.backendStartCount - lastBackendStartCount) : 0;
  const warmupDueAtMs = isWarmupTask(task) ? getWarmupDueAtMs(task) : null;
  const lastDoneText = task.lastCompletedAt
    ? (task.intervalType === "backendStarts"
      ? `${formatDateTime(task.lastCompletedAt)} (bei Start ${lastBackendStartCount})`
      : `${formatDateTime(task.lastCompletedAt)} (bei ${getHoursText(lastRuntimeSec)})`)
    : "Noch nie";
  const sinceDoneText = task.lastCompletedAt
    ? (task.intervalType === "backendStarts"
      ? (startsSinceCompletion <= 0
        ? "seitdem kein Neustart"
        : `seitdem ${startsSinceCompletion} Neustart${startsSinceCompletion === 1 ? "" : "e"}`)
      : `vor ${getHoursText(runtimeSinceSec)} Betriebsstunden`)
    : "-";
  const modalLastDoneText = isWarmupTask(task)
    ? (task.lastCompletedAt ? formatDateTime(task.lastCompletedAt) : "Noch nie")
    : lastDoneText;
  const modalSinceDoneText = isWarmupTask(task)
    ? (task.lastCompletedAt
      ? (warmupDueAtMs !== null && Date.now() < warmupDueAtMs
        ? `noch ${formatDurationMs(warmupDueAtMs - Date.now())} gültig`
        : (warmupDueAtMs !== null
          ? `seit ${formatDurationMs(Date.now() - warmupDueAtMs)} abgelaufen`
          : "-"))
      : "-")
    : sinceDoneText;
  const modalStatusText = autoDue
    ? (isWarmupTask(task)
      ? (due ? "Warmlauf fällig" : (state.spindleRunning ? "Spindel läuft" : "In Ordnung"))
      : (due ? "Fällig" : "In Ordnung"))
    : "Manuell";

  return {
    type: "openMaintenanceTaskModal",
    taskId: String(task.id),
    title: task.title || "Wartungsaufgabe",
    intervalText: formatInterval(task),
    effortText: `${Math.max(1, Math.floor(toNumber(task.effortMin, 1)))}m`,
    statusText: autoDue ? (due ? "Fällig" : "In Ordnung") : "Manuell",
    statusText: modalStatusText,
    due,
    lastDoneText,
    lastDoneText: modalLastDoneText,
    sinceDoneText,
    sinceDoneText: modalSinceDoneText,
    description: task.description || "-",
    steps: normalizeTaskSteps(task.steps),
  };
}

function requestTaskModal(taskId){
  const task = findTask(taskId);
  if (!task) return;
  postToParent(buildTaskModalPayload(task));
}

function renderTable(){
  const sorted = getSortedTasks();
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  if (state.page >= totalPages){
    state.page = totalPages - 1;
  }
  if (state.page < 0){
    state.page = 0;
  }

  const start = state.page * PAGE_SIZE;
  const pageItems = sorted.slice(start, start + PAGE_SIZE);
  taskTableBody.innerHTML = "";

  for (const task of pageItems){
    const rowBtn = document.createElement("button");
    rowBtn.type = "button";
    rowBtn.className = `row task-row${isTaskDue(task) ? " is-due" : ""}`;
    rowBtn.dataset.taskId = String(task.id);
    rowBtn.innerHTML = `
      <div>${task.title || "-"}</div>
      <div>${formatInterval(task)}</div>
      <div>${Math.max(1, Math.floor(toNumber(task.effortMin, 1)))}m</div>
    `;
    rowBtn.addEventListener("click", () => requestTaskModal(String(task.id)));
    taskTableBody.appendChild(rowBtn);
  }

  for (let i = pageItems.length; i < PAGE_SIZE; i += 1){
    const empty = document.createElement("div");
    empty.className = "row task-row is-empty";
    empty.innerHTML = "<div>&nbsp;</div><div>&nbsp;</div><div>&nbsp;</div>";
    taskTableBody.appendChild(empty);
  }

  pageIndicator.textContent = `${state.page + 1} / ${totalPages}`;
  prevPageBtn.disabled = state.page <= 0;
  nextPageBtn.disabled = state.page >= totalPages - 1;
}

function normalizeTask(task){
  if (!task || typeof task !== "object") return null;
  const id = String(task.id || "").trim();
  if (!id) return null;
  const rawIntervalType = String(task.intervalType || "").trim();
  const rawIntervalValue = task.intervalValue;
  let intervalType = "runtimeHours";
  if (rawIntervalType === "calendarMonths"){
    intervalType = "calendarMonths";
  }
  if (rawIntervalType === "backendStarts"){
    intervalType = "backendStarts";
  }
  if (rawIntervalType === "none" || (typeof rawIntervalValue === "string" && rawIntervalValue.trim() === "-")){
    intervalType = "none";
  }
  return {
    id,
    title: String(task.title || id),
    intervalType,
    intervalValue: intervalType === "none"
      ? "-"
      : Math.max(1, Math.floor(toNumber(rawIntervalValue, 1))),
    effortMin: Math.max(1, Math.floor(toNumber(task.effortMin, 1))),
    description: String(task.description || ""),
    steps: normalizeTaskSteps(task.steps),
    lastCompletedAt: task.lastCompletedAt ? String(task.lastCompletedAt) : null,
    spindleRuntimeSecAtCompletion: Math.max(0, Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0))),
    backendStartCountAtCompletion: Math.max(0, Math.floor(toNumber(task.backendStartCountAtCompletion, 0))),
  };
}

async function loadData(){
  try{
    const [settingsRes, tasksRes] = await Promise.all([
      fetch(`${API_BASE}/api/settings`),
      fetch(`${API_BASE}/api/maintenance/tasks`),
    ]);

    let settings = null;
    if (settingsRes.ok){
      settings = await settingsRes.json();
    }

    let tasksPayload = null;
    if (tasksRes.ok){
      tasksPayload = await tasksRes.json();
    }

    state.spindleRuntimeSec = Math.max(0, Math.floor(toNumber(settings && settings.spindleRuntimeSec, 0)));
    state.backendStartCount = Math.max(0, Math.floor(toNumber(settings && settings.backendStartCount, 0)));
    state.spindleRunning = !!(settings && settings.spindleRunning);
    const rawTasks = (tasksPayload && Array.isArray(tasksPayload.tasks))
      ? tasksPayload.tasks
      : (settings && Array.isArray(settings.maintenanceTasks) ? settings.maintenanceTasks : []);

    state.tasks = rawTasks
      .filter((t) => String(t?.id || "").trim() !== "spindle-warmup")
      .map(normalizeTask)
      .filter(Boolean);
  }catch (_err){
    state.tasks = [];
  }

  renderTable();
}

prevPageBtn.addEventListener("click", () => {
  state.page -= 1;
  renderTable();
});

nextPageBtn.addEventListener("click", () => {
  state.page += 1;
  renderTable();
});

layoutEl.addEventListener("touchstart", (ev) => {
  const touch = ev.changedTouches && ev.changedTouches[0];
  if (!touch) return;
  swipeStartX = touch.clientX;
  swipeStartY = touch.clientY;
}, { passive: true });

layoutEl.addEventListener("touchend", (ev) => {
  const touch = ev.changedTouches && ev.changedTouches[0];
  if (!touch || swipeStartX === null || swipeStartY === null) return;
  const deltaX = touch.clientX - swipeStartX;
  const deltaY = touch.clientY - swipeStartY;
  swipeStartX = null;
  swipeStartY = null;
  if (Math.abs(deltaX) < 60 || Math.abs(deltaY) > 40) return;
  if (deltaX < 0 && !nextPageBtn.disabled){
    state.page += 1;
    renderTable();
  } else if (deltaX > 0 && !prevPageBtn.disabled){
    state.page -= 1;
    renderTable();
  }
}, { passive: true });

onParentMessage((msg) => {

  if (msg.type === "init"){
    if (typeof msg.spindleRuntimeSec === "number"){
      state.spindleRuntimeSec = Math.max(0, Math.floor(msg.spindleRuntimeSec));
    }
    if (typeof msg.backendStartCount === "number"){
      state.backendStartCount = Math.max(0, Math.floor(msg.backendStartCount));
    }
    if (typeof msg.spindleRunning === "boolean"){
      state.spindleRunning = msg.spindleRunning;
    }
    renderTable();
  }

  if (msg.type === "spindleRuntime" && typeof msg.seconds === "number"){
    state.spindleRuntimeSec = Math.max(0, Math.floor(msg.seconds));
    renderTable();
  }

  if (msg.type === "spindleRunning"){
    state.spindleRunning = !!msg.active;
    renderTable();
  }

  if (msg.type === "maintenanceTaskCompleted" && msg.task && typeof msg.task === "object"){
    const updated = normalizeTask(msg.task);
    if (!updated) return;
    const idx = state.tasks.findIndex((t) => String(t.id) === String(updated.id));
    if (idx >= 0){
      state.tasks[idx] = updated;
    } else {
      state.tasks.push(updated);
    }
    renderTable();
  }
});

loadData();
