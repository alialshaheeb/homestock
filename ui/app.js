// HomeStock UI: plain JavaScript that only talks to the JSON API.
// API_BASE is "" because the same process serves the UI and the API (Assignment 1).
const API_BASE = "";

const state = { filter: "all", locationId: "" };
const $ = (id) => document.getElementById(id);

async function api(method, path, body) {
  const res = await fetch(API_BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ")
      : data.detail;
    throw new Error(detail || `${method} ${path} failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

function showError(err) {
  $("error").textContent = err.message;
  $("error").hidden = false;
}

// Run an action, then refresh everything; errors go to the banner instead of the console.
async function run(action) {
  $("error").hidden = true;
  try {
    await action();
    await refresh();
  } catch (err) {
    showError(err);
  }
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function button(label, onClick, title) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "small";
  b.textContent = label;
  if (title) b.title = title;
  b.addEventListener("click", onClick);
  return b;
}

function daysUntil(isoDate) {
  const today = new Date(new Date().toDateString());
  return Math.round((new Date(isoDate) - today) / 86400000);
}

async function loadLocations() {
  const locations = await api("GET", "/locations");
  for (const select of [$("location-filter"), $("item-location")]) {
    const keep = select.value;
    select.querySelectorAll("option:not([value=''])").forEach((o) => o.remove());
    for (const loc of locations) select.add(new Option(loc.name, loc.id));
    select.value = keep || (select === $("item-location") && locations[0] ? locations[0].id : "");
  }
}

async function loadItems() {
  const params = new URLSearchParams();
  if (state.filter === "low") params.set("low_stock", "true");
  if (state.filter === "expiring") params.set("expiring_within_days", "3");
  if (state.locationId) params.set("location_id", state.locationId);
  const items = await api("GET", `/items?${params}`);

  const body = $("items");
  body.replaceChildren();
  for (const item of items) {
    const tr = document.createElement("tr");
    const name = cell(item.name);
    if (item.low_stock) name.append(Object.assign(document.createElement("span"), { className: "badge", textContent: "low" }));
    if (item.expiry_date && daysUntil(item.expiry_date) <= 3) {
      name.append(Object.assign(document.createElement("span"), { className: "badge", textContent: "expiring" }));
    }
    tr.append(
      name,
      cell(item.location),
      cell(`${item.quantity} ${item.unit}`),
      cell(item.min_threshold ? `${item.min_threshold} ${item.unit}` : "—"),
      cell(item.expiry_date || "—"),
    );
    const actions = document.createElement("td");
    actions.className = "actions";
    actions.append(
      button("−1", () => run(() => api("POST", `/items/${item.id}/consume`, { amount: 1 })), "Use one"),
      button("+1", () => run(() => api("POST", `/items/${item.id}/restock`, { amount: 1 })), "Add one"),
      button("🛒", () => run(() => api("POST", "/shopping-list", { inventory_item_id: item.id, quantity: Math.max(item.min_threshold, 1) })), "Add to shopping list"),
      button("✕", () => run(() => api("DELETE", `/items/${item.id}`)), "Delete"),
    );
    tr.append(actions);
    body.append(tr);
  }
  $("items-empty").hidden = items.length > 0;
}

async function loadShoppingList() {
  const entries = await api("GET", "/shopping-list");
  const open = $("open-entries");
  const bought = $("bought-entries");
  open.replaceChildren();
  bought.replaceChildren();

  for (const entry of entries) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `${entry.name} — ${entry.quantity} ${entry.unit}`;
    if (entry.source === "low_stock") {
      label.append(Object.assign(document.createElement("span"), { className: "meta", textContent: "  (low stock)" }));
    }
    li.append(label);
    if (entry.status === "open") {
      li.append(
        button("Bought", () => run(async () => {
          const result = await api("POST", `/shopping-list/${entry.id}/bought`);
          if (entry.inventory_item_id && !result.restocked) {
            throw new Error(`${entry.name} was marked bought, but it is no longer in the inventory.`);
          }
        })),
        button("✕", () => run(() => api("DELETE", `/shopping-list/${entry.id}`)), "Remove"),
      );
      open.append(li);
    } else {
      bought.append(li);
    }
  }
  $("entries-empty").hidden = open.children.length > 0;
}

async function refresh() {
  await Promise.all([loadItems(), loadShoppingList()]);
}

function formJson(form) {
  const data = Object.fromEntries(new FormData(form));
  for (const key of ["quantity", "min_threshold", "location_id"]) {
    if (key in data) data[key] = Number(data[key]);
  }
  if (data.expiry_date === "") delete data.expiry_date;
  return data;
}

document.querySelectorAll("[data-filter]").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("[data-filter]").forEach((x) => x.classList.toggle("active", x === b));
    state.filter = b.dataset.filter;
    run(async () => {});
  }),
);
$("location-filter").addEventListener("change", (e) => {
  state.locationId = e.target.value;
  run(async () => {});
});
$("from-low-stock").addEventListener("click", () => run(() => api("POST", "/shopping-list/from-low-stock")));

$("item-form").addEventListener("submit", (e) => {
  e.preventDefault();
  run(async () => {
    await api("POST", "/items", formJson(e.target));
    e.target.reset();
  });
});
$("location-form").addEventListener("submit", (e) => {
  e.preventDefault();
  run(async () => {
    await api("POST", "/locations", formJson(e.target));
    e.target.reset();
    await loadLocations();
  });
});
$("entry-form").addEventListener("submit", (e) => {
  e.preventDefault();
  run(async () => {
    await api("POST", "/shopping-list", formJson(e.target));
    e.target.reset();
  });
});

run(loadLocations);
