(function () {
  const PLACEHOLDER_IMAGE = "../../assets/images/logo/dripzone-logo.png";
  const SAFE_PRODUCT_ID = /^[a-z0-9-]+$/;
  const BLOCKED_PROTOCOLS = new Set(["javascript:", "data:", "vbscript:", "file:"]);
  const ALLOWED_REMOTE_PROTOCOLS = new Set(["http:", "https:"]);

  function text(value, fallback = "") {
    if (value === null || value === undefined) return fallback;
    return String(value);
  }

  function productId(value) {
    const normalized = text(value).trim().toLowerCase();
    return SAFE_PRODUCT_ID.test(normalized) ? normalized : "";
  }

  function safePath(value, { allowRemote = true, fallback = "" } = {}) {
    const raw = text(value).trim();
    if (!raw) return fallback;
    const lowered = raw.replace(/[\u0000-\u001f\u007f\s]+/g, "").toLowerCase();
    for (const protocol of BLOCKED_PROTOCOLS) {
      if (lowered.startsWith(protocol)) return fallback;
    }
    try {
      const parsed = new URL(raw, window.location.href);
      if (!allowRemote && parsed.origin !== window.location.origin) return fallback;
      if (parsed.origin === window.location.origin || ALLOWED_REMOTE_PROTOCOLS.has(parsed.protocol)) {
        return raw;
      }
      return fallback;
    } catch {
      return fallback;
    }
  }

  function imageUrl(value, fallback = PLACEHOLDER_IMAGE) {
    return safePath(value, { allowRemote: true, fallback }) || fallback;
  }

  function productHref(id, basePath = "../produto/") {
    const safeId = productId(id);
    const url = new URL(basePath, window.location.href);
    if (safeId) url.searchParams.set("id", safeId);
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function assetImage(value, fallback = PLACEHOLDER_IMAGE) {
    const valid = imageUrl(value, fallback);
    const assetPath = window.DripZoneUtils?.assetPath || ((path) => path);
    return assetPath(valid);
  }

  function publicUrl(value, fallback = "assets/images/logo/dripzone-logo.png") {
    const valid = safePath(value, { allowRemote: true, fallback });
    const publicUrl = window.DripZoneUtils?.publicUrl || ((path = "") => `https://dripzone.com.br/${String(path).replace(/^(\.\.\/)+/, "")}`);
    return publicUrl(valid);
  }

  function setSafeImage(image, src, alt = "", fallback = PLACEHOLDER_IMAGE) {
    image.src = assetImage(src, fallback);
    image.alt = text(alt);
  }

  function normalizeQuantity(value) {
    return Math.min(Math.max(Number(value) || 1, 1), 10);
  }

  function isPurchasable(product) {
    return Boolean(product?.purchasable) && Number.isFinite(product.price) && product.price > 0;
  }

  function safeCartItem(item, products) {
    if (!item || !Array.isArray(products)) return null;
    const product = products.find((candidate) => candidate.id === item.id);
    if (!product) return null;
    if (!isPurchasable(product)) return null;
    const sizes = Array.isArray(product.sizes) ? product.sizes.map((size) => text(size)) : [];
    const requestedSize = text(item.size || sizes[0] || "");
    const size = sizes.includes(requestedSize) ? requestedSize : (sizes[0] || requestedSize.slice(0, 80));
    const id = productId(product.id);
    if (!id) return null;
    return {
      key: `${id}-${size}`,
      id,
      name: text(product.name, "Produto"),
      price: product.price,
      image: imageUrl(product.image),
      size,
      quantity: normalizeQuantity(item.quantity)
    };
  }

  window.DripZoneSecurity = {
    assetImage,
    imageUrl,
    isPurchasable,
    normalizeQuantity,
    productHref,
    productId,
    publicUrl,
    safeCartItem,
    safePath,
    setSafeImage,
    text
  };
})();
