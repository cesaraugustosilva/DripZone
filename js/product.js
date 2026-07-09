const productFormatPrice = (price) =>
  price.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  });

function getProductIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("id") || "oversized-signal-tee";
}

function getCurrentProduct() {
  const products = window.DripZoneProducts || [];
  const id = getProductIdFromUrl();
  return products.find((product) => product.id === id) || products[0];
}

function setText(selector, text) {
  const element = document.querySelector(selector);
  if (element) element.textContent = text;
}

function renderGallery(product) {
  const mainImage = document.querySelector("[data-product-main-image]");
  const thumbs = document.querySelector("[data-product-thumbs]");
  if (!mainImage || !thumbs) return;

  mainImage.src = product.gallery[0];
  mainImage.alt = product.name;
  thumbs.innerHTML = product.gallery
    .map(
      (image, index) => `
        <button class="product-gallery__thumb ${index === 0 ? "is-active" : ""}" type="button" data-gallery-image="${image}" aria-label="Ver imagem ${index + 1} de ${product.name}">
          <img src="${image}" alt="" aria-hidden="true" />
        </button>
      `
    )
    .join("");

  thumbs.querySelectorAll("[data-gallery-image]").forEach((button) => {
    button.addEventListener("click", () => {
      mainImage.classList.add("is-switching");
      thumbs.querySelectorAll(".product-gallery__thumb").forEach((thumb) => thumb.classList.remove("is-active"));
      button.classList.add("is-active");
      window.setTimeout(() => {
        mainImage.src = button.dataset.galleryImage;
        mainImage.classList.remove("is-switching");
      }, 140);
    });
  });
}

function renderSizes(product) {
  const sizes = document.querySelector("[data-product-sizes]");
  if (!sizes) return;

  sizes.innerHTML = product.sizes
    .map(
      (size, index) => `
        <label class="size-option">
          <input type="radio" name="size" value="${size}" ${index === 0 ? "checked" : ""} />
          <span>${size}</span>
        </label>
      `
    )
    .join("");
}

function renderRelated(product) {
  const relatedGrid = document.querySelector("[data-related-products]");
  const products = window.DripZoneProducts || [];
  if (!relatedGrid) return;

  const sameCategory = products.filter((item) => item.id !== product.id && item.category === product.category);
  const otherProducts = products.filter((item) => item.id !== product.id && item.category !== product.category);
  const related = [...sameCategory, ...otherProducts].slice(0, 3);

  relatedGrid.innerHTML = related
    .map(
      (item) => {
        const badges = (item.badges || [item.tag]).map((badge) => `<span class="product-badge">${badge}</span>`).join("");
        return `
        <a class="product-card catalog-product" href="produto.html?id=${item.id}" aria-label="Ver produto ${item.name}">
          <div class="product-card__media">
            <img src="${item.image}" alt="${item.name}" loading="lazy" />
            <span class="badge-stack">${badges}</span>
          </div>
          <div class="product-card__body">
            <p class="product-card__category">${item.category}</p>
            <h3>${item.name}</h3>
            <div class="product-card__footer">
              <span class="price">${productFormatPrice(item.price)}</span>
              <span class="product-card__cta">Ver peça</span>
            </div>
          </div>
        </a>
      `;
      }
    )
    .join("");
}

function initQuantityControls() {
  const input = document.querySelector("[data-product-qty]");
  const minus = document.querySelector("[data-product-qty-minus]");
  const plus = document.querySelector("[data-product-qty-plus]");
  if (!input || !minus || !plus) return;

  const clamp = (value) => Math.min(Math.max(Number(value) || 1, 1), 10);

  minus.addEventListener("click", () => {
    input.value = String(clamp(Number(input.value) - 1));
  });

  plus.addEventListener("click", () => {
    input.value = String(clamp(Number(input.value) + 1));
  });

  input.addEventListener("input", () => {
    input.value = String(clamp(input.value));
  });
}

function initProductPage() {
  const product = getCurrentProduct();
  if (!product) return;

  document.title = `${product.name} | DripZone`;
  setText("[data-product-category]", product.category);
  setText("[data-product-name]", product.name);
  setText("[data-product-price]", productFormatPrice(product.price));
  setText("[data-product-description]", product.description);

  renderGallery(product);
  renderSizes(product);
  renderRelated(product);
  initQuantityControls();

  document.querySelector("[data-product-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const size = document.querySelector('input[name="size"]:checked')?.value || product.sizes[0];
    const quantity = Number(document.querySelector("[data-product-qty]")?.value || 1);

    window.DripZoneCart?.addToCart({
      productId: product.id,
      size,
      quantity
    });
  });
}

document.addEventListener("DOMContentLoaded", initProductPage);
