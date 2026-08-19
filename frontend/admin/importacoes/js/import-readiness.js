export const itemStatusLabels = {
  pending: "Pendente",
  duplicate: "Duplicado",
  needs_review: "Atencao",
  invalid: "Invalido",
  reviewed: "Revisado",
  approved: "Aprovado",
  publishing: "Publicando",
  published: "Publicado",
  publish_failed: "Falha ao publicar"
};

export const blockerLabels = {
  not_reviewed: "Item ainda nao revisado",
  duplicate_item: "Item duplicado",
  invalid_item: "Item invalido",
  already_published: "Item ja publicado",
  missing_name: "Nome ausente",
  missing_brand: "Marca ausente",
  missing_category: "Categoria ausente",
  missing_images: "Nenhuma imagem selecionada",
  missing_cover: "Imagem principal ausente",
  image_ingestion_failed: "Ingestao de imagem falhou",
  image_ingestion_required: "Imagens selecionadas precisam ser ingeridas",
  ingested_file_missing: "Arquivo ingerido nao encontrado",
  duplicate_product: "Possivel produto duplicado",
  image_not_active: "Imagem nao esta ativa",
  image_not_selected: "Imagem nao selecionada",
  import_not_editable: "Importacao nao editavel",
  already_ingested: "Imagem ja ingerida",
  invalid_source_url: "URL de imagem invalida",
  blocked_host: "Host bloqueado",
  blocked_ip: "IP bloqueado"
};

export const warningLabels = {
  missing_model: "Modelo ausente",
  missing_color: "Cor ausente",
  single_image: "Apenas uma imagem",
  external_images: "Imagens externas",
  external_image: "Imagem externa",
  low_confidence: "Baixa confianca",
  no_selected_images: "Sem imagens selecionadas",
  small_image: "Imagem pequena"
};

export function itemStatusLabel(status) {
  return itemStatusLabels[status] || status || "-";
}

export function itemStatusBadge(status) {
  return {
    pending: "admin-badge--warn",
    duplicate: "admin-badge--off",
    needs_review: "admin-badge--warn",
    invalid: "admin-badge--off",
    reviewed: "admin-badge--info",
    approved: "admin-badge--ok",
    publishing: "admin-badge--info",
    published: "admin-badge--success",
    publish_failed: "admin-badge--off"
  }[status] || "admin-badge--info";
}

export function readinessText(code) {
  return blockerLabels[code] || warningLabels[code] || code;
}

export function isReviewEditable(item) {
  return ["pending", "needs_review", "invalid", "reviewed", "publish_failed"].includes(item?.status);
}

export function canApprove(item, readiness) {
  if (item?.status !== "reviewed") return false;
  const blockers = readiness?.blockers || [];
  return !blockers.some((blocker) => !["image_ingestion_required", "external_images_require_ingestion"].includes(blocker));
}

export function canUnapprove(item) {
  return item?.status === "approved" && !item?.published_product_id;
}

export function canPublish(item, readiness) {
  return item?.status === "approved" && Boolean(readiness?.ready);
}

export function qualityFromImport(record) {
  const total = Number(record?.items_found || 0);
  const invalid = Number(record?.error_count || 0);
  const attention = Number(record?.items_needs_review || 0);
  const approved = Number(record?.items_approved || 0);
  const published = Number(record?.items_published || 0);
  const failed = Number(record?.items_publish_failed || 0);
  const reviewed = Number(record?.items_reviewed || 0);
  const duplicates = Number(record?.duplicate_items || 0);
  const ready = approved + published;
  return {
    total,
    ready,
    attention,
    invalid,
    approved,
    notApproved: Math.max(total - approved - published - duplicates, 0),
    published,
    failed,
    reviewed,
    duplicates,
    blockers: invalid + attention + failed
  };
}

export function filterParams(filter) {
  if (filter === "attention") return { needs_review: true };
  if (filter === "invalid") return { status: "invalid" };
  if (filter === "approved") return { status: "approved" };
  if (filter === "published") return { status: "published" };
  if (filter === "ready") return { status: "reviewed" };
  if (filter === "not_approved") return { needs_review: false };
  return {};
}

export function normalizeItemError(error) {
  if (error?.status === 409) return "Este item foi alterado ou nao esta no estado esperado. Recarregue os dados.";
  if (error?.status === 422) return error.message || "Revise os campos e bloqueios do item.";
  if (error?.status === 403) return "Falha de autorizacao ou CSRF. Recarregue e tente novamente.";
  if (error?.status === 401) return "Sessao expirada. Entre novamente.";
  if (error?.status >= 500) return "Erro interno ao processar a importacao.";
  if (error?.status === 0) return "A API nao respondeu. Recarregue o item antes de tentar novamente.";
  return error?.message || "Nao foi possivel concluir a acao.";
}

export function updatePayloadFromForm(form) {
  const data = new FormData(form);
  const payload = {
    suggested_name: cleanText(data.get("suggested_name")),
    suggested_category_id: data.get("suggested_category_id") ? Number(data.get("suggested_category_id")) : null,
    suggested_model: cleanText(data.get("suggested_model")),
    suggested_color: cleanText(data.get("suggested_color")),
    status: data.get("status") || null,
    updated_at: data.get("updated_at") || null
  };
  Object.keys(payload).forEach((key) => {
    if (payload[key] === null || payload[key] === "") delete payload[key];
  });
  return payload;
}

export function cleanText(value) {
  if (value === null || value === undefined) return null;
  const cleaned = String(value).replace(/\s+/g, " ").trim();
  return cleaned || null;
}

export function confidence(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Math.round(number * 100)}%`;
}
