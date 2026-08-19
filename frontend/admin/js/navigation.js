import { getApiStatus } from "./api.js?v=api-base-3000-20260730";

const navSections = [
  {
    items: [{ href: "/admin/", label: "Dashboard", icon: "D" }]
  },
  {
    label: "Catalogo",
    items: [
      { href: "/admin/produtos/", label: "Produtos", icon: "P" },
      { href: "/admin/marcas/", label: "Marcas", icon: "M" },
      { href: "/admin/categorias/", label: "Categorias", icon: "C" },
      { href: "/admin/colecoes/", label: "Colecoes", icon: "O" }
    ]
  },
  {
    label: "Importacoes",
    items: [
      { href: "/admin/importacoes/", label: "Nova importacao", icon: "N" },
      { href: "/admin/importacoes/#historico", label: "Historico", icon: "H" },
      { label: "Revisoes", icon: "R", badge: "Em breve" },
      { label: "Publicacoes", icon: "B", badge: "Em breve" }
    ]
  },
  {
    label: "Configuracoes",
    items: [{ href: "/admin/configuracoes/", label: "Sistema", icon: "S" }]
  }
];

export function initNavigation(pageMeta = {}) {
  renderShell(pageMeta);
  bindDrawer();
  updateApiStatus();
}

function renderShell({ title = "Dashboard", breadcrumb = "Admin", description = "" } = {}) {
  const sidebar = document.querySelector("[data-admin-sidebar]");
  const nav = document.querySelector("[data-admin-nav]");
  const pageTitle = document.querySelector("[data-page-title]");
  const pageBreadcrumb = document.querySelector("[data-page-breadcrumb]");
  const pageDescription = document.querySelector("[data-page-description]");

  if (pageTitle) pageTitle.textContent = title;
  if (pageBreadcrumb) pageBreadcrumb.textContent = breadcrumb;
  if (pageDescription) {
    pageDescription.textContent = description;
    pageDescription.hidden = !description;
  }

  sidebar?.setAttribute("aria-label", "Navegacao administrativa");
  nav?.setAttribute("aria-label", "Principal");

  if (sidebar && nav && nav.children.length === 0) {
    navSections.forEach((section) => {
      const group = document.createElement("div");
      group.className = "admin-nav__group";

      if (section.label) {
        const heading = document.createElement("p");
        heading.className = "admin-nav__heading";
        heading.textContent = section.label;
        group.append(heading);
      }

      section.items.forEach((route) => group.append(createNavItem(route)));
      nav.append(group);
    });
  }
}

function createNavItem(route) {
  const element = route.href ? document.createElement("a") : document.createElement("button");
  element.className = route.badge ? "admin-nav__item is-disabled" : "admin-nav__item";
  element.innerHTML = `<span class="admin-icon" aria-hidden="true">${route.icon}</span><span class="admin-nav__label"></span>`;
  element.querySelector(".admin-nav__label").textContent = route.label;

  if (route.href) {
    element.href = route.href;
    if (isActive(route.href)) element.setAttribute("aria-current", "page");
    element.addEventListener("click", closeDrawerAfterNavigation);
  } else {
    element.type = "button";
    element.disabled = true;
  }

  if (route.badge) {
    const badge = document.createElement("span");
    badge.className = "admin-nav__badge";
    badge.textContent = route.badge;
    element.append(badge);
  }

  return element;
}

function isActive(href) {
  const current = window.location.pathname.replace(/index\.html$/, "");
  const [normalizedHref, hash] = href.split("#");
  if (normalizedHref === "/admin/") return current === "/admin/" || current === "/admin";
  if (hash) return current.startsWith(normalizedHref) && window.location.hash === `#${hash}`;
  if (normalizedHref === "/admin/importacoes/" && window.location.hash) return false;
  return current.startsWith(normalizedHref);
}

function closeDrawerAfterNavigation() {
  if (window.matchMedia("(min-width: 901px)").matches) return;
  const sidebar = document.querySelector("[data-admin-sidebar]");
  const overlay = document.querySelector("[data-admin-overlay]");
  const open = document.querySelector("[data-sidebar-open]");
  sidebar?.classList.remove("is-open");
  overlay?.classList.remove("is-open");
  open?.setAttribute("aria-expanded", "false");
  document.body.classList.remove("admin-drawer-open");
}

function bindDrawer() {
  const sidebar = document.querySelector("[data-admin-sidebar]");
  const overlay = document.querySelector("[data-admin-overlay]");
  const open = document.querySelector("[data-sidebar-open]");
  const close = document.querySelector("[data-sidebar-close]");
  if (!sidebar || !overlay || !open) return;
  open.setAttribute("aria-controls", sidebar.id || "admin-sidebar");
  open.setAttribute("aria-expanded", "false");

  const openDrawer = () => {
    sidebar.classList.add("is-open");
    overlay.classList.add("is-open");
    open.setAttribute("aria-expanded", "true");
    document.body.classList.add("admin-drawer-open");
    close?.focus();
  };

  const closeDrawer = () => {
    sidebar.classList.remove("is-open");
    overlay.classList.remove("is-open");
    open.setAttribute("aria-expanded", "false");
    document.body.classList.remove("admin-drawer-open");
    open.focus();
  };

  open.addEventListener("click", openDrawer);
  close?.addEventListener("click", closeDrawer);
  overlay.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("is-open")) closeDrawer();
  });
}

async function updateApiStatus() {
  const status = document.querySelector("[data-api-status]");
  if (!status) return;

  status.textContent = "Conectando";
  const result = await getApiStatus();
  status.textContent = result.label;
  status.dataset.state = result.state;
}
