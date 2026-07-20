function initMenu() {
  const header = document.querySelector("[data-header]");
  const toggle = document.querySelector("[data-menu-toggle]");
  const menu = document.querySelector("[data-mobile-menu]");
  let ticking = false;
  let closeTimer = 0;

  if (!header || !toggle || !menu) return;
  if (header.dataset.menuReady === "true") return;
  header.dataset.menuReady = "true";

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
    if (submenu) submenu.hidden = false;
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

  document.querySelectorAll("[data-submenu-item]").forEach((item) => {
    const trigger = item.querySelector("[data-submenu-trigger]");
    const submenu = item.querySelector("[data-submenu]");

    trigger?.addEventListener("click", () => toggleSubmenu(item));

    trigger?.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (toggleSubmenu(item)) focusFirstMenuItem(submenu);
      }
    });
  });

  document.querySelectorAll('[role="menuitem"]').forEach((item) => {
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

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
      closeDropdowns();
      closeMobileAccordions();
      toggle.focus();
    }
  });

  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

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
}

window.DripZone = window.DripZone || {};
window.DripZone.initMenu = initMenu;

document.addEventListener("DOMContentLoaded", initMenu);
