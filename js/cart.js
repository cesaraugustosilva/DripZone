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
  return cartState.items.reduce((total, item) => total + item.price * item.quantity, 0);
}

function getCartShipping() {
  const subtotal = getCartSubtotal();
  if (subtotal === 0 || subtotal >= FREE_SHIPPING_FROM) return 0;
  return SHIPPING_PRICE;
}

function renderCart() {
  const itemsContainer = document.querySelector("[data-cart-items]");
  const empty = document.querySelector("[data-cart-empty]");
  const subtotal = document.querySelector("[data-cart-subtotal]");
  const shipping = document.querySelector("[data-cart-shipping]");
  const total = document.querySelector("[data-cart-total]");
  const count = document.querySelector("[data-cart-count]");

  if (count) count.textContent = String(getCartTotalQuantity());
  if (subtotal) subtotal.textContent = cartFormatPrice(getCartSubtotal());
  if (shipping) shipping.textContent = cartFormatPrice(getCartShipping());
  if (total) total.textContent = cartFormatPrice(getCartSubtotal() + getCartShipping());
  if (!itemsContainer || !empty) return;

  empty.hidden = cartState.items.length > 0;
  itemsContainer.innerHTML = cartState.items
    .map(
      (item) => `
        <article class="cart-item">
          <img src="${item.image}" alt="${item.name}" />
          <div class="cart-item__body">
            <div>
              <h3>${item.name}</h3>
              <p>${item.size} / ${cartFormatPrice(item.price)}</p>
            </div>
            <div class="cart-item__actions">
              <button type="button" data-cart-decrease="${item.key}" aria-label="Diminuir ${item.name}">-</button>
              <span>${item.quantity}</span>
              <button type="button" data-cart-increase="${item.key}" aria-label="Aumentar ${item.name}">+</button>
              <button type="button" data-cart-remove="${item.key}" aria-label="Remover ${item.name}">Remover</button>
            </div>
          </div>
        </article>
      `
    )
    .join("");
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

  const key = `${product.id}-${size}`;
  const existing = cartState.items.find((item) => item.key === key);
  const safeQuantity = Math.min(Math.max(Number(quantity) || 1, 1), 10);

  if (existing) {
    existing.quantity = Math.min(existing.quantity + safeQuantity, 10);
  } else {
    cartState.items.push({
      key,
      id: product.id,
      name: product.name,
      price: product.price,
      image: product.image,
      size,
      quantity: safeQuantity
    });
  }

  saveCart();
  renderCart();
  openCart();

  document.querySelector("[data-cart-drawer]")?.classList.add("cart-bump");
  window.setTimeout(() => document.querySelector("[data-cart-drawer]")?.classList.remove("cart-bump"), 420);
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
  const itemElement = document.querySelector(`[data-cart-increase="${key}"]`)?.closest(".cart-item");
  itemElement?.classList.add("is-updated");
  window.setTimeout(() => itemElement?.classList.remove("is-updated"), 280);
}

function removeCartItem(key) {
  const itemElement = document.querySelector(`[data-cart-remove="${key}"]`)?.closest(".cart-item");
  itemElement?.classList.add("is-removing");
  window.setTimeout(() => {
    cartState.items = cartState.items.filter((item) => item.key !== key);
    saveCart();
    renderCart();
  }, itemElement ? 220 : 0);
}

function initCart() {
  loadCart();
  renderCart();

  document.querySelectorAll("[data-cart-open]").forEach((button) => {
    button.addEventListener("click", () => {
      lastCartTrigger = button;
      openCart();
    });
  });

  document.querySelector("[data-cart-close]")?.addEventListener("click", closeCart);
  document.querySelector("[data-cart-continue]")?.addEventListener("click", closeCart);
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
