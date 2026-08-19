function initSlider() {
  const slider = document.querySelector("[data-slider]");
  if (!slider) return;

  const track = slider.querySelector("[data-slider-track]");
  const prev = slider.querySelector("[data-slider-prev]");
  const next = slider.querySelector("[data-slider-next]");

  if (!track || !prev || !next) return;

  let index = 0;
  let resizeFrame = 0;

  const getVisibleItems = () => {
    if (window.innerWidth <= 640) return 1;
    if (window.innerWidth <= 1120) return 2;
    return 4;
  };

  const update = () => {
    const total = track.children.length;
    const visible = getVisibleItems();
    const maxIndex = Math.max(total - visible, 0);
    index = Math.max(Math.min(index, maxIndex), 0);
    const card = track.children[0];
    const gap = parseFloat(getComputedStyle(track).gap) || 0;
    const step = card ? card.getBoundingClientRect().width + gap : 0;

    track.style.transform = `translateX(${-index * step}px)`;
    prev.disabled = index === 0;
    next.disabled = index === maxIndex;
  };

  prev.addEventListener("click", () => {
    index = Math.max(index - 1, 0);
    update();
  });

  next.addEventListener("click", () => {
    index += 1;
    update();
  });

  window.addEventListener("resize", () => {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(update);
  });
  update();
}

window.DripZone = window.DripZone || {};
window.DripZone.initSlider = initSlider;
