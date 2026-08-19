import { flowState, navigateToStep, resetFlow, setCurrentImport, STEPS, stepDefinitions, stepIndex, stepOrder } from "./import-flow.js?v=api-base-3000-20260730";
import { formatDate, friendlyImportError, statusBadge, statusLabel } from "./import-center.js?v=api-base-3000-20260730";
import { clearChildren, createBadge } from "/admin/js/admin.js?v=api-base-3000-20260730";

const allowedDomain = "yupoo.com";

let brandsCache = [];
let wizardDeps;

export function initImportWizard(deps) {
  wizardDeps = deps;
  document.querySelector("[data-import-form]")?.addEventListener("submit", handlePreviewSubmit);
  document.querySelectorAll("[data-exit-wizard]").forEach((button) => button.addEventListener("click", deps.exitWizard));
  document.querySelector("[data-start-over]")?.addEventListener("click", () => {
    resetFlow();
    deps.setUrlImportId(null);
    renderWizard();
  });
  document.querySelector("[data-review-next]")?.addEventListener("click", async () => {
    if (navigateToStep(STEPS.REVIEW)) {
      await renderWizard();
    }
  });
}

export async function loadWizardBrands(getBrands) {
  const select = document.querySelector("[data-import-brand]");
  try {
    brandsCache = await getBrands();
    select.innerHTML = '<option value="">Selecione uma marca</option>';
    brandsCache.forEach((brand) => select.append(new Option(brand.name, String(brand.id))));
    if (!brandsCache.length) select.innerHTML = '<option value="">Nenhuma marca cadastrada</option>';
  } catch {
    select.innerHTML = '<option value="">Erro ao carregar marcas</option>';
  }
}

export async function resumeImport(importRecord) {
  setCurrentImport(importRecord);
  await renderWizard();
}

export async function renderWizard() {
  renderStepper();
  renderStepShell();
  const step = flowState.currentStep;
  document.querySelector("[data-step-source]").hidden = step !== STEPS.SOURCE;
  document.querySelector("[data-step-analyzing]").hidden = step !== STEPS.ANALYZING;
  document.querySelector("[data-step-preview]").hidden = step !== STEPS.PREVIEW;
  document.querySelector("[data-step-review]").hidden = step !== STEPS.REVIEW;
  document.querySelector("[data-step-review]").hidden = ![STEPS.REVIEW, STEPS.READY_TO_PUBLISH, STEPS.PUBLISHING, STEPS.FINISHED].includes(step);
  document.querySelector("[data-step-failed]").hidden = step !== STEPS.FAILED;

  if (step === STEPS.SOURCE) renderSourceStep();
  if (step === STEPS.PREVIEW) renderPreviewStep();
  if ([STEPS.REVIEW, STEPS.READY_TO_PUBLISH, STEPS.PUBLISHING, STEPS.FINISHED].includes(step)) await wizardDeps.renderReviewExperience?.();
  if (step === STEPS.FAILED) renderFailureStep();
  focusStepTitle();
}

function renderStepShell() {
  const definition = stepDefinitions[flowState.currentStep] || stepDefinitions[STEPS.SOURCE];
  document.querySelector("[data-wizard-title]").textContent = definition.label;
  document.querySelector("[data-wizard-description]").textContent = definition.description;
}

function renderSourceStep() {
  document.querySelector("[data-import-form-error]").hidden = true;
  const brand = document.querySelector("[data-import-brand]");
  const url = document.querySelector("[data-import-url]");
  if (flowState.selectedBrandId) brand.value = String(flowState.selectedBrandId);
  if (flowState.sourceUrl) url.value = flowState.sourceUrl;
}

function renderStepper() {
  const stepper = document.querySelector("[data-import-stepper]");
  clearChildren(stepper);
  const currentIndex = stepIndex(flowState.currentStep);
  stepOrder.forEach((step, index) => {
    const definition = stepDefinitions[step];
    const item = document.createElement("button");
    item.type = "button";
    item.className = "admin-import-stepper__item";
    item.disabled = index > currentIndex || !definition.canGoBack;
    item.dataset.state = index < currentIndex ? "done" : index === currentIndex ? "current" : "future";
    item.innerHTML = `<span>${index + 1}</span><strong></strong><small></small>`;
    item.querySelector("strong").textContent = definition.label;
    item.querySelector("small").textContent = item.dataset.state === "done" ? "Concluida" : item.dataset.state === "current" ? "Atual" : "Futura";
    if (index === currentIndex) item.setAttribute("aria-current", "step");
    item.addEventListener("click", async () => {
      if (navigateToStep(step)) await renderWizard();
    });
    stepper.append(item);
  });

  if (flowState.currentStep === STEPS.FAILED) {
    const failed = document.createElement("div");
    failed.className = "admin-import-stepper__item";
    failed.dataset.state = "error";
    failed.setAttribute("aria-current", "step");
    failed.innerHTML = "<span>!</span><strong>Falha</strong><small>Atual</small>";
    stepper.append(failed);
  }
}

async function handlePreviewSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = document.querySelector("[data-import-submit]");
  const error = document.querySelector("[data-import-form-error]");
  const brandId = Number(document.querySelector("[data-import-brand]").value);
  const sourceUrl = document.querySelector("[data-import-url]").value.trim();

  if (!form.checkValidity()) {
    form.reportValidity();
    showFormError(error, "Preencha marca e URL para continuar.");
    return;
  }
  const localError = validateSourceUrl(sourceUrl);
  if (localError) {
    showFormError(error, localError);
    return;
  }

  submit.disabled = true;
  submit.setAttribute("aria-busy", "true");
  flowState.loading = true;
  flowState.selectedBrandId = brandId;
  flowState.sourceUrl = sourceUrl;
  flowState.currentStep = STEPS.ANALYZING;
  await renderWizard();

  try {
    const result = await wizardDeps.createImportPreview({ brand_id: brandId, source_url: sourceUrl });
    const record = await wizardDeps.getImportById(result.id);
    setCurrentImport(record);
    wizardDeps.setUrlImportId(record.id);
    await renderWizard();
    wizardDeps.notify(result.message || "Pre-visualizacao criada.", "success");
    await wizardDeps.reloadCenter();
  } catch (caught) {
    flowState.currentStep = STEPS.SOURCE;
    flowState.error = caught;
    await renderWizard();
    showFormError(error, friendlyImportError(caught, "Nao foi possivel gerar o preview."));
  } finally {
    submit.disabled = false;
    submit.removeAttribute("aria-busy");
    flowState.loading = false;
  }
}

function validateSourceUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    return "Informe uma URL HTTP ou HTTPS valida.";
  }
  if (!["http:", "https:"].includes(url.protocol)) return "Informe uma URL HTTP ou HTTPS valida.";
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (host !== allowedDomain && !host.endsWith(`.${allowedDomain}`)) return "Use uma URL em yupoo.com ou subdominio permitido.";
  return "";
}

function renderPreviewStep() {
  const record = flowState.currentImport;
  if (!record) return;
  document.querySelector("[data-preview-title]").textContent = record.folder_name || `Importacao #${record.id}`;
  document.querySelector("[data-preview-description]").textContent = `${record.brand?.name || "Marca"} - ${record.normalized_source_url || record.source_url || ""}`;
  const metrics = document.querySelector("[data-preview-metrics]");
  metrics.innerHTML = [
    ["Status", statusLabel(record.status)],
    ["Itens encontrados", record.items_found || 0],
    ["Pendentes", record.items_pending || 0],
    ["Duplicados", record.duplicate_items || 0],
    ["Paginas", `${record.current_page || 0}/${record.total_pages || record.current_page || 0}`],
    ["Falhas", record.error_count || 0]
  ].map(([label, value]) => `<article class="admin-card"><h3>${label}</h3><p>${value}</p></article>`).join("");

  const details = document.querySelector("[data-preview-details]");
  details.innerHTML = "";
  [
    ["ID", `#${record.id}`],
    ["Origem", record.source || record.source_type || "Yupoo"],
    ["URL", record.normalized_source_url || record.source_url || "-"],
    ["Criada em", formatDate(record.created_at)],
    ["Atualizada em", formatDate(record.updated_at)],
    ["Mensagem", record.error_message || "Preview gerado com dados reais da API."]
  ].forEach(([label, value]) => details.append(detailItem(label, value)));

  document.querySelector("[data-review-next]").disabled = record.status !== "preview_ready";
}

async function renderReviewSummary() {
  const table = document.querySelector("[data-review-summary-table]");
  const body = document.querySelector("[data-review-summary-body]");
  const empty = document.querySelector("[data-review-summary-empty]");
  clearChildren(body);
  try {
    const data = await wizardDeps.getImportItems(flowState.currentImportId, { page: 1, page_size: 20 });
    const items = data.items || [];
    table.hidden = !items.length;
    empty.hidden = Boolean(items.length);
    items.forEach((item) => body.append(reviewRow(item)));
  } catch (error) {
    table.hidden = true;
    empty.hidden = false;
    empty.querySelector("h2").textContent = friendlyImportError(error, "Nao foi possivel carregar itens.");
  }
}

function reviewRow(item) {
  const row = document.createElement("tr");
  row.append(
    textCell(item.suggested_name || item.source_title || `Item #${item.id}`),
    textCell(item.suggested_category || "-"),
    textCell(item.image_count || 0),
    badgeCell(item.status || "-", item.status === "reviewed" ? "admin-badge--ok" : item.status === "duplicate" ? "admin-badge--off" : "admin-badge--warn"),
    textCell(percent(item.overall_confidence || item.confidence))
  );
  return row;
}

function renderFailureStep() {
  const record = flowState.currentImport;
  document.querySelector("[data-failure-message]").textContent = record?.error_message || "Nao foi possivel concluir esta pre-visualizacao.";
}

function detailItem(label, value) {
  const item = document.createElement("div");
  item.className = "admin-import-detail-item";
  const title = document.createElement("span");
  title.textContent = label;
  const text = document.createElement("strong");
  text.textContent = String(value || "-");
  item.append(title, text);
  return item;
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

function percent(value) {
  if (value === null || value === undefined || value === "") return "-";
  return `${Math.round(Number(value) * 100)}%`;
}

function showFormError(element, message) {
  element.hidden = false;
  element.textContent = message;
  wizardDeps.notify(message, "error");
}

function focusStepTitle() {
  window.requestAnimationFrame(() => document.querySelector("[data-wizard-title]")?.focus());
}
