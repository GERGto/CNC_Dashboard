import { createApiBase, onParentMessage, postToParent } from "../assets/modules/pageBridge.js?v=20260811-02";

const API_BASE = createApiBase();
const axisKeys = ["spindle", "x", "y", "z"];
const sensorAxisKeys = ["spindle", "x", "y", "z"];
const axisDisplayNames = {
  spindle: "Spindel",
  x: "X Achse",
  y: "Y Achse",
  z: "Z Achse"
};
const AXIS_CALIBRATION_LONG_PRESS_MS = 650;
const AXIS_CALIBRATION_LIMITS = {
  spindle: { minA: 0, maxA: 30 },
  x: { minA: 0, maxA: 10 },
  y: { minA: 0, maxA: 10 },
  z: { minA: 0, maxA: 10 }
};
const AXIS_CALIBRATION_DEFAULTS = {
  spindle: { minA: 0, maxA: 30 },
  x: { minA: 0, maxA: 10 },
  y: { minA: 0, maxA: 10 },
  z: { minA: 0, maxA: 10 }
};
const ENCLOSURE_TEMP_MIN_C = 20;
const ENCLOSURE_TEMP_MAX_C = 55;
const ENCLOSURE_TEMP_REFRESH_MS = 5000;
const axisState = {};

const spindleValueEl = document.getElementById("spindleValue");
const spindleGauge = document.getElementById("spindleGauge");
const spindleGaugeFill = spindleGauge.querySelector(".arc-gauge__fill");
const spindleLoadCard = document.getElementById("spindleLoadCard");
const enclosureTempGauge = document.getElementById("enclosureTempGauge");
const enclosureTempGaugeFill = enclosureTempGauge.querySelector(".arc-gauge__fill");
const enclosureTempValueEl = document.getElementById("enclosureTempValue");

const axisValueEls = {
  spindle: document.getElementById("axis-value-spindle"),
  x: document.getElementById("axis-value-x"),
  y: document.getElementById("axis-value-y"),
  z: document.getElementById("axis-value-z")
};

const cardEls = {
  spindle: document.querySelector('.axis-card[data-axis="spindle"]'),
  x: document.querySelector('.axis-card[data-axis="x"]'),
  y: document.querySelector('.axis-card[data-axis="y"]'),
  z: document.querySelector('.axis-card[data-axis="z"]')
};
const axesCanvas = document.getElementById("axesCanvas");
const axesContext = axesCanvas ? axesCanvas.getContext("2d") : null;
const axisColors = {
  spindle: "#000000",
  x: "#0d5b8a",
  y: "#1c7b35",
  z: "#8a3d0d"
};

const axisValues = { spindle: 0, x: 0, y: 0, z: 0 };
const axisCurrentAmps = { spindle: null, x: null, y: null, z: null };
const axisAvailability = { spindle: false, x: false, y: false, z: false };
const axisLoadCalibration = cloneAxisCalibrationMap(AXIS_CALIBRATION_DEFAULTS);
const history = {
  spindle: [],
  x: [],
  y: [],
  z: []
};
let enclosureTempAvailable = false;
let HISTORY_WINDOW_MS = 60000;
let pageActive = true;
let chartBatchDepth = 0;
let chartDrawQueued = true;
let animationFrameId = 0;
let lastAnimationTs = 0;
let lastChartRenderTs = 0;
let axesCanvasWidth = 0;
let axesCanvasHeight = 0;
let spindleGaugeTargetValue = 0;
let spindleGaugeDisplayValue = 0;
let enclosureTempTargetC = ENCLOSURE_TEMP_MIN_C;
let enclosureTempDisplayC = ENCLOSURE_TEMP_MIN_C;
let graphPressTimer = null;
let settingsSaveTimer = null;
let axisSaveTimer = null;
let activeAxisCalibrationModalAxis = null;
const axisPressTimers = {};
const axisLongPressActive = {};
const axisSuppressClickUntilMs = {};
const axisLabelLeft = document.getElementById("axisLabelLeft");
const axisLabelMid = document.getElementById("axisLabelMid");
const axisLabelRight = document.getElementById("axisLabelRight");
const axesChart = document.querySelector(".axes-chart");
const axisCalibrationUi = {
  spindle: {
    modal: document.getElementById("axisCalibrationModalSpindle"),
    current: document.getElementById("axisCalibrationCurrentSpindle"),
    percent: document.getElementById("axisCalibrationPercentSpindle"),
    error: document.getElementById("axisCalibrationErrorSpindle"),
    minSlider: document.getElementById("axisCalibrationMinSliderSpindle"),
    maxSlider: document.getElementById("axisCalibrationMaxSliderSpindle"),
    minValue: document.getElementById("axisCalibrationMinValueSpindle"),
    maxValue: document.getElementById("axisCalibrationMaxValueSpindle"),
    hint: document.getElementById("axisCalibrationHintSpindle"),
    close: document.getElementById("axisCalibrationCloseSpindle"),
    save: document.getElementById("axisCalibrationSaveSpindle")
  },
  x: {
    modal: document.getElementById("axisCalibrationModalX"),
    current: document.getElementById("axisCalibrationCurrentX"),
    percent: document.getElementById("axisCalibrationPercentX"),
    error: document.getElementById("axisCalibrationErrorX"),
    minSlider: document.getElementById("axisCalibrationMinSliderX"),
    maxSlider: document.getElementById("axisCalibrationMaxSliderX"),
    minValue: document.getElementById("axisCalibrationMinValueX"),
    maxValue: document.getElementById("axisCalibrationMaxValueX"),
    hint: document.getElementById("axisCalibrationHintX"),
    close: document.getElementById("axisCalibrationCloseX"),
    save: document.getElementById("axisCalibrationSaveX")
  },
  y: {
    modal: document.getElementById("axisCalibrationModalY"),
    current: document.getElementById("axisCalibrationCurrentY"),
    percent: document.getElementById("axisCalibrationPercentY"),
    error: document.getElementById("axisCalibrationErrorY"),
    minSlider: document.getElementById("axisCalibrationMinSliderY"),
    maxSlider: document.getElementById("axisCalibrationMaxSliderY"),
    minValue: document.getElementById("axisCalibrationMinValueY"),
    maxValue: document.getElementById("axisCalibrationMaxValueY"),
    hint: document.getElementById("axisCalibrationHintY"),
    close: document.getElementById("axisCalibrationCloseY"),
    save: document.getElementById("axisCalibrationSaveY")
  },
  z: {
    modal: document.getElementById("axisCalibrationModalZ"),
    current: document.getElementById("axisCalibrationCurrentZ"),
    percent: document.getElementById("axisCalibrationPercentZ"),
    error: document.getElementById("axisCalibrationErrorZ"),
    minSlider: document.getElementById("axisCalibrationMinSliderZ"),
    maxSlider: document.getElementById("axisCalibrationMaxSliderZ"),
    minValue: document.getElementById("axisCalibrationMinValueZ"),
    maxValue: document.getElementById("axisCalibrationMaxValueZ"),
    hint: document.getElementById("axisCalibrationHintZ"),
    close: document.getElementById("axisCalibrationCloseZ"),
    save: document.getElementById("axisCalibrationSaveZ")
  }
};

const GAUGE_CX = 180;
const GAUGE_CY = 180;
const GAUGE_R = 140;
const GAUGE_STROKE_W = 52;
const GAUGE_TOTAL_LEN = Math.PI * GAUGE_R;
const CHART_DEVICE_PIXEL_RATIO = 1;
const CHART_RENDER_INTERVAL_MS = 1000 / 50;
const GAUGE_RESPONSE_MS = 160;
const TEMP_GAUGE_RESPONSE_MS = 190;
const DISPLAY_EPSILON = 0.05;
const CHART_LEFT_FADE_FRACTION = 0.14;
const CHART_LEFT_FADE_MIN_PX = 24;

function clampCalibrationAmp(axis, value){
  const limits = AXIS_CALIBRATION_LIMITS[axis] || AXIS_CALIBRATION_LIMITS.x;
  const v = Number(value);
  if (!Number.isFinite(v)) return limits.minA;
  return Math.max(limits.minA, Math.min(limits.maxA, v));
}

function normalizeCalibrationRange(axis, rawValue, fallback){
  const defaultRange = AXIS_CALIBRATION_DEFAULTS[axis] || AXIS_CALIBRATION_DEFAULTS.x;
  const fallbackRange = fallback && typeof fallback === "object" ? fallback : defaultRange;
  let minA = clampCalibrationAmp(axis, rawValue && rawValue.minA !== undefined ? rawValue.minA : fallbackRange.minA);
  let maxA = clampCalibrationAmp(axis, rawValue && rawValue.maxA !== undefined ? rawValue.maxA : fallbackRange.maxA);
  if (maxA < minA){
    maxA = minA;
  }
  return {
    minA: Math.round(minA * 100) / 100,
    maxA: Math.round(maxA * 100) / 100
  };
}

function cloneAxisCalibrationMap(rawValue){
  const normalized = {};
  sensorAxisKeys.forEach((axis) => {
    normalized[axis] = normalizeCalibrationRange(
      axis,
      rawValue && typeof rawValue === "object" ? rawValue[axis] : null,
      AXIS_CALIBRATION_DEFAULTS[axis]
    );
  });
  return normalized;
}

function applyAxisCalibrationMap(rawValue){
  const normalized = cloneAxisCalibrationMap(rawValue);
  sensorAxisKeys.forEach((axis) => {
    axisLoadCalibration[axis] = normalized[axis];
    if (activeAxisCalibrationModalAxis !== axis){
      syncAxisCalibrationModal(axis);
    }
  });
}

function formatAmpValue(value, fractionDigits = 1){
  const v = Number(value);
  if (!Number.isFinite(v)){
    return "-- A";
  }
  return `${v.toLocaleString("de-DE", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits
  })} A`;
}

function formatPercentValue(value){
  const v = Number(value);
  if (!Number.isFinite(v)){
    return "-- %";
  }
  return `${Math.round(v)}%`;
}

function describeArc(start, end){
  const x1 = GAUGE_CX + GAUGE_R * Math.cos(start);
  const y1 = GAUGE_CY + GAUGE_R * Math.sin(start);
  const x2 = GAUGE_CX + GAUGE_R * Math.cos(end);
  const y2 = GAUGE_CY + GAUGE_R * Math.sin(end);
  const sweep = end - start > Math.PI ? 1 : 0;
  return `M ${x1} ${y1} A ${GAUGE_R} ${GAUGE_R} 0 ${sweep} 1 ${x2} ${y2}`;
}

function setupGaugePaths(gaugeEl){
  if (!gaugeEl) return;
  const bgPath = gaugeEl.querySelector(".arc-gauge__bg");
  const fillPath = gaugeEl.querySelector(".arc-gauge__fill");
  if (!bgPath || !fillPath) return;

  const arcPath = describeArc(Math.PI, 2 * Math.PI);
  bgPath.setAttribute("d", arcPath);
  bgPath.setAttribute("stroke-width", String(GAUGE_STROKE_W));
  fillPath.setAttribute("d", arcPath);
  fillPath.setAttribute("stroke-width", String(GAUGE_STROKE_W));
  fillPath.style.strokeDasharray = GAUGE_TOTAL_LEN.toFixed(2);
  fillPath.style.strokeDashoffset = GAUGE_TOTAL_LEN.toFixed(2);
}

function clampPercent(value){
  const v = Number(value);
  if (Number.isNaN(v)) return 0;
  return Math.max(0, Math.min(100, Math.round(v)));
}

function clampEnclosureTemperature(value){
  const v = Number(value);
  if (!Number.isFinite(v)) return ENCLOSURE_TEMP_MIN_C;
  return Math.max(ENCLOSURE_TEMP_MIN_C, Math.min(ENCLOSURE_TEMP_MAX_C, v));
}

function temperatureToProgress(value){
  const clamped = clampEnclosureTemperature(value);
  return ((clamped - ENCLOSURE_TEMP_MIN_C) / (ENCLOSURE_TEMP_MAX_C - ENCLOSURE_TEMP_MIN_C)) * 100;
}

function setGaugeProgress(fillEl, value){
  if (!fillEl) return;
  const progress = Math.max(0, Math.min(100, Number(value) || 0));
  fillEl.style.strokeDashoffset = (GAUGE_TOTAL_LEN * (1 - progress / 100)).toFixed(2);
}

function setSpindleValue(value){
  const v = clampPercent(value);
  if (!axisAvailability.spindle){
    spindleValueEl.textContent = "--";
    spindleGauge.dataset.state = "error";
    spindleGauge.style.setProperty("--gauge-color", "#9b9b9b");
    spindleGaugeTargetValue = 0;
    if (!pageActive){
      spindleGaugeDisplayValue = 0;
    }
    return;
  }
  spindleValueEl.textContent = `${v}%`;
  spindleGauge.dataset.state = "ok";
  spindleGauge.style.setProperty("--gauge-color", "#1a1a1a");
  spindleGaugeTargetValue = v;
}

function setEnclosureTemperatureValue(value){
  const clamped = clampEnclosureTemperature(value);
  enclosureTempValueEl.textContent = `${clamped.toLocaleString("de-DE", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}\u00B0C`;
  enclosureTempTargetC = clamped;
}

function temperatureColorFor(value){
  const temp = clampEnclosureTemperature(value);
  const ratio = (temp - ENCLOSURE_TEMP_MIN_C) / (ENCLOSURE_TEMP_MAX_C - ENCLOSURE_TEMP_MIN_C);
  if (ratio >= 0.85) return "#8c1d18";
  if (ratio >= 0.6) return "#c56a00";
  if (ratio >= 0.35) return "#5f7f14";
  return "#0d5b8a";
}

function applyEnclosureTemperaturePayload(payload){
  const available = !!(payload && payload.available);
  const temperature = Number(payload && payload.temperatureC);
  const wasAvailable = enclosureTempAvailable;

  enclosureTempAvailable = available && Number.isFinite(temperature);
  enclosureTempGauge.dataset.state = enclosureTempAvailable ? "ok" : "error";

  if (!enclosureTempAvailable){
    enclosureTempValueEl.textContent = "--.-\u00B0C";
    enclosureTempTargetC = ENCLOSURE_TEMP_MIN_C;
    enclosureTempDisplayC = ENCLOSURE_TEMP_MIN_C;
    setGaugeProgress(enclosureTempGaugeFill, 0);
    enclosureTempGauge.style.setProperty("--gauge-color", "#9b9b9b");
    return;
  }

  const nextTemperature = clampEnclosureTemperature(temperature);
  enclosureTempGauge.style.setProperty("--gauge-color", temperatureColorFor(nextTemperature));
  setEnclosureTemperatureValue(nextTemperature);
  if (!wasAvailable){
    enclosureTempDisplayC = nextTemperature;
    setGaugeProgress(enclosureTempGaugeFill, temperatureToProgress(nextTemperature));
  }
}

function loadEnclosureTemperature(){
  if (!pageActive){
    return;
  }

  fetch(`${API_BASE}/api/hardware/enclosure-temperature`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      applyEnclosureTemperaturePayload(data);
    })
    .catch(() => {
      applyEnclosureTemperaturePayload(null);
    });
}

function setAxisValue(axis, value){
  const v = clampPercent(value);
  axisValues[axis] = v;
  if (axisValueEls[axis]){
    if (axisAvailability[axis]){
      axisValueEls[axis].textContent = `${v}%`;
    } else {
      axisValueEls[axis].textContent = "--";
    }
  }
  if (axis === "spindle") setSpindleValue(v);
  if (sensorAxisKeys.includes(axis)){
    updateAxisCalibrationStatus(axis);
  }
}

function pruneHistory(now){
  axisKeys.forEach((axis) => {
    const data = history[axis];
    while (data.length && data[0].t < now - HISTORY_WINDOW_MS - 1000){
      data.shift();
    }
  });
}

function updateAxesCanvasSize(){
  if (!axesCanvas || !axesChart) return false;
  const chartStyles = window.getComputedStyle(axesChart);
  const paddingLeft = parseFloat(chartStyles.paddingLeft) || 0;
  const paddingRight = parseFloat(chartStyles.paddingRight) || 0;
  const paddingTop = parseFloat(chartStyles.paddingTop) || 0;
  const paddingBottom = parseFloat(chartStyles.paddingBottom) || 0;
  const width = Math.max(1, Math.round((axesChart.clientWidth - paddingLeft - paddingRight) * CHART_DEVICE_PIXEL_RATIO));
  const height = Math.max(1, Math.round((axesChart.clientHeight - paddingTop - paddingBottom) * CHART_DEVICE_PIXEL_RATIO));

  if (axesCanvasWidth === width && axesCanvasHeight === height){
    return false;
  }
  axesCanvasWidth = width;
  axesCanvasHeight = height;
  axesCanvas.style.width = `${width}px`;
  axesCanvas.style.height = `${height}px`;
  axesCanvas.width = width;
  axesCanvas.height = height;
  return true;
}

function drawAxisSeries(axis, now, width, height, color, lineWidth){
  if (!axesContext){
    return;
  }

  const data = history[axis];
  if (!data.length){
    return;
  }

  const windowStart = now - HISTORY_WINDOW_MS;
  let startIndex = 0;
  while (startIndex < data.length && data[startIndex].t < windowStart){
    startIndex += 1;
  }
  if (startIndex >= data.length){
    return;
  }

  const firstPoint = data[startIndex];
  const firstX = ((firstPoint.t - windowStart) / HISTORY_WINDOW_MS) * width;
  const firstY = height - ((firstPoint.v / 100) * height);

  axesContext.beginPath();
  axesContext.moveTo(firstX, firstY);

  if (startIndex === data.length - 1){
    axesContext.lineTo(width, firstY);
  } else {
    for (let index = startIndex + 1; index < data.length - 1; index += 1){
      const currentPoint = data[index];
      const nextPoint = data[index + 1];
      const currentX = ((currentPoint.t - windowStart) / HISTORY_WINDOW_MS) * width;
      const currentY = height - ((currentPoint.v / 100) * height);
      const nextX = ((nextPoint.t - windowStart) / HISTORY_WINDOW_MS) * width;
      const nextY = height - ((nextPoint.v / 100) * height);
      const controlX = (currentX + nextX) * 0.5;
      const controlY = (currentY + nextY) * 0.5;
      axesContext.quadraticCurveTo(currentX, currentY, controlX, controlY);
    }

    const lastPoint = data[data.length - 1];
    const lastX = ((lastPoint.t - windowStart) / HISTORY_WINDOW_MS) * width;
    const lastY = height - ((lastPoint.v / 100) * height);
    axesContext.lineTo(lastX, lastY);
    if (lastX < width){
      axesContext.lineTo(width, lastY);
    }
  }

  axesContext.strokeStyle = color;
  axesContext.lineWidth = lineWidth;
  axesContext.lineCap = "round";
  axesContext.lineJoin = "round";
  axesContext.stroke();
}

function applyChartLeftFade(width, height){
  if (!axesContext || width <= 0 || height <= 0){
    return;
  }

  const fadeWidth = Math.min(
    width,
    Math.max(CHART_LEFT_FADE_MIN_PX, Math.round(width * CHART_LEFT_FADE_FRACTION))
  );
  if (fadeWidth <= 0){
    return;
  }

  const gradient = axesContext.createLinearGradient(0, 0, fadeWidth, 0);
  gradient.addColorStop(0, "rgba(255, 255, 255, 0.96)");
  gradient.addColorStop(0.55, "rgba(255, 255, 255, 0.34)");
  gradient.addColorStop(1, "rgba(255, 255, 255, 0)");

  axesContext.save();
  axesContext.fillStyle = gradient;
  axesContext.fillRect(0, 0, fadeWidth, height);
  axesContext.restore();
}

function drawChart(now = performance.now()){
  if (!axesCanvas || !axesContext || !pageActive){
    return;
  }

  updateAxesCanvasSize();
  pruneHistory(now);
  if (!axesCanvasWidth || !axesCanvasHeight){
    return;
  }

  const width = axesCanvasWidth;
  const height = axesCanvasHeight;
  axesContext.clearRect(0, 0, width, height);

  axisKeys.forEach((axis) => {
    if (!axisState[axis]){
      return;
    }
    if (axis !== "spindle" && !axisAvailability[axis]){
      return;
    }

    drawAxisSeries(
      axis,
      now,
      width,
      height,
      axisColors[axis],
      axis === "spindle" ? 3 : 2
    );
  });

  applyChartLeftFade(width, height);
}

function animateDisplayValue(current, target, deltaMs, responseMs){
  if (!Number.isFinite(current) || !Number.isFinite(target)){
    return target;
  }
  if (Math.abs(target - current) <= DISPLAY_EPSILON){
    return target;
  }
  const alpha = 1 - Math.exp(-Math.max(0, deltaMs) / responseMs);
  return current + ((target - current) * alpha);
}

function updateGaugeAnimations(deltaMs){
  spindleGaugeDisplayValue = animateDisplayValue(
    spindleGaugeDisplayValue,
    spindleGaugeTargetValue,
    deltaMs,
    GAUGE_RESPONSE_MS
  );
  setGaugeProgress(spindleGaugeFill, spindleGaugeDisplayValue);

  if (enclosureTempAvailable){
    enclosureTempDisplayC = animateDisplayValue(
      enclosureTempDisplayC,
      enclosureTempTargetC,
      deltaMs,
      TEMP_GAUGE_RESPONSE_MS
    );
    setGaugeProgress(enclosureTempGaugeFill, temperatureToProgress(enclosureTempDisplayC));
  }
}

function animateFrame(now){
  if (!pageActive){
    animationFrameId = 0;
    lastAnimationTs = 0;
    lastChartRenderTs = 0;
    return;
  }

  if (!lastAnimationTs){
    lastAnimationTs = now;
    lastChartRenderTs = now - CHART_RENDER_INTERVAL_MS;
  }

  const deltaMs = Math.min(100, now - lastAnimationTs);
  lastAnimationTs = now;

  updateGaugeAnimations(deltaMs);

  if (chartDrawQueued || (now - lastChartRenderTs) >= CHART_RENDER_INTERVAL_MS){
    drawChart(now);
    chartDrawQueued = false;
    lastChartRenderTs = now;
  }

  animationFrameId = requestAnimationFrame((nextNow) => {
    animateFrame(nextNow);
  });
}

function ensureAnimationLoop(){
  if (!pageActive || animationFrameId){
    return;
  }
  animationFrameId = requestAnimationFrame((now) => {
    animateFrame(now);
  });
}

function stopAnimationLoop(){
  if (animationFrameId){
    cancelAnimationFrame(animationFrameId);
    animationFrameId = 0;
  }
  lastAnimationTs = 0;
  lastChartRenderTs = 0;
}

function requestChartDraw(){
  chartDrawQueued = true;
  if (chartBatchDepth > 0){
    return;
  }
  ensureAnimationLoop();
}

function runWithChartBatch(callback){
  chartBatchDepth += 1;
  try{
    callback();
  } finally {
    chartBatchDepth = Math.max(0, chartBatchDepth - 1);
    if (chartBatchDepth === 0 && chartDrawQueued){
      requestChartDraw();
    }
  }
}

function updateAxisLabels(windowMs){
  const seconds = Math.round(windowMs / 1000);
  const mid = Math.round(seconds / 2);
  axisLabelLeft.textContent = `${seconds}s`;
  axisLabelMid.textContent = `${mid}s`;
  axisLabelRight.textContent = "0s";
}

function updateGraphWindow(seconds, persist = false){
  const s = Math.max(10, Math.min(120, Number(seconds) || 60));
  HISTORY_WINDOW_MS = s * 1000;
  updateAxisLabels(HISTORY_WINDOW_MS);
  requestChartDraw();
  if (persist){
    scheduleSettingsSave(s);
  }
}

function scheduleSettingsSave(seconds){
  if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
  settingsSaveTimer = setTimeout(() => {
    fetch(`${API_BASE}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ graphWindowSec: seconds })
    }).catch(() => {});
  }, 300);
}

function loadSettings(){
  fetch(`${API_BASE}/api/settings`)
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      if (!data || typeof data !== "object") return;
      runWithChartBatch(() => {
        if (typeof data.graphWindowSec === "number"){
          updateGraphWindow(data.graphWindowSec, false);
        }
        if (data.axisVisibility && typeof data.axisVisibility === "object"){
          axisKeys.forEach((axis) => {
            if (data.axisVisibility[axis] !== undefined){
              setAxisEnabled(axis, !!data.axisVisibility[axis], false);
            }
          });
        }
        if (data.axisLoadCalibration && typeof data.axisLoadCalibration === "object"){
          applyAxisCalibrationMap(data.axisLoadCalibration);
        }
      });
    })
    .catch(() => {});
}

function scheduleAxisVisibilitySave(){
  if (axisSaveTimer) clearTimeout(axisSaveTimer);
  axisSaveTimer = setTimeout(() => {
    fetch(`${API_BASE}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        axisVisibility: axisState
      })
    }).catch(() => {});
  }, 300);
}

function pushHistory(now){
  axisKeys.forEach((axis) => {
    history[axis].push({ t: now, v: axisValues[axis] });
  });
  pruneHistory(now);
}

function clearGraphPress(){
  if (graphPressTimer) clearTimeout(graphPressTimer);
  graphPressTimer = null;
}

function setAxisEnabled(axis, enabled, persist = true){
  const isOn = !!enabled;
  axisState[axis] = isOn;

  if (cardEls[axis]) cardEls[axis].classList.toggle("is-off", !isOn);
  if (cardEls[axis]) cardEls[axis].setAttribute("aria-pressed", String(isOn));
  requestChartDraw();
  if (persist) scheduleAxisVisibilitySave();
}

function setAxisAvailability(axis, available){
  const isAvailable = !!available;
  axisAvailability[axis] = isAvailable;
  if (cardEls[axis]) cardEls[axis].classList.toggle("is-unavailable", !isAvailable);
  if (!isAvailable && axisValueEls[axis]){
    axisValueEls[axis].textContent = "--";
  }
  if (isAvailable && axisValueEls[axis]){
    axisValueEls[axis].textContent = `${clampPercent(axisValues[axis])}%`;
  }
  if (axis === "spindle"){
    setSpindleValue(axisValues.spindle);
  }
  requestChartDraw();
  updateAxisCalibrationStatus(axis);
}

function setAxisCurrentA(axis, currentA){
  const value = Number(currentA);
  axisCurrentAmps[axis] = Number.isFinite(value) ? value : null;
  updateAxisCalibrationStatus(axis);
}

function updateAxisCalibrationStatus(axis){
  const ui = axisCalibrationUi[axis];
  if (!ui) return;

  ui.current.textContent = axisCurrentAmps[axis] === null
    ? "-- A"
    : formatAmpValue(axisCurrentAmps[axis], 2);

  ui.percent.textContent = axisAvailability[axis]
    ? formatPercentValue(axisValues[axis])
    : "-- %";

  if (axisAvailability[axis]){
    ui.error.hidden = true;
    ui.error.textContent = "";
  } else {
    ui.error.hidden = false;
    ui.error.textContent = "Sensor momentan nicht verfügbar. Die Kalibrierung kann trotzdem gespeichert werden.";
  }
}

function syncAxisCalibrationModal(axis){
  const ui = axisCalibrationUi[axis];
  if (!ui) return;
  const limits = AXIS_CALIBRATION_LIMITS[axis] || AXIS_CALIBRATION_LIMITS.x;
  const calibration = axisLoadCalibration[axis] || AXIS_CALIBRATION_DEFAULTS[axis];
  ui.minSlider.min = String(limits.minA);
  ui.minSlider.max = String(limits.maxA);
  ui.maxSlider.min = String(limits.minA);
  ui.maxSlider.max = String(limits.maxA);
  ui.minSlider.value = String(calibration.minA);
  ui.maxSlider.value = String(calibration.maxA);
  ui.minValue.textContent = formatAmpValue(calibration.minA, 1);
  ui.maxValue.textContent = formatAmpValue(calibration.maxA, 1);
  ui.hint.textContent = `${formatAmpValue(calibration.minA, 1)} entsprechen 0%, ${formatAmpValue(calibration.maxA, 1)} entsprechen 100%.`;
  updateAxisCalibrationStatus(axis);
}

function updateAxisCalibrationDraft(axis, changedField){
  const ui = axisCalibrationUi[axis];
  if (!ui) return;

  let minA = clampCalibrationAmp(axis, ui.minSlider.value);
  let maxA = clampCalibrationAmp(axis, ui.maxSlider.value);

  if (changedField === "min" && minA > maxA){
    maxA = minA;
  }
  if (changedField === "max" && maxA < minA){
    minA = maxA;
  }

  ui.minSlider.value = String(minA);
  ui.maxSlider.value = String(maxA);
  ui.minValue.textContent = formatAmpValue(minA, 1);
  ui.maxValue.textContent = formatAmpValue(maxA, 1);
  ui.hint.textContent = `${formatAmpValue(minA, 1)} entsprechen 0%, ${formatAmpValue(maxA, 1)} entsprechen 100%.`;
}

function openAxisCalibrationModal(axis){
  if (!sensorAxisKeys.includes(axis)) return;
  const ui = axisCalibrationUi[axis];
  if (!ui) return;

  activeAxisCalibrationModalAxis = axis;
  syncAxisCalibrationModal(axis);
  ui.save.disabled = false;
  ui.save.textContent = "Speichern";
  ui.modal.classList.add("is-open");
  ui.modal.setAttribute("aria-hidden", "false");
  ui.minSlider.focus();
}

function closeAxisCalibrationModal(axis, restoreFocus = true){
  const ui = axisCalibrationUi[axis];
  if (!ui) return;

  ui.modal.classList.remove("is-open");
  ui.modal.setAttribute("aria-hidden", "true");
  ui.save.disabled = false;
  ui.save.textContent = "Speichern";
  syncAxisCalibrationModal(axis);
  if (activeAxisCalibrationModalAxis === axis){
    activeAxisCalibrationModalAxis = null;
  }
  if (restoreFocus && cardEls[axis]){
    cardEls[axis].focus();
  }
}

function persistAxisCalibration(axis){
  const ui = axisCalibrationUi[axis];
  if (!ui) return Promise.resolve();

  const nextCalibration = cloneAxisCalibrationMap(axisLoadCalibration);
  nextCalibration[axis] = normalizeCalibrationRange(
    axis,
    {
      minA: ui.minSlider.value,
      maxA: ui.maxSlider.value
    },
    axisLoadCalibration[axis]
  );

  ui.save.disabled = true;
  ui.save.textContent = "Speichert...";

  return fetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      axisLoadCalibration: nextCalibration
    })
  })
    .then((res) => res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`)))
    .then((data) => {
      if (data && data.axisLoadCalibration && typeof data.axisLoadCalibration === "object"){
        applyAxisCalibrationMap(data.axisLoadCalibration);
      } else {
        applyAxisCalibrationMap(nextCalibration);
      }
      closeAxisCalibrationModal(axis);
    })
    .catch(() => {
      ui.save.disabled = false;
      ui.save.textContent = "Speichern";
      ui.error.hidden = false;
      ui.error.textContent = "Kalibrierung konnte nicht gespeichert werden.";
    });
}

function applyAxisSensorPayload(sensorPayloads){
  runWithChartBatch(() => {
    sensorAxisKeys.forEach((axis) => {
      const payload = sensorPayloads && typeof sensorPayloads === "object" ? sensorPayloads[axis] : null;
      setAxisAvailability(axis, !!(payload && payload.available));
      setAxisCurrentA(axis, payload && payload.currentA);
      if (payload && payload.calibration && typeof payload.calibration === "object" && activeAxisCalibrationModalAxis !== axis){
        axisLoadCalibration[axis] = normalizeCalibrationRange(axis, payload.calibration, axisLoadCalibration[axis]);
        syncAxisCalibrationModal(axis);
      }
    });
  });
}

function clearAxisPress(axis){
  if (axisPressTimers[axis]) clearTimeout(axisPressTimers[axis]);
  axisPressTimers[axis] = null;
}

function attachAxisLongPress(axis, element){
  if (!element || !sensorAxisKeys.includes(axis)){
    return;
  }

  element.addEventListener("pointerdown", (ev) => {
    if (ev.pointerType === "mouse" && ev.button !== 0){
      return;
    }
    axisLongPressActive[axis] = false;
    clearAxisPress(axis);
    axisPressTimers[axis] = setTimeout(() => {
      axisLongPressActive[axis] = true;
      axisSuppressClickUntilMs[axis] = performance.now() + AXIS_CALIBRATION_LONG_PRESS_MS;
      openAxisCalibrationModal(axis);
    }, AXIS_CALIBRATION_LONG_PRESS_MS);
  });
  element.addEventListener("pointerup", () => clearAxisPress(axis));
  element.addEventListener("pointerleave", () => clearAxisPress(axis));
  element.addEventListener("pointercancel", () => clearAxisPress(axis));
}

document.querySelectorAll(".axis-card").forEach((card) => {
  const axis = card.dataset.axis;
  setAxisEnabled(axis, true, false);
  attachAxisLongPress(axis, card);
  card.addEventListener("click", () => {
    clearAxisPress(axis);
    if (axisLongPressActive[axis]){
      axisLongPressActive[axis] = false;
      return;
    }
    if (performance.now() < (axisSuppressClickUntilMs[axis] || 0)){
      return;
    }
    setAxisEnabled(axis, !axisState[axis], true);
  });
  card.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " "){
      ev.preventDefault();
      setAxisEnabled(axis, !axisState[axis], true);
    }
  });
});

attachAxisLongPress("spindle", spindleLoadCard);
if (spindleLoadCard){
  spindleLoadCard.addEventListener("click", () => {
    clearAxisPress("spindle");
    if (axisLongPressActive.spindle){
      axisLongPressActive.spindle = false;
    }
  });
}

setupGaugePaths(spindleGauge);
setupGaugePaths(enclosureTempGauge);

const initialValues = { spindle: 0, x: 0, y: 0, z: 0 };
axisKeys.forEach((key) => setAxisValue(key, initialValues[key]));
spindleGaugeDisplayValue = axisValues.spindle;
spindleGaugeTargetValue = axisValues.spindle;
setGaugeProgress(spindleGaugeFill, spindleGaugeDisplayValue);
enclosureTempDisplayC = ENCLOSURE_TEMP_MIN_C;
enclosureTempTargetC = ENCLOSURE_TEMP_MIN_C;
setGaugeProgress(enclosureTempGaugeFill, 0);
sensorAxisKeys.forEach((axis) => {
  syncAxisCalibrationModal(axis);
  axisCalibrationUi[axis].minSlider.addEventListener("input", () => updateAxisCalibrationDraft(axis, "min"));
  axisCalibrationUi[axis].maxSlider.addEventListener("input", () => updateAxisCalibrationDraft(axis, "max"));
  axisCalibrationUi[axis].close.addEventListener("click", () => closeAxisCalibrationModal(axis));
  axisCalibrationUi[axis].save.addEventListener("click", () => {
    void persistAxisCalibration(axis);
  });
  axisCalibrationUi[axis].modal.addEventListener("click", (ev) => {
    if (ev.target && ev.target.dataset && ev.target.dataset.closeAxisCalibration === axis){
      closeAxisCalibrationModal(axis);
    }
  });
});
applyAxisSensorPayload({});
pushHistory(performance.now());
updateGraphWindow(60, false);
loadSettings();
loadEnclosureTemperature();
setInterval(loadEnclosureTemperature, ENCLOSURE_TEMP_REFRESH_MS);
updateAxesCanvasSize();
requestChartDraw();
ensureAnimationLoop();

if (typeof ResizeObserver === "function" && axesChart){
  const resizeObserver = new ResizeObserver(() => {
    if (updateAxesCanvasSize()){
      requestChartDraw();
    }
  });
  resizeObserver.observe(axesChart);
} else {
  window.addEventListener("resize", () => {
    if (updateAxesCanvasSize()){
      requestChartDraw();
    }
  });
}

function applyAxesPayload(payload){
  const now = performance.now();
  axisKeys.forEach((key) => {
    if (payload && payload[key] !== undefined){
      setAxisValue(key, payload[key]);
    }
  });
  pushHistory(now);
  requestChartDraw();
}

onParentMessage((msg) => {
  if (msg.type === "axes"){
    runWithChartBatch(() => {
      const payload = (msg.axes && typeof msg.axes === "object") ? msg.axes : msg;
      if (msg.axisLoadSensors && typeof msg.axisLoadSensors === "object"){
        applyAxisSensorPayload(msg.axisLoadSensors);
      }
      applyAxesPayload(payload);
    });
  }
  if (msg.type === "setGraphWindow"){
    updateGraphWindow(msg.seconds, true);
  }
  if (msg.type === "pageShown"){
    pageActive = true;
    lastAnimationTs = 0;
    lastChartRenderTs = 0;
    loadEnclosureTemperature();
    requestChartDraw();
    ensureAnimationLoop();
  }
  if (msg.type === "pageHidden"){
    pageActive = false;
    stopAnimationLoop();
  }
});

axesChart.addEventListener("pointerdown", (ev) => {
  if (ev.pointerType === "mouse" && ev.button !== 0) return;
  clearGraphPress();
  graphPressTimer = setTimeout(() => {
    postToParent({
      type: "openGraphSettingsModal",
      seconds: Math.round(HISTORY_WINDOW_MS / 1000)
    });
  }, 600);
});
axesChart.addEventListener("pointerup", clearGraphPress);
axesChart.addEventListener("pointerleave", clearGraphPress);
axesChart.addEventListener("pointercancel", clearGraphPress);

window.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape" || !activeAxisCalibrationModalAxis){
    return;
  }
  closeAxisCalibrationModal(activeAxisCalibrationModalAxis);
});
