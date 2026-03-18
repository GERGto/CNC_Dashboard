export function createStatusbarController({ state, statusEl, statusBarEl }) {
  function applyStatusbarState() {
    const isError = state.machineStatus === "ERROR";
    const isMaintenance = !isError && state.maintenanceDue;
    const isRunning = !isError && !isMaintenance && state.machineStatus === "RUNNING";

    if (isError) {
      statusEl.textContent = "ERROR";
      statusEl.style.letterSpacing = "0.8px";
    } else if (isMaintenance) {
      statusEl.textContent = "WARTUNG FÄLLIG";
      statusEl.style.letterSpacing = "0.4px";
    } else {
      statusEl.textContent = state.machineStatus;
      statusEl.style.letterSpacing = "0.2px";
    }

    if (!statusBarEl) return;
    statusBarEl.classList.toggle("is-running", isRunning);
    statusBarEl.classList.toggle("is-error", isError);
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
