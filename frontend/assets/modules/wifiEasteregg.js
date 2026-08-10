export function createWifiEastereggController({
  overlayEl,
  imageEl = null,
  tapTarget = 5,
  tapWindowMs = 1600,
  durationMs = 12000,
  onActiveChange = null,
}) {
  let tapTimestamps = [];
  let eastereggTimer = null;
  let imageReady = false;
  let active = false;

  // Announce the mode so the LED strip can join in. Never let a failing
  // notification break the overlay itself.
  function notifyActive(nextActive) {
    if (active === nextActive) {
      return;
    }
    active = nextActive;
    if (typeof onActiveChange !== "function") {
      return;
    }
    try {
      onActiveChange(nextActive, durationMs);
    } catch (_error) {
      // Ignore: the visual easter egg works without the strip.
    }
  }

  function ensureImageLoaded() {
    if (!imageEl || imageReady) {
      return;
    }
    const deferredSrc = String(imageEl.dataset.src || "").trim();
    if (!deferredSrc) {
      imageReady = true;
      return;
    }
    imageEl.src = deferredSrc;
    imageReady = true;
  }

  function hide() {
    if (eastereggTimer) {
      clearTimeout(eastereggTimer);
      eastereggTimer = null;
    }
    overlayEl.hidden = true;
    overlayEl.setAttribute("aria-hidden", "true");
    notifyActive(false);
  }

  function show() {
    if (eastereggTimer) {
      clearTimeout(eastereggTimer);
      eastereggTimer = null;
    }
    ensureImageLoaded();
    overlayEl.hidden = false;
    overlayEl.setAttribute("aria-hidden", "false");
    notifyActive(true);
    eastereggTimer = setTimeout(() => {
      hide();
    }, durationMs);
  }

  function registerRapidTap() {
    const now = Date.now();
    tapTimestamps.push(now);
    tapTimestamps = tapTimestamps.filter((ts) => (now - ts) <= tapWindowMs);
    if (tapTimestamps.length >= tapTarget) {
      tapTimestamps = [];
      show();
    }
  }

  return {
    show,
    hide,
    registerRapidTap,
  };
}
