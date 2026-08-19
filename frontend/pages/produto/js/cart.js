const CART_KEY = "dripzone-cart";

const cartState = {
  items: []
};

let lastCartTrigger = null;
const SHIPPING_PRICE = 19.9;
const FREE_SHIPPING_FROM = 299;

const cartFormatPrice = window.DripZoneUtils?.formatPrice || ((price) =>
  Number(price || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  }));
const safeText = (value, fallback = "") => window.DripZoneSecurity?.text(value, fallback) ?? String(value ?? fallback);
const isPurchasable = (product) => window.DripZoneSecurity?.isPurchasable(product) || false;

function getProducts() {
  return window.DripZoneProducts || [];
}

function loadCart() {
  try {
    cartState.items = JSON.parse(localStorage.getItem(CART_KEY)) || [];
  } catch {
    cartState.items = [];
  }
}

function sanitizeCartItems() {
  const products = getProducts();
  const validItems = cartState.items
    .map((item) => window.DripZoneSecurity?.safeCartItem(item, products))
    .filter(Boolean);
  if (JSON.stringify(validItems) !== JSON.stringify(cartState.items)) {
    cartState.items = validItems;
    saveCart();
  }
}

function saveCart() {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(cartState.items));
  } catch {
    cartState.items = [...cartState.items];
  }
}

function getCartTotalQuantity() {
  return cartState.items.reduce((total, item) => total + item.quantity, 0);
}

function getCartSubtotal() {
  return cartState.items.reduce((total, item) => {
    if (!Number.isFinite(item.price) || !Number.isFinite(item.quantity)) return total;
    return total + item.price * item.quantity;
  }, 0);
}

function getCartShipping() {
  const subtotal = getCartSubtotal();
  if (subtotal === 0 || subtotal >= FREE_SHIPPING_FROM) return 0;
  return SHIPPING_PRICE;
}

function createCartItem(item) {
  const article = document.createElement("article");
  article.className = "cart-item";

  const image = document.createElement("img");
  window.DripZoneSecurity?.setSafeImage(image, item.image, safeText(item.name, "Produto"));

  const body = document.createElement("div");
  body.className = "cart-item__body";
  const info = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = safeText(item.name, "Produto");
  const meta = document.createElement("p");
  meta.textContent = `${safeText(item.size)} / ${cartFormatPrice(item.price)}`;
  info.append(title, meta);

  const actions = document.createElement("div");
  actions.className = "cart-item__actions";
  const decrease = document.createElement("button");
  decrease.type = "button";
  decrease.dataset.cartDecrease = item.key;
  decrease.setAttribute("aria-label", `Diminuir ${safeText(item.name, "produto")}`);
  decrease.textContent = "-";
  const quantity = document.createElement("span");
  quantity.textContent = String(item.quantity);
  const increase = document.createElement("button");
  increase.type = "button";
  increase.dataset.cartIncrease = item.key;
  increase.setAttribute("aria-label", `Aumentar ${safeText(item.name, "produto")}`);
  increase.textContent = "+";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.dataset.cartRemove = item.key;
  remove.setAttribute("aria-label", `Remover ${safeText(item.name, "produto")}`);
  remove.textContent = "Remover";
  actions.append(decrease, quantity, increase, remove);
  body.append(info, actions);
  article.append(image, body);
  return article;
}

function renderCart() {
  const itemsContainer = document.querySelector("[data-cart-items]");
  const empty = document.querySelector("[data-cart-empty]");
  const subtotal = document.querySelector("[data-cart-subtotal]");
  const shipping = document.querySelector("[data-cart-shipping]");
  const total = document.querySelector("[data-cart-total]");
  const count = document.querySelector("[data-cart-count]");
  const checkout = document.querySelector("[data-cart-checkout]");
  const checkoutMessage = document.querySelector("[data-cart-checkout-message]");
  const hasItems = cartState.items.length > 0;

  if (count) count.textContent = String(getCartTotalQuantity());
  if (subtotal) subtotal.textContent = cartFormatPrice(getCartSubtotal());
  if (shipping) shipping.textContent = cartFormatPrice(getCartShipping());
  if (total) total.textContent = cartFormatPrice(getCartSubtotal() + getCartShipping());
  if (checkout) checkout.disabled = !hasItems;
  if (!hasItems && checkoutMessage) {
    checkoutMessage.hidden = true;
    checkoutMessage.textContent = "";
  }
  if (!itemsContainer || !empty) return;

  empty.hidden = hasItems;
  itemsContainer.replaceChildren(...cartState.items.map(createCartItem));
}

function openCart() {
  const drawer = document.querySelector("[data-cart-drawer]");
  const close = document.querySelector("[data-cart-close]");
  if (!drawer) return;

  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
  drawer.inert = false;
  document.body.classList.add("menu-open");
  close?.focus();
}

function closeCart() {
  const drawer = document.querySelector("[data-cart-drawer]");
  if (!drawer) return;

  drawer.classList.remove("is-open");
  drawer.setAttribute("aria-hidden", "true");
  drawer.inert = true;
  document.body.classList.remove("menu-open");
  lastCartTrigger?.focus();
}

function addToCart({ productId, size, quantity }) {
  const product = getProducts().find((item) => item.id === productId);
  if (!product) return;
  if (!isPurchasable(product)) {
    sanitizeCartItems();
    renderCart();
    return;
  }

  const safeProductId = window.DripZoneSecurity?.productId(product.id) || "";
  if (!safeProductId) return;
  const safeSize = safeText(size || "").slice(0, 80);
  const key = `${safeProductId}-${safeSize}`;
  const existing = cartState.items.find((item) => item.key === key);
  const safeQuantity = window.DripZoneSecurity?.normalizeQuantity(quantity) || 1;

  if (existing) {
    existing.quantity = Math.min(existing.quantity + safeQuantity, 10);
  } else {
    cartState.items.push({
      key,
      id: safeProductId,
      name: safeText(product.name, "Produto"),
      price: product.price,
      image: window.DripZoneSecurity?.imageUrl(product.image) || "../../assets/images/logo/dripzone-logo.png",
      size: safeSize,
      quantity: safeQuantity
    });
  }

  saveCart();
  renderCart();
  openCart();

  document.querySelector("[data-cart-drawer]")?.classList.add("cart-bump");
  window.setTimeout(() => document.querySelector("[data-cart-drawer]")?.classList.remove("cart-bump"), 420);
}

function closestCartItemByButton(type, key) {
  const selector = `[data-cart-${type}]`;
  return [...document.querySelectorAll(selector)]
    .find((button) => button.dataset[`cart${type[0].toUpperCase()}${type.slice(1)}`] === key)
    ?.closest(".cart-item");
}

function changeCartQuantity(key, delta) {
  const item = cartState.items.find((cartItem) => cartItem.key === key);
  if (!item) return;

  item.quantity += delta;
  if (item.quantity <= 0) {
    cartState.items = cartState.items.filter((cartItem) => cartItem.key !== key);
  }

  saveCart();
  renderCart();
  const itemElement = closestCartItemByButton("increase", key);
  itemElement?.classList.add("is-updated");
  window.setTimeout(() => itemElement?.classList.remove("is-updated"), 280);
}

function removeCartItem(key) {
  const itemElement = closestCartItemByButton("remove", key);
  itemElement?.classList.add("is-removing");
  window.setTimeout(() => {
    cartState.items = cartState.items.filter((item) => item.key !== key);
    saveCart();
    renderCart();
  }, itemElement ? 220 : 0);
}

function handleCheckout() {
  if (cartState.items.length === 0) return;

  const message = document.querySelector("[data-cart-checkout-message]");
  if (!message) return;

  message.textContent = "Finalização de pedido em breve. Seu carrinho foi mantido.";
  message.hidden = false;
}

async function initCart() {
  loadCart();
  if (window.DripZoneProductsReady) {
    try {
      await window.DripZoneProductsReady;
    } catch {
      window.DripZoneProducts = [];
    }
  }
  sanitizeCartItems();
  renderCart();

  document.querySelectorAll("[data-cart-open]").forEach((button) => {
    button.addEventListener("click", () => {
      lastCartTrigger = button;
      openCart();
    });
  });

  document.querySelector("[data-cart-close]")?.addEventListener("click", closeCart);
  document.querySelector("[data-cart-continue]")?.addEventListener("click", closeCart);
  document.querySelector("[data-cart-checkout]")?.addEventListener("click", handleCheckout);
  document.querySelector("[data-cart-drawer]")?.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.matches("[data-cart-drawer]")) closeCart();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeCart();
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;

    const increase = event.target.closest("[data-cart-increase]");
    const decrease = event.target.closest("[data-cart-decrease]");
    const remove = event.target.closest("[data-cart-remove]");

    if (increase) changeCartQuantity(increase.dataset.cartIncrease, 1);
    if (decrease) changeCartQuantity(decrease.dataset.cartDecrease, -1);
    if (remove) removeCartItem(remove.dataset.cartRemove);
  });
}

window.DripZoneCart = {
  addToCart,
  initCart,
  openCart,
  renderCart
};

document.addEventListener("DOMContentLoaded", initCart);
