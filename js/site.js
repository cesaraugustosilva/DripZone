const DRIPZONE_SITE_URL = "https://dripzone.com.br";

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

function dzAssetPath(path) {
  const isPage = window.location.pathname.includes("/pages/");
  return `${isPage ? "../" : ""}${path}`;
}

function initImageFallbacks() {
  document.addEventListener(
    "error",
    (event) => {
      const image = event.target;
      if (!(image instanceof HTMLImageElement) || image.dataset.fallbackApplied) return;

      image.dataset.fallbackApplied = "true";
      image.classList.add("is-broken");
      image.src = dzAssetPath("img/logo/dripzone-logo.png");
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
  formatPrice: dzFormatPrice,
  publicUrl: dzPublicUrl,
  siteUrl: DRIPZONE_SITE_URL
};

initImageFallbacks();
initGlobalErrorHandling();
