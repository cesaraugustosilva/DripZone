const state = {
  category: "Todos",
  categoryId: "",
  brandId: "",
  modelId: "",
  collectionId: "",
  search: "",
  maxPrice: 400,
  sort: "recent"
};

const invalidFilterValue = "__invalid-filter__";
const categoryNameToId = {
  Todos: "",
  Camisetas: "camisetas",
  "Calças": "calcas",
  Moletons: "moletons",
  Shorts: "shorts",
  "Acessórios": "acessorios"
};
const categoryIdToName = Object.fromEntries(
  Object.entries(categoryNameToId).map(([name, id]) => [id, name])
);

const formatPrice = window.DripZoneUtils?.formatPrice || ((price) =>
  Number(price || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  }));

function getFilteredProducts() {
  const normalizedSearch = state.search.trim().toLowerCase();

  return (window.DripZoneProducts || [])
    .filter((product) => !state.brandId || product.brandId === state.brandId)
    .filter((product) => !state.categoryId || product.categoryId === state.categoryId)
    .filter((product) => !state.modelId || product.modelId === state.modelId)
    .filter((product) => product.price <= state.maxPrice)
    .filter((product) => {
      if (!normalizedSearch) return true;
      const searchableText = [
        product.name,
        product.description,
        product.category,
        product.brand,
        product.tag,
        ...(product.badges || [])
      ].filter(Boolean).join(" ").toLowerCase();
      return searchableText.includes(normalizedSearch);
    })
    .sort((a, b) => {
      if (state.sort === "price-asc") return a.price - b.price;
      if (state.sort === "price-desc") return b.price - a.price;
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });
}

function hasActiveFilters() {
  return Boolean(state.brandId || state.categoryId || state.modelId || state.collectionId || state.maxPrice < 400);
}

function getEmptyStateCopy() {
  const term = state.search.trim();
  const hasSearch = Boolean(term);
  const hasFilters = hasActiveFilters();
  const hasProducts = (window.DripZoneProducts || []).length > 0;

  if (window.DripZoneProductsLoadError) {
    return {
      title: "Não foi possível carregar os produtos.",
      description: "Tente atualizar a página em alguns instantes."
    };
  }

  if (!hasProducts) {
    return {
      title: "Nenhum produto disponível no momento.",
      description: "Novos produtos serão adicionados em breve."
    };
  }

  if (hasSearch && hasFilters) {
    return {
      title: `Não encontramos produtos para "${term}" com os filtros selecionados.`,
      description: "Tente outro termo ou limpe os filtros."
    };
  }

  if (hasSearch) {
    return {
      title: `Não encontramos produtos para "${term}".`,
      description: "Tente outro termo ou limpe os filtros."
    };
  }

  return {
    title: "Nenhum produto encontrado para os filtros selecionados.",
    description: "Ajuste os filtros ou limpe a seleção atual."
  };
}

function createProductCard(product) {
  const badges = (product.badges || [product.tag])
    .map((badge) => `<span class="product-badge">${badge}</span>`)
    .join("");

  return `
    <a class="product-card catalog-product" href="../produto/?id=${encodeURIComponent(product.id)}" aria-label="Ver produto ${product.name}">
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
  const emptyTitle = document.querySelector("[data-empty-title]");
  const emptyDescription = document.querySelector("[data-empty-description]");
  const resultCount = document.querySelector("[data-result-count]");
  const products = getFilteredProducts();

  if (!grid || !emptyState || !resultCount) return;

  grid.innerHTML = products.map(createProductCard).join("");
  emptyState.hidden = products.length > 0;
  if (products.length === 0) {
    const copy = getEmptyStateCopy();
    if (emptyTitle) emptyTitle.textContent = copy.title;
    if (emptyDescription) emptyDescription.textContent = copy.description;
  }
  resultCount.textContent = `${products.length} ${products.length === 1 ? "produto" : "produtos"}`;
}

function updateCategoryButtons() {
  document.querySelectorAll("[data-category]").forEach((button) => {
    const buttonCategory = button.dataset.category || "Todos";
    const buttonCategoryId = categoryNameToId[buttonCategory] ?? "";
    const isActive = state.categoryId ? buttonCategoryId === state.categoryId : buttonCategory === "Todos";
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function normalizeFilterId(value) {
  if (value === null) return "";
  const normalized = String(value).trim().toLowerCase();
  if (!normalized) return invalidFilterValue;
  return /^[a-z0-9-]+$/.test(normalized) ? normalized : invalidFilterValue;
}

function readCatalogParams() {
  const params = new URLSearchParams(window.location.search);
  const initialSearch = params.get("q") || params.get("busca") || "";

  state.brandId = normalizeFilterId(params.get("marca"));
  state.categoryId = normalizeFilterId(params.get("categoria"));
  state.modelId = normalizeFilterId(params.get("modelo"));
  state.collectionId = normalizeFilterId(params.get("colecao"));
  state.category = categoryIdToName[state.categoryId] || (state.categoryId ? "" : "Todos");

  if (initialSearch) state.search = initialSearch.slice(0, 80);
}

function clearCatalogParams() {
  const params = new URLSearchParams(window.location.search);
  ["marca", "categoria", "modelo", "colecao", "q", "busca"].forEach((key) => params.delete(key));
  const search = params.toString();
  const nextUrl = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
  window.history.replaceState(null, "", nextUrl);
}

async function initCatalog() {
  await (window.DripZoneProductsReady || Promise.resolve());

  const search = document.querySelector("[data-search]");
  const price = document.querySelector("[data-price]");
  const priceOutput = document.querySelector("[data-price-output]");
  const sort = document.querySelector("[data-sort]");
  const clear = document.querySelector("[data-clear-filters]");
  const emptyClear = document.querySelector("[data-empty-clear]");

  readCatalogParams();

  if (state.search) {
    if (search) search.value = state.search;
  }

  document.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", () => {
      state.category = button.dataset.category || "Todos";
      state.categoryId = categoryNameToId[state.category] ?? "";
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

  const resetCatalogFilters = () => {
    state.category = "Todos";
    state.categoryId = "";
    state.brandId = "";
    state.modelId = "";
    state.collectionId = "";
    state.search = "";
    state.maxPrice = 400;
    state.sort = "recent";

    if (search) search.value = "";
    if (price) price.value = "400";
    if (priceOutput) priceOutput.textContent = "Até R$ 400";
    if (sort) sort.value = "recent";

    updateCategoryButtons();
    clearCatalogParams();
    renderProducts();
  };

  clear?.addEventListener("click", resetCatalogFilters);
  emptyClear?.addEventListener("click", resetCatalogFilters);

  updateCategoryButtons();
  renderProducts();
}

document.addEventListener("DOMContentLoaded", initCatalog);
