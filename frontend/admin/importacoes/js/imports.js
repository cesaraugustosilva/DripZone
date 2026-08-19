import { initAdminPage } from "/admin/js/admin.js?v=api-base-3000-20260730";
import {
  approveImportItem,
  createImportPreview,
  getBrands,
  getCategories,
  getImportById,
  getImportImages,
  getImportImageIngestionReadiness,
  getImportItem,
  getImportItems,
  getImportPublicationReadiness,
  getImports,
  ingestImportImage,
  publishImportItem,
  unapproveImportItem,
  updateImportImage,
  updateImportItem
} from "./api.js?v=api-base-3000-20260730";
import { notify } from "/admin/js/notifications.js?v=api-base-3000-20260730";
import { initImportCenter, loadImportCenter } from "./import-center.js?v=api-base-3000-20260730";
import { resetFlow } from "./import-flow.js?v=api-base-3000-20260730";
import { initImportWizard, loadWizardBrands, renderWizard, resumeImport } from "./import-wizard.js?v=api-base-3000-20260730";
import { initImportReview, onPublishFinished, onReviewItemSaved, renderImportReview } from "./import-review.js?v=api-base-3000-20260730";
import { initImportItemEditor, loadEditorResources } from "./import-item-editor.js?v=api-base-3000-20260730";
import { initImportImages } from "./import-images.js?v=api-base-3000-20260730";
import { initImportPreview } from "./import-preview.js?v=api-base-3000-20260730";
import { initImportPublish } from "./import-publish.js?v=api-base-3000-20260730";

await initAdminPage({
  title: "Importacoes",
  breadcrumb: "Admin / Importacoes",
  description: "Crie previews, acompanhe o historico e retome importacoes da DripZone."
});

const center = document.querySelector("[data-import-center]");
const wizard = document.querySelector("[data-import-wizard]");

const deps = {
  getImports,
  getImportById,
  getImportItems,
  getImportItem,
  getImportImages,
  getImportPublicationReadiness,
  createImportPreview,
  updateImportItem,
  updateImportImage,
  getImportImageIngestionReadiness,
  ingestImportImage,
  approveImportItem,
  unapproveImportItem,
  publishImportItem,
  notify,
  reloadCenter,
  openImport,
  setUrlImportId,
  exitWizard,
  renderReviewExperience: renderImportReview,
  onSaved: onReviewItemSaved,
  onPublished: onPublishFinished
};

initImportCenter({ getImports, openImport, startNewImport, notify });
initImportWizard(deps);
initImportReview(deps);
initImportItemEditor(deps);
initImportImages(deps);
initImportPreview(deps);
initImportPublish(deps);
await loadInitialState();

async function reloadCenter() {
  await loadImportCenter({ getImports, openImport, notify });
}

async function loadInitialState() {
  const importId = importIdFromUrl();
  if (importId) {
    showWizard();
    await Promise.all([loadWizardBrands(getBrands), loadEditorResources(getCategories), openImport(importId)]);
    return;
  }
  showCenter();
  await Promise.all([loadWizardBrands(getBrands), loadEditorResources(getCategories), reloadCenter()]);
}

async function openImport(importId) {
  showWizard();
  try {
    const record = await getImportById(importId);
    setUrlImportId(record.id);
    await resumeImport(record);
  } catch (error) {
    resetFlow();
    setUrlImportId(null);
    notify(error?.status === 404 ? "Importacao nao encontrada. Inicie uma nova importacao." : "Nao foi possivel carregar esta importacao.", "error");
    showCenter();
    await reloadCenter();
  }
}

async function startNewImport() {
  resetFlow();
  setUrlImportId(null, { view: "wizard" });
  showWizard();
  await renderWizard();
}

function exitWizard() {
  resetFlow();
  setUrlImportId(null);
  showCenter();
  reloadCenter();
}

function showWizard() {
  center.hidden = true;
  wizard.hidden = false;
}

function showCenter() {
  center.hidden = false;
  wizard.hidden = true;
}

function importIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("import_id");
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function setUrlImportId(importId, extra = {}) {
  const url = new URL(window.location.href);
  url.search = "";
  Object.entries(extra).forEach(([key, value]) => {
    if (value) url.searchParams.set(key, value);
  });
  if (importId) {
    url.searchParams.set("view", "wizard");
    url.searchParams.set("import_id", String(importId));
  }
  window.history.replaceState({}, "", url);
}
