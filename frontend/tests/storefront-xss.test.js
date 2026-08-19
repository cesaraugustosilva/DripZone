const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..", "..");

function loadSecurity() {
  const code = fs.readFileSync(path.join(root, "frontend", "assets", "js", "storefront-security.js"), "utf8");
  const location = new URL("https://dripzone.com.br/pages/catalogo/");
  const window = {
    location,
    DripZoneUtils: {
      assetPath: (asset) => `/safe/${String(asset).replace(/^(\.\.\/)+/, "")}`,
      publicUrl: (asset) => `https://dripzone.com.br/${String(asset).replace(/^(\.\.\/)+/, "")}`
    }
  };
  const context = { URL, window };
  vm.runInNewContext(code, context);
  return window.DripZoneSecurity;
}

test("storefront text helper preserves product text as data", () => {
  const security = loadSecurity();
  const payload = "<img src=x onerror=alert(1)><script>alert(2)</script>";

  assert.equal(security.text(payload), payload);
});

test("storefront URL helper blocks scriptable and local protocols", () => {
  const security = loadSecurity();

  assert.equal(security.imageUrl("javascript:alert(1)", ""), "");
  assert.equal(security.imageUrl("java\nscript:alert(1)", ""), "");
  assert.equal(security.imageUrl("data:text/html,<script>alert(1)</script>", ""), "");
  assert.equal(security.imageUrl("vbscript:msgbox(1)", ""), "");
  assert.equal(security.imageUrl("file:///C:/secret.png", ""), "");
});

test("storefront URL helper allows ordinary local and http image URLs", () => {
  const security = loadSecurity();

  assert.equal(security.imageUrl("../../uploads/products/adidas/a.jpg", ""), "../../uploads/products/adidas/a.jpg");
  assert.equal(security.imageUrl("/uploads/products/adidas/a.jpg", ""), "/uploads/products/adidas/a.jpg");
  assert.equal(security.imageUrl("https://cdn.example.test/a.jpg", ""), "https://cdn.example.test/a.jpg");
});

test("product links only keep safe product ids", () => {
  const security = loadSecurity();

  assert.equal(security.productHref("adidas-jacket-123", "../produto/"), "/pages/produto/?id=adidas-jacket-123");
  assert.equal(security.productHref("javascript:alert(1)", "../produto/"), "/pages/produto/");
  assert.equal(security.productHref("<img src=x onerror=alert(1)>", "../produto/"), "/pages/produto/");
});

test("cart item from localStorage is rebuilt from canonical product data", () => {
  const security = loadSecurity();
  const products = [{
    id: "adidas-hoodie",
    name: "Adidas Hoodie",
    price: 299,
    purchasable: true,
    image: "/uploads/products/adidas/hoodie.jpg",
    sizes: ["M", "G"]
  }];
  const storedItem = {
    id: "adidas-hoodie",
    name: "<img src=x onerror=alert(1)>",
    price: "<script>alert(1)</script>",
    image: "javascript:alert(1)",
    size: "<svg onload=alert(1)>",
    quantity: 99
  };

  assert.equal(JSON.stringify(security.safeCartItem(storedItem, products)), JSON.stringify({
    key: "adidas-hoodie-M",
    id: "adidas-hoodie",
    name: "Adidas Hoodie",
    price: 299,
    image: "/uploads/products/adidas/hoodie.jpg",
    size: "M",
    quantity: 10
  }));
});

test("cart item from localStorage is rejected when product is not purchasable", () => {
  const security = loadSecurity();
  const products = [{
    id: "adidas-showcase",
    name: "Adidas Showcase",
    price: null,
    purchasable: false,
    image: "/uploads/products/adidas/showcase.jpg",
    sizes: ["M"]
  }];

  assert.equal(security.safeCartItem({ id: "adidas-showcase", size: "M", quantity: 1 }, products), null);
  assert.equal(security.isPurchasable(products[0]), false);
});

test("cart item with real price remains purchasable", () => {
  const security = loadSecurity();
  const product = {
    id: "adidas-paid",
    name: "Adidas Paid",
    price: 199.9,
    purchasable: true,
    image: "/uploads/products/adidas/paid.jpg",
    sizes: ["M"]
  };

  assert.equal(security.isPurchasable(product), true);
  assert.equal(security.safeCartItem({ id: "adidas-paid", size: "M", quantity: 2 }, [product]).price, 199.9);
});

test("public storefront product rendering files do not use HTML sinks", () => {
  const files = [
    "frontend/pages/catalogo/js/catalog.js",
    "frontend/pages/produto/js/product.js",
    "frontend/pages/produto/js/cart.js"
  ];
  const forbidden = /\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\s*\(|new Function)\b/;

  for (const file of files) {
    const source = fs.readFileSync(path.join(root, file), "utf8");
    assert.doesNotMatch(source, forbidden, file);
  }
});
