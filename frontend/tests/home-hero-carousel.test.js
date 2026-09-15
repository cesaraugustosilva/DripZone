const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

test("home hero carousel uses the requested local slides in order", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const expectedSlides = [
    "assets/home/hero/hero-drip10-new.png",
    "assets/home/hero/hero-channel-new.png",
    "assets/home/hero/hero-tech-fleece-new.png",
    "assets/home/hero/hero-tn-air-new.png"
  ];

  assert.match(html, /class="hero-carousel" id="inicio"/);
  assert.match(html, /data-hero-carousel-track/);
  assert.match(html, /data-hero-carousel-prev/);
  assert.match(html, /data-hero-carousel-next/);
  assert.match(html, /data-hero-carousel-indicators/);

  let cursor = -1;
  for (const slide of expectedSlides) {
    const nextCursor = html.indexOf(slide);
    assert.ok(nextCursor > cursor, `${slide} should appear in the requested order`);
    cursor = nextCursor;

    const assetPath = path.join(root, "frontend", ...slide.split("/"));
    assert.ok(fs.existsSync(assetPath), `${slide} should exist locally`);
    assert.ok(fs.statSync(assetPath).size > 10000, `${slide} should be a real image asset`);
  }

  assert.match(html, /hero-drip10-new\.png"[^>]*loading="eager"[^>]*fetchpriority="high"/);
  assert.match(html, /hero-channel-new\.png"[^>]*loading="lazy"/);
  assert.match(html, /hero-tech-fleece-new\.png"[^>]*loading="lazy"/);
  assert.match(html, /hero-tn-air-new\.png"[^>]*loading="lazy"/);
});

test("home hero carousel behavior is dynamic and accessible", () => {
  const js = readFile("frontend", "pages", "home", "js", "main.js");
  const css = readFile("frontend", "pages", "home", "css", "style.css");
  const responsiveCss = readFile("frontend", "pages", "home", "css", "responsive.css");
  const animationsCss = readFile("frontend", "pages", "home", "css", "animations.css");

  assert.match(js, /const slides = Array\.from/);
  assert.match(js, /slides\.map/);
  assert.match(js, /cloneNode/);
  assert.match(js, /physicalIndex/);
  assert.match(js, /getSlideWidth/);
  assert.match(js, /currentIndex/);
  assert.match(js, /transitionend/);
  assert.match(js, /track\.style\.transition = "none"/);
  assert.match(js, /void track\.offsetWidth/);
  assert.match(js, /aria-hidden", "true"/);
  assert.match(js, /tabIndex = -1/);
  assert.match(js, /autoplayDelay = 6000/);
  assert.match(js, /prefers-reduced-motion: reduce/);
  assert.match(js, /ArrowRight/);
  assert.match(js, /ArrowLeft/);
  assert.match(js, /touchstart/);
  assert.match(js, /touchend/);
  assert.doesNotMatch(js, /slide === 4/);

  assert.match(css, /\.hero-carousel__track/);
  assert.doesNotMatch(js, /is-jump/);
  assert.doesNotMatch(css, /\.hero-carousel__track\.is-jump/);
  assert.match(css, /translate3d/);
  assert.match(css, /aspect-ratio: 16 \/ 9/);
  assert.match(css, /\.hero-carousel:hover \.hero-carousel__arrow/);
  assert.match(css, /\.hero-carousel:focus-within \.hero-carousel__arrow/);
  assert.match(css, /pointer-events: none/);
  assert.match(responsiveCss, /\.hero-carousel__viewport/);
  assert.match(responsiveCss, /height: clamp\(215px, 62vw, 465px\)/);
  assert.match(responsiveCss, /\.hero-carousel\s*{[^}]*width: calc\(100% - 16px\);[^}]*margin: 8px auto 0/s);
  assert.match(responsiveCss, /aspect-ratio: auto/);
  assert.match(responsiveCss, /pointer-events: auto/);
  assert.match(animationsCss, /\.hero-carousel__track/);
});
