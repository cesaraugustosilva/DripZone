window.DripZoneProducts = [];
window.DripZoneProductsLoadError = false;

window.DripZoneProductsReady = (async () => {
  const dataPath = window.DripZoneUtils?.route
    ? window.DripZoneUtils.route("data/products.json")
    : "data/products.json";
  const assetPath = window.DripZoneUtils?.assetPath || ((path) => path);
  const imageUrl = window.DripZoneSecurity?.imageUrl || ((path) => path);
  const safeAssetPath = (path) => {
    const validPath = imageUrl(path, "");
    return validPath ? assetPath(validPath) : "";
  };
  const normalizeProductAssets = (product) => ({
    ...product,
    image: product.image ? safeAssetPath(product.image) || null : product.image,
    gallery: Array.isArray(product.gallery) ? product.gallery.map(safeAssetPath).filter(Boolean) : product.gallery
  });

  try {
    const response = await fetch(dataPath, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    window.DripZoneProducts = Array.isArray(data.products) ? data.products.map(normalizeProductAssets) : [];
    window.DripZoneProductsLoadError = false;
  } catch {
    window.DripZoneProducts = [];
    window.DripZoneProductsLoadError = true;
  }

  return window.DripZoneProducts;
})();
