"use strict";

const REFRESH_MS = 5000;
const $ = (id) => document.getElementById(id);

const RAM_PARTS = [
  ["app", "App memory", "Memory allocated by apps and processes"],
  ["wired", "Wired", "Kernel memory that can never be compressed or swapped"],
  ["compressed", "Compressed", "RAM the compressor uses to hold compressed pages"],
  ["cached", "Cached files", "File cache; reclaimed instantly when apps need memory"],
  ["other", "Other", "Kernel-reserved and unclassified pages"],
  ["free", "Free", "Unused RAM"],
];
const COLORS = { app: "--app", wired: "--wired", compressed: "--compressed",
  cached: "--cached", other: "--other", free: "--track" };

const state = { data: null, sort: "footprint", asc: false, open: new Set(), timer: null };

function fmt(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(bytes >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}
const pct = (part, whole) => (whole ? (100 * part) / whole : 0);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function segment(bytes, color, tip) {
  if (bytes <= 0) return "";
  return `<div style="flex:${bytes} 0 0;background:var(${color})" data-tip="${esc(tip)}"></div>`;
}

function renderTiles(d) {
  $("t-total").textContent = fmt(d.total);
  $("t-used").textContent = fmt(d.used);
  $("t-used-sub").textContent = `${pct(d.used, d.total).toFixed(0)}% · app + wired + compressed`;
  $("t-swap").textContent = fmt(d.swap.used);
  $("t-swap-sub").textContent = `of ${fmt(d.swap.total)} swap files`;
  const p = $("t-pressure");
  p.textContent = d.pressure[0].toUpperCase() + d.pressure.slice(1);
  p.className = `value status ${d.pressure}`;
  $("t-pressure-sub").textContent = `${d.swap.swapouts.toLocaleString()} swap-outs since boot`;
}

function renderRam(d) {
  $("ram-bar").innerHTML = RAM_PARTS.map(([k, label, desc]) =>
    segment(d.breakdown[k], COLORS[k],
      `${label}: ${fmt(d.breakdown[k])} (${pct(d.breakdown[k], d.total).toFixed(1)}%) — ${desc}`)).join("");
  $("ram-legend").innerHTML = RAM_PARTS.map(([k, label]) =>
    `<li><span class="key" style="background:var(${COLORS[k]})"></span>${label}<b>${fmt(d.breakdown[k])}</b></li>`).join("");
}

function renderSwap(d) {
  const s = d.swap;
  $("swap-bar").innerHTML = s.total
    ? segment(s.used, "--swap", `Used: ${fmt(s.used)}`) +
      segment(s.free, "--track", `Free: ${fmt(s.free)}`)
    : segment(1, "--track", "No swap files allocated");
  $("swap-legend").innerHTML =
    `<li><span class="key" style="background:var(--swap)"></span>Used<b>${fmt(s.used)}</b></li>` +
    `<li><span class="key" style="background:var(--track)"></span>Free<b>${fmt(s.free)}</b></li>`;
  const c = d.compressor;
  $("swap-note").textContent =
    `macOS grows swap files on demand, so the total changes. The compressor holds ${fmt(c.stored)} ` +
    `of memory in ${fmt(c.occupied)} of RAM; pages it evicts go to swap. ` +
    `Swap-ins / swap-outs since boot: ${s.swapins.toLocaleString()} / ${s.swapouts.toLocaleString()}.`;
}

function rowsFor(d) {
  const q = $("filter").value.trim().toLowerCase();
  const procs = d.processes
    .filter((p) => !q || p.name.toLowerCase().includes(q) || p.app.toLowerCase().includes(q) || p.user.toLowerCase().includes(q))
    .map((p) => ({ ...p, label: p.name, count: 1, resident: Math.max(p.footprint - p.compressed, 0) }));
  if (!$("group").checked) return procs;
  const groups = new Map();
  for (const p of procs) {
    let g = groups.get(p.app);
    if (!g) groups.set(p.app, g = { label: p.app, count: 0, footprint: 0, resident: 0, compressed: 0, children: [] });
    g.count++; g.footprint += p.footprint; g.resident += p.resident; g.compressed += p.compressed;
    g.children.push(p);
  }
  return [...groups.values()];
}

function sortRows(rows) {
  const k = state.sort, dir = state.asc ? 1 : -1;
  const cmp = (a, b) => (typeof a[k] === "string" ? a[k].localeCompare(b[k]) : a[k] - b[k]) * dir;
  rows.sort(cmp);
  for (const r of rows) if (r.children) r.children.sort(cmp);
  return rows;
}

function rowHtml(r, max, cls) {
  const name = cls === "group" ? esc(r.label)
    : `${esc(r.label)}<span class="user">${r.pid} · ${esc(r.user)}</span>`;
  const bar = `<div class="stack" style="width:${Math.max(pct(r.footprint, max), 0.5)}%">` +
    segment(r.resident, "--resident", `Resident: ${fmt(r.resident)}`) +
    segment(r.compressed, "--compressed", `Compressed / swapped: ${fmt(r.compressed)}`) + "</div>";
  const open = cls === "group" && state.open.has(r.label) ? " open" : "";
  return `<tr class="${cls}${open}" data-key="${esc(r.label)}"><td>${name}</td>` +
    `<td class="num">${r.count}</td><td>${bar}</td><td class="num">${fmt(r.footprint)}</td>` +
    `<td class="num">${fmt(r.resident)}</td><td class="num">${fmt(r.compressed)}</td></tr>`;
}

function renderTable() {
  const d = state.data;
  if (!d) return;
  const rows = sortRows(rowsFor(d));
  const max = Math.max(1, ...rows.map((r) => r.footprint));
  const html = [];
  for (const r of rows) {
    if (!r.children) { html.push(rowHtml(r, max, "proc")); continue; }
    html.push(rowHtml(r, max, "group"));
    if (state.open.has(r.label)) for (const c of r.children) html.push(rowHtml(c, max, "child"));
  }
  $("rows").innerHTML = html.join("") || `<tr><td colspan="6" class="muted">No matching processes</td></tr>`;
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.sort === state.sort);
    th.classList.toggle("asc", th.dataset.sort === state.sort && state.asc);
  });
}

async function load() {
  try {
    const res = await fetch("/api/memory");
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    state.data = d;
    $("error").hidden = true;
    renderTiles(d); renderRam(d); renderSwap(d); renderTable();
    $("updated").textContent = `Updated ${new Date(d.timestamp * 1000).toLocaleTimeString()}`;
  } catch (e) {
    $("error").textContent = `Could not read memory statistics: ${e.message}`;
    $("error").hidden = false;
  }
}

function schedule() {
  clearInterval(state.timer);
  if ($("auto").checked) state.timer = setInterval(load, REFRESH_MS);
}

$("refresh").addEventListener("click", load);
$("auto").addEventListener("change", schedule);
$("filter").addEventListener("input", renderTable);
$("group").addEventListener("change", renderTable);
document.querySelector("thead").addEventListener("click", (e) => {
  const k = e.target.closest("th")?.dataset.sort;
  if (!k) return;
  state.asc = state.sort === k ? !state.asc : k === "label";
  state.sort = k;
  renderTable();
});
$("rows").addEventListener("click", (e) => {
  const tr = e.target.closest("tr.group");
  if (!tr) return;
  const k = tr.dataset.key;
  state.open.has(k) ? state.open.delete(k) : state.open.add(k);
  renderTable();
});

const tip = $("tip");
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest("[data-tip]");
  if (!el) { tip.hidden = true; return; }
  tip.textContent = el.dataset.tip;
  tip.hidden = false;
  const x = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8);
  const y = e.clientY + 16 + tip.offsetHeight > innerHeight ? e.clientY - tip.offsetHeight - 8 : e.clientY + 16;
  tip.style.left = `${x}px`; tip.style.top = `${y}px`;
});

load();
schedule();
