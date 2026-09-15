const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");
const pages = ["home", "catalogo", "produto"];

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

function headerOf(html) {
  return html.match(/<header[\s\S]*?<\/header>/)?.[0] ?? "";
}

test("mobile header keeps menu and search on the left, logo centered, and cart on the right", () => {
  const mobileCss = readFile("frontend", "assets", "css", "mobile-header.css");

  assert.match(mobileCss, /@media \(max-width: 900px\)/);
  assert.match(mobileCss, /\.mobile-nav__left\s*{[\s\S]*?left: 0;[\s\S]*?display: flex;[\s\S]*?gap: 18px;/);
  assert.match(mobileCss, /\.site-header \.brand\s*{[\s\S]*?left: 50%;[\s\S]*?transform: translate\(-50%, -50%\);/);
  assert.doesNotMatch(mobileCss, /(^|\n)\s*\.brand\s*{[^}]*position: absolute;/);
  assert.match(mobileCss, /\.mobile-cart-trigger\s*{[\s\S]*?right: 0;[\s\S]*?display: grid;/);
  assert.match(mobileCss, /\.mobile-search-trigger,[\s\S]*?\.menu-toggle\s*{[\s\S]*?background: transparent;[\s\S]*?box-shadow: none;/);

  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const header = headerOf(html);

    assert.match(html, /href="\.\.\/\.\.\/assets\/css\/mobile-header\.css"/);
    assert.match(header, /class="mobile-nav__left"/);
    assert.match(header, /data-menu-toggle[\s\S]*?<span><\/span>\s*<span><\/span>\s*<span><\/span>/);
    assert.match(header, /class="mobile-search-trigger"[\s\S]*data-header-search-trigger/);
    assert.match(header, /class="mobile-cart-trigger cart-trigger"/);
    assert.match(header, /assets\/brand\/dripzone-header-logo\.png/);
    assert.doesNotMatch(header, /6ix|6IX|Company/i);
  }
});

test("mobile drawer has overlay, close button, account access, and requested item order", () => {
  const mobileCss = readFile("frontend", "assets", "css", "mobile-header.css");

  assert.match(mobileCss, /\.mobile-menu-overlay\s*{[\s\S]*?position: fixed;[\s\S]*?inset: 0;[\s\S]*?z-index: 1001;/);
  assert.match(mobileCss, /\.mobile-menu\s*{[\s\S]*?width: min\(90vw, 360px\);[\s\S]*?height: 100dvh;[\s\S]*?overflow-y: auto;[\s\S]*?transform: translateX\(-105%\);/);
  assert.match(mobileCss, /\.mobile-menu\.is-open\s*{[\s\S]*?transform: translateX\(0\);/);
  assert.match(mobileCss, /\.mobile-menu__group > button::after\s*{[\s\S]*?content: "\+";/);
  assert.match(mobileCss, /\.mobile-menu__group > button\[aria-expanded="true"\]::after\s*{[\s\S]*?content: "-";/);
  assert.match(mobileCss, /@media \(prefers-reduced-motion: reduce\)/);

  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const header = headerOf(html);
    const order = [
      "In",
      "Loja",
      "mobile-panel-roupas",
      "mobile-panel-sneakers",
      "mobile-panel-acessorios",
      "categoria=conjuntos",
      "mobile-panel-marcas",
      "Contato",
      "mobile-menu__account",
    ];

    assert.match(header, /data-mobile-menu-overlay hidden/);
    assert.match(header, /data-mobile-menu aria-hidden="true"/);
    assert.match(header, /data-mobile-menu-close/);
    assert.match(header, /class="mobile-menu__account-button"[^>]*aria-label="Conta"/);

    let cursor = -1;
    for (const token of order) {
      const next = header.indexOf(token, cursor + 1);
      assert.ok(next > cursor, `${page}: ${token} should follow the previous mobile drawer item`);
      cursor = next;
    }
  }
});

test("mobile menu script wires drawer close paths, body lock, accordions, and sneaker API", () => {
  const menuJs = readFile("frontend", "pages", "home", "js", "menu.js");
  const productCartJs = readFile("frontend", "pages", "produto", "js", "cart.js");

  assert.match(menuJs, /document\.querySelector\("\[data-mobile-menu-overlay\]"\)/);
  assert.match(menuJs, /document\.querySelector\("\[data-mobile-menu-close\]"\)/);
  assert.match(menuJs, /overlay\?\.addEventListener\("click"/);
  assert.match(menuJs, /closeButton\?\.addEventListener\("click"/);
  assert.match(menuJs, /document\.body\.classList\.toggle\("menu-open", isOpen\)/);
  assert.match(menuJs, /menu\.setAttribute\("aria-hidden", String\(!isOpen\)\)/);
  assert.match(menuJs, /panel\?\.setAttribute\("aria-hidden", String\(!willOpen\)\)/);
  assert.match(menuJs, /fetch\(apiUrl\("sneakers"\)/);
  assert.match(productCartJs, /document\.querySelectorAll\("\[data-cart-count\]"\)/);
});
