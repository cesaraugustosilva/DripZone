import { getApiStatus } from "./api.js?v=api-base-3000-20260730";

const routes = [
  { href: "/admin/", label: "Dashboard", icon: "D" },
  { href: "/admin/produtos/", label: "Produtos", icon: "P" },
  { href: "/admin/importacoes/", label: "Importações", icon: "I" },
  { href: "/admin/marcas/", label: "Marcas", icon: "M" },
  { href: "/admin/categorias/", label: "Categorias", icon: "C" },
  { href: "/admin/colecoes/", label: "Coleções", icon: "O" },
  { href: "/admin/configuracoes/", label: "Configurações", icon: "S" }
];

export function initNavigation(pageMeta = {}) {
  renderShell(pageMeta);
  bindDrawer();
  updateApiStatus();
}

function renderShell({ title = "Dashboard", breadcrumb = "Admin" } = {}) {
  const sidebar = document.querySelector("[data-admin-sidebar]");
  const nav = document.querySelector("[data-admin-nav]");
  const pageTitle = document.querySelector("[data-page-title]");
  const pageBreadcrumb = document.querySelector("[data-page-breadcrumb]");

  if (pageTitle) pageTitle.textContent = title;
  if (pageBreadcrumb) pageBreadcrumb.textContent = breadcrumb;

  if (sidebar && nav && nav.children.length === 0) {
    routes.forEach((route) => {
      const link = document.createElement("a");
      link.href = route.href;
      link.innerHTML = `<span class="admin-icon" aria-hidden="true">${route.icon}</span><span></span>`;
      link.querySelector("span:last-child").textContent = route.label;
      if (isActive(route.href)) link.setAttribute("aria-current", "page");
      nav.append(link);
    });
  }
}

function isActive(href) {
  const current = window.location.pathname.replace(/index\.html$/, "");
  if (href === "/admin/") return current === "/admin/" || current === "/admin";
  return current.startsWith(href);
}

function bindDrawer() {
  const sidebar = document.querySelector("[data-admin-sidebar]");
  const overlay = document.querySelector("[data-admin-overlay]");
  const open = document.querySelector("[data-sidebar-open]");
  const close = document.querySelector("[data-sidebar-close]");
  if (!sidebar || !overlay || !open) return;

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
