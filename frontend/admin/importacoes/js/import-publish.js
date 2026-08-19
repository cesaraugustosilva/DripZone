import { normalizeItemError, readinessText } from "./import-readiness.js?v=api-base-3000-20260730";

let publishDeps;
let pendingItems = [];
let publishing = false;

export function initImportPublish(deps) {
  publishDeps = deps;
  document.querySelector("[data-publish-cancel]")?.addEventListener("click", closePublishModal);
  document.querySelector("[data-publish-confirm]")?.addEventListener("click", runPublication);
}

export async function openPublishConfirm(items) {
  pendingItems = items;
  const modal = document.querySelector("[data-publish-modal]");
  const summary = modal.querySelector("[data-publish-summary]");
  const blockers = [];
  const readyItems = [];
  for (const item of items) {
    const fresh = await publishDeps.getImportItem(item.import_record_id, item.id);
    const readiness = await publishDeps.getImportPublicationReadiness(item.import_record_id, item.id);
    if (fresh.status === "approved" && readiness.ready) {
      readyItems.push(fresh);
    } else {
      blockers.push({ item: fresh, readiness });
    }
  }
  pendingItems = readyItems;
  summary.innerHTML = "";
  summary.append(row("Produtos que serao criados", readyItems.length));
  summary.append(row("Itens ignorados", blockers.length));
  if (blockers.length) {
    const list = document.createElement("ul");
    blockers.slice(0, 8).forEach(({ item, readiness }) => {
      const li = document.createElement("li");
      li.textContent = `${item.suggested_name || item.source_title || `Item #${item.id}`}: ${(readiness.blockers || []).map(readinessText).join(", ") || "nao elegivel"}`;
      list.append(li);
    });
    summary.append(list);
  }
  modal.querySelector("[data-publish-confirm]").disabled = readyItems.length === 0;
  modal.hidden = false;
  modal.querySelector("[data-publish-cancel]").focus();
}

async function runPublication() {
  if (publishing) return;
  publishing = true;
  const confirm = document.querySelector("[data-publish-confirm]");
  confirm.disabled = true;
  confirm.setAttribute("aria-busy", "true");
  const result = { created: [], skipped: [], failed: [] };
  for (const item of pendingItems) {
    try {
      const fresh = await publishDeps.getImportItem(item.import_record_id, item.id);
      const response = await publishDeps.publishImportItem(fresh.import_record_id, fresh.id, { updated_at: fresh.updated_at });
      if (response.created) result.created.push(response);
      else result.skipped.push(response);
    } catch (error) {
      result.failed.push({ item, error: normalizeItemError(error) });
    }
  }
  publishing = false;
  confirm.removeAttribute("aria-busy");
  closePublishModal();
  await publishDeps.onPublished?.(result);
}

function closePublishModal() {
  if (publishing) return;
  document.querySelector("[data-publish-modal]").hidden = true;
}

function row(label, value) {
  const item = document.createElement("div");
  item.className = "admin-import-detail-item";
  item.innerHTML = "<span></span><strong></strong>";
  item.querySelector("span").textContent = label;
  item.querySelector("strong").textContent = String(value);
  return item;
}
