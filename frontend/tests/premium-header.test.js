const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");
const pages = ["home", "catalogo", "produto"];

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

test("public premium header uses the transparent DripZone asset", () => {
  const assetPath = path.join(root, "frontend", "assets", "brand", "dripzone-header-logo.png");
  const cartIconPath = path.join(root, "frontend", "assets", "icons", "cart-icons8-buying-ios27.png");
  const png = fs.readFileSync(assetPath);
  const cartIcon = fs.readFileSync(cartIconPath);

  assert.equal(png.subarray(1, 4).toString("ascii"), "PNG");
  assert.equal(png[25], 6, "PNG should preserve truecolor alpha transparency");
  assert.equal(cartIcon.subarray(1, 4).toString("ascii"), "PNG");
  assert.equal(cartIcon[25], 6, "Icons8 cart icon should preserve alpha transparency");

  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const header = html.match(/<header[\s\S]*?<\/header>/)?.[0] ?? "";

    assert.match(html, /assets\/brand\/dripzone-header-logo\.png/);
    assert.match(header, /assets\/icons\/cart-icons8-buying-ios27\.png/);
    assert.doesNotMatch(header, /assets\/images\/icones\/bag\.svg/);
    assert.match(header, /<a class="brand" href="(?:#inicio|\.\.\/home\/)" aria-label="[^"]*DripZone[^"]*">/);
    assert.doesNotMatch(header, /<span class="brand__name">DripZone<\/span>/);
    assert.doesNotMatch(html, /6ix|6IX|Company/i);
  }
});

test("public premium header keeps search, account, cart and desktop nav structure", () => {
  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const style = readFile("frontend", "pages", page, "css", "style.css");
    const responsive = readFile("frontend", "pages", page, "css", "responsive.css");

    assert.match(html, /class="nav-search" id="header-search" role="search"/);
    assert.match(html, /placeholder="Busque na DripZone"/);
    assert.match(html, /class="header-account"[^>]*aria-label="Conta"/);
    assert.match(html, /class="btn btn--neon btn--icon cart-trigger"[^>]*aria-label="(?:Carrinho|Abrir carrinho)"/);
    assert.match(html, /class="cart-count"[^>]*aria-live="polite">0<\/span>/);
    assert.match(html, /href="\.\.\/catalogo\/">Loja<\/a>/);
    assert.match(html, /href="\.\.\/catalogo\/\?categoria=conjuntos">Conjuntos<\/a>/);

    assert.match(style, /\.site-header,\s*\.site-header\.is-scrolled,\s*\.site-header\.is-open\s*{[^}]*background: #ffffff/s);
    assert.match(style, /\.site-header,\s*\.site-header\.is-scrolled,\s*\.site-header\.is-open\s*{[^}]*position: sticky/s);
    assert.match(style, /\.site-header,\s*\.site-header\.is-scrolled,\s*\.site-header\.is-open\s*{[^}]*top: 0/s);
    assert.match(style, /\.site-header,\s*\.site-header\.is-scrolled,\s*\.site-header\.is-open\s*{[^}]*z-index: 1000/s);
    assert.match(style, /\.site-header,\s*\.site-header\.is-scrolled,\s*\.site-header\.is-open\s*{[^}]*backdrop-filter: none/s);
    assert.match(style, /\.nav\s*{[^}]*max-width: 1220px/s);
    assert.match(style, /\.nav\s*{[^}]*grid-template-rows: 88px 54px/s);
    assert.match(style, /\.site-header\.is-compact \.nav\s*{[^}]*grid-template-rows: 88px 54px/s);
    assert.match(style, /\.site-header\.is-compact \.nav\s*{[^}]*min-height: 142px/s);
    assert.match(style, /\.nav-search\s*{[^}]*width: min\(100%, 286px\)/s);
    assert.match(style, /\.brand__mark,\s*\.site-header\.is-compact \.brand__mark\s*{[^}]*width: 92px/s);
    assert.match(style, /\.brand__mark,\s*\.site-header\.is-compact \.brand__mark\s*{[^}]*height: 62px/s);
    assert.match(style, /grid-template-areas:\s*"search brand actions"\s*"links links links"/);
    assert.match(style, /\.nav__links\s*{[^}]*border-top: 1px solid #eeeeee/s);
    assert.match(style, /\.nav__links\s*{[^}]*gap: clamp\(30px, 3vw, 42px\)/s);
    assert.match(style, /\.nav__actions \.cart-trigger\s*{[^}]*width: 44px/s);
    assert.match(style, /\.nav__actions \.cart-trigger\s*{[^}]*height: 44px/s);
    assert.match(style, /\.nav__actions \.cart-trigger\s*{[^}]*border: 0/s);
    assert.match(style, /\.nav__actions \.cart-trigger\s*{[^}]*background: transparent/s);
    assert.match(style, /\.nav__actions \.cart-trigger img\s*{[^}]*width: 28px/s);
    assert.match(style, /\.nav__actions \.cart-trigger img\s*{[^}]*filter: none/s);
    assert.match(style, /\.menu-toggle\s*{[^}]*background: #111111/s);
    assert.match(style, /\.nav__actions \.cart-count\s*{[^}]*top: 1px/s);
    assert.match(style, /\.nav__actions \.cart-count\s*{[^}]*right: 0/s);
    assert.match(style, /\.brand__mark img\s*{\s*filter: none/);
    assert.match(style, /\.site-header \.brand__name\s*{\s*display: none/s);
    assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.nav-search,\s*\.nav__links,\s*\.nav__actions\s*{\s*display: none/s);
    assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.nav\s*{[^}]*min-height: 68px/s);
    assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.site-header,[\s\S]*background: #ffffff/s);
    assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.mobile-menu\s*{[^}]*background: #ffffff/s);

    if (page === "home") {
      assert.match(html, /class="btn btn--dark btn--icon menu-toggle"[\s\S]*?<span><\/span>\s*<span><\/span>\s*<span><\/span>/);
      assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.brand\s*{[^}]*left: 50%;[^}]*transform: translate\(-50%, -50%\)/s);
      assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.brand__mark,[\s\S]*width: 70px/s);
      assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.menu-toggle\s*{[^}]*border: 0;[^}]*background: transparent;[^}]*box-shadow: none;[^}]*color: #111111/s);
      assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*\.menu-toggle span\s*{[^}]*width: 22px;[^}]*background: #111111/s);
    }
  }
});

test("premium header preserves functional hooks", () => {
  const homeJs = readFile("frontend", "pages", "home", "js", "main.js");
  const catalogSite = readFile("frontend", "pages", "catalogo", "js", "site.js");
  const productSite = readFile("frontend", "pages", "produto", "js", "site.js");
  const productHtml = readFile("frontend", "pages", "produto", "index.html");

  assert.match(homeJs, /data-header-search-form/);
  assert.match(homeJs, /params\.set\("q", term\)/);
  assert.match(catalogSite, /function initHeaderSearch\(\)/);
  assert.match(productSite, /function initHeaderSearch\(\)/);
  assert.match(catalogSite, /params\.set\("q", term\)/);
  assert.match(productSite, /params\.set\("q", term\)/);
    assert.match(productHtml, /data-cart-open/);
    assert.match(productHtml, /data-cart-count/);

  for (const file of [homeJs, catalogSite, productSite]) {
    assert.doesNotMatch(file, /addEventListener\(["']scroll["']/);
  }
});
