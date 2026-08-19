import { clearChildren, createBadge } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { normalizeItemError } from "./import-readiness.js?v=api-base-3000-20260730";

const galleryCache = new Map();
const brokenUrls = new Set();

let previewDeps;
let activeModal = null;
let activeIndex = 0;
let activeItem = null;
let activeImages = [];
let returnFocus = null;

export function initImportPreview(deps) {
  previewDeps = deps;
}

export function createImportProductPreview(item, options = {}) {
  const state = resolveItemPreviewImage(item);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "import-product-preview";
  button.dataset.previewItemId = String(item.id);
  button.setAttribute("aria-label", `Ver imagens de ${item.suggested_name || item.source_title || "produto importado"}`);
  button.append(previewMedia(state, item));
  if (state.countText || state.statusText) {
    const meta = document.createElement("span");
    meta.className = "import-product-preview__meta";
    if (state.countText) {
      const count = document.createElement("span");
      count.className = "import-product-preview__count";
      count.textContent = state.countText;
      meta.append(count);
    }
    if (state.statusText) {
      const status = document.createElement("span");
      status.className = "import-product-preview__status";
      status.textContent = state.statusText;
      meta.append(status);
    }
    button.append(meta);
  }
  button.addEventListener("click", () => options.onOpen?.(item, button));
  return button;
}

export function resolveItemPreviewImage(item, images = null) {
  const gallery = Array.isArray(images) ? sortedImages(images) : null;
  if (gallery) {
    const candidates = [
      gallery.find((image) => image.is_cover && isUsableImage(image)),
      gallery.find((image) => image.ingestion_status === "stored" && image.is_selected && isUsableImage(image)),
      gallery.find((image) => image.is_selected && isUsableImage(image)),
      gallery.find((image) => isUsableImage(image))
    ].filter(Boolean);
    const image = candidates[0] || null;
    return previewStateFromImage(image, gallery.length, gallery);
  }

  const url = safeImageUrl(item.cover_image_url) || safeImageUrl(Array.isArray(item.image_urls) ? item.image_urls[0] : null);
  const count = Number.isInteger(item.image_count) ? item.image_count : null;
  if (url) {
    return {
      url,
      count,
      countText: imageCountText(count),
      statusText: item.cover_image_url ? "Capa" : "",
      reason: "",
      image: null
    };
  }
  return {
    url: "",
    count,
    countText: imageCountText(count),
    statusText: emptyReasonFromItem(item),
    reason: emptyReasonFromItem(item),
    image: null
  };
}

export function resolveImportImageUrl(image) {
  return safeImageUrl(image?.local_public_url) || safeImageUrl(image?.source_url);
}

export async function openImportImagePreview(item, trigger, options = {}) {
  returnFocus = trigger || document.activeElement;
  activeItem = item;
  activeIndex = 0;
  activeImages = [];
  activeModal = ensureModal();
  renderModalShell(item, options);
  activeModal.hidden = false;
  activeModal.querySelector("[data-preview-close]")?.focus();
  await loadGallery(item, options);
}

export function invalidateImportPreviewCache(importId, itemId) {
  if (!importId || !itemId) return;
  galleryCache.delete(cacheKey(importId, itemId));
}

export function clearImportPreviewCache() {
  galleryCache.clear();
}

async function loadGallery(item, options) {
  const body = activeModal.querySelector("[data-preview-gallery-body]");
  renderGalleryLoading(body);
  try {
    const images = await getGallery(item.import_record_id, item.id);
    activeImages = sortedImages(images);
    const resolved = resolveItemPreviewImage(item, activeImages);
    activeIndex = Math.max(0, activeImages.findIndex((image) => image.id === resolved.image?.id));
    renderGallery(body, item, options);
  } catch (error) {
    renderGalleryError(body, normalizeItemError(error));
  }
}

async function getGallery(importId, itemId) {
  const key = cacheKey(importId, itemId);
  const cached = galleryCache.get(key);
  if (cached?.images) return cached.images;
  if (cached?.promise) return cached.promise;
  const promise = previewDeps.getImportImages(importId, itemId).then((images) => {
    galleryCache.set(key, { images });
    return images;
  }).catch((error) => {
    galleryCache.delete(key);
    throw error;
  });
  galleryCache.set(key, { promise });
  return promise;
}

function renderModalShell(item, options) {
  activeModal.querySelector("[data-preview-title]").textContent = item.suggested_name || item.source_title || `Item #${item.id}`;
  activeModal.querySelector("[data-preview-manage]").onclick = () => {
    closePreview();
    options.onManageImages?.(item, returnFocus);
  };
}

function renderGallery(container, item, options) {
  clearChildren(container);
  if (!activeImages.length) {
    const empty = document.createElement("div");
    empty.className = "admin-empty admin-empty--compact";
    const box = document.createElement("div");
    box.className = "admin-empty__box";
    const title = document.createElement("h3");
    title.textContent = "Nenhuma imagem encontrada.";
    const text = document.createElement("p");
    text.textContent = "O endpoint de imagens nao retornou registros para este item.";
    box.append(title, text);
    empty.append(box);
    container.append(empty);
    return;
  }

  const image = activeImages[activeIndex] || activeImages[0];
  const state = previewStateFromImage(image, activeImages.length, activeImages);
  const main = document.createElement("div");
  main.className = "import-gallery__main";
  main.append(previewLargeMedia(state, item));

  const details = document.createElement("div");
  details.className = "import-gallery__details";
  const position = document.createElement("strong");
  position.textContent = `Imagem ${activeIndex + 1} de ${activeImages.length}`;
  const badges = document.createElement("div");
  badges.className = "import-gallery__badges";
  if (image.is_cover) badges.append(createBadge("Capa", "admin-badge--ok"));
  badges.append(createBadge(statusLabel(image.status), image.status === "active" ? "admin-badge--ok" : "admin-badge--warn"));
  badges.append(createBadge(ingestionLabel(image.ingestion_status), image.ingestion_status === "stored" ? "admin-badge--ok" : image.ingestion_status === "failed" ? "admin-badge--off" : "admin-badge--info"));
  details.append(position, badges);

  const nav = document.createElement("div");
  nav.className = "import-gallery__nav";
  nav.append(navButton("Anterior", -1, activeImages.length <= 1), navButton("Proxima", 1, activeImages.length <= 1));

  const thumbs = document.createElement("div");
  thumbs.className = "import-gallery__thumbs";
  thumbs.setAttribute("aria-label", "Miniaturas da galeria");
  activeImages.forEach((entry, index) => thumbs.append(galleryThumb(entry, index, item, options)));

  container.append(main, details, nav, thumbs);
}

function renderGalleryLoading(container) {
  clearChildren(container);
  const loading = document.createElement("div");
  loading.className = "import-gallery__loading";
  loading.setAttribute("aria-live", "polite");
  loading.append(skeleton(), skeleton(), skeleton());
  container.append(loading);
}

function renderGalleryError(container, message) {
  clearChildren(container);
  const error = document.createElement("div");
  error.className = "admin-empty admin-empty--compact";
  const box = document.createElement("div");
  box.className = "admin-empty__box";
  const title = document.createElement("h3");
  title.textContent = "Nao foi possivel carregar imagens.";
  const text = document.createElement("p");
  text.textContent = message;
  box.append(title, text);
  error.append(box);
  container.append(error);
}

function previewMedia(state, item) {
  const media = document.createElement("span");
  media.className = "import-product-preview__media";
  if (!state.url) {
    media.append(placeholder(state.reason || "Sem imagem"));
    return media;
  }
  const image = document.createElement("img");
  image.src = state.url;
  image.alt = altText(item);
  image.width = 88;
  image.height = 88;
  image.loading = "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    brokenUrls.add(state.url);
    clearChildren(media);
    media.append(placeholder("Falha ao carregar"));
  }, { once: true });
  if (brokenUrls.has(state.url)) media.append(placeholder("Falha ao carregar"));
  else media.append(image);
  return media;
}

function previewLargeMedia(state, item) {
  const media = document.createElement("div");
  media.className = "import-gallery__media";
  if (!state.url) {
    media.append(placeholder(state.reason || "Sem imagem"));
    return media;
  }
  const image = document.createElement("img");
  image.src = state.url;
  image.alt = altText(item);
  image.loading = "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    brokenUrls.add(state.url);
    clearChildren(media);
    media.append(placeholder("Falha ao carregar"));
  }, { once: true });
  media.append(image);
  return media;
}

function galleryThumb(image, index, item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "import-gallery__thumb";
  button.setAttribute("aria-label", `Ver imagem ${index + 1}${image.is_cover ? ", capa" : ""}`);
  button.setAttribute("aria-current", index === activeIndex ? "true" : "false");
  if (image.is_cover) button.dataset.cover = "true";
  if (image.status !== "active") button.dataset.status = image.status;
  const state = previewStateFromImage(image, activeImages.length, activeImages);
  button.append(previewMedia(state, item));
  const label = document.createElement("span");
  label.textContent = image.is_cover ? "Capa" : statusLabel(image.status);
  button.append(label);
  button.addEventListener("click", () => {
    activeIndex = index;
    renderGallery(activeModal.querySelector("[data-preview-gallery-body]"), activeItem);
  });
  return button;
}

function navButton(label, direction, disabled) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "admin-button admin-button--ghost";
  button.textContent = label;
  button.disabled = disabled;
  button.setAttribute("aria-label", `${label} imagem`);
  button.addEventListener("click", () => {
    activeIndex = (activeIndex + direction + activeImages.length) % activeImages.length;
    renderGallery(activeModal.querySelector("[data-preview-gallery-body]"), activeItem);
  });
  return button;
}

function ensureModal() {
  let modal = document.querySelector("[data-import-preview-modal]");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.className = "admin-modal import-gallery-modal";
  modal.hidden = true;
  modal.dataset.importPreviewModal = "";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "import-preview-title");

  const panel = document.createElement("div");
  panel.className = "admin-modal__panel import-gallery";
  const head = document.createElement("div");
  head.className = "admin-modal__head";
  const titleWrap = document.createElement("div");
  const eyebrow = document.createElement("p");
  eyebrow.className = "admin-eyebrow";
  eyebrow.textContent = "Preview visual";
  const title = document.createElement("h2");
  title.id = "import-preview-title";
  title.dataset.previewTitle = "";
  title.textContent = "Imagem do produto";
  titleWrap.append(eyebrow, title);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "admin-button admin-button--ghost";
  close.dataset.previewClose = "";
  close.textContent = "Fechar";
  close.addEventListener("click", closePreview);
  head.append(titleWrap, close);

  const body = document.createElement("div");
  body.className = "admin-modal__body";
  body.dataset.previewGalleryBody = "";
  const foot = document.createElement("div");
  foot.className = "admin-modal__foot admin-actions";
  const manage = document.createElement("button");
  manage.type = "button";
  manage.className = "admin-button admin-button--primary";
  manage.dataset.previewManage = "";
  manage.textContent = "Gerenciar imagens";
  const closeFoot = document.createElement("button");
  closeFoot.type = "button";
  closeFoot.className = "admin-button";
  closeFoot.textContent = "Fechar";
  closeFoot.addEventListener("click", closePreview);
  foot.append(manage, closeFoot);
  panel.append(head, body, foot);
  modal.append(panel);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closePreview();
  });
  document.addEventListener("keydown", handlePreviewKeydown);
  document.body.append(modal);
  return modal;
}

function handlePreviewKeydown(event) {
  if (!activeModal || activeModal.hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closePreview();
  }
  if (event.key !== "Tab") return;
  const focusable = [...activeModal.querySelectorAll("button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])")];
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function closePreview() {
  if (!activeModal) return;
  activeModal.hidden = true;
  activeItem = null;
  activeImages = [];
  activeIndex = 0;
  returnFocus?.focus?.();
}

function previewStateFromImage(image, count, images) {
  if (!image) {
    return {
      url: "",
      count,
      countText: imageCountText(count),
      statusText: emptyReasonFromImages(images),
      reason: emptyReasonFromImages(images),
      image: null
    };
  }
  return {
    url: safeImageUrl(image.local_public_url) || safeImageUrl(image.source_url),
    count,
    countText: imageCountText(count),
    statusText: image.is_cover ? "Capa" : imageStatusSummary(image),
    reason: imageStatusSummary(image),
    image
  };
}

function isUsableImage(image) {
  return image && image.status === "active" && safeImageUrl(image.local_public_url || image.source_url);
}

function sortedImages(images) {
  return [...images].sort((a, b) => (Number(a.position) || 0) - (Number(b.position) || 0) || (Number(a.id) || 0) - (Number(b.id) || 0));
}

function imageCountText(count) {
  if (!Number.isInteger(count) || count <= 0) return "";
  return `${count} imagem${count === 1 ? "" : "s"}`;
}

function emptyReasonFromItem(item) {
  if (Number(item.image_count) > 0) return "Sem URL valida";
  return "Sem imagem";
}

function emptyReasonFromImages(images = []) {
  if (!images.length) return "Sem imagem";
  if (images.every((image) => image.status === "ignored")) return "Imagens ignoradas";
  if (images.some((image) => image.ingestion_status === "failed")) return "Erro de imagem";
  return "Sem imagem ativa";
}

function imageStatusSummary(image) {
  if (image.status === "ignored") return "Ignorada";
  if (image.status === "duplicate") return "Duplicada";
  if (image.status === "invalid") return "Invalida";
  if (image.ingestion_status === "stored") return "Ingerida";
  if (image.ingestion_status === "failed") return "Erro de ingestao";
  if (image.ingestion_status === "not_requested") return "Nao ingerida";
  return statusLabel(image.status);
}

function statusLabel(status) {
  const labels = { active: "Ativa", ignored: "Ignorada", duplicate: "Duplicada", invalid: "Invalida" };
  return labels[status] || status || "Status";
}

function ingestionLabel(status) {
  const labels = {
    not_requested: "Nao ingerida",
    downloading: "Baixando",
    validating: "Validando",
    stored: "Ingerida",
    failed: "Falha",
    skipped: "Ignorada"
  };
  return labels[status] || status || "Ingestao";
}

function safeImageUrl(value) {
  if (!value || typeof value !== "string") return "";
  const raw = value.trim();
  if (!raw || raw.startsWith("//")) return "";
  try {
    const url = raw.startsWith("/") ? new URL(raw, window.location.origin) : new URL(raw);
    if (!["http:", "https:"].includes(url.protocol)) return "";
    return url.href;
  } catch {
    return "";
  }
}

function altText(item) {
  if (item?.suggested_name) return `Imagem de ${item.suggested_name}`;
  return "Imagem do produto importado";
}

function placeholder(text) {
  const wrap = document.createElement("span");
  wrap.className = "import-product-preview__placeholder";
  wrap.setAttribute("title", text);
  const icon = document.createElement("span");
  icon.className = "import-product-preview__placeholder-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "IMG";
  const label = document.createElement("span");
  label.textContent = text;
  wrap.append(icon, label);
  return wrap;
}

function skeleton() {
  const item = document.createElement("span");
  item.className = "admin-skeleton";
  return item;
}

function cacheKey(importId, itemId) {
  return `${importId}:${itemId}`;
}
