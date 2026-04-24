export function createStatusbarController({ state, statusEl, statusBarEl }) {
  function applyStatusbarState() {
    const isEstop = !!state.eStopEngaged;
    const isError = !isEstop && state.machineStatus === "ERROR";
    const isWarmup = !isEstop && !isError && !!state.warmupDue;
    const isMaintenance = !isEstop && !isError && !isWarmup && !!state.maintenanceDue;
    const isRunning =
      !isEstop && !isError && !isMaintenance && !isWarmup && state.machineStatus === "RUNNING";

    if (isEstop) {
      statusEl.textContent = "E-STOP";
      statusEl.style.letterSpacing = "0.8px";
    } else if (isError) {
      statusEl.textContent = "ERROR";
      statusEl.style.letterSpacing = "0.8px";
    } else if (isWarmup) {
      statusEl.textContent = "WARMLAUF FÄLLIG";
      statusEl.style.letterSpacing = "0.3px";
    } else if (isMaintenance) {
      statusEl.textContent = "WARTUNG FÄLLIG";
      statusEl.style.letterSpacing = "0.4px";
    } else {
      statusEl.textContent = state.machineStatus;
      statusEl.style.letterSpacing = "0.2px";
    }

    if (!statusBarEl) return;
    statusBarEl.classList.toggle("is-running", isRunning);
    statusBarEl.classList.toggle("is-error", isEstop || isError);
    statusBarEl.classList.toggle("is-estop", isEstop);
    statusBarEl.classList.toggle("is-maintenance", isWarmup || isMaintenance);
  }

  function setMachineStatus(newStatus) {
    const s = String(newStatus || "").toUpperCase();
    state.machineStatus = s || "IDLE";
    applyStatusbarState();
  }

  function setMaintenanceDue(isDue) {
    state.maintenanceDue = !!isDue;
    applyStatusbarState();
  }

  return {
    applyStatusbarState,
    setMachineStatus,
    setMaintenanceDue,
  };
}
