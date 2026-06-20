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

  const isBackground = tab === "background";
  $("sprite-controls").classList.toggle("hidden", isBackground);
  $("bg-controls").classList.toggle("hidden", !isBackground);
  $("ai-key-row").classList.toggle("hidden", tab === "image");
  $("host-key-note").classList.toggle("hidden", tab === "image" || !hostHasKey);
  $("go").textContent = tab === "image" ? "Convert" : "Generate";
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// Suggest a filename from the active prompt as the user types.
$("prompt").addEventListener("input", (e) => suggestFilename(e.target.value));
$("bg-prompt").addEventListener("input", (e) => suggestFilename(e.target.value));

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
  } else {
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
}

function showBackground(data) {
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

function setStatus(msg, isError) {
  const el = $("status");
  el.textContent = msg;
  el.style.color = isError ? "#ff6666" : "var(--accent2)";
}

function setBusy(busy) {
  $("go").disabled = busy;
}
