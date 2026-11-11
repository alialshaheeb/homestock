// Where the UI finds the two services. These are the local docker compose ports;
// the deploy pipeline overwrites this file with the Azure URLs (no URL is hardcoded in app.js).
window.HOMESTOCK_CONFIG = {
  inventoryUrl: "http://localhost:8001",
  restockUrl: "http://localhost:8002",
};
