import { initNavigation } from "./navigation.js?v=api-base-3000-20260730";
import { initNotifications, showBackendNotice } from "/admin/js/notifications.js?v=api-base-3000-20260730";
import { getSession, logout } from "./api.js?v=api-base-3000-20260730";

export async function initAdminPage(meta) {
  initNotifications();
  await guardSession();
  initNavigation(meta);
  bindLogoutActions();
  bindGlobalSearch();
}

async function guardSession() {
  if (location.pathname.startsWith("/admin/login")) return;
  document.documentElement.classList.add("admin-auth-loading");
  try {
    await getSession();
  } catch {
    location.href = "/admin/login/";
  } finally {
    document.documentElement.classList.remove("admin-auth-loading");
  }
}

function bindLogoutActions() {
  document.querySelectorAll("[data-backend-action]").forEach((button) => {
    if (button.textContent.trim().toLowerCase() === "sair") {
      button.addEventListener("click", async () => {
        await logout().catch(() => {});
        location.href = "/admin/login/";
      });
    } else {
      button.addEventListener("click", showBackendNotice);
    }
  });
}

function bindGlobalSearch() {
  document.querySelector("[data-global-search]")?.addEventListener("input", (event) => {
    const term = event.target.value.trim().toLowerCase();
    document.dispatchEvent(new CustomEvent("admin:global-search", { detail: { term } }));
  });
}

export function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = String(value);
}

export function createBadge(text, modifier = "") {
  const span = document.createElement("span");
  span.className = `admin-badge ${modifier}`.trim();
  span.textContent = text;
  return span;
}

export function clearChildren(element) {
  while (element?.firstChild) element.firstChild.remove();
}
