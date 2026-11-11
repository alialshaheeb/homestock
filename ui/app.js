// HomeStock UI: plain JavaScript that only talks to the JSON API.
// API_BASE is "" because the same process serves this page and the API (Assignment 1).
const API_BASE = "";

const state = {
  view: "stock",      // "stock" or "list": which tab is open
  filter: "all",      // "all", "low" or "expiring"
  place: "",          // location id to show, "" = every place
  locations: [],
  allItems: [],       // every item, for the counts in the header
  items: [],          // the items matching the current filter
  entries: [],        // the shopping list
  editingId: null,    // item open in the sheet, null when adding a new one
};

const $ = (id) => document.getElementById(id);

// ---------- talking to the API ----------

async function api(method, path, body) {
  const res = await fetch(API_BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    // 422 from FastAPI is a list of field errors; 404/409 carry one message.
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ")
      : data.detail;
    throw new Error(detail || `Something went wrong (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

function itemsPath() {
  const params = new URLSearchParams();
  if (state.filter === "low") params.set("low_stock", "true");
  if (state.filter === "expiring") params.set("expiring_within_days", "3");
  if (state.place) params.set("location_id", state.place);
  return `/items?${params}`;
}

async function load() {
  const filtered = state.filter !== "all" || state.place;
  const [locations, allItems, entries, items] = await Promise.all([
    api("GET", "/locations"),
    api("GET", "/items"),
    api("GET", "/shopping-list"),
    filtered ? api("GET", itemsPath()) : null,
  ]);
  Object.assign(state, { locations, allItems, entries, items: items ?? allItems });
  render();
}

// Run an action, reload everything, and show a message; errors go to the toast.
async function run(action, message) {
  try {
    const result = await action();
    await load();
    const text = typeof message === "function" ? message(result) : message;
    if (text) toast(text);
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- small helpers ----------

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of children) if (child != null) node.append(child);
  return node;
}

function icon(path) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = `<path d="${path}"/>`;
  return svg;
}
const ICON = { minus: "M5 12h14", plus: "M12 5v14M5 12h14", check: "M5 12.5l4.5 4.5L19 7", x: "M6 6l12 12M18 6L6 18" };

const num = (n) => Number(n.toFixed(2)).toString(); // 1.5 -> "1.5", 4.0 -> "4"

function daysUntil(iso) {
  const today = new Date(new Date().toDateString());
  const [y, m, d] = iso.split("-").map(Number);
  return Math.round((new Date(y, m - 1, d) - today) / 86400000);
}

function expiryText(iso) {
  const days = daysUntil(iso);
  if (days < 0) return { text: "expired", cls: "bad" };
  if (days === 0) return { text: "expires today", cls: "bad" };
  if (days === 1) return { text: "expires tomorrow", cls: "warn" };
  if (days <= 3) return { text: `expires in ${days} days`, cls: "warn" };
  return null; // far away: not worth a line
}

let toastTimer;
function toast(text, isError = false) {
  const t = $("toast");
  t.textContent = text;
  t.classList.toggle("error", isError);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), isError ? 5000 : 2500);
}

// ---------- drawing the screens ----------

function render() {
  const onStock = state.view === "stock";
  $("view-stock").hidden = !onStock;
  $("view-list").hidden = onStock;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.view === state.view));
  $("fab").setAttribute("aria-label", onStock ? "Add an item" : "Add to the shopping list");

  const open = state.entries.filter((e) => e.status === "open");
  $("list-count").hidden = open.length === 0;
  $("list-count").textContent = open.length;

  if (onStock) {
    $("screen-title").textContent = "In stock";
    const low = state.allItems.filter((i) => i.low_stock).length;
    const soon = state.allItems.filter((i) => i.expiry_date && daysUntil(i.expiry_date) <= 3).length;
    const parts = [];
    if (low) parts.push(`${low} running low`);
    if (soon) parts.push(`${soon} expiring soon`);
    $("screen-sub").textContent = state.allItems.length === 0 ? "Nothing tracked yet"
      : parts.length ? parts.join(", ") : "Everything is stocked";
    renderStock();
  } else {
    $("screen-title").textContent = "Shopping list";
    $("screen-sub").textContent = open.length ? `${open.length} to buy` : "All bought";
    renderList(open);
  }
}

function renderStock() {
  document.querySelectorAll("[data-filter]").forEach((c) => c.classList.toggle("on", c.dataset.filter === state.filter));

  // Place chips: every place, each location, and one to add a new place.
  const places = $("places");
  places.replaceChildren(
    placeChip("Every place", ""),
    ...state.locations.map((loc) => placeChip(loc.name, String(loc.id))),
    el("button", { type: "button", className: "chip add", textContent: "+ New place", onclick: () => openSheet("place") }),
  );

  // One shelf per location that has items to show.
  const shelves = state.locations
    .map((loc) => ({ loc, items: state.items.filter((i) => i.location_id === loc.id) }))
    .filter((s) => s.items.length > 0)
    .map(({ loc, items }) =>
      el("section", { className: "shelf" },
        el("div", { className: "shelf-head" },
          el("h2", { textContent: loc.name }),
          el("span", { textContent: `${items.length} ${items.length === 1 ? "item" : "items"}` })),
        el("ul", {}, ...items.map(itemRow))));
  $("shelves").replaceChildren(...shelves);

  const empty = $("stock-empty");
  empty.hidden = shelves.length > 0;
  const noItemsAtAll = state.allItems.length === 0;
  empty.replaceChildren(
    el("p", { textContent: noItemsAtAll ? "Your shelves are empty." : "Nothing matches." }),
    el("p", { className: "hint", textContent: noItemsAtAll ? "Tap + to add the first thing in your fridge or pantry." : "Try another filter or place." }),
  );
}

function placeChip(label, id) {
  return el("button", {
    type: "button",
    className: `chip${state.place === id ? " on" : ""}`,
    textContent: label,
    onclick: () => { state.place = id; run(async () => {}); },
  });
}

function itemRow(item) {
  // Gauge: full at twice the restock level, so "low" sits at the halfway mark.
  const full = item.min_threshold > 0 ? item.min_threshold * 2 : Math.max(item.quantity, 1);
  const pct = Math.min(100, (item.quantity / full) * 100);

  const meta = el("span", { className: "item-meta" });
  if (item.min_threshold > 0) meta.append(`restock at ${num(item.min_threshold)} ${item.unit}`);
  const expiry = item.expiry_date && expiryText(item.expiry_date);
  if (expiry) {
    if (meta.childNodes.length) meta.append(", ");
    meta.append(el("span", { className: expiry.cls, textContent: expiry.text }));
  }
  if (!meta.childNodes.length) meta.append("no reminder set");

  const minus = el("button", {
    type: "button", className: "step", ariaLabel: `Use one ${item.name}`,
    disabled: item.quantity <= 0,
    onclick: () => run(() => api("POST", `/items/${item.id}/consume`, { amount: Math.min(1, item.quantity) })),
  }, icon(ICON.minus));
  const plus = el("button", {
    type: "button", className: "step", ariaLabel: `Add one ${item.name}`,
    onclick: () => run(() => api("POST", `/items/${item.id}/restock`, { amount: 1 })),
  }, icon(ICON.plus));

  return el("li", { className: `item${item.low_stock ? " low" : ""}` },
    el("button", { type: "button", className: "item-main", ariaLabel: `Edit ${item.name}`, onclick: () => openSheet("item", item) },
      el("span", { className: "item-name", textContent: item.name }),
      meta,
      el("span", { className: "gauge" }, el("i", { style: `width:${pct}%` }))),
    el("div", { className: "stepper" },
      minus,
      el("span", { className: "qty" }, el("b", { textContent: num(item.quantity) }), el("small", { textContent: item.unit })),
      plus));
}

function renderList(open) {
  $("open-entries").replaceChildren(...open.map(entryRow));
  $("list-empty").hidden = open.length > 0;
  const bought = state.entries.filter((e) => e.status === "bought").slice(0, 15);
  $("bought-title").hidden = bought.length === 0;
  $("bought-entries").replaceChildren(...bought.map(entryRow));
}

function entryRow(entry) {
  const isOpen = entry.status === "open";
  const where = entry.inventory_item_id ? (entry.source === "low_stock" ? "running low at home" : "from your stock") : "not tracked in stock";
  return el("li", { className: "entry" },
    el("button", {
      type: "button", className: "tick", disabled: !isOpen,
      ariaLabel: isOpen ? `Mark ${entry.name} as bought` : `${entry.name} bought`,
      onclick: isOpen ? () => markBought(entry) : null,
    }, icon(ICON.check)),
    el("span", { className: "entry-text" },
      el("span", { className: "entry-name", textContent: entry.name }),
      el("span", { className: "entry-meta", textContent: `${num(entry.quantity)} ${entry.unit}, ${where}` })),
    isOpen ? el("button", {
      type: "button", className: "remove", ariaLabel: `Remove ${entry.name} from the list`,
      onclick: () => run(() => api("DELETE", `/shopping-list/${entry.id}`), `Removed ${entry.name}`),
    }, icon(ICON.x)) : null);
}

function markBought(entry) {
  run(() => api("POST", `/shopping-list/${entry.id}/bought`), (result) => {
    if (!entry.inventory_item_id) return `Bought ${entry.name}`;
    if (!result.restocked) return `Bought ${entry.name}, but it is no longer in your stock`;
    const item = state.allItems.find((i) => i.id === entry.inventory_item_id);
    return item ? `${entry.name} is back to ${num(item.quantity)} ${item.unit}` : `Bought ${entry.name}`;
  });
}

// ---------- the bottom sheet ----------

let lastFocus = null;

function openSheet(kind, item = null) {
  lastFocus = document.activeElement;
  for (const id of ["form-item", "form-entry", "form-place"]) $(id).hidden = id !== `form-${kind}`;
  const form = $(`form-${kind}`);
  form.reset();

  if (kind === "item") {
    state.editingId = item ? item.id : null;
    const select = form.elements.location_id;
    select.replaceChildren(...state.locations.map((l) => new Option(l.name, l.id)));
    const values = item ?? { quantity: 1, unit: "pcs", min_threshold: 0, location_id: Number(state.place) || state.locations[0]?.id };
    for (const key of ["name", "location_id", "quantity", "unit", "min_threshold", "expiry_date"]) {
      if (values[key] != null) form.elements[key].value = values[key];
    }
    $("sheet-title").textContent = item ? item.name : "Add to stock";
    $("item-submit").textContent = item ? "Save changes" : "Add to stock";
    $("item-extra").hidden = !item;
  } else {
    $("sheet-title").textContent = kind === "entry" ? "Add to the list" : "New place";
  }

  $("scrim").hidden = false;
  $("sheet").hidden = false;
  form.querySelector("input, select").focus();
}

function closeSheet() {
  $("sheet").hidden = true;
  $("scrim").hidden = true;
  state.editingId = null;
  lastFocus?.focus();
}

function formValues(form) {
  const data = Object.fromEntries(new FormData(form));
  for (const key of ["quantity", "min_threshold", "location_id"]) {
    if (key in data) data[key] = Number(data[key] || 0);
  }
  if ("expiry_date" in data && data.expiry_date === "") data.expiry_date = null;
  return data;
}

$("form-item").addEventListener("submit", (e) => {
  e.preventDefault();
  const data = formValues(e.target);
  const id = state.editingId;
  closeSheet();
  run(() => (id ? api("PATCH", `/items/${id}`, data) : api("POST", "/items", data)),
    id ? `Saved ${data.name}` : `Added ${data.name}`);
});

$("form-entry").addEventListener("submit", (e) => {
  e.preventDefault();
  const data = formValues(e.target);
  closeSheet();
  run(() => api("POST", "/shopping-list", data), `${data.name} is on the list`);
});

$("form-place").addEventListener("submit", (e) => {
  e.preventDefault();
  const data = formValues(e.target);
  closeSheet();
  run(() => api("POST", "/locations", data), `Added ${data.name.trim().toLowerCase()}`);
});

$("item-to-list").addEventListener("click", () => {
  const item = state.allItems.find((i) => i.id === state.editingId);
  closeSheet();
  const amount = item.min_threshold > 0 ? Math.max(item.min_threshold * 2 - item.quantity, 1) : 1;
  run(() => api("POST", "/shopping-list", { inventory_item_id: item.id, quantity: amount }), `${item.name} is on the list`);
});

$("item-delete").addEventListener("click", () => {
  const item = state.allItems.find((i) => i.id === state.editingId);
  closeSheet();
  run(() => api("DELETE", `/items/${item.id}`), `Deleted ${item.name}`);
});

// ---------- navigation ----------

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => { state.view = tab.dataset.view; render(); window.scrollTo(0, 0); }));

document.querySelectorAll("[data-filter]").forEach((chip) =>
  chip.addEventListener("click", () => { state.filter = chip.dataset.filter; run(async () => {}); }));

$("fab").addEventListener("click", () => openSheet(state.view === "stock" ? "item" : "entry"));

$("from-low-stock").addEventListener("click", () =>
  run(() => api("POST", "/shopping-list/from-low-stock"), (added) =>
    added.length ? `Added ${added.length} ${added.length === 1 ? "item" : "items"} that ${added.length === 1 ? "is" : "are"} running low` : "Nothing is running low"));

$("scrim").addEventListener("click", closeSheet);
$("sheet-close").addEventListener("click", closeSheet);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) closeSheet(); });

run(async () => {});
