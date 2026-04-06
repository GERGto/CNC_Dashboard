export function createWifiEastereggController({
  overlayEl,
  imageEl = null,
  tapTarget = 5,
  tapWindowMs = 1600,
  durationMs = 12000,
}) {
  let tapTimestamps = [];
  let eastereggTimer = null;
  let imageReady = false;

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
  }

  function show() {
    if (eastereggTimer) {
      clearTimeout(eastereggTimer);
      eastereggTimer = null;
    }
    ensureImageLoaded();
    overlayEl.hidden = false;
    overlayEl.setAttribute("aria-hidden", "false");
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
