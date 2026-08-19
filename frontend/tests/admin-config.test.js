const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..", "..");
const source = fs.readFileSync(path.join(root, "frontend", "admin", "js", "config.js"), "utf8");

function loadConfig(hostname, globals = {}) {
  const transformed = source.replace(/export const /g, "const ").concat("\nwindow.__config = { API_BASE_URL, ADMIN_CONFIG, IS_DEVELOPMENT };\n");
  const window = {
    location: { hostname, port: globals.port || "" },
    navigator: {},
    console: { log() {} },
    ...globals
  };
  vm.runInNewContext(transformed, { window, navigator: window.navigator });
  return window.__config;
}

test("admin defaults to Docker/Caddy API during local development", () => {
  assert.equal(loadConfig("127.0.0.1").API_BASE_URL, "/api");
  assert.equal(loadConfig("localhost").API_BASE_URL, "/api");
});

test("admin uses same-origin API when opened through local Docker proxy", () => {
  assert.equal(loadConfig("127.0.0.1", { port: "8080" }).API_BASE_URL, "/api");
});

test("admin defaults to same-origin API behind production proxy", () => {
  const config = loadConfig("dripzone.com.br");

  assert.equal(config.API_BASE_URL, "/api");
  assert.equal(config.IS_DEVELOPMENT, false);
});

test("admin preserves explicit API base URL override", () => {
  const config = loadConfig("dripzone.com.br", { DRIPZONE_API_BASE_URL: "https://api.example.test/api" });

  assert.equal(config.API_BASE_URL, "https://api.example.test/api");
});
