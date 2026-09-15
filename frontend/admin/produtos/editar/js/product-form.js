import { getProductById, createProduct, updateProduct, publishProduct, uploadProductImage, getBrands, getCategories, getSneakers, ApiError } from "./api.js?v=api-base-3000-20260730";
import { initAdminPage, setText } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { notify, openModal } from "/admin/js/notifications.js?v=api-base-3000-20260730";

const isEditPage = window.location.pathname.includes("/editar/");
const pageTitle = isEditPage ? "Editar produto" : "Novo produto";
let loadedProduct = null;
let brands = [];
let categories = [];
let sneakerModels = [];

await initAdminPage({ title: pageTitle, breadcrumb: `Admin / Produtos / ${pageTitle}` });
initProductForm();

async function initProductForm() {
  await loadProductReferenceData();
  bindFormTools();
  bindPreview();

  if (!isEditPage) return;

  const id = new URLSearchParams(window.location.search).get("id");
  const form = document.querySelector("[data-product-form]");
  const notFound = document.querySelector("[data-product-not-found]");
  const product = id ? await getProductById(id).catch(() => null) : null;

  if (!product) {
    if (form) form.hidden = true;
    if (notFound) notFound.hidden = false;
    return;
  }

  loadedProduct = product;
  fillProduct(product);
}

function bindFormTools() {
  document.querySelector("[data-add-variation]")?.addEventListener("click", addVariationRow);
  document.querySelector("[data-image-input]")?.addEventListener("change", handleImagePreview);
  document.querySelector("[data-product-form]")?.addEventListener("submit", handleSubmit);
  document.querySelector("[data-publish-product]")?.addEventListener("click", handleSubmit);
  document.querySelector("[data-preview-product]")?.addEventListener("click", showTemporaryPreview);
  document.getElementById("product-brand")?.addEventListener("change", () => updateSneakerModelField());
  document.getElementById("product-category")?.addEventListener("change", () => updateSneakerModelField());
  document.getElementById("product-type")?.addEventListener("input", () => updateSneakerModelField());
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.matches("[data-remove-row]")) event.target.closest("[data-dynamic-row]")?.remove();
  });
}

async function loadProductReferenceData() {
  const [brandsResult, categoriesResult, sneakersResult] = await Promise.allSettled([
    getBrands(),
    getCategories(),
    getSneakers()
  ]);
  brands = brandsResult.status === "fulfilled" ? brandsResult.value || [] : [];
  categories = categoriesResult.status === "fulfilled" ? categoriesResult.value || [] : [];
  sneakerModels = sneakersResult.status === "fulfilled" ? sneakersResult.value || [] : [];
  fillResourceSelect("product-brand", brands, "Sem marca");
  fillResourceSelect("product-category", categories, "Sem categoria");
  updateSneakerModelField();
}

function fillResourceSelect(id, items, emptyLabel) {
  const select = document.getElementById(id);
  if (!select) return;
  const options = [new Option(emptyLabel, "")];
  items.forEach((item) => {
    const option = new Option(item.name || item.slug || item.id, String(item.id));
    option.dataset.slug = item.slug || "";
    select.append(option);
    options.push(option);
  });
  select.replaceChildren(...options);
}

function selectedResource(id, items) {
  const value = document.getElementById(id)?.value || "";
  return items.find((item) => String(item.id) === value) || null;
}

function selectedId(id) {
  const value = document.getElementById(id)?.value || "";
  return value ? Number(value) : null;
}

function normalizeText(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function isSneakerProduct() {
  const category = selectedResource("product-category", categories);
  const categoryText = normalizeText([category?.slug, category?.name].filter(Boolean).join(" "));
  const productTypeText = normalizeText(document.getElementById("product-type")?.value || "");
  return /\b(sneaker|sneakers|tenis|calcado|calcados)\b/.test(`${categoryText} ${productTypeText}`);
}

function updateSneakerModelField() {
  const wrapper = document.querySelector("[data-sneaker-model-field]");
  const select = document.getElementById("product-model");
  if (!wrapper || !select) return;

  const enabled = isSneakerProduct();
  const brandId = selectedId("product-brand");
  const currentValue = select.value;
  const models = sneakerModels.filter((model) => model.is_active !== false && (!brandId || !model.brand_id || model.brand_id === brandId));
  const options = [new Option("Sem modelo", "")];
  models.forEach((model) => {
    const option = new Option(model.name || model.slug || model.id, String(model.id));
    option.dataset.brandId = model.brand_id ? String(model.brand_id) : "";
    option.dataset.slug = model.slug || "";
    options.push(option);
  });
  select.replaceChildren(...options);
  select.value = models.some((model) => String(model.id) === currentValue) ? currentValue : "";
  select.disabled = !enabled;
  wrapper.hidden = !enabled;
}

function addVariationRow() {
  const list = document.querySelector("[data-variation-list]");
  if (!list) return;
  const row = document.createElement("div");
  row.className = "admin-variation-row";
  row.dataset.dynamicRow = "true";
  ["Tamanho", "Cor", "Quantidade", "SKU"].forEach((placeholder) => {
    const input = document.createElement("input");
    input.className = "admin-inline-input";
    input.placeholder = placeholder;
    row.append(input);
  });
  const remove = document.createElement("button");
  remove.className = "admin-button admin-button--danger";
  remove.type = "button";
  remove.dataset.removeRow = "true";
  remove.textContent = "Remover";
  row.append(remove);
  list.append(row);
}

function handleImagePreview(event) {
  const list = document.querySelector("[data-image-list]");
  if (!list) return;
  Array.from(event.target.files || []).forEach((file) => {
    const row = document.createElement("div");
    row.className = "admin-image-row";
    row.dataset.dynamicRow = "true";

    const img = document.createElement("img");
    img.className = "admin-image-preview";
    img.alt = "";
    img.src = URL.createObjectURL(file);

    const name = document.createElement("input");
    name.className = "admin-inline-input";
    name.value = file.name;
    name.readOnly = true;

    const alt = document.createElement("input");
    alt.className = "admin-inline-input";
    alt.placeholder = "Texto alternativo";

    const remove = document.createElement("button");
    remove.className = "admin-button admin-button--danger";
    remove.type = "button";
    remove.dataset.removeRow = "true";
    remove.textContent = "Remover";

    row.append(img, name, alt, remove);
    list.append(row);
  });
}

function bindPreview() {
  const fields = ["product-name", "product-slug", "seo-title", "seo-description"];
  fields.forEach((id) => {
    document.getElementById(id)?.addEventListener("input", updateSeoPreview);
  });
  updateSeoPreview();
}

function updateSeoPreview() {
  const name = document.getElementById("seo-title")?.value || document.getElementById("product-name")?.value || "Título SEO";
  const slug = document.getElementById("product-slug")?.value || "slug-do-produto";
  const description = document.getElementById("seo-description")?.value || "Descrição SEO aparecerá aqui.";
  setText("[data-seo-preview-title]", name);
  setText("[data-seo-preview-url]", `https://dripzone.com.br/pages/produto/?id=${slug}`);
  setText("[data-seo-preview-description]", description);
}

async function handleSubmit(event) {
  event.preventDefault();
  const form = document.querySelector("[data-product-form]");
  if (!form) return;

  if (!form.checkValidity()) {
    form.reportValidity();
    notify("Preencha os campos obrigatórios.", "warning");
    return;
  }

  const submitter = event.submitter;
  const shouldPublish = submitter?.matches("[data-publish-product]") || event.target?.matches?.("[data-publish-product]");
  try {
    const saved = isEditPage ? await updateProduct(currentProductId(), collectPayload()) : await createProduct(collectPayload());
    loadedProduct = saved;
    await uploadSelectedImages(saved.id);
    if (shouldPublish) loadedProduct = await publishProduct(saved.id);
    notify("Produto salvo com sucesso.", "success");
    if (!isEditPage) location.href = `/admin/produtos/editar/?id=${saved.id}`;
  } catch (error) {
    notify(publicationErrorMessage(error), error instanceof ApiError ? "warning" : "error");
  }
}

function publicationErrorMessage(error) {
  if (error?.code === "PRODUCT_NOT_READY_FOR_PUBLICATION" && Array.isArray(error?.details?.blockers)) {
    return `Nao foi possivel publicar:\n${error.details.blockers.map((blocker) => `- ${blocker.message}`).join("\n")}`;
  }
  return error?.message || "Não foi possível processar a ação.";
}

function currentProductId() {
  return new URLSearchParams(window.location.search).get("id");
}

function moneyValue(id) {
  const value = document.getElementById(id)?.value || "0";
  return value.replace(/[^\d,.-]/g, "").replace(",", ".") || "0";
}

function intValue(id) {
  return Number.parseInt(document.getElementById(id)?.value || "0", 10) || 0;
}

function currentPublicationState() {
  if (isEditPage && loadedProduct) {
    return {
      status: loadedProduct.status || "draft",
      visibility: loadedProduct.visibility || (loadedProduct.status === "published" ? "public" : "hidden")
    };
  }
  return { status: "draft", visibility: "hidden" };
}

function collectPayload() {
  const publication = currentPublicationState();
  return {
    name: document.getElementById("product-name")?.value || "",
    slug: document.getElementById("product-slug")?.value || null,
    sku: document.getElementById("product-sku")?.value || null,
    short_description: document.getElementById("short-description")?.value || null,
    description: document.getElementById("full-description")?.value || null,
    brand_id: selectedId("product-brand"),
    category_id: selectedId("product-category"),
    sneaker_model_id: !document.getElementById("product-model")?.disabled ? selectedId("product-model") : null,
    product_type: document.getElementById("product-type")?.value || null,
    audience: document.getElementById("product-audience")?.value || null,
    price: moneyValue("price"),
    compare_at_price: document.getElementById("old-price")?.value ? moneyValue("old-price") : null,
    cost_price: document.getElementById("cost")?.value ? moneyValue("cost") : null,
    promotional_price: document.getElementById("sale-price")?.value ? moneyValue("sale-price") : null,
    stock_quantity: intValue("stock-qty"),
    minimum_stock: intValue("min-stock"),
    status: publication.status,
    visibility: publication.visibility,
    seo_title: document.getElementById("seo-title")?.value || null,
    seo_description: document.getElementById("seo-description")?.value || null,
    canonical_url: document.getElementById("canonical")?.value || null,
    main_image_alt: document.getElementById("main-alt")?.value || null,
    variants: []
  };
}

async function uploadSelectedImages(productId) {
  const input = document.querySelector("[data-image-input]");
  const files = Array.from(input?.files || []);
  for (const file of files) {
    const data = new FormData();
    data.append("file", file);
    await uploadProductImage(productId, data);
  }
}

function showTemporaryPreview() {
  const name = document.getElementById("product-name")?.value || "Produto sem nome";
  const description = document.getElementById("short-description")?.value || "Prévia temporária do painel. Nada foi salvo.";
  const body = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = name;
  const copy = document.createElement("p");
  copy.textContent = description;
  body.append(title, copy);
  openModal({ title: "Prévia temporária", body, actions: [{ label: "Fechar" }] });
}

function fillProduct(product) {
  const map = {
    "product-name": product.name,
    "product-slug": product.slug,
    "product-sku": product.sku,
    "product-brand": product.brand_id,
    "product-category": product.category_id,
    "product-model": product.sneaker_model_id,
    "product-type": product.product_type,
    "short-description": product.short_description,
    "full-description": product.description,
    "price": product.price,
    "stock-qty": product.stock_quantity,
    "seo-title": product.seo_title,
    "seo-description": product.seo_description
  };
  Object.entries(map).forEach(([id, value]) => {
    const field = document.getElementById(id);
    if (field) field.value = value || "";
  });
  updateSneakerModelField();
  const modelField = document.getElementById("product-model");
  if (modelField && product.sneaker_model_id) modelField.value = String(product.sneaker_model_id);
  updateSeoPreview();
}
