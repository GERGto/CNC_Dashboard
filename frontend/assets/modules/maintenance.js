export function createMaintenanceController({
  apiBase,
  state,
  elements,
  onSetMaintenanceDue,
  onTaskCompleted,
}) {
  const WARMUP_VALIDITY_MS = 2 * 60 * 60 * 1000;
  const {
    taskModal,
    taskTitle,
    detailInterval,
    detailEffort,
    detailStatus,
    detailLastDone,
    detailSinceDone,
    detailDescription,
    detailGuideInfo,
    tabOverview,
    tabGuide,
    panelOverview,
    panelGuide,
    guideContent,
    guideEmpty,
    guideStepMeta,
    guideStepText,
    guideStepImage,
    taskClose,
    guidePrev,
    guideNext,
    taskDone,
    dueDot,
  } = elements;

  let modalTaskId = null;
  let modalTab = "overview";
  let modalSteps = [];
  let modalStepIndex = 0;
  let tasksCache = [];
  let listenersBound = false;
  let guideTouchStartX = null;
  let guideTouchStartY = null;

  function toNumber(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function addMonths(date, months) {
    const d = new Date(date.getTime());
    d.setMonth(d.getMonth() + months);
    return d;
  }

  function isWarmupTask(task) {
    return !!task && String(task.id || "").trim() === "spindle-warmup";
  }

  function getWarmupDueAtMs(task) {
    const lastCompletedAt = String(task?.lastCompletedAt || "").trim();
    if (!lastCompletedAt) {
      return null;
    }
    const completedAt = new Date(lastCompletedAt);
    if (Number.isNaN(completedAt.getTime())) {
      return null;
    }
    return completedAt.getTime() + WARMUP_VALIDITY_MS;
  }

  function normalizeTask(task) {
    if (!task || typeof task !== "object") return null;
    const id = String(task.id || "").trim();
    if (!id) return null;

    const rawIntervalType = String(task.intervalType || "").trim();
    const rawIntervalValue = task.intervalValue;
    let intervalType = "runtimeHours";
    if (rawIntervalType === "calendarMonths") {
      intervalType = "calendarMonths";
    }
    if (rawIntervalType === "backendStarts") {
      intervalType = "backendStarts";
    }
    if (rawIntervalType === "none" || (typeof rawIntervalValue === "string" && rawIntervalValue.trim() === "-")) {
      intervalType = "none";
    }

    return {
      id,
      intervalType,
      intervalValue:
        intervalType === "none" ? "-" : Math.max(1, Math.floor(toNumber(rawIntervalValue, 1))),
      lastCompletedAt: task.lastCompletedAt ? String(task.lastCompletedAt) : null,
      spindleRuntimeSecAtCompletion: Math.max(
        0,
        Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0))
      ),
      backendStartCountAtCompletion: Math.max(
        0,
        Math.floor(toNumber(task.backendStartCountAtCompletion, 0))
      ),
    };
  }

  function hasAutomaticInterval(task) {
    if (!task || typeof task !== "object") return false;
    const intervalType = String(task.intervalType || "").trim();
    const intervalValue = task.intervalValue;
    if (intervalType === "none") return false;
    if (typeof intervalValue === "string" && intervalValue.trim() === "-") return false;
    return intervalType === "runtimeHours" || intervalType === "calendarMonths" || intervalType === "backendStarts";
  }

  function isTaskDue(task) {
    if (!task || typeof task !== "object") return false;
    if (!hasAutomaticInterval(task)) return false;
    if (!task.lastCompletedAt) return true;

    if (isWarmupTask(task)) {
      const dueAtMs = getWarmupDueAtMs(task);
      if (dueAtMs === null) return true;
      return Date.now() >= dueAtMs;
    }

    const intervalType = String(task.intervalType || "");
    const intervalValue = Math.max(1, Math.floor(toNumber(task.intervalValue, 1)));

    if (intervalType === "runtimeHours") {
      const lastSec = Math.max(0, Math.floor(toNumber(task.spindleRuntimeSecAtCompletion, 0)));
      const elapsedSec = Math.max(0, state.spindleRuntimeSec - lastSec);
      return elapsedSec >= intervalValue * 3600;
    }

    if (intervalType === "backendStarts") {
      const lastStartCount = Math.max(0, Math.floor(toNumber(task.backendStartCountAtCompletion, 0)));
      const elapsedStarts = Math.max(0, (state.backendStartCount || 0) - lastStartCount);
      return elapsedStarts >= intervalValue;
    }

    if (intervalType === "calendarMonths") {
      const lastDone = new Date(task.lastCompletedAt);
      if (Number.isNaN(lastDone.getTime())) return true;
      return Date.now() >= addMonths(lastDone, intervalValue).getTime();
    }

    return false;
  }

  function updateDueIndicator() {
    const hasDueTask = tasksCache.some((task) => isTaskDue(task));
    if (dueDot) {
      dueDot.hidden = !hasDueTask;
    }
    onSetMaintenanceDue(!!hasDueTask);
  }

  function setTasks(tasks) {
    const list = Array.isArray(tasks) ? tasks : [];
    tasksCache = list
      .filter((t) => !isWarmupTask(t))
      .map(normalizeTask)
      .filter(Boolean);
    updateDueIndicator();
  }

  function upsertTask(task) {
    const normalized = normalizeTask(task);
    if (!normalized) return;
    const idx = tasksCache.findIndex((item) => item.id === normalized.id);
    if (idx >= 0) {
      tasksCache[idx] = normalized;
    } else {
      tasksCache.push(normalized);
    }
    updateDueIndicator();
  }

  function loadTasks() {
    return fetch(`${apiBase}/api/maintenance/tasks`)
      .then((res) => (res.ok ? res.json() : null))
      .then((payload) => {
        const tasks = payload && Array.isArray(payload.tasks) ? payload.tasks : [];
        setTasks(tasks);
      })
      .catch(() => {});
  }

  function normalizeSteps(rawSteps) {
    if (!Array.isArray(rawSteps)) {
      return [];
    }
    const steps = [];
    for (const step of rawSteps) {
      if (!step || typeof step !== "object") continue;
      const instruction = String(step.instruction || step.text || step.title || "").trim();
      const image = String(step.image || "").trim();
      const imageAlt = String(step.imageAlt || "Arbeitsschritt").trim();
      if (!instruction) continue;
      steps.push({ instruction, image, imageAlt });
    }
    return steps;
  }

  function renderGuideStep() {
    const count = modalSteps.length;
    if (count === 0) {
      guideContent.classList.remove("maintenance-guide--with-image");
      guideContent.hidden = true;
      guideEmpty.hidden = false;
      guidePrev.disabled = true;
      guideNext.disabled = true;
      return;
    }

    guideContent.hidden = false;
    guideEmpty.hidden = true;

    if (modalStepIndex < 0) {
      modalStepIndex = 0;
    }
    if (modalStepIndex > count - 1) {
      modalStepIndex = count - 1;
    }

    const step = modalSteps[modalStepIndex];
    guideStepMeta.textContent = `Schritt ${modalStepIndex + 1} / ${count}`;
    guideStepText.textContent = step.instruction || "-";

    if (step.image) {
      guideStepImage.src = step.image;
      guideStepImage.alt = step.imageAlt || "Arbeitsschritt";
      guideStepImage.hidden = false;
      guideContent.classList.add("maintenance-guide--with-image");
    } else {
      guideStepImage.src = "";
      guideStepImage.alt = "";
      guideStepImage.hidden = true;
      guideContent.classList.remove("maintenance-guide--with-image");
    }

    guidePrev.disabled = modalStepIndex <= 0;
    guideNext.disabled = modalStepIndex >= count - 1;
  }

  function setTab(tab) {
    modalTab = tab === "guide" ? "guide" : "overview";
    const isGuide = modalTab === "guide";

    tabOverview.classList.toggle("is-active", !isGuide);
    tabOverview.setAttribute("aria-selected", isGuide ? "false" : "true");
    tabOverview.setAttribute("tabindex", isGuide ? "-1" : "0");

    tabGuide.classList.toggle("is-active", isGuide);
    tabGuide.setAttribute("aria-selected", isGuide ? "true" : "false");
    tabGuide.setAttribute("tabindex", isGuide ? "0" : "-1");

    panelOverview.classList.toggle("is-active", !isGuide);
    panelOverview.setAttribute("aria-hidden", isGuide ? "true" : "false");

    panelGuide.classList.toggle("is-active", isGuide);
    panelGuide.setAttribute("aria-hidden", isGuide ? "false" : "true");

    guidePrev.hidden = !isGuide;
    guideNext.hidden = !isGuide;

    if (isGuide) {
      renderGuideStep();
      if (!guideNext.disabled) {
        guideNext.focus();
      } else if (!guidePrev.disabled) {
        guidePrev.focus();
      } else {
        taskDone.focus();
      }
      return;
    }
    taskDone.focus();
  }

  function openTaskModal(payload) {
    const data = payload && typeof payload === "object" ? payload : {};
    modalTaskId = data.taskId ? String(data.taskId) : null;
    taskTitle.textContent = String(data.title || "Wartungsaufgabe");
    detailInterval.textContent = String(data.intervalText || "-");
    detailEffort.textContent = String(data.effortText || "-");
    detailStatus.textContent = String(data.statusText || "-");
    detailStatus.classList.toggle("is-due", !!data.due);
    detailLastDone.textContent = String(data.lastDoneText || "-");
    detailSinceDone.textContent = String(data.sinceDoneText || "-");
    detailDescription.textContent = String(data.description || "-");
    modalSteps = normalizeSteps(data.steps);
    modalStepIndex = 0;
    detailGuideInfo.textContent =
      modalSteps.length > 0 ? `${modalSteps.length} Schritte` : "Keine Anleitung hinterlegt";

    taskDone.disabled = !modalTaskId;
    taskModal.classList.add("is-open");
    taskModal.setAttribute("aria-hidden", "false");
    setTab("overview");
  }

  function closeTaskModal() {
    modalTaskId = null;
    modalSteps = [];
    modalStepIndex = 0;
    modalTab = "overview";
    guideContent.classList.remove("maintenance-guide--with-image");
    taskModal.classList.remove("is-open");
    taskModal.setAttribute("aria-hidden", "true");
  }

  function completeTask() {
    if (!modalTaskId) return;
    taskDone.disabled = true;
    fetch(`${apiBase}/api/maintenance/tasks/${encodeURIComponent(modalTaskId)}/complete`, {
      method: "POST",
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data || !data.task) return;
        upsertTask(data.task);
        if (typeof onTaskCompleted === "function") {
          onTaskCompleted(data.task);
        }
        closeTaskModal();
      })
      .catch(() => {})
      .finally(() => {
        taskDone.disabled = false;
      });
  }

  function handleGuidePrev() {
    if (modalStepIndex <= 0) return;
    modalStepIndex -= 1;
    renderGuideStep();
  }

  function handleGuideNext() {
    if (modalStepIndex >= modalSteps.length - 1) return;
    modalStepIndex += 1;
    renderGuideStep();
  }

  function isTaskModalOpen() {
    return taskModal.classList.contains("is-open");
  }

  function handleDocumentKeydown(ev) {
    if (!isTaskModalOpen()) return false;

    if (ev.key === "Escape") {
      closeTaskModal();
      return true;
    }
    if (modalTab === "guide") {
      if (ev.key === "ArrowLeft" && !guidePrev.disabled) {
        guidePrev.click();
        return true;
      }
      if (ev.key === "ArrowRight" && !guideNext.disabled) {
        guideNext.click();
        return true;
      }
    }
    return false;
  }

  function attachEventHandlers() {
    if (listenersBound) return;
    listenersBound = true;

    taskClose.addEventListener("click", closeTaskModal);
    tabOverview.addEventListener("click", () => setTab("overview"));
    tabGuide.addEventListener("click", () => setTab("guide"));
    guidePrev.addEventListener("click", handleGuidePrev);
    guideNext.addEventListener("click", handleGuideNext);
    taskDone.addEventListener("click", completeTask);
    taskModal.addEventListener("click", (ev) => {
      if (ev.target && ev.target.dataset && ev.target.dataset.close) {
        closeTaskModal();
      }
    });
    panelGuide.addEventListener("touchstart", (ev) => {
      const touch = ev.changedTouches && ev.changedTouches[0];
      if (!touch) return;
      guideTouchStartX = touch.clientX;
      guideTouchStartY = touch.clientY;
    }, { passive: true });
    panelGuide.addEventListener("touchend", (ev) => {
      const touch = ev.changedTouches && ev.changedTouches[0];
      if (!touch || guideTouchStartX === null || guideTouchStartY === null) return;
      const deltaX = touch.clientX - guideTouchStartX;
      const deltaY = touch.clientY - guideTouchStartY;
      guideTouchStartX = null;
      guideTouchStartY = null;
      if (Math.abs(deltaX) < 60 || Math.abs(deltaY) > 40 || modalTab !== "guide") return;
      if (deltaX < 0) {
        handleGuideNext();
      } else {
        handleGuidePrev();
      }
    }, { passive: true });
  }

  return {
    attachEventHandlers,
    handleDocumentKeydown,
    loadTasks,
    onSpindleRuntimeChanged: updateDueIndicator,
    openTaskModal,
    closeTaskModal,
  };
}
