import { createApiBase, fetchJson as fetchJsonFrom, onParentMessage, postToParent } from "../assets/modules/pageBridge.js?v=20260811-02";

const API_BASE = createApiBase();
const systemRuntimeSpindleValue = document.getElementById("systemRuntimeSpindleValue");
const systemRuntimeXValue = document.getElementById("systemRuntimeXValue");
const systemRuntimeYValue = document.getElementById("systemRuntimeYValue");
const systemRuntimeZValue = document.getElementById("systemRuntimeZValue");
const systemEnclosureValue = document.getElementById("systemEnclosureValue");
const systemEnclosureBar = document.getElementById("systemEnclosureBar");
const systemCpuTempValue = document.getElementById("systemCpuTempValue");
const systemCpuTempBar = document.getElementById("systemCpuTempBar");
const systemCpuLoadValue = document.getElementById("systemCpuLoadValue");
const systemCpuLoadBar = document.getElementById("systemCpuLoadBar");
const systemRamValue = document.getElementById("systemRamValue");
const systemRamBar = document.getElementById("systemRamBar");
const systemStorageValue = document.getElementById("systemStorageValue");
const systemStorageBar = document.getElementById("systemStorageBar");
const systemVersionValue = document.getElementById("systemVersionValue");
const systemSpindleLastActiveValue = document.getElementById("systemSpindleLastActiveValue");
const systemSpindleStartsValue = document.getElementById("systemSpindleStartsValue");
const openWifiConfigBtn = document.getElementById("openWifiConfigBtn");
const openDocsBtn = document.getElementById("openDocsBtn");
const openSmbGuideBtn = document.getElementById("openSmbGuideBtn");
const wifiStateDot = document.getElementById("wifiStateDot");
const wifiStateText = document.getElementById("wifiStateText");
const wifiIpText = document.getElementById("wifiIpText");
const ddcsStateDot = document.getElementById("ddcsStateDot");
const ddcsStateText = document.getElementById("ddcsStateText");
const remoteCard = document.getElementById("remoteCard");
const qrContainer = document.getElementById("qrContainer");
const remoteUrlEl = document.getElementById("remoteUrl");
const remoteHint = document.getElementById("remoteHint");
const tailscaleStateDot = document.getElementById("tailscaleStateDot");
const tailscaleStateText = document.getElementById("tailscaleStateText");
const tailscaleAddress = document.getElementById("tailscaleAddress");
const tailscaleToggleBtn = document.getElementById("tailscaleToggleBtn");
const tailscaleHint = document.getElementById("tailscaleHint");

let spindleRuntimeSec = 0;
let axisRuntimeSec = { x: 0, y: 0, z: 0 };
let systemHostname = "cncpi";
let wifiConnected = false;
let wifiSsid = "";
let wifiIssue = "";
let wifiIpAddress = "";
let lastQrValue = "";
let tailscaleConnected = false;

function setBar(el, percent){
  if (!el) return;
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  el.style.width = `${value}%`;
}

function formatHours(seconds){
  const sec = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${(sec / 3600).toFixed(1).replace(".", ",")}h`;
}

function formatTemperature(value, available){
  if (!available || !Number.isFinite(Number(value))){
    return "-";
  }
  return `${Number(value).toFixed(1).replace(".", ",")} °C`;
}

function formatPercent(value, available){
  if (!available || !Number.isFinite(Number(value))){
    return "-";
  }
  return `${Math.round(Number(value))} %`;
}

function pad2(value){
  return String(value).padStart(2, "0");
}

// Within the last day the date carries no information - only the clock time
// is shown. Older entries need the date to stay unambiguous.
function formatLastActive(rawValue){
  const raw = String(rawValue || "").trim();
  if (!raw){
    return "Noch nie";
  }
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())){
    return "-";
  }
  const time = `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  if ((Date.now() - date.getTime()) < 24 * 60 * 60 * 1000){
    return time;
  }
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.${date.getFullYear()}, ${time}`;
}

function formatCount(value){
  return String(Math.max(0, Math.floor(Number(value) || 0)));
}

function normalizeAxisRuntimeSnapshot(raw){
  const source = raw && typeof raw === "object" ? raw : {};
  return {
    x: Math.max(0, Math.floor(Number(source.x) || 0)),
    y: Math.max(0, Math.floor(Number(source.y) || 0)),
    z: Math.max(0, Math.floor(Number(source.z) || 0)),
  };
}

function renderRuntimeValues(){
  systemRuntimeSpindleValue.textContent = formatHours(spindleRuntimeSec);
  systemRuntimeXValue.textContent = formatHours(axisRuntimeSec.x);
  systemRuntimeYValue.textContent = formatHours(axisRuntimeSec.y);
  systemRuntimeZValue.textContent = formatHours(axisRuntimeSec.z);
}

function applySystemStatus(snapshot){
  const data = snapshot && typeof snapshot === "object" ? snapshot : {};
  const reportedHostname = String(data.hostname || "").trim();
  if (/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(reportedHostname)){
    systemHostname = reportedHostname;
  }
  spindleRuntimeSec = Math.max(0, Math.floor(Number(data.spindleRuntimeSec) || 0));
  axisRuntimeSec = normalizeAxisRuntimeSnapshot(data.axisRuntimeSec);
  renderRuntimeValues();

  systemEnclosureValue.textContent = formatTemperature(
    data.enclosureTemperatureC,
    !!data.enclosureTemperatureAvailable
  );
  systemCpuTempValue.textContent = formatTemperature(
    data.cpuTemperatureC,
    !!data.cpuTemperatureAvailable
  );
  systemCpuLoadValue.textContent = formatPercent(
    data.cpuUsagePercent,
    !!data.cpuUsageAvailable
  );
  systemRamValue.textContent = formatPercent(data.ramUsedPercent, !!data.ramAvailable);
  systemStorageValue.textContent = formatPercent(data.storageUsedPercent, !!data.storageAvailable);
  systemVersionValue.textContent = String(data.softwareVersion || "-").trim() || "-";
  systemSpindleLastActiveValue.textContent = formatLastActive(data.spindleLastActiveAt);
  systemSpindleStartsValue.textContent = formatCount(data.spindleStartCount);

  const bars = data.bars && typeof data.bars === "object" ? data.bars : {};
  setBar(systemEnclosureBar, bars.enclosureTemperaturePercent);
  setBar(systemCpuTempBar, bars.cpuTemperaturePercent);
  setBar(systemCpuLoadBar, bars.cpuUsagePercent);
  setBar(systemRamBar, bars.ramUsedPercent);
  setBar(systemStorageBar, bars.storageUsedPercent);
}

function setRemotePlaceholder(qrText, hintText, urlText){
  lastQrValue = "";
  remoteCard.classList.remove("is-ready");
  qrContainer.classList.add("is-placeholder");
  qrContainer.textContent = qrText;
  remoteHint.textContent = hintText;
  remoteUrlEl.textContent = urlText;
}

// The hostname stays valid across DHCP leases, so it is the address that
// The IP is encoded, not the hostname: name resolution depends on the
// router and proved unreliable in practice, an IP always works.
function renderQrCode(ip){
  if (!ip){
    setRemotePlaceholder("IP wird ermittelt", "Die Netzwerkadresse wird noch aufgebaut.", "Wird ermittelt…");
    return;
  }

  const url = `http://${ip}`;
  remoteCard.classList.add("is-ready");
  remoteHint.textContent = "QR-Code für den Direktzugriff im Heimnetz.";
  remoteUrlEl.textContent = url;

  if (url === lastQrValue){
    return;
  }

  lastQrValue = url;
  const qr = qrcode(0, "L");
  qr.addData(url, "Byte");
  qr.make();
  qrContainer.classList.remove("is-placeholder");
  qrContainer.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
}

function openWifiConfigModal(){
  postToParent({ type: "openWifiConfigModal" });
}

// Same reason as the QR code: the IP is what reliably works from Windows.
// The hostname is only the fallback until the address is known.
function currentSmbPath(){
  return `\\\\${wifiIpAddress || systemHostname}\\cnc-programs`;
}

function openSmbGuide(){
  postToParent({ type: "openSmbGuideModal", sharePath: currentSmbPath() });
}

function openDocs(){
  postToParent({ type: "openDocsModal" });
}

function setWifiStatus(connected, ssid = "", issue = "", ipAddress = ""){
  wifiConnected = !!connected;
  if (typeof ssid === "string") wifiSsid = ssid.trim();
  if (typeof issue === "string") wifiIssue = issue.trim();
  if (typeof ipAddress === "string") wifiIpAddress = ipAddress.trim();

  wifiStateDot.classList.toggle("is-on", wifiConnected);
  wifiStateDot.classList.toggle("is-off", !wifiConnected);

  if (wifiConnected){
    wifiStateText.textContent = wifiSsid ? `Verbunden mit ${wifiSsid}` : "Verbunden";
    wifiIpText.textContent = wifiIpAddress ? wifiIpAddress : "Wird ermittelt…";
    renderQrCode(wifiIpAddress);
  } else {
    wifiStateText.textContent = wifiIssue ? wifiIssue : "Nicht verbunden";
    wifiIpText.textContent = "-";
    setRemotePlaceholder(
      "WLAN verbinden",
      "QR-Code für den Direktzugriff im Heimnetz.",
      "Noch nicht verfügbar"
    );
  }
}

function applyDdcsStatus(snapshot){
  const data = snapshot && typeof snapshot === "object" ? snapshot : {};
  const configured = !!data.configured;
  const connected = !!data.connected;

  ddcsStateDot.classList.toggle("is-on", connected);
  ddcsStateDot.classList.toggle("is-off", configured && !connected);

  if (connected){
    ddcsStateText.textContent = "DDCS V4.1 verbunden";
  } else if (configured){
    ddcsStateText.textContent = "DDCS V4.1 nicht verbunden";
  } else {
    ddcsStateText.textContent = "DDCS V4.1 nicht eingerichtet";
  }
}

function applyTailscaleStatus(snapshot, actionMessage = ""){
  const data = snapshot && typeof snapshot === "object" ? snapshot : {};
  const installed = !!data.installed;
  const inProgress = !!data.operationInProgress;
  const needsLogin = !!data.needsLogin;
  tailscaleConnected = !!data.connected;

  tailscaleStateDot.classList.toggle("is-on", tailscaleConnected);
  tailscaleStateDot.classList.toggle("is-off", !tailscaleConnected);
  tailscaleToggleBtn.disabled = !installed || inProgress || needsLogin;

  if (!installed){
    tailscaleStateText.textContent = "Nicht installiert";
  } else if (inProgress){
    tailscaleStateText.textContent = data.requestedEnabled ? "Wird aktiviert…" : "Wird deaktiviert…";
  } else if (needsLogin){
    tailscaleStateText.textContent = "Einrichtung erforderlich";
  } else {
    tailscaleStateText.textContent = tailscaleConnected ? "Aktiv" : "Deaktiviert";
  }

  tailscaleToggleBtn.textContent = tailscaleConnected ? "Deaktivieren" : "Aktivieren";
  tailscaleAddress.textContent = String(data.dnsName || data.ipAddress || "Tailscale").trim();

  const error = String(data.error || "").trim();
  if (actionMessage){
    tailscaleHint.textContent = actionMessage;
  } else if (error){
    tailscaleHint.textContent = error;
  } else if (needsLogin){
    tailscaleHint.textContent = "";
  } else {
    tailscaleHint.textContent = "Sicherer Wartungszugang über Tailscale.";
  }
}

function toBool(value){
  if (typeof value === "boolean") return value;
  if (typeof value === "number" && (value === 0 || value === 1)) return Boolean(value);
  return null;
}

function fetchJson(path){
  return fetchJsonFrom(API_BASE, path);
}

async function loadSystemPageData(){
  try{
    const [systemStatus, wifiStatus, tailscaleStatus, programsStatus] = await Promise.all([
      fetchJson("/api/system/status"),
      fetchJson("/api/wifi/status"),
      fetchJson("/api/tailscale/status"),
      fetchJson("/api/programs"),
    ]);

    applySystemStatus(systemStatus);

    const connected = toBool(wifiStatus?.wifiConnected);
    const ssid = typeof wifiStatus?.wifiSsid === "string" ? wifiStatus.wifiSsid : "";
    const issue = typeof wifiStatus?.wifiIssue === "string" ? wifiStatus.wifiIssue : "";
    const ipAddress = typeof wifiStatus?.wifiIpAddress === "string" ? wifiStatus.wifiIpAddress : "";
    setWifiStatus(connected === null ? false : connected, ssid, issue, ipAddress);
    applyTailscaleStatus(tailscaleStatus);
    applyDdcsStatus(programsStatus?.controller);
  }catch (_error){
  }
}

async function toggleTailscale(){
  tailscaleToggleBtn.disabled = true;
  const action = tailscaleConnected ? "disable" : "enable";
  try{
    const response = await fetch(`${API_BASE}/api/tailscale/${action}`, {
      method: "POST",
      cache: "no-store",
    });
    const payload = await response.json();
    applyTailscaleStatus(payload.status, String(payload.message || "").trim());
  }catch (_error){
    tailscaleHint.textContent = "Tailscale ist momentan nicht erreichbar.";
    tailscaleToggleBtn.disabled = false;
  }
}

onParentMessage((msg) => {

  if (msg.type === "init" && typeof msg.spindleRuntimeSec === "number"){
    spindleRuntimeSec = Math.max(0, Math.floor(Number(msg.spindleRuntimeSec) || 0));
    renderRuntimeValues();
  }
  if (msg.type === "spindleRuntime" && typeof msg.seconds === "number"){
    spindleRuntimeSec = Math.max(0, Math.floor(Number(msg.seconds) || 0));
    renderRuntimeValues();
  }
  if (msg.type === "init"){
    const connected = toBool(msg.wifiConnected);
    const ssid = typeof msg.wifiSsid === "string" ? msg.wifiSsid : wifiSsid;
    const issue = typeof msg.wifiIssue === "string" ? msg.wifiIssue : wifiIssue;
    const ipAddress = typeof msg.wifiIpAddress === "string" ? msg.wifiIpAddress : wifiIpAddress;
    if (connected !== null){
      setWifiStatus(connected, ssid, issue, ipAddress);
    }
  }
  if (msg.type === "wifi"){
    const connected = toBool(msg.connected);
    const ssid = typeof msg.ssid === "string" ? msg.ssid : wifiSsid;
    const issue = typeof msg.issue === "string" ? msg.issue : wifiIssue;
    const ipAddress = typeof msg.wifiIpAddress === "string" ? msg.wifiIpAddress : wifiIpAddress;
    if (connected !== null){
      setWifiStatus(connected, ssid, issue, ipAddress);
    }
  }
  if (msg.type === "openWifiConfig" && msg.openModal !== false){
    openWifiConfigModal();
  }
  if (msg.type === "smbGuideClosed"){
    openSmbGuideBtn.focus();
  }
  if (msg.type === "pageShown"){
    loadSystemPageData();
  }
});

openWifiConfigBtn.addEventListener("click", openWifiConfigModal);
openSmbGuideBtn.addEventListener("click", openSmbGuide);
openDocsBtn.addEventListener("click", openDocs);
tailscaleToggleBtn.addEventListener("click", toggleTailscale);

applySystemStatus({});
setWifiStatus(wifiConnected);
applyTailscaleStatus({});
applyDdcsStatus({});
loadSystemPageData();
window.setInterval(loadSystemPageData, 5000);
