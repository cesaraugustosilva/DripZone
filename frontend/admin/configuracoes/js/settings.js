import { ADMIN_CONFIG } from "../../js/config.js";
import { getSettings, updateSettings } from "./api.js?v=api-base-3000-20260730";
import { initAdminPage } from "/admin/js/admin.js?v=api-base-3000-20260730";
import { notify, showBackendNotice } from "/admin/js/notifications.js?v=api-base-3000-20260730";

await initAdminPage({ title: "Configurações", breadcrumb: "Admin / Configurações" });
initSettings();

function initSettings() {
  document.querySelectorAll("[role='tab']").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab));
  });

  document.querySelector("[data-save-appearance]")?.addEventListener("click", () => {
    const sidebar = document.querySelector("[name='sidebar-mode']")?.value || "expanded";
    const density = document.querySelector("[name='table-density']")?.value || "comfortable";
    const theme = document.querySelector("[name='admin-theme']")?.value || "dark";
    localStorage.setItem(ADMIN_CONFIG.storageKeys.sidebarCollapsed, sidebar);
    localStorage.setItem(ADMIN_CONFIG.storageKeys.tableDensity, density);
    localStorage.setItem(ADMIN_CONFIG.storageKeys.theme, theme);
    updateSettings({ admin_table_density: density }).catch(() => null);
    notify("Configuração visual salva neste navegador.", "success");
  });

  document.querySelectorAll("[data-settings-backend]").forEach((button) => {
    button.addEventListener("click", showBackendNotice);
  });
}

function activateTab(tab) {
  const target = document.getElementById(tab.getAttribute("aria-controls"));
  if (!target) return;
  document.querySelectorAll("[role='tab']").forEach((item) => item.setAttribute("aria-selected", "false"));
  document.querySelectorAll(".admin-tab-panel").forEach((panel) => panel.hidden = true);
  tab.setAttribute("aria-selected", "true");
  target.hidden = false;
}
