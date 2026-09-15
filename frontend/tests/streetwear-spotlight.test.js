const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

function readJson(...parts) {
  return JSON.parse(readFile(...parts).replace(/^\uFEFF/, ""));
}

test("streetwear spotlight is wired to the published catalog brand slugs", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const js = readFile("frontend", "pages", "home", "js", "main.js");
  const brands = readJson("frontend", "data", "brands.json").brands;
  const products = readJson("frontend", "data", "products.json").products;

  const expected = [
    ["bape", "bape"],
    ["synaworld", "syna-world"],
    ["corteiz", "corteiz"]
  ];

  assert.match(html, /data-streetwear-spotlight/);
  assert.match(html, /role="tablist"/);
  assert.match(html, /role="tabpanel"/);
  assert.doesNotMatch(html, />Streetwear spotlight</);
  assert.doesNotMatch(html, />BAPE, SynaWorld e Corteiz</);
  assert.doesNotMatch(html, /streetwear-spotlight-title/);
  assert.doesNotMatch(html, /streetwear-spotlight__head/);
  assert.match(
    html,
    /<article class="streetwear-spotlight__banner"[\s\S]*?<\/article>\s*<div class="streetwear-spotlight__tabs" role="tablist"/
  );
  assert.match(
    html,
    /data-spotlight-tab="bape">BAPE<\/button>[\s\S]*data-spotlight-tab="synaworld">SynaWorld<\/button>[\s\S]*data-spotlight-tab="corteiz">Corteiz<\/button>/
  );
  assert.doesNotMatch(html, /data-spotlight-title/);
  assert.doesNotMatch(html, /streetwear-spotlight__banner-copy/);
  assert.match(html, /editorial\/brands\/corteiz\/corteiz-hero\.webp/);
  assert.match(js, /editorial\/brands\/bape\/bape-hero\.png/);
  assert.match(js, /editorial\/brands\/synaworld\/synaworld-hero\.webp/);
  assert.match(js, /editorial\/brands\/corteiz\/corteiz-hero\.webp/);
  assert.match(js, /objectPosition: "50% 10%"/);
  assert.match(js, /mobileObjectPosition: "50% 5%"/);
  assert.match(js, /--spotlight-object-position/);
  assert.match(js, /window\.DripZoneProductsReady/);
  assert.match(js, /buildCatalogBrandHref\(brand\.slug\)/);
  assert.match(js, /tab\.classList\.toggle\("is-active", isActive\)/);
  assert.match(js, /tab\.setAttribute\("aria-selected", String\(isActive\)\)/);

  for (const [tabKey, brandId] of expected) {
    const brand = brands.find((candidate) => candidate.id === brandId);
    assert.ok(brand, `${brandId} should exist in brands.json`);
    assert.match(js, new RegExp(`${tabKey}: \\{[\\s\\S]*id: "${brandId}"`));
    assert.match(js, new RegExp(`slug: "${brand.slug}"`));
  }

  const publishedCounts = Object.fromEntries(
    expected.map(([, brandId]) => [brandId, products.filter((product) => product.brandId === brandId).length])
  );

  assert.deepEqual(publishedCounts, {
    bape: 0,
    "syna-world": 0,
    corteiz: 0
  });
});

test("streetwear spotlight assets are local and organized by brand", () => {
  const assets = [
    ["bape", "bape-hero.png"],
    ["synaworld", "synaworld-hero.webp"],
    ["corteiz", "corteiz-hero.webp"]
  ];

  for (const [brand, fileName] of assets) {
    const assetPath = path.join(root, "frontend", "assets", "editorial", "brands", brand, fileName);
    assert.ok(fs.existsSync(assetPath), `${fileName} should exist`);
    assert.ok(fs.statSync(assetPath).size > 10000, `${fileName} should be a real image asset`);
  }
});
