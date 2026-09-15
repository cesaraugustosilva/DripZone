const DRIPZONE_SITE_URL = "https://dripzone.com.br";

const DRIPZONE_STATIC_DEV_PORT = "5500";
const DRIPZONE_LOCAL_BACKEND_PORT = "8000";

function dzFormatPrice(price) {
  return Number(price || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  });
}

function dzAbsoluteUrl(path) {
  try {
    return new URL(path, window.location.href).href;
  } catch {
    return `${DRIPZONE_SITE_URL}/`;
  }
}

function dzPublicUrl(path = "") {
  const cleanPath = String(path).replace(/^(\.\.\/)+/, "").replace(/^\.\//, "").replace(/^\/+/, "");
  return `${DRIPZONE_SITE_URL}/${cleanPath}`;
}

function dzRootPrefix() {
  const pathname = window.location.pathname.replace(/\\/g, "/");
  const pagesIndex = pathname.indexOf("/pages/");
  if (pagesIndex === -1) return "";

  const afterPages = pathname.slice(pagesIndex + "/pages/".length);
  const segments = afterPages.split("/").filter(Boolean);
  const pageDepth = segments.at(-1)?.includes(".") ? segments.length - 1 : segments.length;
  return "../".repeat(pageDepth + 1);
}

function dzAssetPath(path) {
  const value = String(path || "");
  if (/^(https?:|data:|blob:)/.test(value)) return value;

  const cleanPath = value.replace(/^(\.\.\/)+/, "").replace(/^\.\//, "").replace(/^\/+/, "");
  if (cleanPath.startsWith("uploads/")) {
    const backendOrigin = dzBackendOrigin();
    if (backendOrigin) return `${backendOrigin}/${cleanPath}`;
  }

  return `${dzRootPrefix()}${cleanPath}`;
}

function dzRoute(path = "") {
  return `${dzRootPrefix()}${String(path).replace(/^\/+/, "")}`;
}

function dzIsDevelopmentHost() {
  return ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
}

function dzIsStaticLocalDevelopment() {
  return dzIsDevelopmentHost() && window.location.port === DRIPZONE_STATIC_DEV_PORT;
}

function dzBackendOrigin() {
  if (!dzIsStaticLocalDevelopment()) return "";

  const hostname = window.location.hostname === "127.0.0.1" ? "127.0.0.1" : "localhost";
  return `${window.location.protocol}//${hostname}:${DRIPZONE_LOCAL_BACKEND_PORT}`;
}

function initImageFallbacks() {
  document.addEventListener(
    "error",
    (event) => {
      const image = event.target;
      if (!(image instanceof HTMLImageElement) || image.dataset.fallbackApplied) return;
      if (image.closest("[data-featured-brands]")) return;

      if (dzIsDevelopmentHost()) {
        console.warn("DripZone: imagem publica falhou; usando placeholder.", image.currentSrc || image.src);
      }
      image.dataset.fallbackApplied = "true";
      image.classList.add("is-broken");
      image.src = dzAssetPath("assets/images/logo/dripzone-logo.png");
      image.alt = image.alt || "Logo DripZone";
    },
    true
  );
}

function initGlobalErrorHandling() {
  window.addEventListener("error", (event) => {
    if (event.target instanceof HTMLImageElement) return;
    console.warn("DripZone: erro inesperado capturado.", event.message);
  });

  window.addEventListener("unhandledrejection", () => {
    console.warn("DripZone: uma operação assíncrona falhou e foi contida.");
  });
}

window.DripZoneUtils = {
  absoluteUrl: dzAbsoluteUrl,
  assetPath: dzAssetPath,
  backendOrigin: dzBackendOrigin,
  formatPrice: dzFormatPrice,
  publicUrl: dzPublicUrl,
  rootPrefix: dzRootPrefix,
  route: dzRoute,
  siteUrl: DRIPZONE_SITE_URL
};

initImageFallbacks();
initGlobalErrorHandling();
