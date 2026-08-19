function resolveDefaultApiBaseUrl() {
  if (!["localhost", "127.0.0.1", ""].includes(window.location.hostname)) {
    return "/api";
  }
  return "/api";
}

export const API_BASE_URL = window.DRIPZONE_API_BASE_URL ?? window.API_BASE_URL ?? resolveDefaultApiBaseUrl();
export const IS_DEVELOPMENT = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);

export const ADMIN_CONFIG = {
  mode: "api",
  apiBaseUrl: API_BASE_URL,
  apiEnabled: true,
  isDevelopment: IS_DEVELOPMENT,
  apiTimeoutMs: 4500,
  features: {
    productPersistence: true,
    imageUpload: true,
    imports: true,
    authentication: true
  },
  storageKeys: {
    sidebarCollapsed: "dripzone-admin-sidebar-collapsed",
    tableDensity: "dripzone-admin-table-density",
    theme: "dripzone-admin-theme"
  }
};

if (ADMIN_CONFIG.isDevelopment) {
  console.log(`[DripZone Admin] API: ${API_BASE_URL}`);
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then((registrations) => registrations.forEach((registration) => registration.unregister()))
      .catch(() => {});
  }
  if ("caches" in window) {
    caches.keys()
      .then((keys) => keys.filter((key) => key.toLowerCase().includes("dripzone")).forEach((key) => caches.delete(key)))
      .catch(() => {});
  }
}
