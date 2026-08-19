import { createResource, deleteResource, getBrands, getCategories, getCollections, updateResource } from "./api.js?v=api-base-3000-20260730";
import { clearChildren, createBadge, initAdminPage } from "./admin.js?v=api-base-3000-20260730";
import { closeModal, notify, openModal } from "./notifications.js?v=api-base-3000-20260730";

const pageSize = 20;
const resourceType = document.body.dataset.resourceType || "brands";
const settings = {
  brands: {
    title: "Marcas",
    breadcrumb: "Admin / Marcas",
    description: "Organize os produtos pelas marcas disponiveis na loja.",
    singular: "Marca",
    article: "a marca",
    empty: "Nenhuma marca cadastrada.",
    load: getBrands
  },
  categories: {
    title: "Categorias",
    breadcrumb: "Admin / Categorias",
    description: "Agrupe produtos por tipo e facilite a navegacao da loja.",
    singular: "Categoria",
    article: "a categoria",
    empty: "Nenhuma categoria cadastrada.",
    load: getCategories
  },
  collections: {
    title: "Colecoes",
    breadcrumb: "Admin / Colecoes",
    description: "Crie agrupamentos editoriais e comerciais de produtos.",
    singular: "Colecao",
    article: "a colecao",
    empty: "Nenhuma colecao cadastrada.",
    load: getCollections
  }
}[resourceType];

let allItems = [];
let filteredItems = [];
let page = 1;
let searchTimer;

await initAdminPage({
  title: settings.title,
  breadcrumb: settings.breadcrumb,
  description: settings.description
});

bindResourceActions();
renderResources();

function bindResourceActions() {
  document.querySelector("[data-create-resource]")?.addEventListener("click", () => openResourceModal());
  document.querySelector("[data-retry-resources]")?.addEventListener("click", renderResources);
  document.querySelector("[data-resource-prev]")?.addEventListener("click", () => changePage(page - 1));
  document.querySelector("[data-resource-next]")?.addEventListener("click", () => changePage(page + 1));
  document.querySelector("[data-clear-resource-filters]")?.addEventListener("click", clearFilters);
  document.querySelector("[data-resource-search]")?.addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      page = 1;
      applyFilters(event.target.value, document.querySelector("[data-resource-status]")?.value || "");
    }, 300);
  });
  document.querySelector("[data-resource-status]")?.addEventListener("change", (event) => {
    page = 1;
    applyFilters(document.querySelector("[data-resource-search]")?.value || "", event.target.value);
  });
}

async function renderResources() {
  setLoading(true);
  setError(false);
  try {
    allItems = await settings.load();
    page = 1;
    applyFilters(document.querySelector("[data-resource-search]")?.value || "", document.querySelector("[data-resource-status]")?.value || "");
  } catch (error) {
    setLoading(false);
    setError(true, error);
  }
}

function applyFilters(termValue, statusValue) {
  const term = termValue.trim().toLowerCase();
  filteredItems = allItems.filter((item) => {
    const matchesText = !term || [item.name, item.slug, item.description].filter(Boolean).some((value) => String(value).toLowerCase().includes(term));
    const matchesStatus = !statusValue || (statusValue === "active" ? item.is_active !== false : item.is_active === false);
    return matchesText && matchesStatus;
  });
  renderCurrentPage();
}

function renderCurrentPage() {
  const tbody = document.querySelector("[data-resource-tbody]");
  const table = document.querySelector("[data-resource-table]");
  const empty = document.querySelector("[data-resource-empty]");
  if (!tbody || !table || !empty) return;

  const start = (page - 1) * pageSize;
  const items = filteredItems.slice(start, start + pageSize);
  clearChildren(tbody);
  items.forEach((item) => tbody.append(resourceRow(item)));

  const hasRows = items.length > 0;
  table.hidden = !hasRows;
  empty.hidden = hasRows;
  empty.querySelector("h2").textContent = settings.empty;
  setLoading(false);
  setError(false);
  renderResults();
  renderPagination();
}

function resourceRow(item) {
  const row = document.createElement("tr");
  row.append(nameCell(item), textCell(item.slug || "-"), badgeCell(item.is_active === false ? "Inativo" : "Ativo", item.is_active === false ? "admin-badge--off" : "admin-badge--ok"), textCell(item.position ?? 0));
  if (resourceType === "collections") row.append(textCell(formatDate(item.updated_at)));
  row.append(actionsCell(item));
  return row;
}

function nameCell(item) {
  const cell = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "admin-resource-cell";
  const name = document.createElement("strong");
  name.textContent = item.name || "Sem nome";
  const description = document.createElement("small");
  description.textContent = item.description || `ID ${item.id}`;
  wrap.append(name, description);
  cell.append(wrap);
  return cell;
}

function actionsCell(item) {
  const cell = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "admin-row-actions";

  const edit = document.createElement("button");
  edit.className = "admin-button admin-button--ghost";
  edit.type = "button";
  edit.textContent = "Editar";
  edit.addEventListener("click", () => openResourceModal(item));

  const remove = document.createElement("button");
  remove.className = "admin-button admin-button--danger";
  remove.type = "button";
  remove.textContent = "Excluir";
  remove.addEventListener("click", () => confirmDeleteResource(item));

  actions.append(edit, remove);
  cell.append(actions);
  return cell;
}

function openResourceModal(item = null) {
  const isEditing = Boolean(item);
  const form = document.createElement("form");
  form.className = "admin-form";
  form.noValidate = true;
  form.innerHTML = `
    <p class="admin-help">${isEditing ? "Atualize os campos reais deste registro." : "Preencha os campos principais para cadastrar o registro."}</p>
    <div class="admin-field">
      <label for="resource-name">Nome de ${settings.article}</label>
      <input id="resource-name" name="name" type="text" maxlength="120" required autocomplete="off" value="${escapeHtml(item?.name || "")}" />
      <small>Campo obrigatorio usado no painel e na loja.</small>
    </div>
    <div class="admin-field">
      <label for="resource-slug">Slug</label>
      <input id="resource-slug" name="slug" type="text" maxlength="160" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="gerado automaticamente se ficar vazio" value="${escapeHtml(item?.slug || "")}" />
      <small>Use letras minusculas, numeros e hifens.</small>
    </div>
    <div class="admin-field">
      <label for="resource-description">Descricao</label>
      <textarea id="resource-description" name="description" maxlength="2000" rows="4">${escapeHtml(item?.description || "")}</textarea>
    </div>
    <div class="admin-form-grid">
      <label class="admin-field" for="resource-position"><span>Ordem</span><input id="resource-position" name="position" type="number" min="0" step="1" value="${Number(item?.position ?? 0)}" /></label>
      <label class="admin-check"><input name="is_active" type="checkbox" ${item?.is_active === false ? "" : "checked"} /> ${settings.singular} ativa</label>
    </div>
    <p class="admin-help" data-form-error hidden></p>
  `;

  openModal({
    title: isEditing ? `Editar ${settings.singular.toLowerCase()}` : `Nova ${settings.singular.toLowerCase()}`,
    body: form,
    actions: [
      { label: "Cancelar", className: "admin-button admin-button--ghost", onClick: closeModal },
      { label: isEditing ? "Salvar alteracoes" : `Salvar ${settings.singular.toLowerCase()}`, className: "admin-button admin-button--primary", onClick: () => form.requestSubmit() }
    ]
  });

  form.querySelector("#resource-name")?.focus();
  form.addEventListener("submit", (event) => handleResourceSubmit(event, item));
}

async function handleResourceSubmit(event, item) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = document.querySelector(".admin-modal__foot .admin-button--primary");
  const error = form.querySelector("[data-form-error]");

  if (!form.checkValidity()) {
    form.reportValidity();
    showFormError(error, "Preencha os campos obrigatorios corretamente.");
    return;
  }

  const payload = resourcePayload(form);
  if (!payload.name) {
    showFormError(error, `Preencha o nome de ${settings.article}.`);
    return;
  }

  submit.disabled = true;
  submit.setAttribute("aria-busy", "true");
  try {
    if (item) await updateResource(resourceType, item.id, payload);
    else await createResource(resourceType, payload);
    closeModal();
    notify(item ? `${settings.singular} atualizada com sucesso.` : `${settings.singular} criada com sucesso.`, "success");
    await renderResources();
  } catch (errorCaught) {
    showFormError(error, errorMessage(errorCaught, `Nao foi possivel salvar ${settings.article}.`));
  } finally {
    submit.disabled = false;
    submit.removeAttribute("aria-busy");
  }
}

function confirmDeleteResource(item) {
  const form = document.createElement("form");
  form.className = "admin-form";
  form.innerHTML = `
    <p class="admin-help">Para excluir, digite o nome exatamente como aparece abaixo. Registros vinculados a produtos nao serao apagados.</p>
    <strong>${escapeHtml(item.name || "Sem nome")}</strong>
    <label class="admin-field" for="resource-delete-confirm"><span>Nome de ${settings.article}</span><input id="resource-delete-confirm" type="text" required autocomplete="off" /></label>
    <p class="admin-help" data-form-error hidden></p>
  `;

  openModal({
    title: `Excluir ${settings.singular.toLowerCase()}`,
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
    if (input.value.trim() !== (item.name || "").trim()) {
      showFormError(error, `Digite o nome de ${settings.article} para confirmar.`);
      return;
    }
    await deleteConfirmedResource(item, form);
  });
}

async function deleteConfirmedResource(item, form) {
  const submit = document.querySelector(".admin-modal__foot .admin-button--danger");
  submit.disabled = true;
  submit.setAttribute("aria-busy", "true");
  try {
    await deleteResource(resourceType, item.id);
    closeModal();
    notify(`${settings.singular} excluida com sucesso.`, "success");
    await renderResources();
  } catch (errorCaught) {
    showFormError(form.querySelector("[data-form-error]"), errorMessage(errorCaught, `Nao foi possivel excluir ${settings.article}.`));
  } finally {
    submit.disabled = false;
    submit.removeAttribute("aria-busy");
  }
}

function resourcePayload(form) {
  const data = new FormData(form);
  const payload = {
    name: String(data.get("name") || "").trim(),
    slug: String(data.get("slug") || "").trim() || null,
    description: String(data.get("description") || "").trim() || null,
    is_active: data.get("is_active") === "on",
    position: Number(data.get("position") || 0)
  };
  if (resourceType === "brands") payload.logo_path = null;
  return payload;
}

function clearFilters() {
  document.querySelector("[data-resource-search]").value = "";
  document.querySelector("[data-resource-status]").value = "";
  page = 1;
  applyFilters("", "");
}

function changePage(nextPage) {
  const pages = Math.max(Math.ceil(filteredItems.length / pageSize), 1);
  if (nextPage < 1 || nextPage > pages) return;
  page = nextPage;
  renderCurrentPage();
}

function renderResults() {
  const total = filteredItems.length;
  document.querySelector("[data-resource-results]").textContent = `${total} ${total === 1 ? "resultado" : "resultados"}`;
}

function renderPagination() {
  const pages = Math.max(Math.ceil(filteredItems.length / pageSize), 1);
  const wrapper = document.querySelector("[data-resource-pagination]");
  wrapper.hidden = pages <= 1;
  document.querySelector("[data-resource-prev]").disabled = page <= 1;
  document.querySelector("[data-resource-next]").disabled = page >= pages;
  document.querySelector("[data-resource-page]").textContent = `Pagina ${page} de ${pages}`;
}

function setLoading(isLoading) {
  document.querySelector("[data-resource-loading]").hidden = !isLoading;
}

function setError(isError, error = null) {
  const errorBox = document.querySelector("[data-resource-error]");
  const table = document.querySelector("[data-resource-table]");
  const empty = document.querySelector("[data-resource-empty]");
  errorBox.hidden = !isError;
  if (isError) {
    table.hidden = true;
    empty.hidden = true;
    document.querySelector("[data-resource-results]").textContent = errorMessage(error, "Erro ao carregar registros.");
  }
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

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function errorMessage(error, fallback) {
  if (error?.status === 403) return "Falha de autorizacao ou CSRF. Recarregue a pagina e tente novamente.";
  if (error?.status === 409) return "Registro em uso por produtos ou com dados conflitantes.";
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
