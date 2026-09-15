const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readProjectFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

test("admin product form preserves publication state while editing", () => {
  for (const page of ["novo", "editar"]) {
    const source = readProjectFile("frontend", "admin", "produtos", page, "js", "product-form.js");
    const html = readProjectFile("frontend", "admin", "produtos", page, "index.html");

    assert.match(source, /let loadedProduct = null/);
    assert.match(source, /loadedProduct = product/);
    assert.match(source, /loadedProduct = saved/);
    assert.match(source, /loadedProduct = await publishProduct\(saved\.id\)/);
    assert.doesNotMatch(source, /collectPayload\(false\)/);
    assert.match(source, /status: loadedProduct\.status \|\| "draft"/);
    assert.match(source, /visibility: loadedProduct\.visibility/);
    assert.match(source, /getBrands/);
    assert.match(source, /getCategories/);
    assert.match(source, /getSneakers/);
    assert.match(source, /sneaker_model_id: !document\.getElementById\("product-model"\)\?\.disabled \? selectedId\("product-model"\) : null/);
    assert.match(source, /model\.brand_id === brandId/);
    assert.match(source, /wrapper\.hidden = !enabled/);
    assert.match(source, /select\.disabled = !enabled/);
    assert.match(html, /<select id="product-brand" data-product-brand-select>/);
    assert.match(html, /<select id="product-category" data-product-category-select>/);
    assert.match(html, /data-sneaker-model-field hidden/);
    assert.match(html, /<select id="product-model" data-sneaker-model-select disabled>/);
  }
});

test("public catalog supports collection filters exported as collectionIds", () => {
  const source = readProjectFile("frontend", "pages", "catalogo", "js", "catalog.js");

  assert.match(source, /productCollectionIds/);
  assert.match(source, /Array\.isArray\(product\.collectionIds\)/);
  assert.match(source, /productCollectionIds\(product\)\.includes\(state\.collectionId\)/);
});

test("public catalog treats roupas as a real aggregate filter", () => {
  const source = readProjectFile("frontend", "pages", "catalogo", "js", "catalog.js");

  assert.match(source, /Roupas: "roupas"/);
  assert.match(source, /roupas: new Set\(\["camisetas", "calcas", "moletons", "jaquetas", "shorts", "conjuntos"\]\)/);
  assert.match(source, /categoryGroup \? categoryGroup\.has\(product\.categoryId\) : product\.categoryId === state\.categoryId/);
});
