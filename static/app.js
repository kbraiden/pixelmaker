"use strict";

const $ = (id) => document.getElementById(id);

let currentTab = "text";
let selectedFile = null;
let spriteUrl = null;
let previewUrl = null;
let filenameEdited = false;

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
});

function suggestFilename(source) {
  if (filenameEdited) return;
  const slug = slugify(source);
  if (slug) filenameInput.value = slug;
}

function currentBaseName() {
  return slugify(filenameInput.value) || "pixelart";
}

// --- Tab switching -------------------------------------------------------
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    currentTab = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    $("tab-text").classList.toggle("active", currentTab === "text");
    $("tab-image").classList.toggle("active", currentTab === "image");
    $("go").textContent = currentTab === "text" ? "Generate" : "Convert";
  });
});

// Suggest a filename from the prompt as the user types.
$("prompt").addEventListener("input", (e) => suggestFilename(e.target.value));

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

// --- API key persistence ------------------------------------------------
const KEY_STORAGE = "pixelmaker_openai_key";
const keyInput = $("api_key");
const rememberKey = $("remember_key");

const savedKey = localStorage.getItem(KEY_STORAGE);
if (savedKey) keyInput.value = savedKey;

function persistKey() {
  if (rememberKey.checked && keyInput.value.trim()) {
    localStorage.setItem(KEY_STORAGE, keyInput.value.trim());
  } else {
    localStorage.removeItem(KEY_STORAGE);
  }
}
keyInput.addEventListener("change", persistKey);
rememberKey.addEventListener("change", persistKey);

// --- Health check: note if the host already supplies a key --------------
fetch("/api/health")
  .then((r) => r.json())
  .then((info) => {
    if (info.host_key) {
      $("host-key-note").classList.remove("hidden");
    }
  })
  .catch(() => {});

// --- Generate / Convert --------------------------------------------------
$("go").addEventListener("click", run);

async function run() {
  const size = $("size").value;
  const palette = $("palette").value;
  const colors = $("colors").value;
  const removeBg = $("remove_bg").checked;
  const fill = $("fill").checked;

  const form = new FormData();
  form.append("size", size);
  form.append("palette", palette);
  form.append("colors", colors);
  form.append("remove_bg", removeBg);
  form.append("fill", fill);

  let url;
  if (currentTab === "text") {
    const prompt = $("prompt").value.trim();
    if (!prompt) return setStatus("Enter a subject first.", true);
    form.append("prompt", prompt);
    persistKey();
    form.append("api_key", keyInput.value.trim());
    url = "/api/generate";
  } else {
    if (!selectedFile) return setStatus("Choose an image first.", true);
    form.append("file", selectedFile);
    url = "/api/convert";
  }

  setBusy(true);
  setStatus(currentTab === "text" ? "Generating pixel art..." : "Converting...");
  try {
    const resp = await fetch(url, { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Request failed");
    }
    const data = await resp.json();
    showResult(data, size);
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

function showResult(data, size) {
  if (spriteUrl) URL.revokeObjectURL(spriteUrl);
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = b64ToBlobUrl(data.preview_png);
  spriteUrl = b64ToBlobUrl(data.sprite_png);

  $("output").src = previewUrl;

  const base = currentBaseName();
  const spriteLink = $("download-sprite");
  spriteLink.href = spriteUrl;
  spriteLink.download = `${base}_${data.size}x${data.size}.png`;

  const previewLink = $("download-preview");
  previewLink.href = previewUrl;
  previewLink.download = `${base}_512.png`;

  $("result").classList.remove("hidden");
}

function setStatus(msg, isError) {
  const el = $("status");
  el.textContent = msg;
  el.style.color = isError ? "#ff6666" : "var(--accent2)";
}

function setBusy(busy) {
  $("go").disabled = busy;
}
