import { getSession, login } from "./api.js?v=api-base-3000-20260730";
import { initNotifications, notify } from "/admin/js/notifications.js?v=api-base-3000-20260730";

initNotifications();

const form = document.querySelector("[data-login-form]");
const toggle = document.querySelector("[data-toggle-password]");
const password = document.querySelector("#admin-password");

getSession().then(() => {
  location.href = "/admin/";
}).catch(() => {});

toggle?.addEventListener("click", () => {
  if (!password) return;
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  toggle.setAttribute("aria-pressed", String(!visible));
  toggle.textContent = visible ? "Mostrar" : "Ocultar";
});

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.checkValidity()) {
    form.reportValidity();
    notify("Preencha os campos obrigatórios.", "warning");
    return;
  }
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;
  try {
    await login(document.getElementById("admin-email").value, document.getElementById("admin-password").value);
    notify("Login realizado.", "success");
    location.href = "/admin/";
  } catch (error) {
    notify(error.message || "Não foi possível entrar.", "error");
  } finally {
    button.disabled = false;
  }
});
