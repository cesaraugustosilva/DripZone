window.DripZoneProducts = [];
window.DripZoneProductsLoadError = false;

window.DripZoneProductsReady = (async () => {
  const dataPath = window.DripZoneUtils?.route
    ? window.DripZoneUtils.route("data/products.json")
    : "data/products.json";
  const assetPath = window.DripZoneUtils?.assetPath || ((path) => path);
  const normalizeProductAssets = (product) => ({
    ...product,
    image: product.image ? assetPath(product.image) : product.image,
    gallery: Array.isArray(product.gallery) ? product.gallery.map((image) => assetPath(image)) : product.gallery
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
