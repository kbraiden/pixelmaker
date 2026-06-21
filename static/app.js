"use strict";

const $ = (id) => document.getElementById(id);

let currentTab = "text";
let selectedFile = null;
let filenameEdited = false;
let currentOutputs = []; // [{ url, getLabel(), getName(base) }]

// --- Filename suggestion --------------------------------------------------
const filenameInput = $("filename");

function slugify(text) {
  return (text || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

// Mark as user-overridden once they type their own name.
filenameInput.addEventListener("input", () => {
  filenameEdited = filenameInput.value.trim().length > 0;
  updateDownloadNames();
});

function suggestFilename(source) {
  if (filenameEdited) return;
  const slug = slugify(source);
  if (slug) filenameInput.value = slug;
}

function currentBaseName() {
  return slugify(filenameInput.value) || "pixelart";
}

// Keep the download links in sync with the filename field at any time, so
// renaming after a result is shown updates the next download immediately.
function updateDownloadNames() {
  const base = currentBaseName();
  ["download-a", "download-b"].forEach((id, i) => {
    if (i < currentOutputs.length) $(id).download = currentOutputs[i].getName(base);
  });
}

// --- Tab switching -------------------------------------------------------
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab)
  );
  $("tab-text").classList.toggle("active", tab === "text");
  $("tab-image").classList.toggle("active", tab === "image");
  $("tab-background").classList.toggle("active", tab === "background");
  $("tab-walk").classList.toggle("active", tab === "walk");

  const isBackground = tab === "background";
  const isWalk = tab === "walk";
  const isIso = tab === "iso";
  $("sprite-controls").classList.toggle("hidden", isBackground || isWalk || isIso);
  $("bg-controls").classList.toggle("hidden", !isBackground);
  $("walk-controls").classList.toggle("hidden", !isWalk);
  $("iso-controls").classList.toggle("hidden", !isIso);
  $("shared-controls").classList.toggle("hidden", isWalk);
  $("ai-key-row").classList.toggle("hidden", tab === "image" || isWalk);
  $("host-key-note").classList.toggle("hidden", tab === "image" || isWalk || !hostHasKey);
  $("go").textContent = tab === "image" ? "Convert" : "Generate";

  // Only one result panel is visible at a time.
  $("tab-iso").classList.toggle("active", isIso);
  if (isWalk) {
    $("result").classList.add("hidden");
    $("iso-result").classList.add("hidden");
  } else if (isIso) {
    stopWalkPlayback();
    $("walk-result").classList.add("hidden");
    $("result").classList.add("hidden");
  } else {
    stopWalkPlayback();
    $("walk-result").classList.add("hidden");
    $("iso-result").classList.add("hidden");
  }
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// Suggest a filename from the active prompt as the user types.
$("prompt").addEventListener("input", (e) => suggestFilename(e.target.value));
$("bg-prompt").addEventListener("input", (e) => suggestFilename(e.target.value));
$("iso-prompt").addEventListener("input", (e) => suggestFilename(e.target.value));

// --- File picking / drag-drop -------------------------------------------
const dropzone = $("dropzone");
const fileInput = $("file");

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

["dragover", "dragenter"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});

function setFile(file) {
  selectedFile = file || null;
  $("file-label").textContent = file ? file.name : "Click or drop an image here";
  if (file) {
    const base = file.name.replace(/\.[^.]+$/, "");
    suggestFilename(base);
  }
}

// --- API key handling (modal dialog) ------------------------------------
const KEY_STORAGE = "pixelmaker_openai_key";
let apiKey = localStorage.getItem(KEY_STORAGE) || "";
let hostHasKey = false;

const keyDialog = $("key-dialog");
const keyInput = $("api_key");
const rememberKey = $("remember_key");

function updateKeyStatus() {
  const el = $("key-status");
  if (apiKey) {
    el.textContent = "Key saved \u2713";
    el.className = "key-status ok";
  } else if (hostHasKey) {
    el.textContent = "Using host key";
    el.className = "key-status host";
  } else {
    el.textContent = "No key set";
    el.className = "key-status none";
  }
}
updateKeyStatus();

$("open-key").addEventListener("click", () => {
  keyInput.value = ""; // never reveal a previously saved key
  keyInput.placeholder = apiKey ? "Enter a new key to replace the saved one" : "sk-...";
  rememberKey.checked = !!localStorage.getItem(KEY_STORAGE) || !apiKey;
  keyDialog.showModal();
});

$("key-cancel").addEventListener("click", () => {
  keyInput.value = "";
  keyDialog.close();
});

$("key-save").addEventListener("click", () => {
  const value = keyInput.value.trim();
  if (value) {
    apiKey = value;
    if (rememberKey.checked) {
      localStorage.setItem(KEY_STORAGE, value);
    } else {
      localStorage.removeItem(KEY_STORAGE);
    }
  }
  keyInput.value = "";
  updateKeyStatus();
  keyDialog.close();
});

$("key-clear").addEventListener("click", () => {
  apiKey = "";
  localStorage.removeItem(KEY_STORAGE);
  keyInput.value = "";
  updateKeyStatus();
  keyDialog.close();
});

// --- Health check: note if the host already supplies a key --------------
fetch("/api/health")
  .then((r) => r.json())
  .then((info) => {
    hostHasKey = !!info.host_key;
    $("host-key-note").classList.toggle("hidden", currentTab === "image" || !hostHasKey);
    updateKeyStatus();
  })
  .catch(() => {});

// --- Generate / Convert --------------------------------------------------
$("go").addEventListener("click", run);

async function run() {
  const palette = $("palette").value;
  const colors = $("colors").value;

  const form = new FormData();
  form.append("palette", palette);
  form.append("colors", colors);

  let url;
  let statusMsg;
  if (currentTab === "text") {
    const prompt = $("prompt").value.trim();
    if (!prompt) return setStatus("Enter a subject first.", true);
    form.append("prompt", prompt);
    form.append("size", $("size").value);
    form.append("remove_bg", $("remove_bg").checked);
    form.append("fill", $("fill").checked);
    form.append("api_key", apiKey);
    url = "/api/generate";
    statusMsg = "Generating pixel art...";
  } else if (currentTab === "image") {
    if (!selectedFile) return setStatus("Choose an image first.", true);
    form.append("file", selectedFile);
    form.append("size", $("size").value);
    form.append("remove_bg", $("remove_bg").checked);
    form.append("fill", $("fill").checked);
    url = "/api/convert";
    statusMsg = "Converting...";
  } else if (currentTab === "background") {
    const prompt = $("bg-prompt").value.trim();
    if (!prompt) return setStatus("Enter a scene prompt first.", true);
    form.append("prompt", prompt);
    form.append("width", $("bg-width").value);
    form.append("height", $("bg-height").value);
    form.append("pixel_size", $("bg-pixel").value);
    form.append("tileable", $("bg-tileable").checked);
    form.append("tile_div", $("bg-tilediv").value);
    form.append("api_key", apiKey);
    url = "/api/background";
    statusMsg = "Generating background...";
  } else {
    const prompt = $("iso-prompt").value.trim();
    if (!prompt) return setStatus("Enter a tile material first.", true);
    const variants = ["full", "half", "quarter", "slab"].filter((v) => $(`iso-${v}`).checked);
    if (!variants.length) return setStatus("Pick at least one height variant.", true);
    form.append("prompt", prompt);
    form.append("side_prompt", $("iso-side-prompt").value.trim());
    form.append("width", $("iso-size").value);
    form.append("variants", variants.join(","));
    form.append("rim", $("iso-rim").checked);
    form.append("name", currentBaseName());
    form.append("api_key", apiKey);
    url = "/api/isometric";
    statusMsg = "Generating isometric tiles...";
  }

  setBusy(true);
  setStatus(statusMsg);
  try {
    const resp = await fetch(url, { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Request failed");
    }
    const data = await resp.json();
    if (currentTab === "background") showBackground(data);
    else if (currentTab === "iso") showIsometric(data);
    else showSprite(data);
    setStatus("Done.");
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    setBusy(false);
  }
}

function b64ToBlobUrl(b64) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return URL.createObjectURL(new Blob([arr], { type: "image/png" }));
}

// Base64 PNG -> File, so a generated sprite can be fed to the walk endpoint.
function b64ToPngFile(b64, name) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new File([arr], name, { type: "image/png" });
}

// Holds the most recent true-size sprite (base64 PNG) for the "Animate this" hand-off.
let lastSpriteB64 = null;

// Render up to two download links; `displayUrl` is shown in the preview.
function renderOutputs(displayUrl, outputs) {
  currentOutputs.forEach((o) => URL.revokeObjectURL(o.url));
  currentOutputs = outputs;

  $("output").src = displayUrl;
  ["download-a", "download-b"].forEach((id, i) => {
    const a = $(id);
    if (i < outputs.length) {
      a.href = outputs[i].url;
      a.textContent = outputs[i].getLabel();
      a.classList.remove("hidden");
    } else {
      a.classList.add("hidden");
      a.removeAttribute("href");
    }
  });
  updateDownloadNames();
  $("result").classList.remove("hidden");
}

function showSprite(data) {
  const previewUrl = b64ToBlobUrl(data.preview_png);
  const spriteUrl = b64ToBlobUrl(data.sprite_png);
  renderOutputs(previewUrl, [
    {
      url: spriteUrl,
      getLabel: () => "Download sprite (true size, for LibreSprite)",
      getName: (b) => `${b}_${data.size}x${data.size}.png`,
    },
    {
      url: previewUrl,
      getLabel: () => "Download large preview",
      getName: (b) => `${b}_512.png`,
    },
  ]);
  // Remember the true-size sprite so it can be sent straight to the walk tab.
  lastSpriteB64 = data.sprite_png;
  $("animate-this").classList.remove("hidden");
}

function showBackground(data) {
  lastSpriteB64 = null;
  $("animate-this").classList.add("hidden");
  const bgUrl = b64ToBlobUrl(data.background_png);
  const outputs = [
    {
      url: bgUrl,
      getLabel: () => `Download background (${data.width}x${data.height})`,
      getName: (b) => `${b}_${data.width}x${data.height}.png`,
    },
  ];
  if (data.tile_png) {
    outputs.push({
      url: b64ToBlobUrl(data.tile_png),
      getLabel: () => "Download seamless tile",
      getName: (b) => `${b}_tile.png`,
    });
  }
  renderOutputs(bgUrl, outputs);
}

function b64ToBlobUrlTyped(b64, type) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return URL.createObjectURL(new Blob([arr], { type: type || "application/octet-stream" }));
}

let isoDownloadUrls = [];

function showIsometric(data) {
  isoDownloadUrls.forEach((u) => URL.revokeObjectURL(u));
  isoDownloadUrls = [];

  $("iso-output").src = b64ToBlobUrl(data.preview_png);

  // One button: the whole tileset (atlas + .tres + notes + tiles) in a folder.
  const zipUrl = b64ToBlobUrlTyped(data.zip, "application/zip");
  isoDownloadUrls.push(zipUrl);
  const dl = $("iso-downloads");
  dl.innerHTML = "";
  const a = document.createElement("a");
  a.href = zipUrl;
  a.download = data.zip_name;
  a.textContent = `Download tileset \u2014 ${data.zip_name}`;
  dl.appendChild(a);

  $("iso-result").classList.remove("hidden");
}

function setStatus(msg, isError) {
  const el = $("status");
  el.textContent = msg;
  el.style.color = isError ? "#ff6666" : "var(--accent2)";
}

function setBusy(busy) {
  $("go").disabled = busy;
}

// --- Walk cycle ----------------------------------------------------------
let walkFile = null;
let walkFilenameEdited = false;
let walkFrameUrls = []; // object URLs for the true-size frame PNGs
let walkFrameImages = []; // decoded HTMLImageElements for canvas drawing
let walkSheetUrl = null;
let walkGifUrl = null;
let walkTimer = null;
let walkIndex = 0;
let walkPlaying = false;
let walkFps = 120;

const walkDropzone = $("walk-dropzone");
const walkFileInput = $("walk-file");
const walkCanvas = $("walk-canvas");
const walkCtx = walkCanvas.getContext("2d");
walkCtx.imageSmoothingEnabled = false;

walkDropzone.addEventListener("click", () => walkFileInput.click());
walkFileInput.addEventListener("change", () => setWalkFile(walkFileInput.files[0]));
["dragover", "dragenter"].forEach((ev) =>
  walkDropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    walkDropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  walkDropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    walkDropzone.classList.remove("dragover");
  })
);
walkDropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) setWalkFile(e.dataTransfer.files[0]);
});

function setWalkFile(file) {
  walkFile = file || null;
  $("walk-file-label").textContent = file ? file.name : "Click or drop a sprite to animate";
  if (file && !walkFilenameEdited) {
    const base = file.name.replace(/\.[^.]+$/, "");
    const slug = slugify(base);
    if (slug) $("walk-filename").value = slug;
  }
}

$("walk-filename").addEventListener("input", (e) => {
  walkFilenameEdited = e.target.value.trim().length > 0;
  updateWalkDownloadNames();
});

const walkSpeed = $("walk-speed");
walkSpeed.addEventListener("input", () => {
  walkFps = parseInt(walkSpeed.value, 10);
  $("walk-speed-val").textContent = `${walkFps} ms`;
  if (walkPlaying) startWalkPlayback(); // restart timer at the new speed
});

const walkAction = $("walk-action");
walkAction.addEventListener("change", () => {
  // The frame-count choice only affects the walk action.
  $("walk-frames-label").classList.toggle("hidden", walkAction.value !== "walk");
});

$("walk-go").addEventListener("click", runWalk);
$("walk-playpause").addEventListener("click", () => {
  if (walkPlaying) stopWalkPlayback();
  else startWalkPlayback();
});

// "Animate this" on a generated/converted sprite: send it straight to the walk tab.
$("animate-this").addEventListener("click", () => {
  if (!lastSpriteB64) return;
  const base = currentBaseName();
  const file = b64ToPngFile(lastSpriteB64, `${base}.png`);
  switchTab("walk");
  setWalkFile(file);
  $("walk-filename").value = base;
  walkFilenameEdited = false;
  runWalk();
});

function walkBaseName() {
  return slugify($("walk-filename").value) || "walk";
}

function updateWalkDownloadNames() {
  const base = walkBaseName();
  const action = $("walk-action").value;
  $("walk-download-sheet").download = `${base}_${action}_sheet.png`;
  $("walk-download-gif").download = `${base}_${action}.gif`;
}

async function runWalk() {
  if (!walkFile) return setStatus("Choose a sprite to animate first.", true);
  const action = $("walk-action").value;
  const form = new FormData();
  form.append("file", walkFile);
  form.append("action", action);
  form.append("frames", $("walk-frames").value);
  form.append("fps_ms", String(walkFps));

  $("walk-go").disabled = true;
  setStatus(`Building ${action} animation...`);
  try {
    const resp = await fetch("/api/walk", { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Request failed");
    }
    const data = await resp.json();
    await showWalk(data);
    setStatus("Done.");
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    $("walk-go").disabled = false;
  }
}

function clearWalkAssets() {
  stopWalkPlayback();
  walkFrameUrls.forEach((u) => URL.revokeObjectURL(u));
  if (walkSheetUrl) URL.revokeObjectURL(walkSheetUrl);
  if (walkGifUrl) URL.revokeObjectURL(walkGifUrl);
  walkFrameUrls = [];
  walkFrameImages = [];
  walkSheetUrl = null;
  walkGifUrl = null;
}

async function showWalk(data) {
  clearWalkAssets();

  walkFrameUrls = data.frames.map((b64) => b64ToBlobUrl(b64));
  walkFrameImages = await Promise.all(
    walkFrameUrls.map(
      (url) =>
        new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = reject;
          img.src = url;
        })
    )
  );

  // Size the canvas to an integer upscale of the sprite for crisp pixels.
  const scale = Math.max(1, Math.floor(256 / Math.max(data.width, data.height)));
  walkCanvas.width = data.width * scale;
  walkCanvas.height = data.height * scale;
  walkCtx.imageSmoothingEnabled = false;
  walkCanvas.dataset.scale = String(scale);

  walkSheetUrl = b64ToBlobUrl(data.sheet_png);
  walkGifUrl = b64ToBlobUrl(data.gif_png);
  $("walk-download-sheet").href = walkSheetUrl;
  $("walk-download-gif").href = walkGifUrl;
  updateWalkDownloadNames();

  $("walk-frame-info").textContent = `${data.action} \u00b7 ${data.frame_count} frames \u00b7 ${data.width}\u00d7${data.height}`;
  $("walk-result").classList.remove("hidden");

  walkIndex = 0;
  startWalkPlayback();
}

function drawWalkFrame() {
  if (!walkFrameImages.length) return;
  const img = walkFrameImages[walkIndex];
  walkCtx.clearRect(0, 0, walkCanvas.width, walkCanvas.height);
  walkCtx.drawImage(img, 0, 0, walkCanvas.width, walkCanvas.height);
}

function startWalkPlayback() {
  if (!walkFrameImages.length) return;
  if (walkTimer) clearInterval(walkTimer);
  walkPlaying = true;
  $("walk-playpause").textContent = "Pause";
  drawWalkFrame();
  walkTimer = setInterval(() => {
    walkIndex = (walkIndex + 1) % walkFrameImages.length;
    drawWalkFrame();
  }, walkFps);
}

function stopWalkPlayback() {
  if (walkTimer) clearInterval(walkTimer);
  walkTimer = null;
  walkPlaying = false;
  const btn = $("walk-playpause");
  if (btn) btn.textContent = "Play";
}
