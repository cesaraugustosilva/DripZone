import { clearChildren, createBadge } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { formatDate } from "./import-center.js?v=api-base-3000-20260730";
import { flowState, navigateToStep, setCurrentImport, STEPS } from "./import-flow.js?v=api-base-3000-20260730";
import { canApprove, canUnapprove, confidence, filterParams, itemStatusBadge, itemStatusLabel, normalizeItemError, qualityFromImport, readinessText } from "./import-readiness.js?v=api-base-3000-20260730";
import { openItemEditor } from "./import-item-editor.js?v=api-base-3000-20260730";
import { openPublishConfirm } from "./import-publish.js?v=api-base-3000-20260730";
import { createImportProductPreview, openImportImagePreview } from "./import-preview.js?v=api-base-3000-20260730";

const pageSize = 20;

let reviewDeps;
let reviewPage = 1;
let reviewFilter = "all";
let selected = new Set();
let currentItems = [];
let busyIds = new Set();

export function initImportReview(deps) {
  reviewDeps = deps;
  document.querySelector("[data-review-filter]")?.addEventListener("change", (event) => {
    reviewFilter = event.target.value;
    reviewPage = 1;
    selected.clear();
    renderImportReview();
  });
  document.querySelector("[data-review-refresh]")?.addEventListener("click", renderImportReview);
  document.querySelector("[data-review-prev]")?.addEventListener("click", () => {
    reviewPage = Math.max(reviewPage - 1, 1);
    renderImportReview();
  });
  document.querySelector("[data-review-next-page]")?.addEventListener("click", () => {
    reviewPage += 1;
    renderImportReview();
  });
  document.querySelector("[data-review-select-page]")?.addEventListener("change", (event) => {
    if (event.target.checked) currentItems.forEach((item) => selected.add(item.id));
    else currentItems.forEach((item) => selected.delete(item.id));
    renderSelection();
  });
  document.querySelector("[data-review-approve-selected]")?.addEventListener("click", approveSelected);
  document.querySelector("[data-review-publish-selected]")?.addEventListener("click", publishSelected);
  document.querySelector("[data-review-body]")?.addEventListener("click", handleTableAction);
}

export async function renderImportReview() {
  if (!flowState.currentImportId) return;
  const loading = document.querySelector("[data-review-loading]");
  const table = document.querySelector("[data-review-table]");
  const empty = document.querySelector("[data-review-empty]");
  const error = document.querySelector("[data-review-error]");
  loading.hidden = false;
  table.hidden = true;
  empty.hidden = true;
  error.hidden = true;
  try {
    const [record, data] = await Promise.all([
      reviewDeps.getImportById(flowState.currentImportId),
      reviewDeps.getImportItems(flowState.currentImportId, { page: reviewPage, page_size: pageSize, ...filterParams(reviewFilter) })
    ]);
    setCurrentImport(record);
    renderQuality(record);
    currentItems = normalizeFilteredItems(data.items || []);
    renderRows(currentItems);
    renderPagination(data.pagination || {});
    renderSelection();
    loading.hidden = true;
    table.hidden = !currentItems.length;
    empty.hidden = Boolean(currentItems.length);
    resolveReviewStep(record);
  } catch (caught) {
    loading.hidden = true;
    error.hidden = false;
    error.querySelector("h2").textContent = normalizeItemError(caught);
    reviewDeps.notify(normalizeItemError(caught), "error");
  }
}

function resolveReviewStep(record) {
  if (record.items_published > 0 || record.items_publish_failed > 0) navigateToStep(STEPS.FINISHED);
  else if (record.items_approved > 0) navigateToStep(STEPS.READY_TO_PUBLISH);
}

function renderQuality(record) {
  const quality = qualityFromImport(record);
  const items = [
    ["Produtos encontrados", quality.total],
    ["Prontos", quality.ready],
    ["Precisam de atencao", quality.attention],
    ["Invalidos", quality.invalid],
    ["Aprovados", quality.approved],
    ["Nao aprovados", quality.notApproved],
    ["Publicados", quality.published],
    ["Falhas", quality.failed]
  ];
  const container = document.querySelector("[data-review-quality]");
  clearChildren(container);
  items.forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "admin-card admin-metric";
    card.innerHTML = "<span></span><strong></strong>";
    card.querySelector("span").textContent = label;
    card.querySelector("strong").textContent = String(value);
    container.append(card);
  });
  document.querySelector("[data-review-updated]").textContent = `Atualizado em ${formatDate(record.updated_at)}`;
}

function renderRows(items) {
  const body = document.querySelector("[data-review-body]");
  clearChildren(body);
  items.forEach((item) => body.append(reviewRow(item)));
}

function normalizeFilteredItems(items) {
  const note = document.querySelector("[data-review-filter-note]");
  note.textContent = "";
  if (reviewFilter !== "not_approved") return items;
  note.textContent = "Filtro local somente nesta pagina carregada.";
  return items.filter((item) => !["approved", "published"].includes(item.status));
}

function reviewRow(item) {
  const row = document.createElement("tr");
  row.dataset.itemId = String(item.id);
  row.append(
    selectCell(item),
    imageCell(item),
    titleCell(item),
    textCell(item.brand?.name || flowState.currentImport?.brand?.name || "-", "Marca"),
    textCell(item.suggested_category || "-", "Categoria"),
    textCell("Nao fornecido", "Preco"),
    badgeCell(itemStatusLabel(item.status), itemStatusBadge(item.status)),
    notesCell(item),
    textCell(confidence(item.overall_confidence || item.confidence), "Confianca"),
    actionsCell(item)
  );
  return row;
}

function selectCell(item) {
  const cell = document.createElement("td");
  cell.dataset.label = "Selecao";
  const label = document.createElement("label");
  label.className = "admin-check admin-check--compact";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = selected.has(item.id);
  input.addEventListener("change", () => {
    if (input.checked) selected.add(item.id);
    else selected.delete(item.id);
    renderSelection();
  });
  const span = document.createElement("span");
  span.className = "sr-only";
  span.textContent = `Selecionar item ${item.suggested_name || item.id}`;
  label.append(input, span);
  cell.append(label);
  return cell;
}

function imageCell(item) {
  const cell = document.createElement("td");
  cell.dataset.label = "Imagem";
  cell.append(createImportProductPreview(item, {
    onOpen: (target, trigger) => openImportImagePreview(target, trigger, {
      onManageImages: (managedItem, modalTrigger) => openItemEditor(managedItem, modalTrigger)
    })
  }));
  return cell;
}

function titleCell(item) {
  const cell = document.createElement("td");
  cell.dataset.label = "Produto";
  const wrap = document.createElement("div");
  wrap.className = "admin-resource-cell";
  const title = document.createElement("strong");
  title.textContent = item.suggested_name || item.source_title || `Item #${item.id}`;
  const small = document.createElement("small");
  small.textContent = item.source_url || "-";
  wrap.append(title, small);
  cell.append(wrap);
  return cell;
}

function notesCell(item) {
  const cell = document.createElement("td");
  cell.dataset.label = "Avisos";
  const notes = [...(item.warnings || [])];
  if (item.duplicate_reason) notes.push(item.duplicate_reason);
  cell.textContent = notes.length ? notes.slice(0, 2).join(", ") : "-";
  return cell;
}

function actionsCell(item) {
  const cell = document.createElement("td");
  cell.dataset.label = "Acoes";
  const wrap = document.createElement("div");
  wrap.className = "admin-row-actions";
  wrap.append(action("Editar", "edit", item));
  wrap.append(action("Aprovar", "approve", item, item.status !== "reviewed"));
  wrap.append(action("Desaprovar", "unapprove", item, !canUnapprove(item)));
  wrap.append(action("Publicar", "publish", item, item.status !== "approved"));
  cell.append(wrap);
  return cell;
}

function action(label, actionName, item, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "admin-button admin-button--ghost";
  button.dataset.reviewAction = actionName;
  button.dataset.itemId = String(item.id);
  button.textContent = label;
  button.disabled = disabled || busyIds.has(item.id);
  return button;
}

async function handleTableAction(event) {
  const button = event.target.closest("[data-review-action]");
  if (!button) return;
  const item = currentItems.find((entry) => entry.id === Number(button.dataset.itemId));
  if (!item) return;
  if (button.dataset.reviewAction === "edit") await openItemEditor(item, button);
  if (button.dataset.reviewAction === "approve") await approveItem(item);
  if (button.dataset.reviewAction === "unapprove") await unapproveItem(item);
  if (button.dataset.reviewAction === "publish") await openPublishConfirm([item]);
}

async function approveItem(item) {
  await runItemAction(item, async (fresh) => {
    const readiness = await reviewDeps.getImportPublicationReadiness(fresh.import_record_id, fresh.id);
    if (!canApprove(fresh, readiness)) {
      reviewDeps.notify(`Aprovacao bloqueada: ${(readiness.blockers || []).map(readinessText).join(", ") || "item nao revisado"}`, "warning");
      return;
    }
    await reviewDeps.approveImportItem(fresh.import_record_id, fresh.id, { updated_at: fresh.updated_at });
    reviewDeps.notify("Item aprovado.", "success");
  });
}

async function unapproveItem(item) {
  await runItemAction(item, async (fresh) => {
    await reviewDeps.unapproveImportItem(fresh.import_record_id, fresh.id, { updated_at: fresh.updated_at });
    reviewDeps.notify("Aprovacao removida.", "success");
  });
}

async function approveSelected() {
  const targets = currentItems.filter((item) => selected.has(item.id) && item.status === "reviewed");
  const result = { ok: 0, skipped: selected.size - targets.length, failed: 0 };
  for (const item of targets) {
    try {
      await approveItem(item);
      result.ok += 1;
    } catch {
      result.failed += 1;
    }
  }
  reviewDeps.notify(`${result.ok} aprovados, ${result.skipped} ignorados, ${result.failed} falharam.`, result.failed ? "warning" : "success");
  selected.clear();
  await renderImportReview();
}

async function publishSelected() {
  const targets = currentItems.filter((item) => selected.has(item.id) && item.status === "approved");
  await openPublishConfirm(targets);
}

async function runItemAction(item, actionCallback) {
  busyIds.add(item.id);
  renderRows(currentItems);
  try {
    const fresh = await reviewDeps.getImportItem(item.import_record_id, item.id);
    await actionCallback(fresh);
    await renderImportReview();
  } catch (caught) {
    reviewDeps.notify(normalizeItemError(caught), "error");
    throw caught;
  } finally {
    busyIds.delete(item.id);
  }
}

function renderSelection() {
  const count = currentItems.filter((item) => selected.has(item.id)).length;
  document.querySelector("[data-review-selection-count]").textContent = `${count} selecionado${count === 1 ? "" : "s"} nesta pagina`;
  document.querySelector("[data-review-approve-selected]").disabled = !currentItems.some((item) => selected.has(item.id) && item.status === "reviewed");
  document.querySelector("[data-review-publish-selected]").disabled = !currentItems.some((item) => selected.has(item.id) && item.status === "approved");
  const checkbox = document.querySelector("[data-review-select-page]");
  checkbox.checked = Boolean(currentItems.length) && currentItems.every((item) => selected.has(item.id));
  checkbox.indeterminate = currentItems.some((item) => selected.has(item.id)) && !checkbox.checked;
}

function renderPagination(pagination) {
  const pages = pagination.pages || 0;
  document.querySelector("[data-review-pagination]").hidden = pages <= 1;
  document.querySelector("[data-review-prev]").disabled = (pagination.page || reviewPage) <= 1;
  document.querySelector("[data-review-next-page]").disabled = (pagination.page || reviewPage) >= pages;
  document.querySelector("[data-review-page]").textContent = `Pagina ${pagination.page || reviewPage} de ${Math.max(pages, 1)}`;
}

export async function onReviewItemSaved() {
  await renderImportReview();
}

export async function onPublishFinished(result) {
  const created = result.created.length;
  const skipped = result.skipped.length;
  const failed = result.failed.length;
  reviewDeps.notify(`${created} produto(s) criado(s), ${skipped} ignorado(s), ${failed} falha(s).`, failed ? "warning" : "success");
  renderPublishResult(result);
  selected.clear();
  await renderImportReview();
}

function renderPublishResult(result) {
  const panel = document.querySelector("[data-publish-result]");
  panel.hidden = false;
  panel.querySelector("[data-publish-created]").textContent = String(result.created.length);
  panel.querySelector("[data-publish-skipped]").textContent = String(result.skipped.length);
  panel.querySelector("[data-publish-failed]").textContent = String(result.failed.length);
  const list = panel.querySelector("[data-publish-result-list]");
  clearChildren(list);
  [...result.created, ...result.skipped].forEach((entry) => {
    const li = document.createElement("li");
    const productId = entry.product_id;
    li.innerHTML = `<span></span>${productId ? ` <a class="admin-button admin-button--ghost" href="/admin/produtos/?product_id=${productId}">Abrir produto</a>` : ""}`;
    li.querySelector("span").textContent = entry.message || `Produto #${productId}`;
    list.append(li);
  });
  result.failed.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = `${entry.item.suggested_name || entry.item.id}: ${entry.error}`;
    list.append(li);
  });
}

function textCell(value, label = "") {
  const cell = document.createElement("td");
  if (label) cell.dataset.label = label;
  cell.textContent = String(value ?? "-");
  return cell;
}

function badgeCell(label, modifier) {
  const cell = document.createElement("td");
  cell.dataset.label = "Status";
  cell.append(createBadge(label, modifier));
  return cell;
}
