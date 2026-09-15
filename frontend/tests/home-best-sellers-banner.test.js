const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

test("home banners are local and ordered between category carousel and spotlight", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const css = readFile("frontend", "pages", "home", "css", "style.css");
  const responsive = readFile("frontend", "pages", "home", "css", "responsive.css");
  const assetPath = path.join(root, "frontend", "assets", "home", "banners", "mais-vendidos-dripzone.jpg");
  const novidadesAssetPath = path.join(root, "frontend", "assets", "home", "banners", "novidades-dripzone.jfif");
  const discountAssetPath = path.join(root, "frontend", "assets", "home", "banners", "30-off-dripzone.jfif");

  assert.ok(fs.existsSync(assetPath), "best sellers banner asset should exist locally");
  assert.ok(fs.statSync(assetPath).size > 10000, "best sellers banner should be the real image asset");
  assert.ok(fs.existsSync(novidadesAssetPath), "novidades banner asset should exist locally");
  assert.ok(fs.statSync(novidadesAssetPath).size > 10000, "novidades banner should be the real image asset");
  assert.ok(fs.existsSync(discountAssetPath), "discount banner asset should exist locally");
  assert.ok(fs.statSync(discountAssetPath).size > 10000, "discount banner should be the real image asset");

  const categoryIndex = html.indexOf('<section class="home-categories"');
  const bannerIndex = html.indexOf('<section class="home-best-sellers-banner"');
  const novidadesIndex = html.indexOf('<section class="home-promo-banner home-promo-banner--novidades"');
  const discountIndex = html.indexOf('<section class="home-promo-banner home-promo-banner--discount"');
  const spotlightIndex = html.indexOf("data-streetwear-spotlight");

  assert.ok(categoryIndex >= 0, "category carousel section should exist");
  assert.ok(bannerIndex > categoryIndex, "best sellers banner should follow category carousel");
  assert.ok(novidadesIndex > bannerIndex, "novidades banner should follow best sellers banner");
  assert.ok(discountIndex > novidadesIndex, "discount banner should follow novidades banner");
  assert.ok(spotlightIndex > discountIndex, "spotlight should follow home banners");

  assert.match(html, /src="\.\.\/\.\.\/assets\/home\/banners\/mais-vendidos-dripzone\.jpg"/);
  assert.match(html, /src="\.\.\/\.\.\/assets\/home\/banners\/novidades-dripzone\.jfif"/);
  assert.match(html, /src="\.\.\/\.\.\/assets\/home\/banners\/30-off-dripzone\.jfif"/);
  assert.doesNotMatch(html, /mais-vendidos-dripzone\.jfif/);
  assert.match(html, /alt="Mais vendidos DripZone"/);
  assert.match(html, /alt="Novidades DripZone"/);
  assert.match(html, /alt="Até 30% OFF DripZone"/);
  assert.match(html, /loading="lazy"/);
  assert.match(html, /decoding="async"/);
  assert.doesNotMatch(html.slice(bannerIndex, spotlightIndex), /<a\b/);

  assert.match(css, /\.home-best-sellers-banner\s*{[^}]*padding: 32px 0 12px/s);
  assert.match(css, /\.home-promo-banner\s*{[^}]*padding: 8px 0 12px/s);
  assert.match(css, /\.home-promo-banner--discount\s*{[^}]*padding-bottom: 36px/s);
  assert.match(css, /\.home-best-sellers-banner img,\s*\.home-promo-banner img\s*{[^}]*display: block;[^}]*width: 100%;[^}]*height: auto/s);
  assert.doesNotMatch(css, /\.home-(?:best-sellers-banner|promo-banner) img\s*{[^}]*object-fit:\s*cover/s);
  assert.match(responsive, /\.home-best-sellers-banner\s*{[^}]*padding: 24px 0 8px/s);
  assert.match(responsive, /\.home-promo-banner\s*{[^}]*padding: 8px 0/s);
});

test("home does not render removed legacy sections", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const legacyContent = [
    "Catálogo",
    "Categorias para montar sua presença",
    "Essenciais de impacto",
    "Drop limitado",
    "Peças exclusivas por tempo limitado",
    "Segundo drop",
    "Base limpa. Presença alta.",
    "Sobre a DripZone",
    "Identidade para quem vive a rua",
    "URBAN FILES",
    "CHROME CLUB",
    "NOISE LAB",
    "DROP INDEX",
    "ZONE RADIO",
    "Avaliações",
    "Quem veste sente o peso",
    "Rafa M.",
    "Bianca L.",
    "Caio V.",
    "Lista VIP",
    "Receba os próximos drops primeiro",
    "Drop aberto",
    "Vista a peça antes que ela vire referência",
  ];

  for (const text of legacyContent) {
    assert.doesNotMatch(html, new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.doesNotMatch(html, /data-newsletter-form|data-slider|category-grid|testimonial-grid|final-cta/);
  assert.match(html, /home-categories/);
  assert.match(html, /home-best-sellers-banner/);
  assert.match(html, /streetwear-spotlight/);
  assert.match(html, /site-footer/);
});
