const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

function getCategorySection(source) {
  const start = source.indexOf('<section class="home-categories"');
  const end = source.indexOf('<section class="streetwear-spotlight"', start);
  assert.ok(start >= 0, "home categories section should exist");
  assert.ok(end > start, "home categories section should end before spotlight");
  return source.slice(start, end);
}

function getCategoryFunction(source) {
  const start = source.indexOf("const initCategoryCarousel = () => {");
  const end = source.indexOf("const setSearchExpanded", start);
  assert.ok(start >= 0, "category gallery initializer should exist");
  assert.ok(end > start, "category gallery initializer should be scoped");
  return source.slice(start, end);
}

test("home reference category carousel preserves the 11 category links in order", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const section = getCategorySection(html);
  const items = Array.from(
    section.matchAll(/<a class="home-category-card[^>]*href="([^"]+)"[^>]*aria-label="Ver ([^"]+)">\s*<img src="([^"]+)" alt="([^"]+)"/g)
  ).map((match) => ({
    href: match[1],
    label: match[2],
    image: match[3],
    alt: match[4]
  }));
  const expected = ["Sneakers", "Bonés", "Shorts", "Calças", "Camisetas", "Bag", "Relógios", "Óculos", "Conjuntos", "Moletons", "Jaquetas"];

  assert.equal(items.length, 11);
  assert.deepEqual(items.map((item) => item.label), expected);
  assert.deepEqual(items.map((item) => item.alt), expected);
  assert.deepEqual(items.map((item) => item.href), [
    "../catalogo/?categoria=sneakers",
    "../catalogo/?categoria=acessorios",
    "../catalogo/?categoria=shorts",
    "../catalogo/?categoria=calcas",
    "../catalogo/?categoria=camisetas",
    "../catalogo/?categoria=acessorios",
    "../catalogo/?categoria=acessorios",
    "../catalogo/?categoria=acessorios",
    "../catalogo/?categoria=conjuntos",
    "../catalogo/?categoria=moletons",
    "../catalogo/?categoria=jaquetas"
  ]);
  items.forEach((item) => {
    assert.match(item.image, /^..\/..\/assets\/home\/categories\/.+\.(png|webp|jpg|jpeg|svg)$/);
  });
});

test("home reference category carousel uses centered relative states", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const js = readFile("frontend", "pages", "home", "js", "main.js");
  const css = readFile("frontend", "pages", "home", "css", "style.css");
  const responsiveCss = readFile("frontend", "pages", "home", "css", "responsive.css");
  const section = getCategorySection(html);
  const categoryJs = getCategoryFunction(js);
  const categoryCssStart = css.indexOf(".home-categories {");
  const categoryCssEnd = css.indexOf(".streetwear-spotlight {", categoryCssStart);
  assert.ok(categoryCssStart >= 0 && categoryCssEnd > categoryCssStart);
  const categoryCss = css.slice(categoryCssStart, categoryCssEnd);
  const mobileCategoryStart = responsiveCss.indexOf("@media (max-width: 768px)");
  const mobileCategoryEnd = responsiveCss.indexOf("@media (max-width: 640px)", mobileCategoryStart);
  const narrowCategoryStart = responsiveCss.indexOf("  .home-categories__viewport {", mobileCategoryEnd);
  const narrowCategoryEnd = responsiveCss.indexOf("  .streetwear-spotlight {", narrowCategoryStart);
  assert.ok(mobileCategoryStart >= 0 && mobileCategoryEnd > mobileCategoryStart);
  assert.ok(narrowCategoryStart >= 0 && narrowCategoryEnd > narrowCategoryStart);
  const categoryResponsiveCss = [
    responsiveCss.slice(mobileCategoryStart, mobileCategoryEnd),
    responsiveCss.slice(narrowCategoryStart, narrowCategoryEnd)
  ].join("\n");

  assert.match(section, /data-category-carousel-prev/);
  assert.match(section, /data-category-carousel-next/);
  assert.doesNotMatch(section, /data-category-carousel-counter|category-gallery-counter|\b\d+\s*\/\s*11\b/);
  assert.match(section, /aria-label="Categoria anterior"/);
  assert.match(section, /aria-label="Próxima categoria"/);
  assert.match(categoryCss, /\.category-gallery-nav/);
  assert.match(categoryCss, /\.category-gallery-prev/);
  assert.match(categoryCss, /\.category-gallery-next/);
  assert.doesNotMatch(categoryCss, /\.category-gallery-counter/);
  assert.doesNotMatch(categoryResponsiveCss, /\.category-gallery-counter/);
  assert.doesNotMatch(categoryJs, /cloneNode|modulo|dragStart|translateZ|categoryOffset|getDepthForOffset|requestAnimationFrame|setTimeout|setInterval/);
  assert.doesNotMatch(categoryCss, /perspective|preserve-3d|rotateY|category-depth/);
  assert.equal((section.match(/home-category-card/g) || []).length, 11);
  assert.match(categoryJs, /let activeIndex = 0/);
  assert.match(categoryJs, /const wrapIndex = \(index\) => \(index \+ cards\.length\) % cards\.length/);
  assert.match(categoryJs, /const getCircularOffset = \(index\) =>/);
  assert.match(categoryJs, /const setActive = \(index\) =>/);
  assert.match(categoryJs, /activeIndex = wrapIndex\(index\)/);
  assert.match(categoryJs, /card\.classList\.remove\(\.\.\.positionClasses\)/);
  assert.match(categoryJs, /is-prev/);
  assert.match(categoryJs, /is-next/);
  assert.match(categoryJs, /is-prev-2/);
  assert.match(categoryJs, /is-next-2/);
  assert.match(categoryJs, /is-prev-3/);
  assert.match(categoryJs, /is-next-3/);
  assert.match(categoryJs, /is-distant/);
  assert.match(categoryJs, /const getPosition = \(offset\) =>/);
  assert.match(categoryJs, /card\.style\.setProperty\("--category-x", position\.x\)/);
  assert.match(categoryJs, /card\.style\.setProperty\("--category-scale", position\.scale\)/);
  assert.match(categoryJs, /card\.style\.setProperty\("--category-opacity", position\.opacity\)/);
  assert.match(categoryJs, /card\.style\.setProperty\("--category-z", position\.z\)/);
  assert.match(categoryJs, /\[0, 300, 540, 740\]/);
  assert.doesNotMatch(categoryJs, /--category-offset|activeIndex \*|offsetLeft|scrollWidth|track\.style\.transform|counter/);
  assert.match(categoryJs, /aria-selected/);
  assert.match(categoryJs, /previousButton\?\.addEventListener\("click", \(\) => moveBy\(-1\)\)/);
  assert.match(categoryJs, /nextButton\?\.addEventListener\("click", \(\) => moveBy\(1\)\)/);
  assert.match(categoryJs, /focus/);
  assert.match(categoryJs, /event\.preventDefault\(\);\s*setActive\(index\)/);
  assert.match(categoryJs, /touchstart/);
  assert.match(categoryJs, /touchend/);
  assert.match(categoryJs, /const swipeThreshold = 48/);
  assert.match(categoryJs, /moveBy\(deltaX < 0 \? 1 : -1\)/);
  assert.match(categoryJs, /ArrowLeft/);
  assert.match(categoryJs, /ArrowRight/);
  assert.match(categoryJs, /setActive\(0\)/);
  assert.doesNotMatch(categoryJs, /IntersectionObserver|rootMargin|threshold|disconnectMobileObserver|observe\(card\)|addEventListener\("scroll"/);
  assert.doesNotMatch(categoryJs, /ArrowUp|ArrowDown/);
  assert.doesNotMatch(categoryJs, /pointerenter|finePointerQuery|isCoarsePointer/);

  assert.match(categoryCss, /\.home-categories__track\s*{[^}]*position: relative;[^}]*height: clamp\(360px, 29vw, 430px\)/s);
  assert.match(categoryCss, /overflow: hidden/);
  assert.match(categoryCss, /position: absolute/);
  assert.match(categoryCss, /top: 50%/);
  assert.match(categoryCss, /left: 50%/);
  assert.match(categoryCss, /width: clamp\(300px, 23vw, 350px\)/);
  assert.match(categoryCss, /height: clamp\(300px, 25vw, 380px\)/);
  assert.match(categoryCss, /transform: translate\(-50%, -50%\) translate3d\(var\(--category-x\), var\(--category-y\), 0\) scale\(var\(--category-scale\)\)/);
  assert.match(categoryCss, /transform 700ms cubic-bezier\(0\.22, 1, 0\.36, 1\)/);
  assert.match(categoryCss, /opacity 500ms ease/);
  assert.match(categoryCss, /\.home-category-card\.reveal/);
  assert.match(categoryCss, /\.home-category-card\.is-active/);
  assert.match(categoryCss, /--category-scale: 1/);
  assert.match(categoryCss, /\.home-category-card\.is-prev,\s*\.home-category-card\.is-next/);
  assert.match(categoryCss, /--category-scale: 0\.9/);
  assert.match(categoryCss, /\.home-category-card\.is-prev-2,\s*\.home-category-card\.is-next-2/);
  assert.match(categoryCss, /--category-scale: 0\.84/);
  assert.match(categoryCss, /\.home-category-card\.is-prev-3,\s*\.home-category-card\.is-next-3/);
  assert.match(categoryCss, /--category-opacity: 0\.78/);
  assert.match(categoryCss, /\.home-category-card\.is-distant/);
  assert.match(categoryCss, /--category-opacity: 0/);
  assert.doesNotMatch(categoryCss, /\.home-category-card\.is-(?:prev|next|prev-2|next-2|prev-3|next-3)[^{]*{[^}]*display:\s*none/s);
  assert.doesNotMatch(categoryCss, /\.home-category-card\.is-(?:prev|next|prev-2|next-2|prev-3|next-3)[^{]*{[^}]*visibility:\s*hidden/s);
  assert.match(categoryCss, /linear-gradient\(to top/);
  assert.match(categoryCss, /\.home-category-card::after\s*{\s*content: none;\s*}/);
  assert.doesNotMatch(categoryCss, /content: attr\(data-category-label\)/);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-category-card(?:::after|\.is-active::after)/);
  assert.match(categoryCss, /object-fit: cover/);
  assert.match(categoryCss, /prefers-reduced-motion: reduce/);
  assert.match(categoryResponsiveCss, /max-width: 768px/);
  assert.match(categoryResponsiveCss, /\.home-categories__viewport\s*{\s*overflow: hidden/);
  assert.match(categoryResponsiveCss, /\.home-categories\s*{\s*padding: 0 0 34px;\s*}/);
  assert.match(categoryResponsiveCss, /\.home-categories__viewport\s*{[^}]*width: 100vw;[^}]*max-width: none;[^}]*margin-inline: calc\(50% - 50vw\);[^}]*padding: 2px 4px 10px/s);
  assert.match(categoryResponsiveCss, /\.home-categories__viewport\s*{[^}]*width: 100vw;[^}]*max-width: none;[^}]*margin-inline: calc\(50% - 50vw\);[^}]*padding-inline: 4px/s);
  assert.match(categoryResponsiveCss, /\.home-categories__track\s*{\s*height: clamp\(245px, 72vw, 310px\)/);
  assert.match(categoryResponsiveCss, /\.home-category-card\s*{\s*width: var\(--category-card-width, clamp\(165px, 46vw, 205px\)\);\s*height: auto;\s*aspect-ratio: 4 \/ 5/);
  assert.match(categoryResponsiveCss, /--category-x: -134px/);
  assert.match(categoryResponsiveCss, /--category-x: 134px/);
  assert.match(categoryResponsiveCss, /--category-scale: 0\.82/);
  assert.match(categoryResponsiveCss, /\.home-category-card\.is-active\s*{\s*box-shadow: 0 10px 22px rgba\(17, 17, 17, 0\.12\)/);
  assert.match(categoryResponsiveCss, /\.category-gallery-nav\s*{[^}]*width: 44px/s);
  assert.match(categoryJs, /viewport\.getBoundingClientRect\(\)\.width/);
  assert.match(categoryJs, /const mobileSizingWidth = Math\.max\(0, galleryWidth - \(window\.innerWidth <= 640 \? 28 : 40\)\)/);
  assert.match(categoryJs, /const mobileCardWidth = Math\.min\(205, Math\.max\(165, mobileSizingWidth \* 0\.5\)\)/);
  assert.match(categoryJs, /mobileCardWidth \* 0\.74/);
  assert.match(categoryJs, /\{ scale: 0\.82, y: 12, opacity: 0\.94, z: 4 \}/);
  assert.match(categoryJs, /\{ scale: 0\.7, y: 22, opacity: 0\.76, z: 3 \}/);
  assert.match(categoryJs, /card\.style\.setProperty\("--category-card-width", position\.width\)/);
  assert.match(responsiveCss, /@media \(min-width: 769px\) and \(max-width: 1023px\)/);
  assert.match(responsiveCss, /width: clamp\(320px, 44vw, 450px\)/);
  assert.doesNotMatch(categoryResponsiveCss, /flex-direction: column/);
  assert.doesNotMatch(categoryResponsiveCss, /flex-basis/);
  assert.doesNotMatch(categoryResponsiveCss, /width: 72vw|76vw|80vw|58vw/);
  assert.doesNotMatch(categoryResponsiveCss, /height: clamp\(300px, 96vw, 390px\)|height: clamp\(250px, 72vw, 320px\)/);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-category-card\s*{\s*height: clamp\(84px, 18vw, 112px\)/);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-category-card\.is-active\s*{\s*height: clamp\(300px, 95vw, 430px\)/);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-categories__viewport\s*{[^}]*overflow-x: auto/s);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-categories__viewport\s*{[^}]*scroll-snap-type/s);
  assert.doesNotMatch(categoryResponsiveCss, /margin-right:\s*[1-9]/);
  assert.doesNotMatch(categoryResponsiveCss, /padding-left:\s*0;\s*padding-right:\s*(?:[1-9]|\d{2,})/);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-category-card,\s*\.home-category-card\.is-active\s*{[^}]*86vw/s);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-category-card[^{}]*{[^}]*scroll-snap-align/s);
  assert.doesNotMatch(categoryResponsiveCss, /\.home-category-card[^{}]*{[^}]*width: 100vw/s);
});

test("mobile category carousel reduces side gaps while staying centered", () => {
  const widths = [320, 375, 390, 430, 600, 768];

  widths.forEach((windowWidth) => {
    const viewportWidth = windowWidth;
    const sizingWidth = viewportWidth - (windowWidth <= 640 ? 28 : 40);
    const activeWidth = Math.min(205, Math.max(165, sizingWidth * 0.5));
    const offset = activeWidth * 0.74;
    const neighborWidth = activeWidth * 0.82;
    const viewportLeft = 0;
    const viewportRight = windowWidth;
    const viewportCenter = viewportLeft + viewportWidth / 2;
    const activeCenter = viewportCenter;
    const prevCenter = activeCenter - offset;
    const nextCenter = activeCenter + offset;
    const activeLeft = activeCenter - activeWidth / 2;
    const activeRight = activeCenter + activeWidth / 2;
    const prevLeft = prevCenter - neighborWidth / 2;
    const prevRight = prevCenter + neighborWidth / 2;
    const nextLeft = nextCenter - neighborWidth / 2;
    const nextRight = nextCenter + neighborWidth / 2;
    const prevVisible = Math.max(0, Math.min(activeLeft, prevRight) - Math.max(viewportLeft, prevLeft));
    const nextVisible = Math.max(0, Math.min(viewportRight, nextRight) - Math.max(activeRight, nextLeft));
    const leftFreeSpace = viewportLeft;
    const rightFreeSpace = windowWidth - viewportRight;
    const scrollWidth = viewportRight - viewportLeft;

    assert.ok(Math.abs(activeCenter - viewportCenter) <= 2);
    assert.ok(Math.abs(Math.abs(activeCenter - prevCenter) - Math.abs(nextCenter - activeCenter)) <= 2);
    assert.ok(Math.abs(prevVisible - nextVisible) <= 5);
    assert.ok(Math.abs(leftFreeSpace - rightFreeSpace) <= 2);
    assert.ok(scrollWidth <= windowWidth);
    assert.ok(activeWidth >= 165 && activeWidth <= 205);
  });
});
