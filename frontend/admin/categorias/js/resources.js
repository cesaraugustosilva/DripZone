import { ApiError, createResource, getBrands, getCategories, getCollections } from "./api.js?v=api-base-3000-20260730";
import { initAdminPage, clearChildren, createBadge } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { closeModal, notify, openModal } from "/admin/js/notifications.js?v=api-base-3000-20260730";

const resourceType = document.body.dataset.resourceType || "brands";
const meta = {
  brands: ["Marcas", "Admin / Marcas"],
  categories: ["Categorias", "Admin / Categorias"],
  collections: ["Coleções", "Admin / Coleções"]
};

await initAdminPage({ title: meta[resourceType][0], breadcrumb: meta[resourceType][1] });
bindResourceActions();
renderResources();

function bindResourceActions() {
  document.querySelector("[data-create-resource]")?.addEventListener("click", () => {
    openResourceModal();
  });
}

async function renderResources() {
  const list = document.querySelector("[data-resource-list]");
  const empty = document.querySelector("[data-resource-empty]");
  const count = document.querySelector("[data-resource-count]");
  if (!list || !empty) return;

  const items = await loadItems();
  if (count) count.textContent = String(items.length);
  clearChildren(list);
  empty.hidden = items.length > 0;
  list.hidden = items.length === 0;

  items.forEach((item) => {
    const row = document.createElement("li");
    const details = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = item.name || item.title || item.label || item.id || "Sem nome";
    const metaText = document.createElement("p");
    metaText.className = "admin-muted";
    metaText.textContent = [item.id, item.slug, item.description].filter(Boolean).join(" / ") || "Registro real carregado do JSON";
    details.append(name, metaText);

    const actions = document.createElement("div");
    actions.className = "admin-actions";
    actions.append(createBadge(item.is_active === false ? "Inativo" : "Ativo", item.is_active === false ? "admin-badge--off" : "admin-badge--ok"));
    const edit = document.createElement("button");
    edit.className = "admin-button admin-button--ghost";
    edit.type = "button";
    edit.textContent = "Editar";
    edit.addEventListener("click", () => notify(`Edicao de ${resourceLabel().singular.toLowerCase()} ainda nao implementada nesta tela.`, "info"));
    actions.append(edit);
    row.append(details, actions);
    list.append(row);
  });
}

async function loadItems() {
  if (resourceType === "brands") return getBrands().catch(() => []);
  if (resourceType === "categories") return getCategories().catch(() => []);
  return getCollections().catch(() => []);
}

function openResourceModal() {
  const label = resourceLabel();
  const form = document.createElement("form");
  form.className = "admin-form";
  form.noValidate = true;
  form.innerHTML = `
    <div class="admin-field">
      <label for="resource-name">Nome de ${label.article}</label>
      <input id="resource-name" name="name" type="text" maxlength="120" required autocomplete="off" />
    </div>
    <div class="admin-field">
      <label for="resource-slug">Slug</label>
      <input id="resource-slug" name="slug" type="text" maxlength="160" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="gerado automaticamente se ficar vazio" />
      <small>Use letras minusculas, numeros e hifens.</small>
    </div>
    <div class="admin-field">
      <label for="resource-description">Descricao</label>
      <textarea id="resource-description" name="description" maxlength="2000" rows="4"></textarea>
    </div>
    <div class="admin-form-grid">
      <label class="admin-field" for="resource-position"><span>Posicao</span><input id="resource-position" name="position" type="number" min="0" step="1" value="0" /></label>
      <label class="admin-check"><input name="is_active" type="checkbox" checked /> ${label.singular} ativa</label>
    </div>
    <p class="admin-help" data-form-error hidden></p>
  `;

  openModal({
    title: `Nova ${label.singular.toLowerCase()}`,
    body: form,
    actions: [
      { label: "Cancelar", className: "admin-button admin-button--ghost", onClick: closeModal },
      { label: `Salvar ${label.singular.toLowerCase()}`, className: "admin-button admin-button--primary", onClick: () => form.requestSubmit() }
    ]
  });

  form.querySelector("#resource-name")?.focus();
  form.addEventListener("submit", handleResourceSubmit);
}

async function handleResourceSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.querySelector(".admin-modal__foot .admin-button--primary");
  const error = form.querySelector("[data-form-error]");

  if (!form.checkValidity()) {
    form.reportValidity();
    showFormError(error, "Preencha os campos obrigatorios corretamente.");
    return;
  }

  const payload = resourcePayload(form);
  if (!payload.name) {
    showFormError(error, `Preencha o nome de ${resourceLabel().article}.`);
    return;
  }

  submitButton.disabled = true;
  try {
    await createResource(resourceType, payload);
    closeModal();
    notify(`${resourceLabel().singular} criada com sucesso.`, "success");
    await renderResources();
  } catch (caught) {
    showFormError(error, resourceErrorMessage(caught));
  } finally {
    submitButton.disabled = false;
  }
}

function resourcePayload(form) {
  const data = new FormData(form);
  const slug = String(data.get("slug") || "").trim();
  const description = String(data.get("description") || "").trim();
  const payload = {
    name: String(data.get("name") || "").trim(),
    slug: slug || null,
    description: description || null,
    is_active: data.get("is_active") === "on",
    position: Number(data.get("position") || 0)
  };
  if (resourceType === "brands") payload.logo_path = null;
  return payload;
}

function resourceErrorMessage(error) {
  if (!(error instanceof ApiError)) return "Nao foi possivel salvar a marca.";
  if (error.status === 0) return "Nao foi possivel conectar a API.";
  if (error.status === 401) return "Sua sessao expirou. Entre novamente.";
  if (error.status === 403) return "Falha de autorizacao ou CSRF. Recarregue a pagina e tente novamente.";
  if (error.status === 409) return `Ja existe ${resourceLabel().article} com esse nome ou slug.`;
  if (error.status === 422) return error.message || "Preencha os campos obrigatorios corretamente.";
  if (error.status >= 500) return "Erro interno do servidor. Tente novamente em instantes.";
  return error.message || `Nao foi possivel salvar ${resourceLabel().article}.`;
}

function resourceLabel() {
  return {
    brands: { singular: "Marca", article: "a marca" },
    categories: { singular: "Categoria", article: "a categoria" },
    collections: { singular: "Colecao", article: "a colecao" }
  }[resourceType] || { singular: "Registro", article: "o registro" };
}

function showFormError(element, message) {
  if (!element) {
    notify(message, "error");
    return;
  }
  element.hidden = false;
  element.textContent = message;
  notify(message, "error");
}
