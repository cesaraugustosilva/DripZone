document.addEventListener("DOMContentLoaded", () => {
  const app = window.DripZone || {};

  app.initMenu?.();
  app.initSlider?.();
  app.initScrollReveal?.();
  app.initParallax?.();
  app.initImageLoading?.();
  app.initRippleButtons?.();
});
