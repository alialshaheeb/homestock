// HomeStock UI: plain JavaScript that only talks to the two services' JSON APIs.
// Their addresses come from config.js (local compose ports, or the Azure URLs written at deploy time).
const CONFIG = window.HOMESTOCK_CONFIG;

const state = {
  view: "stock",      // "stock", "places" or "list": which tab is open
  filter: "all",      // "all", "low" or "expiring"
  place: "",          // location id to show, "" = every place
  locations: [],
  allItems: [],       // every item, for counts
  items: [],          // the items matching the current filter
  entries: [],        // the shopping list
  editingId: null,    // item open in the sheet, null when adding a new one
};

const $ = (id) => document.getElementById(id);
const SOON_DAYS = 3;  // "expiring soon" = within 3 days, same as the API filter the UI uses

// ---------- talking to the API ----------

// /shopping-list belongs to the restock service; everything else to the inventory service.
function serviceFor(path) {
  return path.startsWith("/shopping-list")
    ? { name: "shopping list", url: CONFIG.restockUrl }
    : { name: "inventory", url: CONFIG.inventoryUrl };
}

// On Azure both services scale to zero. The first request after a quiet period starts the
// container and may wake a paused database; until it is ready Azure answers 503 "App port is
// not ready" (after ~30 s) without CORS headers, so the browser only sees a failed fetch.
// Reads are retried while a "starting up" message is shown. Writes are never retried, because a
// write may already have reached the service: the user is told to try again instead.
const COLD_START_RETRIES = 4;
const COLD_START_DELAY_MS = 5000;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function api(method, path, body, attempt = 1) {
  const service = serviceFor(path);
  let res;
  try {
    res = await fetch(service.url + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // No answer we can read: the service is starting up, stopped or unreachable.
    if (method === "GET" && attempt <= COLD_START_RETRIES) {
      toast(`The ${service.name} service is starting up, trying again (${attempt}/${COLD_START_RETRIES})…`);
      await sleep(COLD_START_DELAY_MS);
      return api(method, path, body, attempt + 1);
    }
    throw new Error(`The ${service.name} service is starting up or unreachable. Try again in a minute.`);
  }
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
  if (state.filter === "expiring") params.set("expiring_within_days", String(SOON_DAYS));
  if (state.place) params.set("location_id", state.place);
  return `/items?${params}`;
}

async function load() {
  const filtered = state.filter !== "all" || state.place;
  // Each service is loaded on its own, so one being down does not blank the other's screen.
  const [stock, list] = await Promise.allSettled([
    Promise.all([api("GET", "/locations"), api("GET", "/items"), filtered ? api("GET", itemsPath()) : null]),
    api("GET", "/shopping-list"),
  ]);
  if (stock.status === "fulfilled") {
    const [locations, allItems, items] = stock.value;
    // Places in the order they were added (fridge, pantry, toiletries, then your own).
    locations.sort((a, b) => a.id - b.id);
    Object.assign(state, { locations, allItems, items: items ?? allItems });
  }
  if (list.status === "fulfilled") state.entries = list.value;
  render();
  const failed = [stock, list].find((r) => r.status === "rejected");
  if (failed) throw failed.reason;
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
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1); // "fridge" -> "Fridge"

function daysUntil(iso) {
  const today = new Date(new Date().toDateString());
  const [y, m, d] = iso.split("-").map(Number);
  return Math.round((new Date(y, m - 1, d) - today) / 86400000);
}

const isSoon = (item) => item.expiry_date && daysUntil(item.expiry_date) <= SOON_DAYS;

function expiryText(iso) {
  const days = daysUntil(iso);
  if (days < 0) return "expired";
  if (days === 0) return "expires today";
  if (days === 1) return "expires tomorrow";
  if (days <= SOON_DAYS) return `expires in ${days} days`;
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

const SCREENS = {
  stock: { title: "In stock", fab: "Add an item" },
  places: { title: "Places", fab: "Add a place" },
  list: { title: "Shopping list", fab: "Add to the shopping list" },
};

function render() {
  for (const view of Object.keys(SCREENS)) $(`view-${view}`).hidden = view !== state.view;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.view === state.view));
  $("screen-title").textContent = SCREENS[state.view].title;
  $("fab").setAttribute("aria-label", SCREENS[state.view].fab);

  const open = state.entries.filter((e) => e.status === "open");
  $("list-count").hidden = open.length === 0;
  $("list-count").textContent = open.length;

  if (state.view === "stock") renderStock();
  if (state.view === "places") renderPlaces();
  if (state.view === "list") renderList(open);
}

function renderStock() {
  const low = state.allItems.filter((i) => i.low_stock).length;
  const soon = state.allItems.filter(isSoon).length;
  const parts = [];
  if (low) parts.push(`${low} running low`);
  if (soon) parts.push(`${soon} expiring soon`);
  $("screen-sub").textContent = state.allItems.length === 0 ? "Nothing tracked yet"
    : parts.length ? parts.join(", ") : "Everything is stocked";

  // Filter chips with their counts.
  $("n-all").textContent = state.allItems.length;
  $("n-low").textContent = low;
  $("n-expiring").textContent = soon;
  document.querySelectorAll("[data-filter]").forEach((c) => c.classList.toggle("on", c.dataset.filter === state.filter));

  // Place chips.
  $("places").replaceChildren(
    placeChip("Every place", ""),
    ...state.locations.map((loc) => placeChip(cap(loc.name), String(loc.id))),
  );

  // One shelf per place that has items to show.
  const shelves = state.locations
    .map((loc) => ({ loc, items: state.items.filter((i) => i.location_id === loc.id) }))
    .filter((s) => s.items.length > 0)
    .map(({ loc, items }) =>
      el("section", { className: "shelf" },
        el("div", { className: "shelf-head" },
          el("h2", { textContent: cap(loc.name) }),
          el("span", { textContent: plural(items.length, "item", "items") })),
        el("ul", {}, ...items.map(itemRow))));
  $("shelves").replaceChildren(...shelves);

  const empty = $("stock-empty");
  empty.hidden = shelves.length > 0;
  const nothing = state.allItems.length === 0;
  empty.replaceChildren(
    el("p", { textContent: nothing ? "Your shelves are empty." : "Nothing matches." }),
    el("p", { className: "hint", textContent: nothing ? "Tap + to add the first thing in your fridge or pantry." : "Try another filter or place." }),
  );
}

function placeChip(label, id) {
  return el("button", {
    type: "button",
    className: `chip place${state.place === id ? " on" : ""}`,
    textContent: label,
    onclick: () => { state.place = id; run(async () => {}); },
  });
}

function itemRow(item) {
  // Gauge: full at twice the restock level, so "low" sits at the halfway mark.
  const full = item.min_threshold > 0 ? item.min_threshold * 2 : Math.max(item.quantity, 1);
  const pct = Math.min(100, (item.quantity / full) * 100);
  const expiry = item.expiry_date && expiryText(item.expiry_date);

  // With a restock level, the expiry gets its own line; without one it sits beside "no reminder".
  const main = el("button", { type: "button", className: "item-main", ariaLabel: `Edit ${item.name}`, onclick: () => openSheet("item", item) },
    el("span", { className: "item-name", textContent: item.name }));
  if (item.min_threshold > 0) {
    main.append(el("span", { className: "item-meta", textContent: `restock at ${num(item.min_threshold)} ${item.unit}` }));
    if (expiry) main.append(el("span", { className: "expiry", textContent: expiry }));
  } else {
    main.append(el("span", { className: "item-meta" }, "no reminder", expiry ? el("span", { className: "expiry", textContent: expiry }) : null));
  }
  main.append(el("span", { className: "gauge" }, el("i", { style: `width:${pct}%` })));

  return el("li", { className: `item${item.low_stock ? " low" : ""}` },
    main,
    el("div", { className: "stepper" },
      el("button", {
        type: "button", className: "step", ariaLabel: `Use one ${item.name}`, disabled: item.quantity <= 0,
        onclick: () => run(() => api("POST", `/items/${item.id}/consume`, { amount: Math.min(1, item.quantity) })),
      }, icon(ICON.minus)),
      el("span", { className: "qty" }, el("b", { textContent: num(item.quantity) }), el("small", { textContent: item.unit })),
      el("button", {
        type: "button", className: "step", ariaLabel: `Add one ${item.name}`,
        onclick: () => run(() => api("POST", `/items/${item.id}/restock`, { amount: 1 })),
      }, icon(ICON.plus))));
}

const BLOBS = ["#FBD9C6", "#DFEBCB", "#F7B993", "#C9D7AE"]; // corner colour of each place card, in turn

function renderPlaces() {
  $("screen-sub").textContent = "Where things are kept at home";
  const cards = state.locations.map((loc, i) => {
    const items = state.allItems.filter((it) => it.location_id === loc.id);
    const low = items.filter((it) => it.low_stock).length;
    const soon = items.filter(isSoon).length;
    const notes = [];
    if (low) notes.push(`${low} low`);
    if (soon) notes.push(`${soon} expiring`);
    const meta = items.length === 0 ? "Empty" : notes.length ? notes.join(" · ") : "All stocked";
    return el("button", {
      type: "button", className: "place-card", ariaLabel: `Show what is in ${loc.name}`,
      onclick: () => { state.place = String(loc.id); state.filter = "all"; state.view = "stock"; run(async () => {}); window.scrollTo(0, 0); },
    },
      el("span", { className: "blob", style: `background:${BLOBS[i % BLOBS.length]}` }),
      el("span", { className: "count serif", textContent: items.length }),
      el("span", { className: "name serif", textContent: cap(loc.name) }),
      el("span", { className: "meta", textContent: meta }));
  });
  const add = el("button", { type: "button", className: "place-card new", onclick: () => openSheet("place") },
    icon(ICON.plus), el("span", { className: "name serif", textContent: "New place" }));
  $("place-grid").replaceChildren(...cards, add);
}

function renderList(open) {
  $("screen-sub").textContent = open.length ? `${open.length} to buy` : "All bought";

  // How many low items are not on the list yet: what the big button would add.
  const onList = new Set(open.map((e) => e.inventory_item_id));
  const toAdd = state.allItems.filter((i) => i.low_stock && !onList.has(i.id)).length;
  $("low-count").hidden = toAdd === 0;
  $("low-count").textContent = toAdd;

  $("open-entries").replaceChildren(...open.map(entryRow));
  $("list-empty").hidden = open.length > 0;
  const bought = state.entries.filter((e) => e.status === "bought").slice(0, 15);
  $("bought-title").hidden = bought.length === 0;
  $("bought-entries").replaceChildren(...bought.map(entryRow));
}

function entryRow(entry) {
  const isOpen = entry.status === "open";
  const amount = `${num(entry.quantity)} ${entry.unit}`;
  const where = entry.inventory_item_id
    ? (entry.source === "low_stock" ? "running low at home" : "from your stock")
    : "not tracked in stock";
  return el("li", { className: "entry" },
    el("button", {
      type: "button", className: "tick", disabled: !isOpen,
      ariaLabel: isOpen ? `Mark ${entry.name} as bought` : `${entry.name} bought`,
      onclick: isOpen ? () => markBought(entry) : null,
    }, icon(ICON.check)),
    el("span", { className: "entry-text" },
      el("span", { className: "entry-name", textContent: entry.name }),
      el("span", { className: "entry-meta", textContent: isOpen ? `${amount} · ${where}` : amount })),
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
  $("toast").hidden = true;
  for (const id of ["form-item", "form-entry", "form-place"]) $(id).hidden = id !== `form-${kind}`;
  const form = $(`form-${kind}`);
  form.reset();

  if (kind === "item") {
    // One form for both: state.editingId says whether Save sends PATCH (edit) or POST (new).
    state.editingId = item ? item.id : null;
    form.elements.location_id.replaceChildren(...state.locations.map((l) => new Option(cap(l.name), l.id)));
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

$("fab").addEventListener("click", () =>
  openSheet({ stock: "item", places: "place", list: "entry" }[state.view]));

$("from-low-stock").addEventListener("click", () =>
  run(() => api("POST", "/shopping-list/from-low-stock"), (added) =>
    added.length ? `Added ${plural(added.length, "item", "items")} that ${added.length === 1 ? "is" : "are"} running low` : "Nothing is running low"));

$("scrim").addEventListener("click", closeSheet);
$("sheet-close").addEventListener("click", closeSheet);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) closeSheet(); });

run(async () => {});
