const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..", "..");
const source = fs.readFileSync(path.join(root, "frontend", "pages", "catalogo", "js", "site.js"), "utf8");

function loadSiteUtils(url) {
  const location = new URL(url);
  const window = {
    location,
    addEventListener() {}
  };
  const document = {
    addEventListener() {}
  };
  const HTMLImageElement = class HTMLImageElement {};

  vm.runInNewContext(source, {
    console: { warn() {} },
    document,
    HTMLImageElement,
    URL,
    window
  });

  return window.DripZoneUtils;
}

test("static local frontend resolves uploads through the local backend", () => {
  const utils = loadSiteUtils("http://localhost:5500/pages/catalogo/");

  assert.equal(
    utils.assetPath("/uploads/products/example/image.webp"),
    "http://localhost:8000/uploads/products/example/image.webp"
  );
  assert.equal(utils.backendOrigin(), "http://localhost:8000");
});

test("static local frontend preserves the current localhost family for uploads", () => {
  const utils = loadSiteUtils("http://127.0.0.1:5500/pages/catalogo/");

  assert.equal(
    utils.assetPath("/uploads/products/example/image.webp"),
    "http://127.0.0.1:8000/uploads/products/example/image.webp"
  );
});

test("proxy and production modes keep uploads same-origin relative", () => {
  assert.equal(
    loadSiteUtils("http://localhost:8080/pages/catalogo/").assetPath("/uploads/products/example/image.webp"),
    "../../uploads/products/example/image.webp"
  );
  assert.equal(
    loadSiteUtils("https://dripzone.com.br/pages/catalogo/").assetPath("/uploads/products/example/image.webp"),
    "../../uploads/products/example/image.webp"
  );
});
