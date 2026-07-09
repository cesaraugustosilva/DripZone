function initScrollReveal() {
  const elements = document.querySelectorAll(".reveal");
  if (!elements.length) return;

  if (!("IntersectionObserver" in window)) {
    elements.forEach((element) => element.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.16 }
  );

  elements.forEach((element) => observer.observe(element));
}

function initParallax() {
  const media = document.querySelector("[data-parallax]");
  if (!media) return;

  const update = () => {
    const offset = Math.min(window.scrollY * 0.08, 46);
    media.style.transform = `translateY(${offset}px) scale(1.04)`;
  };

  window.addEventListener("scroll", update, { passive: true });
  update();
}

function initImageLoading() {
  document.querySelectorAll("img").forEach((image) => {
    if (image.complete) {
      image.classList.add("is-loaded");
      return;
    }

    image.addEventListener("load", () => image.classList.add("is-loaded"), { once: true });
  });
}

function initRippleButtons() {
  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest(".btn") : null;
    if (!button) return;

    const rect = button.getBoundingClientRect();
    const ripple = document.createElement("span");
    ripple.className = "ripple";
    ripple.style.left = `${event.clientX - rect.left}px`;
    ripple.style.top = `${event.clientY - rect.top}px`;
    button.appendChild(ripple);
    window.setTimeout(() => ripple.remove(), 640);
  });
}

window.DripZone = window.DripZone || {};
window.DripZone.initScrollReveal = initScrollReveal;
window.DripZone.initParallax = initParallax;
window.DripZone.initImageLoading = initImageLoading;
window.DripZone.initRippleButtons = initRippleButtons;
