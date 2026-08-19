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
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const error = data?.error || {};
      throw new ApiError(error.message || "Erro na API.", { status: response.status, code: error.code || "API_ERROR", details: error.details || null });
    }
    return data;
  } catch (error) {
    window.clearTimeout(timeout);
    if (error instanceof ApiError) throw error;
    throw new ApiError("API offline ou indisponível.", { status: 0, code: "API_OFFLINE" });
  }
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
