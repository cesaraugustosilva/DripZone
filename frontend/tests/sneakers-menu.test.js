const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..", "..");
const pages = ["home", "catalogo", "produto", "contato", "sobre"];
const modelBrands = ["nike", "jordan", "adidas", "new-balance", "golden-goose"];
const expectedSneakerLinks = [
  ["Nike", "../catalogo/?marca=nike"],
  ["Jordan", "../catalogo/?marca=jordan"],
  ["Adidas", "../catalogo/?marca=adidas"],
  ["Amiri", "../catalogo/?marca=amiri"],
  ["Balenciaga", "../catalogo/?marca=balenciaga"],
  ["Louis Vuitton", "../catalogo/?marca=louis-vuitton"],
  ["Off-White", "../catalogo/?marca=off-white"],
  ["New Balance", "../catalogo/?marca=new-balance"],
  ["Bape", "../catalogo/?marca=bape"],
  ["Maison Mihara", "../catalogo/?marca=maison-mihara-yasuhiro"],
  ["Dior", "../catalogo/?marca=dior"],
  ["Golden Goose", "../catalogo/?marca=golden-goose"],
  ["Lanvin Curb", "../catalogo/?modelo=lanvin-curb"],
  ["Gucci", "../catalogo/?marca=gucci"],
  ["Alexander McQueen", "../catalogo/?marca=alexander-mcqueen"],
  ["Tênis Esportivos", "../catalogo/?categoria=tenis-esportivos"]
];
const expectedClothingLinks = [
  ["Ver tudo em Roupas", "../catalogo/?categoria=roupas"],
  ["Camisetas", "../catalogo/?categoria=camisetas"],
  ["Moletons / Jaquetas", "../catalogo/?categoria=moletons"],
  ["Shorts", "../catalogo/?categoria=shorts"],
  ["Calças", "../catalogo/?categoria=calcas"],
  ["Todos os Produtos", "../catalogo/"]
];
const expectedAccessoriesLinks = [
  ["Ver tudo em Acessórios", "../catalogo/?categoria=acessorios"],
  ["Anéis", "../catalogo/?categoria=aneis"],
  ["Bags/Mochilas", "../catalogo/?categoria=bags-mochilas"],
  ["Bonés", "../catalogo/?categoria=bones"],
  ["Balaclavas", "../catalogo/?categoria=balaclavas"],
  ["Carteiras", "../catalogo/?categoria=carteiras"],
  ["Cintos", "../catalogo/?categoria=cintos"],
  ["Óculos", "../catalogo/?categoria=oculos"],
  ["Pulseiras", "../catalogo/?categoria=pulseiras"],
  ["Relógios", "../catalogo/?categoria=relogios"],
  ["Toucas", "../catalogo/?categoria=toucas"]
];

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

function getBlock(html, startPattern, endPattern) {
  const start = html.search(startPattern);
  assert.notEqual(start, -1, `start ${startPattern} should exist`);
  const rest = html.slice(start);
  const end = rest.search(endPattern);
  assert.notEqual(end, -1, `end ${endPattern} should exist`);
  return rest.slice(0, end);
}

function extractAnchorPairs(block) {
  return [...block.matchAll(/<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/g)].map((match) => [match[2], match[1]]);
}

function getMobilePanel(html, id) {
  const match = html.match(new RegExp(`<div class="mobile-menu__panel" id="${id}">([\\s\\S]*?)\\n\\s*</div>`));
  assert.ok(match, `mobile panel ${id} should exist`);
  return match[1];
}

class FakeClassList {
  constructor(element) {
    this.element = element;
    this.values = new Set();
  }

  add(...names) {
    names.forEach((name) => this.values.add(name));
    this.element.className = [...this.values].join(" ");
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
    this.element.className = [...this.values].join(" ");
  }

  contains(name) {
    return this.values.has(name);
  }

  toggle(name, force) {
    const next = force ?? !this.values.has(name);
    if (next) this.add(name);
    else this.remove(name);
    return next;
  }

  setFromString(value) {
    this.values = new Set(String(value || "").split(/\s+/).filter(Boolean));
  }
}

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentElement = null;
    this.attributes = new Map();
    this.dataset = {};
    this.eventListeners = {};
    this.hidden = false;
    this.textContent = "";
    this.classList = new FakeClassList(this);
    this.style = { setProperty: () => {} };
  }

  set className(value) {
    this._className = String(value || "");
    this.classList?.setFromString(this._className);
  }

  get className() {
    return this._className || "";
  }

  set id(value) {
    this.setAttribute("id", value);
  }

  get id() {
    return this.getAttribute("id") || "";
  }

  set href(value) {
    this.setAttribute("href", value);
  }

  get href() {
    return this.getAttribute("href") || "";
  }

  append(...nodes) {
    nodes.forEach((node) => {
      if (typeof node === "string") {
        this.textContent += node;
        return;
      }
      node.parentElement = this;
      this.children.push(node);
    });
  }

  replaceChildren(...nodes) {
    this.children = [];
    this.textContent = "";
    this.append(...nodes);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === "class") this.className = value;
    if (name === "id") this.attributes.set("id", String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) || null;
  }

  addEventListener(name, callback) {
    this.eventListeners[name] = callback;
  }

  matches(selector) {
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
    if (/^\[[^\]]+\]$/.test(selector)) {
      const attr = selector.slice(1, -1).split("=")[0];
      if (attr.startsWith("data-")) return this.dataset[toDatasetKey(attr)] !== undefined;
      return this.attributes.has(attr);
    }
    return this.tagName.toLowerCase() === selector.toLowerCase();
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (matchesAny(current, selector)) return current;
      current = current.parentElement;
    }
    return null;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const result = [];
    walk(this, (node) => {
      if (node !== this && matchesAny(node, selector)) result.push(node);
    });
    return result;
  }

  getBoundingClientRect() {
    return { top: 0, left: 0, right: 180, width: 180 };
  }
}

function toDatasetKey(attribute) {
  return attribute.replace(/^data-/, "").replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

function matchesAny(element, selector) {
  return selector.split(",").some((part) => element.matches(part.trim()));
}

function walk(element, callback) {
  element.children.forEach((child) => {
    callback(child);
    walk(child, callback);
  });
}

function createFakeDocument() {
  const all = [];
  const document = {
    body: new FakeElement("body"),
    createElement(tag) {
      const element = new FakeElement(tag);
      all.push(element);
      return element;
    },
    createTextNode(text) {
      return String(text);
    },
    getElementById(id) {
      return all.find((element) => element.id === id) || null;
    },
    querySelector(selector) {
      return all.find((element) => matchesAny(element, selector)) || null;
    },
    querySelectorAll(selector) {
      return all.filter((element) => matchesAny(element, selector));
    },
    addEventListener() {}
  };
  all.push(document.body);
  return { document, all };
}

test("sneaker menu models are not derived from product data", () => {
  const data = JSON.parse(readFile("frontend", "data", "products.json"));

  for (const brandId of modelBrands) {
    const modelIds = new Set(
      data.products
        .filter((product) => product.brandId === brandId)
        .map((product) => product.modelId)
        .filter(Boolean)
    );
    assert.equal(modelIds.size, 0, `${brandId} has no product modelIds in exported products`);
  }
});

test("public Sneakers menu keeps ordered direct links on desktop and mobile", () => {
  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const desktop = getBlock(
      html,
      /<div class="dropdown-menu dropdown-menu--vertical dropdown-menu--tall" id="menu-sneakers"/,
      /<button class="nav__trigger"[^>]*aria-controls="menu-acessorios"/
    );
    const mobile = getBlock(
      html,
      /<div class="mobile-menu__panel" id="mobile-panel-sneakers">/,
      /<div class="mobile-menu__group">\s*<button type="button" data-mobile-accordion[^>]+aria-controls="mobile-panel-acessorios"/
    );

    assert.deepEqual(extractAnchorPairs(desktop), expectedSneakerLinks, `${page} desktop Sneakers order/links`);
    assert.deepEqual(extractAnchorPairs(mobile), expectedSneakerLinks, `${page} mobile Sneakers order/links`);
    assert.doesNotMatch(desktop, /data-submenu|dropdown-menu__arrow|dropdown-submenu|aria-haspopup="true"/);
    assert.doesNotMatch(mobile, /data-submenu|mobile-menu__nested|mobile-menu__nested-list/);
  }
});

test("public clothing and accessories menus start with scoped view-all links", () => {
  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const desktopClothing = getBlock(
      html,
      /<div class="dropdown-menu " id="menu-roupas"/,
      /<button class="nav__trigger"[^>]*aria-controls="menu-sneakers"/
    );
    const desktopAccessories = getBlock(
      html,
      /<div class="dropdown-menu dropdown-menu--vertical" id="menu-acessorios"/,
      /<button class="nav__trigger"[^>]*aria-controls="menu-marcas"/
    );
    const mobileClothing = getBlock(
      html,
      /<div class="mobile-menu__panel" id="mobile-panel-roupas">/,
      /<div class="mobile-menu__group">\s*<button type="button" data-mobile-accordion[^>]+aria-controls="mobile-panel-sneakers"/
    );
    const mobileAccessories = getMobilePanel(html, "mobile-panel-acessorios");

    assert.deepEqual(extractAnchorPairs(desktopClothing), expectedClothingLinks, `${page} desktop Roupas order/links`);
    assert.deepEqual(extractAnchorPairs(mobileClothing), expectedClothingLinks, `${page} mobile Roupas order/links`);
    assert.deepEqual(extractAnchorPairs(desktopAccessories), expectedAccessoriesLinks, `${page} desktop Acessórios order/links`);
    assert.deepEqual(extractAnchorPairs(mobileAccessories), expectedAccessoriesLinks, `${page} mobile Acessórios order/links`);
  }
});

test("public Sneakers submenus are generated from sneaker taxonomy API data", () => {
  const menuJs = readFile("frontend", "pages", "home", "js", "menu.js");
  const desktopRenderer = menuJs.slice(
    menuJs.indexOf("const renderDesktopSneakers"),
    menuJs.indexOf("const renderMobileSneakers")
  );

  assert.match(menuJs, /window\.DripZoneSneakerModelsReady/);
  assert.match(menuJs, /fetch\(apiUrl\("sneakers"\)/);
  assert.match(menuJs, /model\.brand_slug \|\| model\.brandId/);
  assert.match(menuJs, /model\.slug \|\| model\.modelId/);
  assert.match(menuJs, /model\.name \|\| model\.model \|\| model\.modelName \|\| model\.slug/);
  assert.match(menuJs, /model\.is_active === false/);
  assert.match(menuJs, /renderSneakerMenus\(models \|\| \[\]\)/);
  assert.doesNotMatch(menuJs, /products\.json/);
  assert.doesNotMatch(menuJs, /DripZoneProductsReady/);
  assert.match(menuJs, /dropdown-menu__item has-submenu/);
  assert.doesNotMatch(desktopRenderer, /submenu\.hidden = true/);
  assert.doesNotMatch(desktopRenderer, /dataset\.submenu/);
  assert.doesNotMatch(desktopRenderer, /dataset\.submenuItem/);
  assert.doesNotMatch(desktopRenderer, /data-submenu/);
  assert.match(menuJs, /mobile-menu__nested-row/);
  assert.match(menuJs, /catalogModelHref/);
  assert.match(menuJs, /heading\.className = "dropdown-submenu__heading"/);
  assert.match(menuJs, /heading\.textContent = entry\.label/);
  assert.match(menuJs, /Ver tudo em \$\{entry\.label\}/);
  assert.match(menuJs, /arrow\.textContent = ">"/);
  assert.match(menuJs, /button\.textContent = ">"/);
  assert.match(menuJs, /marca=\$\{encodeURIComponent\(brandId\)\}&modelo=\$\{encodeURIComponent\(modelId\)\}/);
  assert.doesNotMatch(menuJs, /positionDesktopSubmenu/);
  assert.doesNotMatch(menuJs, /--submenu-top/);
  assert.doesNotMatch(menuJs, /--submenu-left/);
  assert.doesNotMatch(menuJs, /scheduleSubmenuClose/);
  assert.doesNotMatch(menuJs, /submenuCloseTimer/);
  assert.doesNotMatch(menuJs, /positionDesktopSubmenu|mouseenter[\s\S]*openSubmenu|mouseleave[\s\S]*scheduleSubmenuClose/);
  assert.doesNotMatch(menuJs, /dropdown-submenu--left/);

  for (const page of pages) {
    const html = readFile("frontend", "pages", page, "index.html");
    const desktop = getBlock(
      html,
      /<div class="dropdown-menu dropdown-menu--vertical dropdown-menu--tall" id="menu-sneakers"/,
      /<button class="nav__trigger"[^>]*aria-controls="menu-acessorios"/
    );
    assert.doesNotMatch(desktop, /modelo=(air-force|air-max|dunk|jordan-|yeezy|new-balance-|golden-goose-)/);
  }
});

test("sneaker taxonomy API payload renders Nike submenu DOM", async () => {
  const { document } = createFakeDocument();
  const header = document.createElement("header");
  header.dataset.header = "";
  const toggle = document.createElement("button");
  toggle.dataset.menuToggle = "";
  const mobileMenu = document.createElement("div");
  mobileMenu.dataset.mobileMenu = "";
  const desktopSneakers = document.createElement("div");
  desktopSneakers.id = "menu-sneakers";
  const mobileSneakers = document.createElement("div");
  mobileSneakers.id = "mobile-panel-sneakers";

  header.append(toggle, desktopSneakers);
  mobileMenu.append(mobileSneakers);
  document.body.append(header, mobileMenu);

  const requestedUrls = [];
  const window = {
    DripZoneUtils: { backendOrigin: () => "" },
    innerWidth: 1280,
    clearTimeout,
    setTimeout,
    requestAnimationFrame: (callback) => callback(),
    addEventListener() {},
    fetch: async (url) => {
      requestedUrls.push(url);
      return {
        ok: true,
        status: 200,
        json: async () => [
          { brand_slug: "nike", name: "Air Force", slug: "air-force", is_active: true },
          { brand_slug: "nike", name: "Air Max TN Plus", slug: "air-max-tn-plus", is_active: true },
          { brand_slug: "nike", name: "Nike Mind", slug: "nike-mind", is_active: true },
          { brand_slug: "nike", name: "Air Max 95", slug: "air-max-95", is_active: true },
          { brand_slug: "nike", name: "Air Max DN", slug: "air-max-dn", is_active: true },
          { brand_slug: "nike", name: "Dunk", slug: "dunk", is_active: true },
          { brand_slug: "nike", name: "Nike x Kobe Bryant", slug: "nike-x-kobe-bryant", is_active: true },
          { brand_slug: "nike", name: "Nike Ja Morant", slug: "nike-ja-morant", is_active: true },
          { brand_slug: "nike", name: "Nike Shox", slug: "nike-shox", is_active: true },
          { brand_slug: "nike", name: "Uptempo", slug: "uptempo", is_active: true },
          { brand_slug: "nike", name: "Vomero Premium", slug: "vomero-premium", is_active: true },
          { brand_slug: "nike", name: "Travis Scott", slug: "travis-scott", is_active: true },
          { brand_slug: "jordan", name: "Jordan 4", slug: "jordan-4", is_active: true }
        ]
      };
    }
  };

  vm.runInNewContext(readFile("frontend", "pages", "home", "js", "menu.js"), {
    document,
    fetch: window.fetch,
    window,
    Element: FakeElement,
    setTimeout,
    clearTimeout
  });

  window.DripZone.initMenu();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const nikeItem = desktopSneakers.querySelector("#menu-sneakers-nike")?.closest(".dropdown-menu__item");
  const nikeLinks = nikeItem?.querySelector(".dropdown-submenu")?.querySelectorAll(".dropdown-menu__link") || [];
  const mobileNikeLinks = mobileSneakers.querySelector("#mobile-sneakers-nike")?.querySelectorAll("a") || [];

  assert.deepEqual(requestedUrls, ["/api/sneakers"]);
  assert.ok(nikeItem, "Nike should render as a submenu item from API taxonomy");
  assert.equal(nikeItem.querySelector(".dropdown-menu__link--button")?.textContent, "Nike");
  assert.equal(nikeItem.querySelector(".dropdown-menu__arrow")?.textContent, ">");
  assert.equal(nikeItem.querySelector(".dropdown-submenu__heading")?.textContent, "Nike");
  assert.equal(nikeLinks.length, 13);
  assert.equal(nikeLinks[0].textContent, "Ver tudo em Nike");
  assert.equal(nikeLinks[0].getAttribute("href"), "../catalogo/?marca=nike");
  assert.equal(nikeLinks[1].textContent, "Air Force");
  assert.equal(nikeLinks[1].getAttribute("href"), "../catalogo/?marca=nike&modelo=air-force");
  assert.equal(nikeLinks[12].textContent, "Travis Scott");
  assert.equal(nikeLinks[12].getAttribute("href"), "../catalogo/?marca=nike&modelo=travis-scott");
  assert.equal(mobileNikeLinks.length, 13);
  assert.equal(mobileNikeLinks[0].textContent, "Ver tudo em Nike");
  assert.equal(mobileNikeLinks[1].textContent, "Air Force");
  const amiri = desktopSneakers.children.find((child) => child.textContent === "Amiri");
  assert.ok(amiri, "Amiri should remain a simple link");
  assert.equal(amiri.querySelector(".dropdown-menu__arrow"), null);
});

test("Sneakers flyout CSS opens laterally without clipping or a dead hover gap", () => {
  for (const page of pages) {
    const style = readFile("frontend", "pages", page, "css", "style.css");
    const responsive = readFile("frontend", "pages", page, "css", "responsive.css");

    assert.match(style, /\.dropdown-menu__link,[\s\S]*?min-height: 42px/s);
    assert.match(style, /\.dropdown-menu__link,[\s\S]*?align-items: center/s);
    assert.match(style, /\.dropdown-menu__link,[\s\S]*?padding: 0 12px/s);
    assert.match(style, /\.dropdown-menu__link,[\s\S]*?white-space: nowrap/s);
    assert.match(style, /\.nav__item\.is-open \.dropdown-menu,[\s\S]*?\.nav__item:focus-within \.dropdown-menu\s*{[\s\S]*?opacity: 1;[\s\S]*?pointer-events: auto;[\s\S]*?transform: none;/);
    assert.match(style, /\.dropdown-menu--tall\s*{[\s\S]*?overflow: visible;/);
    assert.doesNotMatch(style, /\.dropdown-menu__item\.has-submenu::after/);
    assert.match(style, /#menu-sneakers\.dropdown-menu--tall\s*{[\s\S]*?top: calc\(100% \+ 8px\);[\s\S]*?min-width: 280px;[\s\S]*?max-height: calc\(100vh - 24px\);[\s\S]*?overflow: visible;/);
    assert.match(style, /#menu-sneakers > \.dropdown-menu__link,[\s\S]*?#menu-sneakers > \.dropdown-menu__item > \.dropdown-menu__link\s*{[\s\S]*?min-height: 35px;/);
    assert.match(style, /#menu-sneakers > \.dropdown-menu__item:nth-child\(n\+8\) > \.dropdown-submenu\s*{[\s\S]*?top: auto;[\s\S]*?bottom: 0;/);
    assert.match(style, /\.dropdown-menu__arrow\s*{[\s\S]*?margin-left: auto;[\s\S]*?color: #111111;[\s\S]*?font-size: 1\.1rem;[\s\S]*?opacity: 1;/);
    assert.match(style, /\.dropdown-submenu\s*{[\s\S]*?position: absolute;[\s\S]*?top: 0;[\s\S]*?left: calc\(100% - 1px\);[\s\S]*?min-width: 230px;[\s\S]*?max-width: min\(300px, calc\(100vw - 32px\)\);[\s\S]*?background: #ffffff;[\s\S]*?visibility: hidden;/);
    assert.match(style, /\.dropdown-submenu__heading\s*{[\s\S]*?letter-spacing: 0\.08em;[\s\S]*?text-transform: uppercase;/);
    assert.match(style, /\.dropdown-submenu > \.dropdown-menu__link\s*{[\s\S]*?font-weight: 650;[\s\S]*?text-transform: none;/);
    assert.match(style, /\.dropdown-submenu > \.dropdown-submenu__view-all\s*{[\s\S]*?font-weight: 800;/);
    assert.doesNotMatch(style, /\.dropdown-submenu--left/);
    assert.match(style, /\.dropdown-menu__item:hover > \.dropdown-submenu,[\s\S]*?visibility: visible;[\s\S]*?transform: translateX\(0\);/);
    assert.match(responsive, /@media \(max-width: 900px\)[\s\S]*?\.dropdown-menu\s*{[\s\S]*?display: none;/);
    assert.match(responsive, /\.mobile-menu__nested-row \.mobile-menu__nested-link\s*{[\s\S]*?font-weight: 700;/);
    assert.match(responsive, /\.mobile-menu__nested-toggle\[aria-expanded="true"\]\s*{[\s\S]*?transform: rotate\(90deg\);/);
    assert.match(responsive, /\.mobile-menu__nested-list\s*{[\s\S]*?margin: 0 0 10px 18px;[\s\S]*?padding-left: 12px;/);
    assert.match(responsive, /\.mobile-menu__nested-list a\s*{[\s\S]*?font-weight: 500;/);
    assert.match(responsive, /\.mobile-menu__nested-list\[hidden\]\s*{[\s\S]*?display: none;/);
  }
});
