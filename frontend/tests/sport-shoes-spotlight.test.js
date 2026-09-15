const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

function getFunctionSource(source, name) {
  const start = source.indexOf(`const ${name} =`);
  assert.ok(start >= 0, `${name} should exist`);
  const bodyStart = source.indexOf("{", start);
  assert.ok(bodyStart > start, `${name} should have a body`);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    if (depth === 0) {
      return source.slice(start, source.indexOf(";", index) + 1);
    }
  }
  assert.fail(`${name} body should close`);
}

test("sport shoes spotlight is ordered after discount banner and before streetwear spotlight", () => {
  const html = readFile("frontend", "pages", "home", "index.html");

  const discountIndex = html.indexOf('<section class="home-promo-banner home-promo-banner--discount"');
  const sportShoesIndex = html.indexOf("data-sport-shoes-spotlight");
  const streetwearIndex = html.indexOf("data-streetwear-spotlight");

  assert.ok(discountIndex >= 0, "discount banner should exist");
  assert.ok(sportShoesIndex > discountIndex, "sport shoes spotlight should follow discount banner");
  assert.ok(streetwearIndex > sportShoesIndex, "streetwear spotlight should remain after sport shoes spotlight");
});

test("sport shoes spotlight preserves brand order, initial state, and image mapping", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const js = readFile("frontend", "pages", "home", "js", "main.js");

  const expected = [
    ["on-running", "ON RUNNING", "on-running.jfif"],
    ["nike", "NIKE", "nike.jfif"],
    ["fila", "FILA", "fila.jfif"],
    ["hoka", "HOKA", "hoka.jfif"],
    ["puma", "PUMA", "puma.jfif"],
    ["adidas", "ADIDAS", "adidas.jfif"]
  ];

  assert.match(html, /<h2 class="sport-shoes-spotlight__title"[^>]*>Tênis Esportivos<\/h2>/);
  assert.match(html, /data-sport-shoes-spotlight/);
  assert.match(html, /role="tablist" aria-label="Selecionar marca de tênis esportivos"/);
  assert.match(html, /role="tabpanel" aria-labelledby="sport-shoes-tab-on-running"/);
  assert.match(html, /data-sport-shoes-tab="on-running">ON RUNNING<\/button>[\s\S]*data-sport-shoes-tab="nike">NIKE<\/button>[\s\S]*data-sport-shoes-tab="fila">FILA<\/button>[\s\S]*data-sport-shoes-tab="hoka">HOKA<\/button>[\s\S]*data-sport-shoes-tab="puma">PUMA<\/button>[\s\S]*data-sport-shoes-tab="adidas">ADIDAS<\/button>/);
  assert.match(html, /<button class="streetwear-spotlight__tab sport-shoes-spotlight__tab is-active"[^>]*aria-selected="true"[^>]*data-sport-shoes-tab="on-running"/);
  assert.match(html, /src="\.\.\/\.\.\/assets\/home\/sport-shoes\/on-running\.jfif"/);
  assert.match(html, /fetchpriority="high"/);

  for (const [key, label, fileName] of expected) {
    const assetPath = path.join(root, "frontend", "assets", "home", "sport-shoes", fileName);
    assert.ok(fs.existsSync(assetPath), `${fileName} should exist`);
    assert.ok(fs.statSync(assetPath).size > 10000, `${fileName} should be a real image asset`);
    assert.match(js, new RegExp(`(?:"${key}"|${key}): \\{[\\s\\S]*name: "${label}"[\\s\\S]*home/sport-shoes/${fileName}`));
  }
});

test("sport shoes spotlight reuses spotlight interaction without product dependency", () => {
  const js = readFile("frontend", "pages", "home", "js", "main.js");
  const initSource = getFunctionSource(js, "initSportShoesSpotlight");
  const responsiveCss = readFile("frontend", "pages", "home", "css", "responsive.css");

  assert.match(initSource, /\[data-sport-shoes-spotlight\]/);
  assert.match(initSource, /Object\.values\(sportShoeBrands\)\.forEach/);
  assert.match(initSource, /const preload = new Image\(\)/);
  assert.match(initSource, /tab\.classList\.toggle\("is-active", isActive\)/);
  assert.match(initSource, /tab\.setAttribute\("aria-selected", String\(isActive\)\)/);
  assert.match(initSource, /image\.src = brand\.image/);
  assert.match(initSource, /image\.alt = brand\.alt/);
  assert.match(initSource, /--spotlight-object-position/);
  assert.match(js, /puma: \{[\s\S]*objectPosition: "50% 88%"[\s\S]*mobileObjectPosition: "50% 58%"/);
  assert.match(initSource, /ArrowRight/);
  assert.match(initSource, /ArrowLeft/);
  assert.match(initSource, /scrollIntoView\(\{\s*behavior: prefersReducedMotion \? "auto" : "smooth",\s*block: "nearest",\s*inline: "center"\s*\}\)/);
  assert.match(initSource, /setActiveSportShoeBrand\("on-running"\)/);
  assert.doesNotMatch(initSource, /DripZoneProductsReady|DripZoneProducts|productsByBrand|buildCatalogBrandHref/);
  assert.match(js, /initSportShoesSpotlight\(\);\s*\n  initStreetwearSpotlight\(\);/);

  assert.match(responsiveCss, /\.sport-shoes-spotlight__tabs\s*{[^}]*display: flex;[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto;[^}]*overflow-y: hidden;[^}]*padding-inline: 6px 24px;[^}]*scrollbar-width: none;[^}]*white-space: nowrap/s);
  assert.match(responsiveCss, /\.sport-shoes-spotlight__tabs::\-webkit-scrollbar\s*{\s*display: none;\s*}/);
  assert.match(responsiveCss, /\.sport-shoes-spotlight__tab\s*{[^}]*flex: 0 0 auto;[^}]*min-width: max-content;[^}]*white-space: nowrap/s);
});
