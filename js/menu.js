function initMenu() {
  const header = document.querySelector("[data-header]");
  const toggle = document.querySelector("[data-menu-toggle]");
  const menu = document.querySelector("[data-mobile-menu]");
  let ticking = false;

  if (!header || !toggle || !menu) return;

  const setScrolled = () => {
    const isScrolled = window.scrollY > 12;
    header.classList.toggle("is-scrolled", isScrolled);
    header.classList.toggle("is-compact", isScrolled);
  };

  const closeMenu = () => {
    menu.classList.remove("is-open");
    header.classList.remove("is-open");
    toggle.classList.remove("is-active");
    document.body.classList.remove("menu-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Abrir menu");
  };

  toggle.addEventListener("click", () => {
    const isOpen = menu.classList.toggle("is-open");
    header.classList.toggle("is-open", isOpen);
    toggle.classList.toggle("is-active", isOpen);
    document.body.classList.toggle("menu-open", isOpen);
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Fechar menu" : "Abrir menu");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });

  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  window.addEventListener(
    "scroll",
    () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        setScrolled();
        ticking = false;
      });
    },
    { passive: true }
  );
  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) closeMenu();
  }, { passive: true });

  setScrolled();
}

window.DripZone = window.DripZone || {};
window.DripZone.initMenu = initMenu;
