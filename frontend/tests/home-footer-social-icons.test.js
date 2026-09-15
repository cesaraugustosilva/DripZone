const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function readFile(...parts) {
  return fs.readFileSync(path.join(root, ...parts), "utf8");
}

test("home footer replaces legacy social text with accessible local icons", () => {
  const html = readFile("frontend", "pages", "home", "index.html");
  const css = readFile("frontend", "pages", "home", "css", "style.css");
  const footer = html.slice(html.indexOf('<footer class="site-footer"'));
  const social = footer.slice(footer.indexOf('<div class="social">'), footer.indexOf('<div class="footer__links">'));
  const icons = [
    {
      name: "Instagram",
      href: "https://www.instagram.com/_dripzone_0/",
      label: "Instagram da DripZone",
      src: "../../assets/social/instagram.png",
      asset: path.join(root, "frontend", "assets", "social", "instagram.png"),
    },
    {
      name: "TikTok",
      href: "https://vt.tiktok.com/ZSXS331c1/",
      label: "TikTok da DripZone",
      src: "../../assets/social/tiktok.png",
      asset: path.join(root, "frontend", "assets", "social", "tiktok.png"),
    },
    {
      name: "WhatsApp",
      href: "https://chat.whatsapp.com/BlTu7ZS6zSzGrANMhLBmPg",
      label: "WhatsApp da DripZone",
      src: "../../assets/social/whatsapp.png",
      asset: path.join(root, "frontend", "assets", "social", "whatsapp.png"),
    },
  ];

  assert.ok(social.length > 0, "footer social block should exist");
  assert.doesNotMatch(social, />\s*IG\s*</);
  assert.doesNotMatch(social, />\s*TK\s*</);
  assert.doesNotMatch(social, />\s*WA\s*</);

  for (const icon of icons) {
    assert.match(social, new RegExp(`href="${icon.href.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`));
    assert.match(social, new RegExp(`aria-label="${icon.label}"`));
    assert.match(social, new RegExp(`src="${icon.src.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`));
    assert.match(social, new RegExp(`alt="${icon.name}"`));
    assert.ok(fs.existsSync(icon.asset), `${icon.name} icon asset should exist locally`);
    assert.ok(fs.statSync(icon.asset).size > 1000, `${icon.name} icon should be a real PNG asset`);
  }

  assert.match(css, /\.social\s*{[^}]*align-items: center;[^}]*gap: 18px/s);
  assert.match(css, /\.social a,\s*\.social__item\s*{[^}]*width: 24px;[^}]*height: 24px/s);
  assert.match(css, /\.social__icon\s*{[^}]*object-fit: contain/s);
  assert.doesNotMatch(css, /\.social a,\s*\.social__item\s*{[^}]*background:/s);
});
