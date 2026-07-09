const catalogProducts = window.DripZoneProducts || [];

const state = {
  category: "Todos",
  search: "",
  maxPrice: 400,
  sort: "recent"
};

const formatPrice = (price) =>
  price.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  });

function getFilteredProducts() {
  const normalizedSearch = state.search.trim().toLowerCase();

  return catalogProducts
    .filter((product) => state.category === "Todos" || product.category === state.category)
    .filter((product) => product.price <= state.maxPrice)
    .filter((product) => product.name.toLowerCase().includes(normalizedSearch))
    .sort((a, b) => {
      if (state.sort === "price-asc") return a.price - b.price;
      if (state.sort === "price-desc") return b.price - a.price;
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });
}

function createProductCard(product) {
  const badges = (product.badges || [product.tag])
    .map((badge) => `<span class="product-badge">${badge}</span>`)
    .join("");

  return `
    <a class="product-card catalog-product" href="produto.html?id=${product.id}" aria-label="Ver produto ${product.name}">
      <div class="product-card__media">
        <img src="${product.image}" alt="${product.name}" loading="lazy" />
        <span class="badge-stack">${badges}</span>
      </div>
      <div class="product-card__body">
        <p class="product-card__category">${product.category}</p>
        <h3>${product.name}</h3>
        <div class="product-card__footer">
          <span class="price">${formatPrice(product.price)}</span>
          <span class="product-card__cta">Ver peça</span>
        </div>
      </div>
    </a>
  `;
}

function renderProducts() {
  const grid = document.querySelector("[data-products-grid]");
  const emptyState = document.querySelector("[data-empty-state]");
  const resultCount = document.querySelector("[data-result-count]");
  const products = getFilteredProducts();

  if (!grid || !emptyState || !resultCount) return;

  grid.innerHTML = products.map(createProductCard).join("");
  emptyState.hidden = products.length > 0;
  resultCount.textContent = `${products.length} ${products.length === 1 ? "produto" : "produtos"}`;
}

function updateCategoryButtons() {
  document.querySelectorAll("[data-category]").forEach((button) => {
    const isActive = button.dataset.category === state.category;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function initCatalog() {
  const search = document.querySelector("[data-search]");
  const price = document.querySelector("[data-price]");
  const priceOutput = document.querySelector("[data-price-output]");
  const sort = document.querySelector("[data-sort]");
  const clear = document.querySelector("[data-clear-filters]");

  document.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", () => {
      state.category = button.dataset.category || "Todos";
      updateCategoryButtons();
      renderProducts();
    });
  });

  search?.addEventListener("input", (event) => {
    state.search = event.target.value;
    renderProducts();
  });

  price?.addEventListener("input", (event) => {
    state.maxPrice = Number(event.target.value);
    if (priceOutput) priceOutput.textContent = `Até R$ ${state.maxPrice}`;
    renderProducts();
  });

  sort?.addEventListener("change", (event) => {
    state.sort = event.target.value;
    renderProducts();
  });

  clear?.addEventListener("click", () => {
    state.category = "Todos";
    state.search = "";
    state.maxPrice = 400;
    state.sort = "recent";

    if (search) search.value = "";
    if (price) price.value = "400";
    if (priceOutput) priceOutput.textContent = "Até R$ 400";
    if (sort) sort.value = "recent";

    updateCategoryButtons();
    renderProducts();
  });

  updateCategoryButtons();
  renderProducts();
}

document.addEventListener("DOMContentLoaded", initCatalog);
