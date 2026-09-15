const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");
const publicPages = ["home", "catalogo", "produto", "contato", "sobre"];

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

test("public storefront uses Roboto as the single global font family", () => {
  for (const page of publicPages) {
    const variables = readFile("frontend", "pages", page, "css", "variables.css");
    const style = readFile("frontend", "pages", page, "css", "style.css");

    assert.match(variables, /family=Roboto:ital,wght@0,100\.\.900;1,100\.\.900&display=swap/);
    assert.match(variables, /--font-family-base: "Roboto", Arial, sans-serif;/);
    assert.match(variables, /--font-main: var\(--font-family-base\);/);
    assert.match(variables, /--font-display: var\(--font-family-base\);/);
    assert.match(style, /body\s*{[^}]*font-family: var\(--font-main\)/s);
    assert.match(style, /button,\s*input,\s*select,\s*textarea,\s*option\s*{\s*font: inherit;\s*}/s);
    assert.doesNotMatch(variables, /Inter|Segoe UI|Arial Black|Helvetica/);
  }
});

test("admin uses Roboto globally and keeps form controls inheriting typography", () => {
  const adminFiles = [
    ["frontend", "admin", "css", "admin.css"],
    ["frontend", "admin", "categorias", "css", "admin.css"],
    ["frontend", "admin", "colecoes", "css", "admin.css"],
    ["frontend", "admin", "configuracoes", "css", "admin.css"],
    ["frontend", "admin", "importacoes", "css", "admin.css"],
    ["frontend", "admin", "login", "css", "admin.css"],
    ["frontend", "admin", "marcas", "css", "admin.css"],
    ["frontend", "admin", "produtos", "css", "admin.css"],
    ["frontend", "admin", "produtos", "editar", "css", "admin.css"],
    ["frontend", "admin", "produtos", "novo", "css", "admin.css"]
  ];

  for (const parts of adminFiles) {
    const css = readFile(...parts);

    assert.match(css, /family=Roboto:ital,wght@0,100\.\.900;1,100\.\.900&display=swap/);
    assert.match(css, /--font-family-base: "Roboto", Arial, sans-serif;/);
    assert.match(css, /body\s*{[^}]*font-family: var\(--font-family-base\)/s);
    assert.match(css, /button,\s*input,\s*select,\s*textarea,\s*option\s*{\s*font: inherit;\s*}/s);
    assert.doesNotMatch(css, /Inter|Helvetica|Segoe UI|Arial Black/);
  }

  const theme = readFile("frontend", "admin", "css", "theme.css");
  assert.match(theme, /--font-family-base: "Roboto", Arial, sans-serif;/);
  assert.match(theme, /body\s*{[^}]*font-family: var\(--font-family-base\)/s);
  assert.doesNotMatch(theme, /Inter|Helvetica|Segoe UI|Arial Black/);
});
