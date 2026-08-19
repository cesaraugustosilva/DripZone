import { actionForImport } from "./import-flow.js?v=api-base-3000-20260730";
import { createBadge } from "/admin/js/admin.js?v=api-base-3000-20260730";

const pageSize = 20;

let centerPage = 1;
let centerStatus = "";

export function initImportCenter({ getImports, openImport, startNewImport, notify }) {
  const elements = getCenterElements();
  document.querySelectorAll("[data-new-import]").forEach((button) => button.addEventListener("click", startNewImport));
  elements.refresh?.addEventListener("click", () => loadImportCenter({ getImports, openImport, notify }));
  elements.status?.addEventListener("change", () => {
    centerStatus = elements.status.value;
    centerPage = 1;
    loadImportCenter({ getImports, openImport, notify });
  });
  elements.prev?.addEventListener("click", () => {
    centerPage = Math.max(centerPage - 1, 1);
    loadImportCenter({ getImports, openImport, notify });
  });
  elements.next?.addEventListener("click", () => {
    centerPage += 1;
    loadImportCenter({ getImports, openImport, notify });
  });
  elements.body?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-resume-import]");
    if (button) openImport(Number(button.dataset.resumeImport));
  });
}

export async function loadImportCenter({ getImports, openImport, notify }) {
  const elements = getCenterElements();
  setLoading(elements, true);
  try {
    const data = await getImports(queryParams());
    renderHistory(data, openImport);
    renderSummary(data.items || []);
    setLoading(elements, false);
  } catch (error) {
    setLoading(elements, false);
    elements.error.hidden = false;
    elements.results.textContent = "Erro ao carregar importacoes.";
    notify?.(friendlyImportError(error, "Nao foi possivel carregar o historico."), "error");
  }
}

function queryParams() {
  const params = { page: centerPage, page_size: pageSize };
  if (centerStatus) params.status = centerStatus;
  return params;
}

function renderHistory(data) {
  const elements = getCenterElements();
  const items = data.items || [];
  const pagination = data.pagination || {};
  elements.body.innerHTML = "";

  if (!items.length) {
    elements.history.hidden = true;
    elements.empty.hidden = false;
  } else {
    elements.history.hidden = false;
    elements.empty.hidden = true;
    items.forEach((item) => elements.body.append(historyRow(item)));
  }

  elements.results.textContent = `${pagination.total ?? items.length} ${Number(pagination.total ?? items.length) === 1 ? "importacao" : "importacoes"}`;
  renderPagination(elements, pagination);
}

function historyRow(item) {
  const row = document.createElement("tr");
  row.append(
    textCell(`#${item.id}`),
    sourceCell(item),
    textCell(item.brand?.name || "-"),
    textCell(item.items_found || 0),
    badgeCell(statusLabel(item.status), statusBadge(item.status)),
    textCell(formatDate(item.created_at)),
    textCell(formatDate(item.updated_at)),
    actionCell(item)
  );
  return row;
}

function sourceCell(item) {
  const cell = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "admin-resource-cell";
  const title = document.createElement("strong");
  title.textContent = item.folder_name || item.source_type || "Yupoo";
  const url = document.createElement("small");
  url.textContent = item.normalized_source_url || item.source_url || "-";
  wrap.append(title, url);
  cell.append(wrap);
  return cell;
}

function actionCell(item) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  button.className = "admin-button admin-button--ghost";
  button.type = "button";
  button.dataset.resumeImport = String(item.id);
  button.textContent = actionForImport(item);
  cell.append(button);
  return cell;
}

function renderSummary(items) {
  const total = items.length;
  const review = items.reduce((sum, item) => sum + Number(item.items_pending || item.items_needs_review || 0), 0);
  const ready = items.filter((item) => item.status === "preview_ready" || item.status === "scanning").length;
  const failed = items.filter((item) => item.status === "failed").length;
  setText("[data-summary-total]", total);
  setText("[data-summary-review]", review);
  setText("[data-summary-ready]", ready);
  setText("[data-summary-failed]", failed);
}

function renderPagination(elements, pagination) {
  const pages = pagination.pages || 0;
  elements.pagination.hidden = pages <= 1;
  elements.prev.disabled = (pagination.page || centerPage) <= 1;
  elements.next.disabled = (pagination.page || centerPage) >= pages;
  elements.pageLabel.textContent = `Pagina ${pagination.page || centerPage} de ${Math.max(pages, 1)}`;
}

function setLoading(elements, loading) {
  elements.loading.hidden = !loading;
  if (loading) {
    elements.history.hidden = true;
    elements.empty.hidden = true;
    elements.error.hidden = true;
  }
}

function getCenterElements() {
  return {
    status: document.querySelector("[data-import-status-filter]"),
    refresh: document.querySelector("[data-refresh-imports]"),
    history: document.querySelector("[data-import-history]"),
    body: document.querySelector("[data-import-history-body]"),
    loading: document.querySelector("[data-import-history-loading]"),
    empty: document.querySelector("[data-import-history-empty]"),
    error: document.querySelector("[data-import-history-error]"),
    results: document.querySelector("[data-import-results]"),
    pagination: document.querySelector("[data-import-pagination]"),
    prev: document.querySelector("[data-import-prev]"),
    next: document.querySelector("[data-import-next]"),
    pageLabel: document.querySelector("[data-import-page]")
  };
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = String(value);
}

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = String(value ?? "-");
  return cell;
}

function badgeCell(label, modifier) {
  const cell = document.createElement("td");
  cell.append(createBadge(label, modifier));
  return cell;
}

export function statusLabel(status) {
  return {
    draft: "Rascunho",
    scanning: "Analisando",
    preview_ready: "Preview pronto",
    failed: "Falha",
    cancelled: "Cancelada"
  }[status] || status || "-";
}

export function statusBadge(status) {
  return {
    draft: "admin-badge--warn",
    scanning: "admin-badge--info",
    preview_ready: "admin-badge--ok",
    failed: "admin-badge--off",
    cancelled: "admin-badge--warn"
  }[status] || "admin-badge--info";
}

export function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

export function friendlyImportError(error, fallback) {
  if (error?.code === "IMPORT_HOST_NOT_ALLOWED") return "Fonte de importacao invalida. Use uma URL Yupoo permitida.";
  if (error?.code === "IMPORT_INVALID_URL") return "Informe uma URL HTTP ou HTTPS valida.";
  if (error?.code === "IMPORT_SOURCE_NOT_FOUND") return "O album ou pasta informado nao foi encontrado.";
  if (error?.code === "IMPORT_BRAND_NOT_FOUND") return "Selecione uma marca cadastrada.";
  if (error?.code === "CSRF_INVALID" || error?.status === 403) return "Falha de autorizacao ou CSRF. Recarregue e tente novamente.";
  if (error?.status === 401) return "Sua sessao expirou. Entre novamente.";
  if (error?.status === 404) return "Importacao nao encontrada.";
  if (error?.status === 409) return error.message || "Existe uma importacao ativa para esta origem.";
  if (error?.status === 422) return error.message || "Revise os campos informados.";
  if (error?.status >= 500) return "Erro interno do servidor. Tente novamente em instantes.";
  if (error?.status === 0) return "API temporariamente indisponivel.";
  return error?.message || fallback;
}
