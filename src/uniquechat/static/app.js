"use strict";
const el = id => document.getElementById(id);
const screens = ["picker", "loading", "conversation"];
let config, database, current, pending = [], busy = false;
const textTypes = ".txt,.md,.csv,.json";
const imageTypes = ".png,.jpg,.jpeg,.webp";

function show(id) {
  screens.forEach(name => el(name).hidden = name !== id);
}
function notice(message = "") { el("notice").textContent = message; }
function button(text, click) {
  const b = document.createElement("button");
  b.type = "button"; b.textContent = text; b.onclick = click;
  return b;
}
async function api(path, body) {
  const options = body ? {method: "POST", headers: {"Content-Type": "application/json",
    "X-Uniquechat": config.token}, body: JSON.stringify(body)} : {};
  const result = await fetch("/api/" + path, options);
  const value = await result.json();
  if (!result.ok) throw Error(value.error || "Request failed.");
  return value;
}
function openHistory() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("uniquechat-history", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("chats", {keyPath: "id"});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
function historyOp(write, chat) {
  return new Promise((resolve, reject) => {
    const tx = database.transaction("chats", write ? "readwrite" : "readonly");
    const store = tx.objectStore("chats");
    const request = write ? store.put(chat) : store.getAll();
    tx.oncomplete = () => resolve(request.result);
    tx.onabort = () => reject(tx.error || Error("Could not save history."));
    tx.onerror = () => reject(tx.error);
  });
}
async function sidebar() {
  if (!database) return;
  const chats = await historyOp(false);
  el("history").replaceChildren();
  for (const chat of chats.sort((a,b) => b.time-a.time)) {
    const b = button(chat.title, () => { if (!busy) load(chat.model, chat); });
    if (current && chat.id === current.id) b.className = "current";
    el("history").append(b);
  }
}
function render() {
  const list = el("messages");
  list.replaceChildren();
  if (!current.turns.length) {
    const title = document.createElement("h2");
    title.className = "empty"; title.textContent = "How can I help?";
    list.append(title);
  }
  for (const entry of current.turns) {
    const bubble = document.createElement("div");
    bubble.className = "bubble " + entry.role;
    bubble.textContent = [entry.text, ...(entry.files || []).map(f => "📎 " + f.name)]
      .filter(Boolean).join("\n");
    list.append(bubble);
  }
  list.scrollTop = list.scrollHeight;
}
function updateDetails() {
  const selected = el("model").value.trim();
  el("details").textContent = selected === config.models[0] ? "Text and documents · about 270 MB"
    : selected === config.models[1] ? "Text, documents and images · about 510 MB" : "Compatible Hugging Face chat model";
}
function chips() {
  el("chips").replaceChildren(...pending.map((f,i) => button(f.name + " ×", () => {
    if (!busy) { pending.splice(i, 1); chips(); }
  })));
}
async function load(repo, previous) {
  if (busy) return;
  busy = true;
  if (innerWidth <= 700) el("side").hidden = true;
  notice(); show("loading"); el("phase").textContent = "Checking local files…";
  try {
    let state = await api("status");
    if (state.model !== repo || state.phase !== "ready") {
      await api("load", {model:repo});
      do {
        state = await api("status");
        el("phase").textContent = state.message;
        if (state.phase === "loading") await new Promise(resolve => setTimeout(resolve, 400));
      } while (state.phase === "loading");
      if (state.phase !== "ready" || state.model !== repo) throw Error(state.message);
    }
    current = previous || {id:crypto.randomUUID(), model:repo, turns:[], title:"New chat", time:Date.now()};
    el("modelName").textContent = repo.split("/").pop();
    el("file").accept = textTypes + (state.vision ? "," + imageTypes : "");
    el("types").textContent = state.vision ? "Images and text files" : "Text files";
    pending = []; chips(); el("prompt").value = "";
    show("conversation"); render(); await sidebar(); el("prompt").focus();
  } catch (err) { show("picker"); notice(err.message); }
  finally { busy = false; }
}
function encodeFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({name:file.name, data:reader.result.split(",")[1]});
    reader.onerror = () => reject(Error("Could not read " + file.name));
    reader.readAsDataURL(file);
  });
}
el("pick").onsubmit = e => { e.preventDefault(); load(el("model").value.trim()); };
el("model").oninput = updateDetails;
el("new").onclick = () => {
  if (busy) return;
  current = null; pending = []; notice(); show("picker");
  el("modelName").textContent = "Model picker"; sidebar();
  if (innerWidth <= 700) el("side").hidden = true;
};
el("menu").onclick = () => el("side").hidden = !el("side").hidden;
el("plus").onclick = () => { if (!busy) el("file").click(); };
el("file").onchange = () => {
  const list = [...el("file").files]; el("file").value = "";
  if (pending.length + list.length > 3) return notice("Choose up to three files.");
  for (const f of list) {
    const ext = "." + f.name.split(".").pop().toLowerCase();
    if (!el("file").accept.split(",").includes(ext)) return notice("Unsupported file type: " + f.name);
    const limit = imageTypes.split(",").includes(ext) ? 8*1024*1024 : 32768;
    if (f.size > limit) return notice("This file is too large: " + f.name);
  }
  pending.push(...list); notice(); chips();
};
el("prompt").onkeydown = e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); el("compose").requestSubmit(); }
};
el("compose").onsubmit = async e => {
  e.preventDefault();
  const text = el("prompt").value.trim();
  if (busy || (!text && !pending.length)) return;
  busy = true; el("send").disabled = true; el("prompt").disabled = true;
  const original = current.turns;
  try {
    const files = await Promise.all(pending.map(encodeFile));
    current.turns = [...original, {role:"user", text, files}];
    render(); notice("Generating locally…");
    const response = await api("chat", {model:current.model, turns:current.turns});
    current.turns.push({role:"assistant", text:response.text});
    current.title = current.turns[0].text.slice(0,60) || current.turns[0].files[0].name;
    current.time = Date.now(); pending = []; chips(); el("prompt").value = "";
    render(); notice();
    try {
      if (!database) throw Error();
      await historyOp(true, current); await sidebar();
    } catch { notice("Chat is open, but browser storage could not save it."); }
  } catch (err) { current.turns = original; render(); notice(err.message); }
  finally { busy = false; el("send").disabled = false; el("prompt").disabled = false; el("prompt").focus(); }
};
async function init() {
  el("side").hidden = innerWidth <= 700;
  config = await api("config");
  try { database = await openHistory(); await sidebar(); }
  catch { notice("Browser history storage is unavailable."); }
  for (const model of config.models) {
    const option = document.createElement("option"); option.value = model; el("models").append(option);
  }
  el("model").value = config.initial || config.models[0]; updateDetails();
  if (config.initial) await load(config.initial);
}
init().catch(err => notice(err.message));
