export function createStatusbarController({ state, statusEl, statusBarEl }) {
  function applyStatusbarState() {
    const isEstop = !!state.eStopEngaged;
    const isError = !isEstop && state.machineStatus === "ERROR";
    const isRunning = !isEstop && !isError && state.machineStatus === "RUNNING";
    const hasMaintenance = !!state.maintenanceDue || !!state.warmupDue;
    const isMaintenance = !isEstop && !isError && !isRunning && hasMaintenance;

    if (isEstop) {
      statusEl.textContent = "E-STOP";
      statusEl.style.letterSpacing = "0.8px";
    } else if (isError) {
      statusEl.textContent = "ERROR";
      statusEl.style.letterSpacing = "0.8px";
    } else if (isRunning) {
      statusEl.textContent = "RUNNING";
      statusEl.style.letterSpacing = "0.2px";
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
    statusBarEl.classList.toggle("is-maintenance", isMaintenance);
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
