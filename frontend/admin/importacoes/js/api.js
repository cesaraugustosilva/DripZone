import { ADMIN_CONFIG } from "../../js/config.js";

export class ApiError extends Error {
  constructor(message, { status = 0, code = "API_ERROR", details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let csrfToken = null;

function isLoginPage() {
  return location.pathname.startsWith("/admin/login");
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs || ADMIN_CONFIG.apiTimeoutMs;
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const method = options.method || "GET";
  const headers = new Headers(options.headers || {});
  const body = options.body instanceof FormData ? options.body : options.body === undefined ? undefined : JSON.stringify(options.body);
  if (body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!options.skipCsrf && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    if (!csrfToken) await refreshCsrf();
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }

  try {
    const requestUrl = `${ADMIN_CONFIG.apiBaseUrl}${path}`;
    if (ADMIN_CONFIG.isDevelopment && path === "/auth/login") console.log("Login URL:", requestUrl);
    const response = await fetch(requestUrl, {
      method,
      body,
      headers,
      credentials: "include",
      signal: controller.signal
    });
    window.clearTimeout(timeout);
    if (response.status === 401 && !isLoginPage()) {
      location.href = "/admin/login/";
      throw new ApiError("Sessão expirada.", { status: 401, code: "UNAUTHORIZED" });
    }
    const text = await response.text();
    const data = parseResponseBody(text);
    if (!response.ok) {
      throw apiErrorFromResponse(response.status, data);
    }
    return data;
  } catch (error) {
    window.clearTimeout(timeout);
    if (error instanceof ApiError) throw error;
    throw new ApiError("API offline ou indisponível.", { status: 0, code: "API_OFFLINE" });
  }
}

function parseResponseBody(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

function apiErrorFromResponse(status, data) {
  const error = data?.error || {};
  const detailMessage = detailToMessage(data?.detail);
  const message = error.message || data?.message || detailMessage || defaultErrorMessage(status);
  return new ApiError(message, {
    status,
    code: error.code || data?.code || "API_ERROR",
    details: error.details || data?.detail || null
  });
}

function detailToMessage(detail) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) return detail.message || detail.msg || null;
  if (!Array.isArray(detail)) return null;
  return detail
    .map((item) => item?.msg || item?.message)
    .filter(Boolean)
    .join(" ");
}

function defaultErrorMessage(status) {
  if (status === 400) return "Dados invalidos.";
  if (status === 401) return "Sessao expirada. Entre novamente.";
  if (status === 403) return "Falha de autorizacao ou CSRF.";
  if (status === 404) return "Recurso nao encontrado.";
  if (status === 409) return "Conflito com um registro existente.";
  if (status === 422) return "Erro de validacao.";
  if (status >= 500) return "Erro interno do servidor.";
  return "Erro na API.";
}

export async function refreshCsrf() {
  const data = await request("/auth/csrf", { skipCsrf: true }).catch(() => null);
  csrfToken = data?.csrf_token || null;
  return csrfToken;
}

export async function login(email, password) {
  const data = await request("/auth/login", { method: "POST", body: { email, password }, skipCsrf: true });
  csrfToken = null;
  await refreshCsrf();
  return data;
}

export async function logout() {
  await request("/auth/logout", { method: "POST" });
  csrfToken = null;
}

export async function getSession() {
  return request("/auth/session");
}

export async function getApiStatus() {
  try {
    const data = await request("/status");
    return { state: "connected", label: "API conectada", data };
  } catch {
    return { state: "disconnected", label: "API desconectada" };
  }
}

export const getBrands = () => request("/brands");
export const getCategories = () => request("/categories");
export const getImports = (params = {}) => {
  const query = new URLSearchParams(params);
  return request(`/imports${query.size ? `?${query}` : ""}`);
};
export const createImportPreview = (payload) => request("/imports/preview", { method: "POST", body: payload, timeoutMs: Math.max(ADMIN_CONFIG.apiTimeoutMs, 120000) });
export const getImportById = (id) => request(`/imports/${encodeURIComponent(id)}`);
export const getImportItems = (id, params = {}) => {
  const query = new URLSearchParams(params);
  return request(`/imports/${encodeURIComponent(id)}/items${query.size ? `?${query}` : ""}`);
};
export const getImportItem = (importId, itemId) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}`);
export const updateImportItem = (importId, itemId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}`, { method: "PATCH", body: payload });
export const getImportImages = (importId, itemId) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/images`);
export const updateImportImage = (importId, itemId, imageId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/images/${encodeURIComponent(imageId)}`, { method: "PATCH", body: payload });
export const reorderImportImages = (importId, itemId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/images/reorder`, { method: "POST", body: payload });
export const getImportImageIngestionReadiness = (importId, itemId, imageId) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/images/${encodeURIComponent(imageId)}/ingestion-readiness`);
export const ingestImportImage = (importId, itemId, imageId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/images/${encodeURIComponent(imageId)}/ingest`, { method: "POST", body: payload });
export const ingestSelectedImportImages = (importId, itemId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/images/ingest-selected`, { method: "POST", body: payload });
export const getImportPublicationReadiness = (importId, itemId) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/publication-readiness`);
export const approveImportItem = (importId, itemId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/approve`, { method: "POST", body: payload });
export const unapproveImportItem = (importId, itemId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/unapprove`, { method: "POST", body: payload });
export const publishImportItem = (importId, itemId, payload) => request(`/imports/${encodeURIComponent(importId)}/items/${encodeURIComponent(itemId)}/publish`, { method: "POST", body: payload });
