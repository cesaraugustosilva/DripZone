const productFormatPrice = window.DripZoneUtils?.formatPrice || ((price) =>
  Number(price || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  }));
const productPublicUrl = window.DripZoneUtils?.publicUrl || ((path = "") => `https://dripzone.com.br/${String(path).replace(/^(\.\.\/)+/, "")}`);
const PRODUCT_ID_PATTERN = /^[a-z0-9-]+$/;

function getProductIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id") || "";
  return PRODUCT_ID_PATTERN.test(id) ? id : null;
}

function getCurrentProduct() {
  const products = window.DripZoneProducts || [];
  const id = getProductIdFromUrl();
  return id ? products.find((product) => product.id === id) || null : null;
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
  const relatedSection = document.querySelector(".related-section");
  const products = window.DripZoneProducts || [];
  if (!relatedGrid) return;

  const sameCategory = products.filter((item) => item.id !== product.id && item.category === product.category);
  const otherProducts = products.filter((item) => item.id !== product.id && item.category !== product.category);
  const related = [...sameCategory, ...otherProducts].slice(0, 3);

  if (related.length === 0) {
    if (relatedSection) {
      relatedSection.hidden = true;
      relatedSection.style.display = "none";
    }
    relatedGrid.innerHTML = "";
    return;
  }

  relatedGrid.innerHTML = related
    .map(
      (item) => {
        const badges = (item.badges || [item.tag]).map((badge) => `<span class="product-badge">${badge}</span>`).join("");
        return `
        <a class="product-card catalog-product" href="?id=${encodeURIComponent(item.id)}" aria-label="Ver produto ${item.name}">
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

function setMeta(selector, attribute, value) {
  const element = document.querySelector(selector);
  if (element) element.setAttribute(attribute, value);
}

function upsertJsonLd(id, data) {
  let script = document.getElementById(id);
  if (!script) {
    script = document.createElement("script");
    script.type = "application/ld+json";
    script.id = id;
    document.head.appendChild(script);
  }

  script.textContent = JSON.stringify(data);
}

function renderProductStructuredData(product) {
  const productUrl = productPublicUrl(`pages/produto/?id=${encodeURIComponent(product.id)}`);
  const productImage = productPublicUrl(product.image);

  upsertJsonLd("product-json-ld", {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Product",
        "@id": `${productUrl}#product`,
        "name": product.name,
        "description": product.description,
        "image": productImage,
        "brand": {
          "@type": "Brand",
          "name": "DripZone"
        },
        "category": product.category,
        "offers": {
          "@type": "Offer",
          "url": productUrl,
          "priceCurrency": "BRL",
          "price": product.price.toFixed(2),
          "availability": "https://schema.org/InStock",
          "itemCondition": "https://schema.org/NewCondition"
        }
      },
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          {
            "@type": "ListItem",
            "position": 1,
            "name": "Início",
            "item": "https://dripzone.com.br/"
          },
          {
            "@type": "ListItem",
            "position": 2,
            "name": "Catálogo",
            "item": "https://dripzone.com.br/pages/catalogo/"
          },
          {
            "@type": "ListItem",
            "position": 3,
            "name": product.name,
            "item": productUrl
          }
        ]
      }
    ]
  });
}

function updateProductMeta(product) {
  const productUrl = productPublicUrl(`pages/produto/?id=${encodeURIComponent(product.id)}`);
  const productImage = productPublicUrl(product.image);
  const description = `${product.name} da DripZone: ${product.description}`;

  document.title = `${product.name} | DripZone`;
  setMeta('meta[name="description"]', "content", description);
  setMeta('meta[property="og:title"]', "content", `${product.name} | DripZone`);
  setMeta('meta[property="og:description"]', "content", description);
  setMeta('meta[property="og:url"]', "content", productUrl);
  setMeta('meta[property="og:image"]', "content", productImage);
  setMeta('meta[name="twitter:title"]', "content", `${product.name} | DripZone`);
  setMeta('meta[name="twitter:description"]', "content", description);
  setMeta('meta[name="twitter:image"]', "content", productImage);
  setMeta('link[rel="canonical"]', "href", productUrl);
}

function updateNotFoundMeta() {
  const productUrl = productPublicUrl("pages/produto/");
  const description = "Produto não encontrado no catálogo da DripZone.";

  document.title = "Produto não encontrado | DripZone";
  setMeta('meta[name="description"]', "content", description);
  setMeta('meta[property="og:title"]', "content", "Produto não encontrado | DripZone");
  setMeta('meta[property="og:description"]', "content", description);
  setMeta('meta[property="og:url"]', "content", productUrl);
  setMeta('meta[name="twitter:title"]', "content", "Produto não encontrado | DripZone");
  setMeta('meta[name="twitter:description"]', "content", description);
  setMeta('link[rel="canonical"]', "href", productUrl);
  document.getElementById("product-json-ld")?.remove();
}

function hideProductSection(selector) {
  const element = document.querySelector(selector);
  if (!element) return;

  element.hidden = true;
  element.style.display = "none";
}

function renderProductNotFound() {
  updateNotFoundMeta();

  hideProductSection(".product-gallery");
  hideProductSection(".related-section");
  hideProductSection("[data-product-form]");

  const detail = document.querySelector(".product-detail");
  if (!detail) return;

  detail.classList.add("product-detail--not-found");
  detail.innerHTML = `
    <p class="section__eyebrow">Produto não encontrado</p>
    <h1>Produto não encontrado</h1>
    <p class="product-detail__description">
      O item solicitado não existe no catálogo atual ou o link usado está incompleto.
    </p>
    <a class="btn btn--neon product-add" href="../catalogo/">Voltar ao catálogo</a>
  `;
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

async function initProductPage() {
  await (window.DripZoneProductsReady || Promise.resolve());

  const product = getCurrentProduct();
  if (!product) {
    renderProductNotFound();
    return;
  }

  updateProductMeta(product);
  setText("[data-product-category]", product.category);
  setText("[data-product-name]", product.name);
  setText("[data-product-price]", productFormatPrice(product.price));
  setText("[data-product-description]", product.description);

  renderGallery(product);
  renderSizes(product);
  renderRelated(product);
  renderProductStructuredData(product);
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
