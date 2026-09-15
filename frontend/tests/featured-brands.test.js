const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readJson(...parts) {
  return JSON.parse(fs.readFileSync(path.join(root, ...parts), "utf8"));
}

test("featured brands are unique and use the catalog brand filter", () => {
  const data = readJson("frontend", "data", "featured-brands.json");
  const brands = data.brands.filter((brand) => brand.featured !== false);
  const slugs = brands.map((brand) => brand.slug);

  assert.equal(data.catalogParam, "marca");
  assert.equal(brands.length, 24);
  assert.equal(new Set(slugs).size, slugs.length);
  assert.ok(brands.every((brand) => /^[a-z0-9-]+$/.test(brand.slug)));

  for (const slug of ["nike", "adidas", "supreme", "stussy", "palm-angels"]) {
    assert.ok(slugs.includes(slug), `${slug} should be featured`);
    assert.equal(`/pages/catalogo/?${data.catalogParam}=${slug}`, `/pages/catalogo/?marca=${slug}`);
  }
});

test("featured brand assets are local when present and can fall back to text", () => {
  const data = readJson("frontend", "data", "featured-brands.json");
  const manifest = readJson("frontend", "assets", "brands", "brands-assets.json");
  const manifestBySlug = new Map(manifest.assets.map((asset) => [asset.slug, asset]));

  for (const brand of data.brands) {
    const asset = manifestBySlug.get(brand.slug);
    assert.ok(asset, `${brand.slug} should be listed in brands-assets.json`);

    if (!brand.logo) {
      assert.equal(asset.review_status, "NEEDS_REVIEW");
      assert.equal(asset.format, "typographic");
      continue;
    }

    assert.match(brand.logo, /^assets\/brands\/[a-z0-9-]+\.(svg|png)$/);
    assert.ok(fs.existsSync(path.join(root, "frontend", brand.logo)), `${brand.logo} should exist locally`);
  }
});

test("home renderer includes logo error fallback and duplicate visual track", () => {
  const source = fs.readFileSync(path.join(root, "frontend", "pages", "home", "js", "main.js"), "utf8");
  const siteSource = fs.readFileSync(path.join(root, "frontend", "pages", "home", "js", "site.js"), "utf8");

  assert.match(source, /data\/featured-brands\.json/);
  assert.match(source, /featured-brand__fallback/);
  assert.match(source, /addEventListener\("error"/);
  assert.match(source, /image\.dataset\.featuredBrandLogo = slug/);
  assert.ok(source.indexOf('image.addEventListener("error"') < source.indexOf("image.src = `../../${logo.replace"));
  assert.match(siteSource, /image\.closest\("\[data-featured-brands\]"\)/);
  assert.match(source, /cloneNode\(true\)/);
  assert.match(source, /aria-hidden/);
});

test("featured brands keep their mobile carousel while hiding redundant DripZone identity", () => {
  const css = fs.readFileSync(path.join(root, "frontend", "pages", "home", "css", "style.css"), "utf8");
  const responsiveCss = fs.readFileSync(path.join(root, "frontend", "pages", "home", "css", "responsive.css"), "utf8");
  const html = fs.readFileSync(path.join(root, "frontend", "pages", "home", "index.html"), "utf8");

  assert.match(css, /\.featured-brands\s*{[^}]*padding: 48px 0 80px/s);
  assert.match(css, /\.featured-brand__logo\s*{[^}]*object-fit: contain/s);
  assert.match(html, /<section class="featured-brands"[^>]*data-featured-brands>[\s\S]*data-featured-brands-track/);
  assert.match(responsiveCss, /@media \(max-width: 900px\)[\s\S]*\.featured-brands\s*{\s*display: block;\s*margin: 0;\s*border-block: 1px solid #eeeeee;\s*background: #ffffff;\s*padding: 22px 0 12px;\s*}/s);
  assert.match(responsiveCss, /@media \(max-width: 900px\)[\s\S]*\.featured-brands__viewport\s*{\s*min-height: 58px;\s*}/s);
  assert.match(responsiveCss, /@media \(max-width: 900px\)[\s\S]*\.featured-brands \.brand,\s*\.featured-brands \[data-brand="dripzone"\],\s*\.featured-brands__signature\s*{\s*display: none;\s*}/s);
  assert.doesNotMatch(responsiveCss, /\.featured-brands__track,\s*\.featured-brands__status\s*{\s*display: none;\s*}/);
  assert.doesNotMatch(responsiveCss, /\.featured-brands__viewport\s*{[^}]*pointer-events: none/s);
  assert.doesNotMatch(responsiveCss, /\.featured-brands\s*{\s*padding: 44px 0 62px/);
  assert.doesNotMatch(responsiveCss, /\.featured-brands__track,\s*\.featured-brands__group\s*{\s*gap: 34px/);
});

test("mobile header brand positioning is scoped away from the footer", () => {
  const styleCss = fs.readFileSync(path.join(root, "frontend", "pages", "home", "css", "style.css"), "utf8");
  const responsiveCss = fs.readFileSync(path.join(root, "frontend", "pages", "home", "css", "responsive.css"), "utf8");
  const sharedMobileCss = fs.readFileSync(path.join(root, "frontend", "assets", "css", "mobile-header.css"), "utf8");

  for (const source of [styleCss, responsiveCss, sharedMobileCss]) {
    assert.doesNotMatch(source, /(^|\n)\s*\.brand\s*{[^}]*position: absolute;/);
    assert.doesNotMatch(source, /(^|\n)\s*\.brand\s*{[^}]*grid-area: brand;/);
    assert.doesNotMatch(source, /(^|\n)\s*\.brand__mark,\s*\n\s*\.site-header\.is-compact \.brand__mark/);
  }

  assert.match(sharedMobileCss, /\.site-header \.brand\s*{[\s\S]*?position: absolute;[\s\S]*?transform: translate\(-50%, -50%\);/);
  assert.match(styleCss, /\.site-header \.brand\s*{[\s\S]*?grid-area: brand;/);
  assert.match(responsiveCss, /\.site-header \.brand\s*{[\s\S]*?position: absolute;/);
});

test("mobile home vertical flow shows the brand carousel below the hero", () => {
  const responsiveCss = fs.readFileSync(path.join(root, "frontend", "pages", "home", "css", "responsive.css"), "utf8");

  assert.match(responsiveCss, /@media \(max-width: 900px\)[\s\S]*\.featured-brands\s*{\s*display: block;[\s\S]*padding: 22px 0 12px;\s*}/s);
  assert.match(responsiveCss, /\.featured-brands__track,\s*\.featured-brands__group\s*{\s*gap: 18px/s);
  assert.match(responsiveCss, /\.featured-brand\s*{\s*min-width: 100px;\s*min-height: 72px/s);
  assert.match(responsiveCss, /\.featured-brand__logo\s*{\s*max-width: 108px;\s*max-height: 58px/s);
  assert.match(responsiveCss, /\.home-categories\s*{\s*padding: 0 0 34px;\s*}/);
  assert.match(responsiveCss, /\.home-categories__viewport\s*{[^}]*padding: 2px 4px 10px/s);
});
