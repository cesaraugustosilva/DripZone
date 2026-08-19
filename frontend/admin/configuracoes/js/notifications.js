let toastRegion;
let activeModal;
let modalReturnFocus;

export function initNotifications() {
  toastRegion = document.querySelector("[data-toast-region]");
}

export function notify(message, type = "info", options = {}) {
  if (!toastRegion) initNotifications();
  if (!toastRegion) return;

  const toast = document.createElement("div");
  toast.className = `admin-toast admin-toast--${type}`;
  toast.setAttribute("role", type === "error" ? "alert" : "status");

  const text = document.createElement("span");
  text.textContent = message;
  const close = document.createElement("button");
  close.className = "admin-button admin-button--ghost";
  close.type = "button";
  close.textContent = "Fechar";
  close.addEventListener("click", () => toast.remove());

  toast.append(text, close);
  toastRegion.append(toast);

  const timeout = options.timeout ?? 5200;
  if (timeout) window.setTimeout(() => toast.remove(), timeout);
}

export function showBackendNotice() {
  notify("Acao ainda nao implementada nesta tela.", "warning");
}

export function openModal({ title, body, actions = [] }) {
  closeModal();
  modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;

  const modal = document.createElement("div");
  modal.className = "admin-modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "admin-modal-title");

  const panel = document.createElement("div");
  panel.className = "admin-modal__panel";

  const head = document.createElement("div");
  head.className = "admin-modal__head";
  const heading = document.createElement("h2");
  heading.id = "admin-modal-title";
  heading.textContent = title;
  const close = document.createElement("button");
  close.className = "admin-button admin-button--ghost";
  close.type = "button";
  close.textContent = "Fechar";
  close.addEventListener("click", closeModal);
  head.append(heading, close);

  const content = document.createElement("div");
  content.className = "admin-modal__body";
  if (body instanceof Node) content.append(body);
  else content.textContent = String(body || "");

  const foot = document.createElement("div");
  foot.className = "admin-modal__foot admin-actions";
  actions.forEach((action) => {
    const button = document.createElement("button");
    button.className = action.className || "admin-button";
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", action.onClick || closeModal);
    foot.append(button);
  });

  panel.append(head, content, foot);
  modal.append(panel);
  document.body.append(modal);
  document.body.style.overflow = "hidden";
  activeModal = modal;

  close.focus();
  document.addEventListener("keydown", handleModalKeydown);
}

export function closeModal() {
  if (!activeModal) return;
  activeModal.remove();
  activeModal = null;
  document.body.style.overflow = "";
  document.removeEventListener("keydown", handleModalKeydown);
  modalReturnFocus?.focus();
}

function handleModalKeydown(event) {
  if (event.key === "Escape") closeModal();
  if (event.key !== "Tab" || !activeModal) return;

  const focusable = Array.from(activeModal.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"))
    .filter((element) => !element.disabled);
  if (focusable.length === 0) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
