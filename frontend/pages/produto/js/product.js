const productFormatPrice = window.DripZoneUtils?.formatPrice || ((price) =>
  Number(price || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  }));
const productPublicUrl = window.DripZoneUtils?.publicUrl || ((path = "") => `https://dripzone.com.br/${String(path).replace(/^(\.\.\/)+/, "")}`);
const PRODUCT_ID_PATTERN = /^[a-z0-9-]+$/;
const hasProductPrice = (product) => Number.isFinite(product.price);
const isPurchasable = (product) => window.DripZoneSecurity?.isPurchasable(product) || false;
const displayProductPrice = (product) => isPurchasable(product) ? productFormatPrice(product.price) : "Preço sob consulta";
const safeText = (value, fallback = "") => window.DripZoneSecurity?.text(value, fallback) ?? String(value ?? fallback);
const productCardImage = (product) => window.DripZoneSecurity?.assetImage(product.image) || "../../assets/images/logo/dripzone-logo.png";
const productGallery = (product) => {
  const gallery = Array.isArray(product.gallery) && product.gallery.length ? product.gallery : (product.image ? [product.image] : []);
  return gallery.map((image) => window.DripZoneSecurity?.imageUrl(image, "") || "").filter(Boolean);
};
const productLink = (product) => window.DripZoneSecurity?.productHref(product.id, "./") || "./";

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
  const gallery = productGallery(product);
  if (gallery.length === 0) {
    hideProductSection(".product-gallery");
    return;
  }

  const productName = safeText(product.name, "Produto");
  window.DripZoneSecurity?.setSafeImage(mainImage, gallery[0], productName);
  thumbs.replaceChildren(...gallery.map((imageUrl, index) => {
    const button = document.createElement("button");
    button.className = `product-gallery__thumb ${index === 0 ? "is-active" : ""}`;
    button.type = "button";
    button.dataset.galleryImage = imageUrl;
    button.setAttribute("aria-label", `Ver imagem ${index + 1} de ${productName}`);
    const image = document.createElement("img");
    image.alt = "";
    image.setAttribute("aria-hidden", "true");
    window.DripZoneSecurity?.setSafeImage(image, imageUrl, "");
    button.append(image);
    return button;
  }));

  thumbs.querySelectorAll("[data-gallery-image]").forEach((button) => {
    button.addEventListener("click", () => {
      mainImage.classList.add("is-switching");
      thumbs.querySelectorAll(".product-gallery__thumb").forEach((thumb) => thumb.classList.remove("is-active"));
      button.classList.add("is-active");
      window.setTimeout(() => {
        window.DripZoneSecurity?.setSafeImage(mainImage, button.dataset.galleryImage, productName);
        mainImage.classList.remove("is-switching");
      }, 140);
    });
  });
}

function renderSizes(product) {
  const sizes = document.querySelector("[data-product-sizes]");
  if (!sizes) return;

  const options = (Array.isArray(product.sizes) ? product.sizes : []).map((size, index) => {
    const label = document.createElement("label");
    label.className = "size-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "size";
    input.value = safeText(size).slice(0, 80);
    input.checked = index === 0;
    const text = document.createElement("span");
    text.textContent = safeText(size);
    label.append(input, text);
    return label;
  });
  sizes.replaceChildren(...options);
}

function createRelatedCard(item) {
  const card = document.createElement("a");
  const productName = safeText(item.name, "Produto");
  card.className = "product-card catalog-product";
  card.href = productLink(item);
  card.setAttribute("aria-label", `Ver produto ${productName}`);

  const media = document.createElement("div");
  media.className = "product-card__media";
  const image = document.createElement("img");
  image.loading = "lazy";
  window.DripZoneSecurity?.setSafeImage(image, item.image, productName);
  const badgeStack = document.createElement("span");
  badgeStack.className = "badge-stack";
  (Array.isArray(item.badges) ? item.badges : [item.tag]).filter(Boolean).forEach((badge) => {
    const badgeElement = document.createElement("span");
    badgeElement.className = "product-badge";
    badgeElement.textContent = safeText(badge);
    badgeStack.append(badgeElement);
  });
  media.append(image, badgeStack);

  const body = document.createElement("div");
  body.className = "product-card__body";
  const category = document.createElement("p");
  category.className = "product-card__category";
  category.textContent = safeText(item.category);
  const title = document.createElement("h3");
  title.textContent = productName;
  const footer = document.createElement("div");
  footer.className = "product-card__footer";
  const price = document.createElement("span");
  price.className = "price";
  price.textContent = displayProductPrice(item);
  const cta = document.createElement("span");
  cta.className = "product-card__cta";
  cta.textContent = "Ver peça";
  footer.append(price, cta);
  body.append(category, title, footer);
  card.append(media, body);
  return card;
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
    relatedGrid.replaceChildren();
    return;
  }

  relatedGrid.replaceChildren(...related.map(createRelatedCard));
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
  const productUrl = productPublicUrl(`pages/produto/?id=${encodeURIComponent(window.DripZoneSecurity?.productId(product.id) || "")}`);
  const productImage = window.DripZoneSecurity?.publicUrl(product.image) || productPublicUrl("assets/images/logo/dripzone-logo.png");
  const offer = {
    "@type": "Offer",
    "url": productUrl,
    "priceCurrency": "BRL",
    "availability": "https://schema.org/InStock",
    "itemCondition": "https://schema.org/NewCondition"
  };
  if (hasProductPrice(product)) {
    offer.price = product.price.toFixed(2);
  }

  upsertJsonLd("product-json-ld", {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Product",
        "@id": `${productUrl}#product`,
        "name": safeText(product.name),
        "description": safeText(product.description),
        "image": productImage,
        "brand": {
          "@type": "Brand",
          "name": "DripZone"
        },
        "category": safeText(product.category),
        "offers": offer
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
            "name": safeText(product.name),
            "item": productUrl
          }
        ]
      }
    ]
  });
}

function updateProductMeta(product) {
  const productName = safeText(product.name, "Produto");
  const productUrl = productPublicUrl(`pages/produto/?id=${encodeURIComponent(window.DripZoneSecurity?.productId(product.id) || "")}`);
  const productImage = window.DripZoneSecurity?.publicUrl(product.image) || productPublicUrl("assets/images/logo/dripzone-logo.png");
  const description = `${productName} da DripZone: ${safeText(product.description)}`;

  document.title = `${productName} | DripZone`;
  setMeta('meta[name="description"]', "content", description);
  setMeta('meta[property="og:title"]', "content", `${productName} | DripZone`);
  setMeta('meta[property="og:description"]', "content", description);
  setMeta('meta[property="og:url"]', "content", productUrl);
  setMeta('meta[property="og:image"]', "content", productImage);
  setMeta('meta[name="twitter:title"]', "content", `${productName} | DripZone`);
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
  const eyebrow = document.createElement("p");
  eyebrow.className = "section__eyebrow";
  eyebrow.textContent = "Produto não encontrado";
  const title = document.createElement("h1");
  title.textContent = "Produto não encontrado";
  const description = document.createElement("p");
  description.className = "product-detail__description";
  description.textContent = "O item solicitado não existe no catálogo atual ou o link usado está incompleto.";
  const link = document.createElement("a");
  link.className = "btn btn--neon product-add";
  link.href = "../catalogo/";
  link.textContent = "Voltar ao catálogo";
  detail.replaceChildren(eyebrow, title, description, link);
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
  setText("[data-product-category]", safeText(product.category));
  setText("[data-product-name]", safeText(product.name));
  setText("[data-product-price]", displayProductPrice(product));
  setText("[data-product-description]", safeText(product.description));
  const buyForm = document.querySelector("[data-product-form]");
  const addButton = buyForm?.querySelector(".product-add");
  if (!isPurchasable(product)) {
    buyForm?.classList.add("product-buy--showcase");
    if (addButton) {
      addButton.disabled = true;
      addButton.textContent = "Compra em breve";
      addButton.setAttribute("aria-disabled", "true");
    }
  }

  renderGallery(product);
  renderSizes(product);
  renderRelated(product);
  renderProductStructuredData(product);
  initQuantityControls();

  buyForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!isPurchasable(product)) return;
    const size = document.querySelector('input[name="size"]:checked')?.value || (Array.isArray(product.sizes) ? product.sizes[0] : "");
    const quantity = Number(document.querySelector("[data-product-qty]")?.value || 1);

    window.DripZoneCart?.addToCart({
      productId: product.id,
      size,
      quantity
    });
  });
}

document.addEventListener("DOMContentLoaded", initProductPage);
