import { clearChildren, createBadge } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { normalizeItemError, readinessText } from "./import-readiness.js?v=api-base-3000-20260730";
import { invalidateImportPreviewCache, resolveImportImageUrl } from "./import-preview.js?v=api-base-3000-20260730";

let imageDeps;

export function initImportImages(deps) {
  imageDeps = deps;
}

export function renderImages(container, item, options = {}) {
  clearChildren(container);
  const images = item?.images || [];
  if (!images.length) {
    container.innerHTML = '<div class="admin-empty admin-empty--compact"><div class="admin-empty__box"><h3>Nenhuma imagem encontrada.</h3><p>O backend nao retornou imagens para este item.</p></div></div>';
    return;
  }
  images.forEach((image) => container.append(imageCard(item, image, options)));
}

function imageCard(item, image, options) {
  const card = document.createElement("article");
  card.className = "admin-import-image-card";
  const media = document.createElement("div");
  media.className = "admin-import-image-card__media";
  const src = resolveImportImageUrl(image);
  if (src) {
    const img = document.createElement("img");
    img.src = src;
    img.alt = image.alt_text || item.suggested_name || "Imagem da importacao";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error", () => {
      clearChildren(media);
      const failed = document.createElement("span");
      failed.textContent = "Falha ao carregar";
      media.append(failed);
    }, { once: true });
    media.append(img);
  } else {
    const empty = document.createElement("span");
    empty.textContent = "Sem imagem";
    media.append(empty);
  }
  const body = document.createElement("div");
  body.className = "admin-import-image-card__body";
  const title = document.createElement("strong");
  title.textContent = image.is_cover ? "Imagem principal" : `Imagem ${image.position + 1}`;
  const source = document.createElement("p");
  source.textContent = image.local_public_url ? "Armazenada localmente" : "Imagem remota";
  const actions = document.createElement("div");
  actions.className = "admin-actions";
  body.append(title, source, actions);
  card.append(media, body);
  const badges = document.createElement("div");
  badges.className = "admin-import-image-card__badges";
  badges.append(createBadge(image.status, image.status === "active" ? "admin-badge--ok" : "admin-badge--warn"));
  badges.append(createBadge(image.ingestion_status, image.ingestion_status === "stored" ? "admin-badge--ok" : image.ingestion_status === "failed" ? "admin-badge--off" : "admin-badge--info"));
  body.insertBefore(badges, actions);

  actions.append(actionButton("Capa", () => updateImage(item, image, { is_cover: true }, options), image.is_cover || image.status !== "active" || !image.is_selected));
  actions.append(actionButton(image.is_selected ? "Remover" : "Selecionar", () => updateImage(item, image, { is_selected: !image.is_selected }, options), image.status !== "active"));
  actions.append(actionButton(image.status === "ignored" ? "Ativar" : "Ignorar", () => updateImage(item, image, { status: image.status === "ignored" ? "active" : "ignored" }, options), image.status === "duplicate" || image.status === "invalid"));
  actions.append(actionButton("Ingerir", () => ingestImage(item, image, options), image.ingestion_status === "stored" || image.status !== "active" || !image.is_selected));
  return card;
}

async function updateImage(item, image, payload, options) {
  await runImageAction(options, async () => {
    const updated = await imageDeps.updateImportImage(item.import_record_id, item.id, image.id, { ...payload, updated_at: item.updated_at });
    invalidateImportPreviewCache(item.import_record_id, item.id);
    imageDeps.notify("Imagem atualizada.", "success");
    await options.onItemChanged?.(updated);
  });
}

async function ingestImage(item, image, options) {
  await runImageAction(options, async () => {
    const readiness = await imageDeps.getImportImageIngestionReadiness(item.import_record_id, item.id, image.id);
    if (!readiness.ready) {
      imageDeps.notify(`Imagem bloqueada: ${(readiness.blockers || []).map(readinessText).join(", ")}`, "warning");
      return;
    }
    const result = await imageDeps.ingestImportImage(item.import_record_id, item.id, image.id, { updated_at: item.updated_at });
    invalidateImportPreviewCache(item.import_record_id, item.id);
    imageDeps.notify(result.message || "Imagem ingerida.", "success");
    await options.onItemChanged?.(result.image);
  });
}

async function runImageAction(options, action) {
  try {
    options.setBusy?.(true);
    await action();
  } catch (error) {
    imageDeps.notify(normalizeItemError(error), "error");
  } finally {
    options.setBusy?.(false);
  }
}

function actionButton(label, onClick, disabled) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "admin-button admin-button--ghost";
  button.textContent = label;
  button.disabled = Boolean(disabled);
  button.addEventListener("click", onClick);
  return button;
}
