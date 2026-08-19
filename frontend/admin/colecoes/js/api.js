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
  const timeout = window.setTimeout(() => controller.abort(), ADMIN_CONFIG.apiTimeoutMs);
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
    return null;
  }
}

function apiErrorFromResponse(status, data) {
  const error = data?.error || {};
  const details = error.details || data?.detail || null;
  const code = error.code || codeForStatus(status);
  const message = error.message || messageForStatus(status, details);
  return new ApiError(message, { status, code, details });
}

function codeForStatus(status) {
  return {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "SERVER_ERROR"
  }[status] || "API_ERROR";
}

function messageForStatus(status, details) {
  if (status === 400) return "Dados invalidos. Revise as informacoes enviadas.";
  if (status === 401) return "Sua sessao expirou. Entre novamente.";
  if (status === 403) return "Falha de autorizacao ou CSRF. Recarregue a pagina e tente novamente.";
  if (status === 404) return "Endpoint nao encontrado.";
  if (status === 409) return "Registro duplicado ou em uso.";
  if (status === 422) return validationMessage(details);
  if (status >= 500) return "Erro interno do servidor. Tente novamente em instantes.";
  return "Erro na API.";
}

function validationMessage(details) {
  if (!Array.isArray(details) || details.length === 0) return "Preencha os campos obrigatorios corretamente.";
  const first = details[0];
  const field = Array.isArray(first?.loc) ? first.loc.filter((item) => item !== "body").join(".") : "";
  return field ? `Campo invalido: ${field}.` : "Preencha os campos obrigatorios corretamente.";
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
  } catch (error) {
    return { state: "disconnected", label: "API desconectada", error };
  }
}

export async function getProducts(params = {}) {
  const query = new URLSearchParams(params);
  const data = await request(`/products${query.size ? `?${query}` : ""}`);
  return data.items || [];
}

export async function getProductsPage(params = {}) {
  const query = new URLSearchParams(params);
  return request(`/products${query.size ? `?${query}` : ""}`);
}

export async function getProductById(id) {
  return request(`/products/${encodeURIComponent(id)}`);
}

export async function createProduct(payload) {
  return request("/products", { method: "POST", body: payload });
}

export async function updateProduct(id, payload) {
  return request(`/products/${encodeURIComponent(id)}`, { method: "PUT", body: payload });
}

export async function deleteProduct(id) {
  return request(`/products/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function publishProduct(id) {
  return request(`/products/${encodeURIComponent(id)}/publish`, { method: "POST" });
}

export async function unpublishProduct(id) {
  return request(`/products/${encodeURIComponent(id)}/unpublish`, { method: "POST" });
}

export async function uploadProductImage(id, formData) {
  return request(`/products/${encodeURIComponent(id)}/images`, { method: "POST", body: formData });
}

export const getBrands = () => request("/brands");
export const getCategories = () => request("/categories");
export const getCollections = () => request("/collections");
export const getAccessories = () => request("/accessories");
export const getSneakers = () => request("/sneakers");
export const getImports = () => request("/imports");
export const getActivities = () => request("/activities");
export const getSettings = () => request("/settings");
export const updateSettings = (payload) => request("/settings", { method: "PUT", body: payload });

export async function createResource(type, payload) {
  return request(`/${type}`, { method: "POST", body: payload });
}

export async function updateResource(type, id, payload) {
  return request(`/${type}/${encodeURIComponent(id)}`, { method: "PUT", body: payload });
}

export async function deleteResource(type, id) {
  return request(`/${type}/${encodeURIComponent(id)}`, { method: "DELETE" });
}
