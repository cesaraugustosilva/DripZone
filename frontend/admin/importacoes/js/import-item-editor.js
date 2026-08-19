import { updatePayloadFromForm, normalizeItemError } from "./import-readiness.js?v=api-base-3000-20260730";
import { renderImages } from "./import-images.js?v=api-base-3000-20260730";

let editorDeps;
let categories = [];
let activeItem = null;
let returnFocus = null;
let dirty = false;
let saving = false;

export function initImportItemEditor(deps) {
  editorDeps = deps;
  const modal = document.querySelector("[data-import-editor-modal]");
  modal?.addEventListener("click", (event) => {
    if (event.target === modal && !saving && confirmUnsaved()) closeEditor();
  });
  modal?.querySelectorAll("[data-editor-close]")?.forEach((button) => button.addEventListener("click", () => {
    if (!saving && confirmUnsaved()) closeEditor();
  }));
  modal?.querySelector("[data-editor-form]")?.addEventListener("input", () => {
    dirty = true;
  });
  modal?.querySelector("[data-editor-form]")?.addEventListener("submit", saveEditor);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal?.hidden && !saving && confirmUnsaved()) closeEditor();
  });
}

export async function loadEditorResources(getCategories) {
  categories = await getCategories().catch(() => []);
}

export async function openItemEditor(item, trigger) {
  returnFocus = trigger || document.activeElement;
  activeItem = await editorDeps.getImportItem(item.import_record_id, item.id);
  dirty = false;
  renderEditor();
}

function renderEditor() {
  const modal = document.querySelector("[data-import-editor-modal]");
  const form = modal.querySelector("[data-editor-form]");
  const title = modal.querySelector("[data-editor-title]");
  const images = modal.querySelector("[data-editor-images]");
  title.textContent = activeItem.suggested_name || activeItem.source_title || `Item #${activeItem.id}`;
  form.elements.suggested_name.value = activeItem.suggested_name || "";
  form.elements.suggested_category_id.innerHTML = '<option value="">Sem categoria</option>';
  categories.forEach((category) => form.elements.suggested_category_id.append(new Option(category.name, String(category.id))));
  form.elements.suggested_category_id.value = activeItem.suggested_category_id ? String(activeItem.suggested_category_id) : "";
  form.elements.suggested_model.value = activeItem.suggested_model || "";
  form.elements.suggested_color.value = activeItem.suggested_color || "";
  form.elements.status.value = activeItem.status === "approved" ? "reviewed" : activeItem.status;
  form.elements.updated_at.value = activeItem.updated_at || "";
  modal.querySelector("[data-editor-error]").hidden = true;
  renderImages(images, activeItem, {
    setBusy,
    onItemChanged: async () => {
      activeItem = await editorDeps.getImportItem(activeItem.import_record_id, activeItem.id);
      dirty = false;
      renderEditor();
      await editorDeps.onSaved?.(activeItem);
    }
  });
  modal.hidden = false;
  modal.querySelector("[data-editor-close]").focus();
}

async function saveEditor(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.querySelector("[data-editor-error]");
  error.hidden = true;
  const payload = updatePayloadFromForm(form);
  if (payload.suggested_name && /[<>]/.test(payload.suggested_name)) {
    showError("Nome nao aceita HTML.");
    return;
  }
  try {
    setBusy(true);
    const updated = await editorDeps.updateImportItem(activeItem.import_record_id, activeItem.id, payload);
    activeItem = updated;
    dirty = false;
    editorDeps.notify("Item salvo.", "success");
    await editorDeps.onSaved?.(updated);
    closeEditor();
  } catch (caught) {
    showError(normalizeItemError(caught));
  } finally {
    setBusy(false);
  }
}

function showError(message) {
  const error = document.querySelector("[data-editor-error]");
  error.textContent = message;
  error.hidden = false;
  editorDeps.notify(message, "error");
}

function setBusy(value) {
  saving = value;
  document.querySelectorAll("[data-import-editor-modal] button, [data-import-editor-modal] input, [data-import-editor-modal] select").forEach((control) => {
    control.disabled = value;
  });
  const submit = document.querySelector("[data-editor-submit]");
  if (value) submit?.setAttribute("aria-busy", "true");
  else submit?.removeAttribute("aria-busy");
}

function closeEditor() {
  const modal = document.querySelector("[data-import-editor-modal]");
  modal.hidden = true;
  activeItem = null;
  dirty = false;
  returnFocus?.focus?.();
}

function confirmUnsaved() {
  if (!dirty) return true;
  const message = "Existem alteracoes nao salvas neste item. Salve ou descarte antes de fechar.";
  showError(message);
  return false;
}
