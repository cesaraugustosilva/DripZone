export const STEPS = {
  SOURCE: "source",
  ANALYZING: "analyzing",
  PREVIEW: "preview",
  REVIEW: "review",
  READY_TO_PUBLISH: "ready_to_publish",
  PUBLISHING: "publishing",
  FAILED: "failed",
  FINISHED: "finished"
};

export const stepOrder = [STEPS.SOURCE, STEPS.ANALYZING, STEPS.PREVIEW, STEPS.REVIEW, STEPS.READY_TO_PUBLISH, STEPS.PUBLISHING, STEPS.FINISHED];

export const stepDefinitions = {
  [STEPS.SOURCE]: {
    label: "Origem",
    description: "Informe marca e URL Yupoo.",
    canGoBack: true,
    resumable: false
  },
  [STEPS.ANALYZING]: {
    label: "Analise",
    description: "Aguardando a pre-visualizacao do backend.",
    canGoBack: false,
    resumable: true
  },
  [STEPS.PREVIEW]: {
    label: "Preview",
    description: "Resumo da importacao gerada.",
    canGoBack: true,
    resumable: true
  },
  [STEPS.REVIEW]: {
    label: "Revisao",
    description: "Revise, edite e aprove itens reais.",
    canGoBack: true,
    resumable: true
  },
  [STEPS.READY_TO_PUBLISH]: {
    label: "Publicar",
    description: "Confirme a publicacao dos itens aprovados.",
    canGoBack: true,
    resumable: true
  },
  [STEPS.PUBLISHING]: {
    label: "Publicando",
    description: "Criando produtos a partir dos itens aprovados.",
    canGoBack: false,
    resumable: true
  },
  [STEPS.FINISHED]: {
    label: "Concluido",
    description: "Importacao finalizada.",
    canGoBack: false,
    resumable: true
  },
  [STEPS.FAILED]: {
    label: "Falha",
    description: "A importacao nao foi concluida.",
    canGoBack: true,
    resumable: true
  }
};

export const statusMap = {
  draft: {
    step: STEPS.SOURCE,
    action: "Continuar",
    nextStep: STEPS.ANALYZING,
    canReturn: true,
    resumable: true
  },
  scanning: {
    step: STEPS.ANALYZING,
    action: "Ver analise",
    nextStep: STEPS.PREVIEW,
    canReturn: false,
    resumable: true
  },
  preview_ready: {
    step: STEPS.REVIEW,
    action: "Revisar",
    nextStep: STEPS.REVIEW,
    canReturn: true,
    resumable: true
  },
  failed: {
    step: STEPS.FAILED,
    action: "Ver falha",
    nextStep: STEPS.SOURCE,
    canReturn: true,
    resumable: true
  },
  cancelled: {
    step: STEPS.FAILED,
    action: "Ver detalhes",
    nextStep: STEPS.SOURCE,
    canReturn: true,
    resumable: true
  }
};

export const flowState = {
  currentStep: STEPS.SOURCE,
  currentImportId: null,
  currentImport: null,
  sourceType: "yupoo",
  sourceUrl: "",
  selectedBrandId: "",
  loading: false,
  error: null,
  lastUpdatedAt: null
};

export function resolveStepFromImport(importRecord) {
  if (!importRecord) return STEPS.SOURCE;
  if (importRecord.status === "failed" || importRecord.status === "cancelled") return STEPS.FAILED;
  if (importRecord.status === "scanning") return STEPS.ANALYZING;
  if (importRecord.status === "draft") return STEPS.SOURCE;
  if (importRecord.items_published > 0 || importRecord.items_publish_failed > 0) return STEPS.FINISHED;
  if (importRecord.publishing_started_at && !importRecord.publishing_finished_at) return STEPS.PUBLISHING;
  if (importRecord.items_approved > 0) return STEPS.READY_TO_PUBLISH;
  if (importRecord.status === "preview_ready") return STEPS.REVIEW;
  return statusMap[importRecord.status]?.step || STEPS.SOURCE;
}

export function setCurrentImport(importRecord) {
  flowState.currentImport = importRecord || null;
  flowState.currentImportId = importRecord?.id || null;
  flowState.currentStep = importRecord ? resolveStepFromImport(importRecord) : STEPS.SOURCE;
  flowState.sourceUrl = importRecord?.normalized_source_url || importRecord?.source_url || "";
  flowState.selectedBrandId = importRecord?.brand_id || "";
  flowState.lastUpdatedAt = importRecord?.updated_at || null;
  flowState.error = null;
  return flowState;
}

export function resetFlow() {
  flowState.currentStep = STEPS.SOURCE;
  flowState.currentImportId = null;
  flowState.currentImport = null;
  flowState.sourceType = "yupoo";
  flowState.sourceUrl = "";
  flowState.selectedBrandId = "";
  flowState.loading = false;
  flowState.error = null;
  flowState.lastUpdatedAt = null;
  return flowState;
}

export function navigateToStep(step) {
  if (!canTransition(flowState.currentStep, step)) return false;
  flowState.currentStep = step;
  return true;
}

export function canTransition(currentStep, nextStep) {
  if (currentStep === nextStep) return true;
  if (nextStep === STEPS.SOURCE) return true;
  if (currentStep === STEPS.PREVIEW && nextStep === STEPS.REVIEW) return true;
  if (currentStep === STEPS.REVIEW && nextStep === STEPS.READY_TO_PUBLISH) return true;
  if (currentStep === STEPS.READY_TO_PUBLISH && nextStep === STEPS.REVIEW) return true;
  if (currentStep === STEPS.READY_TO_PUBLISH && nextStep === STEPS.PUBLISHING) return true;
  if (currentStep === STEPS.PUBLISHING && nextStep === STEPS.FINISHED) return true;
  if (currentStep === STEPS.FAILED && nextStep === STEPS.SOURCE) return true;
  return false;
}

export function actionForImport(importRecord) {
  return statusMap[importRecord?.status]?.action || "Ver detalhes";
}

export function stepIndex(step) {
  const index = stepOrder.indexOf(step);
  return index < 0 ? 0 : index;
}
