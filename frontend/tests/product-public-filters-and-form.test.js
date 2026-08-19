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

    assert.match(source, /let loadedProduct = null/);
    assert.match(source, /loadedProduct = product/);
    assert.match(source, /loadedProduct = saved/);
    assert.match(source, /loadedProduct = await publishProduct\(saved\.id\)/);
    assert.doesNotMatch(source, /collectPayload\(false\)/);
    assert.match(source, /status: loadedProduct\.status \|\| "draft"/);
    assert.match(source, /visibility: loadedProduct\.visibility/);
  }
});

test("public catalog supports collection filters exported as collectionIds", () => {
  const source = readProjectFile("frontend", "pages", "catalogo", "js", "catalog.js");

  assert.match(source, /productCollectionIds/);
  assert.match(source, /Array\.isArray\(product\.collectionIds\)/);
  assert.match(source, /productCollectionIds\(product\)\.includes\(state\.collectionId\)/);
});
