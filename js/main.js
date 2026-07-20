document.addEventListener("DOMContentLoaded", () => {
  const app = window.DripZone || {};
  const newsletterForm = document.querySelector("[data-newsletter-form]");
  const newsletterMessage = document.querySelector("[data-newsletter-message]");
  const searchForm = document.querySelector("[data-header-search-form]");
  const searchInput = document.querySelector("[data-header-search-input]");
  const searchClose = document.querySelector("[data-header-search-close]");
  const getSearchTriggers = () => document.querySelectorAll("[data-header-search-trigger]");
  let activeSearchTrigger = null;

  const setSearchExpanded = (isExpanded) => {
    getSearchTriggers().forEach((trigger) => {
      trigger.setAttribute("aria-expanded", String(isExpanded));
    });
  };

  const openHeaderSearch = (trigger) => {
    if (!searchForm || !searchInput) return;
    activeSearchTrigger = trigger || activeSearchTrigger;
    searchForm.hidden = false;
    searchForm.classList.add("is-open");
    setSearchExpanded(true);
    searchInput.focus({ preventScroll: true });
    window.requestAnimationFrame(() => searchInput.focus());
  };

  const closeHeaderSearch = () => {
    if (!searchForm) return;
    searchForm.classList.remove("is-open");
    searchForm.hidden = true;
    setSearchExpanded(false);
    activeSearchTrigger?.focus();
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest?.("[data-header-search-trigger]");
    if (!trigger) return;

    const isOpen = searchForm?.classList.contains("is-open");
    if (isOpen) {
      closeHeaderSearch();
      return;
    }

    openHeaderSearch(trigger);
  });

  searchClose?.addEventListener("click", closeHeaderSearch);

  searchForm?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeHeaderSearch();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && searchForm?.classList.contains("is-open")) {
      event.preventDefault();
      closeHeaderSearch();
    }
  });

  searchForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const term = searchInput?.value.trim() || "";
    if (!term) {
      searchInput?.focus();
      return;
    }

    const params = new URLSearchParams();
    params.set("q", term);
    const catalogUrl = window.DripZoneUtils?.route ? window.DripZoneUtils.route("pages/catalogo/") : "pages/catalogo/";
    window.location.href = `${catalogUrl}?${params.toString()}`;
  });

  newsletterForm?.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!newsletterForm.checkValidity()) {
      if (newsletterMessage) {
        newsletterMessage.hidden = true;
        newsletterMessage.textContent = "";
      }

      newsletterForm.reportValidity();
      return;
    }

    if (newsletterMessage) {
      newsletterMessage.textContent = "Cadastro de newsletter em breve. Seu e-mail não foi enviado.";
      newsletterMessage.hidden = false;
    }
  });

  app.initMenu?.();
  app.initSlider?.();
  app.initScrollReveal?.();
  app.initParallax?.();
  app.initImageLoading?.();
  app.initRippleButtons?.();
});
