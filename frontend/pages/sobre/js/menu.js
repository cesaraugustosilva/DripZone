function initMenu() {
  const header = document.querySelector("[data-header]");
  const toggle = document.querySelector("[data-menu-toggle]");
  const menu = document.querySelector("[data-mobile-menu]");
  let ticking = false;
  let closeTimer = 0;

  if (!header || !toggle || !menu) return;
  if (header.dataset.menuReady === "true") return;
  header.dataset.menuReady = "true";

  const sneakerEntries = [
    { label: "Nike", href: "../catalogo/?marca=nike", brandId: "nike" },
    { label: "Jordan", href: "../catalogo/?marca=jordan", brandId: "jordan" },
    { label: "Adidas", href: "../catalogo/?marca=adidas", brandId: "adidas" },
    { label: "Amiri", href: "../catalogo/?marca=amiri", brandId: "amiri" },
    { label: "Balenciaga", href: "../catalogo/?marca=balenciaga", brandId: "balenciaga" },
    { label: "Louis Vuitton", href: "../catalogo/?marca=louis-vuitton", brandId: "louis-vuitton" },
    { label: "Off-White", href: "../catalogo/?marca=off-white", brandId: "off-white" },
    { label: "New Balance", href: "../catalogo/?marca=new-balance", brandId: "new-balance" },
    { label: "Bape", href: "../catalogo/?marca=bape", brandId: "bape" },
    { label: "Maison Mihara", href: "../catalogo/?marca=maison-mihara-yasuhiro", brandId: "maison-mihara-yasuhiro" },
    { label: "Dior", href: "../catalogo/?marca=dior", brandId: "dior" },
    { label: "Golden Goose", href: "../catalogo/?marca=golden-goose", brandId: "golden-goose" },
    { label: "Lanvin Curb", href: "../catalogo/?modelo=lanvin-curb" },
    { label: "Gucci", href: "../catalogo/?marca=gucci", brandId: "gucci" },
    { label: "Alexander McQueen", href: "../catalogo/?marca=alexander-mcqueen", brandId: "alexander-mcqueen" },
    { label: "Tênis Esportivos", href: "../catalogo/?categoria=tenis-esportivos" }
  ];
  const submenuBrandIds = new Set(["nike", "jordan", "adidas", "new-balance", "golden-goose"]);

  const createAnchor = (className, href, label) => {
    const anchor = document.createElement("a");
    if (className) anchor.className = className;
    anchor.href = href;
    anchor.textContent = label;
    return anchor;
  };

  const catalogModelHref = (brandId, modelId) => `../catalogo/?marca=${encodeURIComponent(brandId)}&modelo=${encodeURIComponent(modelId)}`;

  const getSneakerModelsByBrand = (models = []) => {
    const modelsByBrand = new Map();
    models.forEach((model) => {
      const brandId = String(model.brand_slug || model.brandId || "").trim();
      const modelId = String(model.slug || model.modelId || "").trim();
      const label = String(model.name || model.model || model.modelName || model.slug || "").trim();
      if (model.is_active === false || !submenuBrandIds.has(brandId) || !modelId || !label) return;
      if (!modelsByBrand.has(brandId)) modelsByBrand.set(brandId, new Map());
      if (!modelsByBrand.get(brandId).has(modelId)) modelsByBrand.get(brandId).set(modelId, { label, modelId });
    });
    return modelsByBrand;
  };

  const renderDesktopSneakers = (models) => {
    const menuRoot = document.getElementById("menu-sneakers");
    if (!menuRoot) return;
    const modelsByBrand = getSneakerModelsByBrand(models);
    menuRoot.replaceChildren();
    sneakerEntries.forEach((entry) => {
      const models = entry.brandId ? Array.from(modelsByBrand.get(entry.brandId)?.values() || []) : [];
      if (!models.length) {
        const link = createAnchor("dropdown-menu__link", entry.href, entry.label);
        link.setAttribute("role", "menuitem");
        menuRoot.append(link);
        return;
      }
      const item = document.createElement("div");
      const submenuId = `menu-sneakers-${entry.brandId}`;
      item.className = "dropdown-menu__item has-submenu";
      const link = createAnchor("dropdown-menu__link dropdown-menu__link--button", entry.href, entry.label);
      link.setAttribute("role", "menuitem");
      link.setAttribute("aria-haspopup", "true");
      link.setAttribute("aria-controls", submenuId);
      const arrow = document.createElement("span");
      arrow.className = "dropdown-menu__arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = ">";
      link.replaceChildren(document.createTextNode(entry.label), arrow);
      const submenu = document.createElement("div");
      submenu.className = "dropdown-submenu";
      submenu.id = submenuId;
      submenu.setAttribute("role", "menu");
      const heading = document.createElement("span");
      heading.className = "dropdown-submenu__heading";
      heading.textContent = entry.label;
      const viewAll = createAnchor("dropdown-menu__link dropdown-submenu__view-all", entry.href, `Ver tudo em ${entry.label}`);
      viewAll.setAttribute("role", "menuitem");
      submenu.append(heading, viewAll);
      models.forEach((model) => {
        const modelLink = createAnchor("dropdown-menu__link", catalogModelHref(entry.brandId, model.modelId), model.label);
        modelLink.setAttribute("role", "menuitem");
        submenu.append(modelLink);
      });
      item.append(link, submenu);
      menuRoot.append(item);
    });
  };

  const renderMobileSneakers = (models) => {
    const panel = document.getElementById("mobile-panel-sneakers");
    if (!panel) return;
    const modelsByBrand = getSneakerModelsByBrand(models);
    panel.replaceChildren();
    sneakerEntries.forEach((entry) => {
      const models = entry.brandId ? Array.from(modelsByBrand.get(entry.brandId)?.values() || []) : [];
      if (!models.length) {
        panel.append(createAnchor("", entry.href, entry.label));
        return;
      }
      const item = document.createElement("div");
      const submenuId = `mobile-sneakers-${entry.brandId}`;
      item.className = "mobile-menu__nested";
      item.dataset.submenuItem = "";
      const row = document.createElement("div");
      row.className = "mobile-menu__nested-row";
      row.append(createAnchor("mobile-menu__nested-link", entry.href, entry.label));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "mobile-menu__nested-toggle";
      button.setAttribute("aria-label", `Mostrar modelos ${entry.label}`);
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", submenuId);
      button.dataset.submenuTrigger = "";
      button.textContent = ">";
      row.append(button);
      const submenu = document.createElement("div");
      submenu.className = "mobile-menu__nested-list";
      submenu.id = submenuId;
      submenu.dataset.submenu = "";
      submenu.hidden = true;
      submenu.append(createAnchor("mobile-menu__nested-view-all", entry.href, `Ver tudo em ${entry.label}`));
      models.forEach((model) => submenu.append(createAnchor("", catalogModelHref(entry.brandId, model.modelId), model.label)));
      item.append(row, submenu);
      panel.append(item);
    });
  };

  const renderSneakerMenus = (models = []) => {
    renderDesktopSneakers(models);
    renderMobileSneakers(models);
  };

  const apiUrl = (path) => {
    const backendOrigin = window.DripZoneUtils?.backendOrigin?.() || "";
    return `${backendOrigin}/api/${path.replace(/^\/+/, "")}`;
  };

  const loadSneakerModels = async () => {
    if (window.DripZoneSneakerModelsReady) return window.DripZoneSneakerModelsReady;
    try {
      const response = await fetch(apiUrl("sneakers"), { cache: "no-store" });
      if (!response.ok) return [];
      const data = await response.json();
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  };

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

  const closeSubmenus = (container = document) => {
    container.querySelectorAll?.("[data-submenu-item]").forEach((item) => item.classList.remove("is-subopen"));
    container.querySelectorAll?.("[data-submenu-trigger]").forEach((trigger) => trigger.setAttribute("aria-expanded", "false"));
    container.querySelectorAll?.("[data-submenu]").forEach((submenu) => {
      submenu.hidden = true;
      submenu.setAttribute("aria-hidden", "true");
    });
  };

  const closeDropdowns = () => {
    window.clearTimeout(closeTimer);
    document.querySelectorAll("[data-menu-item]").forEach((item) => item.classList.remove("is-open"));
    document.querySelectorAll("[data-menu-trigger]").forEach((trigger) => trigger.setAttribute("aria-expanded", "false"));
    closeSubmenus();
  };

  const closeMobileAccordions = () => {
    menu.querySelectorAll("[data-mobile-accordion]").forEach((button) => button.setAttribute("aria-expanded", "false"));
    menu.querySelectorAll(".mobile-menu__panel").forEach((panel) => panel.classList.remove("is-open"));
    closeSubmenus(menu);
  };

  const openDropdown = (item) => {
    if (!item) return;
    window.clearTimeout(closeTimer);
    closeDropdowns();
    item.classList.add("is-open");
    item.querySelector("[data-menu-trigger]")?.setAttribute("aria-expanded", "true");
  };

  const scheduleDropdownClose = (item) => {
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(() => {
      item?.classList.remove("is-open");
      item?.querySelector("[data-menu-trigger]")?.setAttribute("aria-expanded", "false");
      closeSubmenus(item);
    }, 180);
  };

  const openSubmenu = (item) => {
    if (!item) return;
    const parent = item.closest("[data-dropdown-menu], .mobile-menu__panel") || document;
    closeSubmenus(parent);
    item.classList.add("is-subopen");
    item.querySelector("[data-submenu-trigger]")?.setAttribute("aria-expanded", "true");
    const submenu = item.querySelector("[data-submenu]");
    if (submenu) {
      submenu.hidden = false;
      submenu.setAttribute("aria-hidden", "false");
    }
  };

  const toggleSubmenu = (item) => {
    if (!item) return;
    const isOpen = item.classList.contains("is-subopen");
    const parent = item.closest("[data-dropdown-menu], .mobile-menu__panel") || document;
    closeSubmenus(parent);
    if (!isOpen) {
      openSubmenu(item);
      return true;
    }
    return false;
  };

  const focusFirstMenuItem = (container) => {
    container?.querySelector('[role="menuitem"]')?.focus();
  };

  const moveFocus = (current, direction) => {
    const menuRoot = current.closest('[role="menu"]');
    const items = Array.from(menuRoot?.querySelectorAll(':scope > [role="menuitem"], :scope > .dropdown-menu__item > [role="menuitem"], :scope > .dropdown-menu__section [role="menuitem"]') || []);
    const index = items.indexOf(current);
    if (index === -1 || !items.length) return;
    const nextIndex = (index + direction + items.length) % items.length;
    items[nextIndex]?.focus();
  };

  const bindMenuItemKeys = (container = document) => {
    container.querySelectorAll('[role="menuitem"]').forEach((item) => {
      if (item.dataset.menuitemReady === "true") return;
      item.dataset.menuitemReady = "true";
      item.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          moveFocus(item, 1);
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          moveFocus(item, -1);
        }
        if (event.key === "ArrowLeft") {
          const submenu = item.closest("[data-submenu]");
          const parent = submenu?.closest("[data-submenu-item]");
          if (parent) {
            event.preventDefault();
            parent.classList.remove("is-subopen");
            parent.querySelector("[data-submenu-trigger]")?.setAttribute("aria-expanded", "false");
            parent.querySelector("[data-submenu-trigger]")?.focus();
          }
        }
      });
    });
  };

  const bindMobileLinks = (container = menu) => {
    container.querySelectorAll("a").forEach((link) => {
      if (link.dataset.mobileCloseReady === "true") return;
      link.dataset.mobileCloseReady = "true";
      link.addEventListener("click", closeMenu);
    });
  };

  toggle.addEventListener("click", () => {
    const isOpen = menu.classList.toggle("is-open");
    header.classList.toggle("is-open", isOpen);
    toggle.classList.toggle("is-active", isOpen);
    document.body.classList.toggle("menu-open", isOpen);
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Fechar menu" : "Abrir menu");
  });

  document.querySelectorAll("[data-menu-item]").forEach((item) => {
    const trigger = item.querySelector("[data-menu-trigger]");
    const dropdown = item.querySelector("[data-dropdown-menu]");

    item.addEventListener("mouseenter", () => {
      window.clearTimeout(closeTimer);
      openDropdown(item);
    });
    item.addEventListener("mouseleave", () => scheduleDropdownClose(item));

    trigger?.addEventListener("click", () => {
      if (item.classList.contains("is-open") && item.matches(":hover")) {
        openDropdown(item);
        return;
      }
      const willOpen = !item.classList.contains("is-open");
      closeDropdowns();
      if (willOpen) openDropdown(item);
    });

    trigger?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
        event.preventDefault();
        openDropdown(item);
        focusFirstMenuItem(dropdown);
      }
    });
  });

  const bindSubmenuItems = (container = document) => {
    container.querySelectorAll("[data-submenu-item]").forEach((item) => {
      if (item.dataset.submenuReady === "true") return;
      item.dataset.submenuReady = "true";
      const trigger = item.querySelector("[data-submenu-trigger]");
      const submenu = item.querySelector("[data-submenu]");

      trigger?.addEventListener("click", (event) => {
        if (trigger.matches("a")) return;
        event.preventDefault();
        toggleSubmenu(item);
      });

      trigger?.addEventListener("keydown", (event) => {
        if (event.key === "ArrowRight" || event.key === "Enter" || event.key === " ") {
          if (trigger.matches("a") && (event.key === "Enter" || event.key === " ")) return;
          event.preventDefault();
          if (toggleSubmenu(item)) focusFirstMenuItem(submenu);
        }
      });
    });
  };

  bindSubmenuItems();

  bindMenuItemKeys();

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
      closeDropdowns();
      closeMobileAccordions();
      toggle.focus();
    }
  });

  bindMobileLinks();

  menu.querySelectorAll("[data-mobile-accordion]").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = button.nextElementSibling;
      const willOpen = button.getAttribute("aria-expanded") !== "true";
      closeMobileAccordions();
      button.setAttribute("aria-expanded", String(willOpen));
      panel?.classList.toggle("is-open", willOpen);
    });
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const insideDesktopMenu = event.target.closest("[data-menu-item]");
    const insideMobileMenu = event.target.closest("[data-mobile-menu]");
    if (!insideDesktopMenu && !insideMobileMenu) closeDropdowns();
    if (!insideMobileMenu && !event.target.closest("[data-menu-toggle]")) closeMenu();
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
    if (window.innerWidth > 900) {
      closeMenu();
      closeMobileAccordions();
    }
    if (window.innerWidth <= 900) closeDropdowns();
  }, { passive: true });

  setScrolled();
  loadSneakerModels().then((models) => {
    renderSneakerMenus(models || []);
    bindSubmenuItems(header);
    bindMenuItemKeys(header);
    bindMobileLinks(menu);
  });
}

window.DripZone = window.DripZone || {};
window.DripZone.initMenu = initMenu;

document.addEventListener("DOMContentLoaded", initMenu);
