import { deleteProduct, exportProducts, getBrands, getCategories, getProductsPage, publishProduct, unpublishProduct } from "./api.js?v=api-base-3000-20260730";
import { clearChildren, createBadge, initAdminPage } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { closeModal, notify, openModal } from "/admin/js/notifications.js?v=api-base-3000-20260730";

const pageSize = 20;
let state = { page: 1, search: "", status: "", brand_id: "", category_id: "" };
let requestId = 0;
let searchTimer;
const brandNames = new Map();
const categoryNames = new Map();

await initAdminPage({
  title: "Produtos",
  breadcrumb: "Admin / Produtos",
  description: "Gerencie o catalogo de produtos da DripZone."
});

bindProductActions();
await loadFilterOptions();
renderProductsPage();

function bindProductActions() {
  document.querySelector("[data-export-products]")?.addEventListener("click", handleExport);
  document.querySelector("[data-retry-products]")?.addEventListener("click", renderProductsPage);
  document.querySelector("[data-products-prev]")?.addEventListener("click", () => changePage(state.page - 1));
  document.querySelector("[data-products-next]")?.addEventListener("click", () => changePage(state.page + 1));
  document.querySelector("[data-clear-product-filters]")?.addEventListener("click", clearFilters);
  document.querySelector("[data-product-search]")?.addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = event.target.value.trim();
      state.page = 1;
      renderProductsPage();
    }, 300);
  });
  document.querySelector("[data-product-status]")?.addEventListener("change", (event) => updateFilter("status", event.target.value));
  document.querySelector("[data-product-brand]")?.addEventListener("change", (event) => updateFilter("brand_id", event.target.value));
  document.querySelector("[data-product-category]")?.addEventListener("change", (event) => updateFilter("category_id", event.target.value));
}

async function handleExport(event) {
  const button = event.currentTarget;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    await exportProducts();
    notify("Produtos publicados exportados com sucesso.", "success");
  } catch (error) {
    notify(errorMessage(error, "Nao foi possivel exportar os produtos."), "error");
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

async function loadFilterOptions() {
  const [brandsResult, categoriesResult] = await Promise.allSettled([getBrands(), getCategories()]);
  if (brandsResult.status === "fulfilled") {
    brandsResult.value.forEach((item) => brandNames.set(Number(item.id), item.name));
    fillSelect("[data-product-brand]", brandsResult.value, "Todas");
  }
  if (categoriesResult.status === "fulfilled") {
    categoriesResult.value.forEach((item) => categoryNames.set(Number(item.id), item.name));
    fillSelect("[data-product-category]", categoriesResult.value, "Todas");
  }
}

function fillSelect(selector, items, defaultLabel) {
  const select = document.querySelector(selector);
  if (!select) return;
  clearChildren(select);
  select.append(new Option(defaultLabel, ""));
  items.forEach((item) => select.append(new Option(item.name, String(item.id))));
}

function updateFilter(key, value) {
  state[key] = value;
  state.page = 1;
  renderProductsPage();
}

function clearFilters() {
  state = { page: 1, search: "", status: "", brand_id: "", category_id: "" };
  document.querySelector("[data-product-search]").value = "";
  document.querySelector("[data-product-status]").value = "";
  document.querySelector("[data-product-brand]").value = "";
  document.querySelector("[data-product-category]").value = "";
  renderProductsPage();
}

function changePage(page) {
  if (page < 1) return;
  state.page = page;
  renderProductsPage();
}

async function renderProductsPage() {
  const currentRequest = ++requestId;
  setLoading(true);
  setError(false);

  try {
    const page = await getProductsPage(queryParams());
    if (currentRequest !== requestId) return;
    renderProducts(page.items || [], page.pagination || {});
  } catch (error) {
    if (currentRequest !== requestId) return;
    renderError(error);
  }
}

function queryParams() {
  return Object.fromEntries(Object.entries({
    page: state.page,
    page_size: pageSize,
    search: state.search,
    status: state.status,
    brand_id: state.brand_id,
    category_id: state.category_id,
    sort: "updated_at",
    order: "desc"
  }).filter(([, value]) => value !== ""));
}

function renderProducts(products, pagination) {
  const tbody = document.querySelector("[data-products-tbody]");
  const table = document.querySelector("[data-products-table]");
  const empty = document.querySelector("[data-products-empty]");
  if (!tbody || !table || !empty) return;

  clearChildren(tbody);
  products.forEach((product) => tbody.append(productRow(product)));

  const hasRows = products.length > 0;
  table.hidden = !hasRows;
  empty.hidden = hasRows;
  setLoading(false);
  renderResults(pagination, products.length);
  renderPagination(pagination);
}

function productRow(product) {
  const row = document.createElement("tr");
  row.append(
    productCell(product),
    textCell(brandNames.get(Number(product.brand_id)) || product.brand_id || "-"),
    textCell(categoryNames.get(Number(product.category_id)) || product.category_id || "-"),
    textCell(formatCurrency(product.price)),
    badgeCell(statusLabel(product.status), statusBadge(product.status)),
    textCell(formatDate(product.updated_at)),
    actionsCell(product)
  );
  return row;
}

function productCell(product) {
  const cell = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "admin-product-cell";
  const thumb = document.createElement(productImage(product) ? "img" : "span");
  thumb.className = "admin-product-thumb";
  if (thumb.tagName === "IMG") {
    thumb.src = productImage(product);
    thumb.alt = "";
  } else {
    thumb.textContent = initials(product.name);
    thumb.setAttribute("aria-hidden", "true");
  }
  const text = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = product.name || "Produto sem nome";
  const slug = document.createElement("small");
  slug.textContent = product.slug || product.sku || `ID ${product.id}`;
  text.append(name, slug);
  wrap.append(thumb, text);
  cell.append(wrap);
  return cell;
}

function actionsCell(product) {
  const cell = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "admin-row-actions";
  actions.append(actionLink("Editar", `/admin/produtos/editar/?id=${product.id}`));

  const publish = document.createElement("button");
  publish.className = "admin-button admin-button--ghost";
  publish.type = "button";
  publish.textContent = product.status === "published" ? "Despublicar" : "Publicar";
  publish.addEventListener("click", () => togglePublish(product, publish));
  actions.append(publish);

  const remove = document.createElement("button");
  remove.className = "admin-button admin-button--danger";
  remove.type = "button";
  remove.textContent = "Excluir";
  remove.addEventListener("click", () => confirmDeleteProduct(product));
  actions.append(remove);

  cell.append(actions);
  return cell;
}

async function togglePublish(product, button) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    if (product.status === "published") {
      await unpublishProduct(product.id);
      notify("Produto despublicado.", "success");
    } else {
      await publishProduct(product.id);
      notify("Produto publicado.", "success");
    }
    await renderProductsPage();
  } catch (error) {
    notify(errorMessage(error, "Nao foi possivel atualizar o produto."), "error");
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function confirmDeleteProduct(product) {
  const form = document.createElement("form");
  form.className = "admin-form";
  form.innerHTML = `
    <p class="admin-help">Para excluir, digite o nome do produto exatamente como aparece abaixo.</p>
    <strong>${escapeHtml(product.name || "Produto sem nome")}</strong>
    <label class="admin-field" for="product-delete-confirm"><span>Nome do produto</span><input id="product-delete-confirm" type="text" required autocomplete="off" /></label>
    <p class="admin-help" data-form-error hidden></p>
  `;

  openModal({
    title: "Excluir produto",
    body: form,
    actions: [
      { label: "Cancelar", className: "admin-button admin-button--ghost", onClick: closeModal },
      { label: "Excluir", className: "admin-button admin-button--danger", onClick: () => form.requestSubmit() }
    ]
  });

  form.querySelector("input")?.focus();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = form.querySelector("input");
    const error = form.querySelector("[data-form-error]");
    if (input.value.trim() !== (product.name || "").trim()) {
      showFormError(error, "Digite o nome do produto para confirmar.");
      return;
    }
    await deleteConfirmedProduct(product, form);
  });
}

async function deleteConfirmedProduct(product, form) {
  const submit = document.querySelector(".admin-modal__foot .admin-button--danger");
  submit.disabled = true;
  submit.setAttribute("aria-busy", "true");
  try {
    await deleteProduct(product.id);
    closeModal();
    notify("Produto excluido.", "success");
    await renderProductsPage();
  } catch (error) {
    showFormError(form.querySelector("[data-form-error]"), errorMessage(error, "Nao foi possivel excluir o produto."));
  } finally {
    submit.disabled = false;
    submit.removeAttribute("aria-busy");
  }
}

function renderError(error) {
  setLoading(false);
  setError(true);
  const table = document.querySelector("[data-products-table]");
  const empty = document.querySelector("[data-products-empty]");
  const results = document.querySelector("[data-product-results]");
  if (table) table.hidden = true;
  if (empty) empty.hidden = true;
  if (results) results.textContent = errorMessage(error, "Erro ao carregar produtos.");
}

function setLoading(isLoading) {
  document.querySelector("[data-products-loading]").hidden = !isLoading;
}

function setError(isError) {
  document.querySelector("[data-products-error]").hidden = !isError;
}

function renderResults(pagination, visibleCount) {
  const total = pagination.total ?? visibleCount;
  document.querySelector("[data-product-results]").textContent = `${total} ${total === 1 ? "resultado" : "resultados"}`;
}

function renderPagination(pagination) {
  const wrapper = document.querySelector("[data-products-pagination]");
  const prev = document.querySelector("[data-products-prev]");
  const next = document.querySelector("[data-products-next]");
  const label = document.querySelector("[data-products-page]");
  const pages = pagination.pages ?? 0;
  wrapper.hidden = pages <= 1;
  prev.disabled = (pagination.page ?? state.page) <= 1;
  next.disabled = (pagination.page ?? state.page) >= pages;
  label.textContent = `Pagina ${pagination.page ?? state.page} de ${Math.max(pages, 1)}`;
}

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = String(value || "-");
  return cell;
}

function badgeCell(label, modifier) {
  const cell = document.createElement("td");
  cell.append(createBadge(label, modifier));
  return cell;
}

function actionLink(label, href) {
  const link = document.createElement("a");
  link.className = "admin-button admin-button--ghost";
  link.href = href;
  link.textContent = label;
  return link;
}

function productImage(product) {
  const primary = product.images?.find((image) => image.is_primary) || product.images?.[0];
  return primary?.public_url || "";
}

function statusLabel(status) {
  return { published: "Publicado", draft: "Rascunho", archived: "Arquivado" }[status] || status || "Sem status";
}

function statusBadge(status) {
  return { published: "admin-badge--ok", draft: "admin-badge--warn", archived: "admin-badge--off" }[status] || "admin-badge--info";
}

function formatCurrency(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(amount);
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function initials(value) {
  return String(value || "DZ").trim().slice(0, 2).toUpperCase();
}

function errorMessage(error, fallback) {
  if (error?.status === 403) return "Falha de autorizacao ou CSRF. Recarregue a pagina e tente novamente.";
  if (error?.status === 409) return "Este registro possui vinculos ou dados conflitantes.";
  if (error?.code === "PRODUCT_NOT_READY_FOR_PUBLICATION" && Array.isArray(error?.details?.blockers)) {
    return `Nao foi possivel publicar:\n${error.details.blockers.map((blocker) => `- ${blocker.message}`).join("\n")}`;
  }
  if (error?.status === 422) return error.message || "Revise os campos informados.";
  if (error?.status >= 500) return "Erro interno do servidor. Tente novamente em instantes.";
  if (error?.status === 0) return "API temporariamente indisponivel.";
  return error?.message || fallback;
}

function showFormError(element, message) {
  element.hidden = false;
  element.textContent = message;
  notify(message, "error");
}

function escapeHtml(value) {
  const span = document.createElement("span");
  span.textContent = value;
  return span.innerHTML;
}
