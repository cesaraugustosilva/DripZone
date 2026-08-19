import { getActivities, getApiStatus, getImports, getProductsPage, getSession } from "./api.js?v=api-base-3000-20260730";
import { clearChildren, createBadge, initAdminPage } from "/admin/js/admin.js?v=api-base-3000-20260730";

const ACTIVITY_LIMIT = 6;

await initAdminPage({
  title: "Dashboard",
  breadcrumb: "Admin / Dashboard",
  description: "Resumo geral da operacao da DripZone."
});

loadKpis();
loadActivities();
loadSystemStatus();

async function loadKpis() {
  const [productsResult, publishedResult, draftsResult, importsResult] = await Promise.allSettled([
    getProductsPage({ page: 1, page_size: 1 }),
    getProductsPage({ page: 1, page_size: 1, status: "published" }),
    getProductsPage({ page: 1, page_size: 1, status: "draft" }),
    getImports({ page: 1, page_size: 1, status: "pending" })
  ]);

  renderKpi("products", productsResult, {
    loaded: "Catalogo total",
    empty: "Nenhum produto cadastrado."
  });
  renderKpi("published", publishedResult, {
    loaded: "Produtos visiveis na loja",
    empty: "Nenhum produto publicado."
  });
  renderKpi("drafts", draftsResult, {
    loaded: "Produtos em preparacao",
    empty: "Nenhum rascunho."
  });
  renderKpi("imports", importsResult, {
    loaded: "Importacoes aguardando revisao",
    empty: "Nenhuma importacao encontrada."
  });
}

function renderKpi(name, result, messages) {
  const valueElement = document.querySelector(`[data-kpi-${name}]`);
  const stateElement = document.querySelector(`[data-kpi-${name}-state]`);
  const emptyAction = document.querySelector(`[data-kpi-${name}-empty]`);
  if (!valueElement || !stateElement) return;

  if (result.status !== "fulfilled") {
    valueElement.textContent = "-";
    stateElement.textContent = "Nao foi possivel carregar.";
    if (emptyAction) emptyAction.hidden = true;
    valueElement.closest(".admin-kpi-card")?.setAttribute("data-state", "warning");
    return;
  }

  const total = totalFromPage(result.value);
  valueElement.textContent = String(total);
  stateElement.textContent = total === 0 ? messages.empty : messages.loaded;
  if (emptyAction) emptyAction.hidden = total !== 0;
  valueElement.closest(".admin-kpi-card")?.setAttribute("data-state", total === 0 ? "empty" : "ok");
}

async function loadActivities() {
  const list = document.querySelector("[data-activity-list]");
  const empty = document.querySelector("[data-activity-empty]");
  if (!list || !empty) return;

  try {
    const data = await getActivities({ page: 1, page_size: ACTIVITY_LIMIT });
    const activities = data.items || [];
    clearChildren(list);

    if (!activities.length) {
      list.hidden = true;
      empty.hidden = false;
      return;
    }

    list.hidden = false;
    empty.hidden = true;
    activities.forEach((activity) => list.append(createActivityItem(activity)));
  } catch {
    clearChildren(list);
    list.hidden = true;
    empty.hidden = false;
    empty.querySelector("h2").textContent = "Nao foi possivel carregar atividades.";
  }
}

function createActivityItem(activity) {
  const item = document.createElement("li");
  item.className = "admin-activity-item";

  const icon = document.createElement("span");
  icon.className = "admin-activity-item__icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = iconForActivity(activity.action);

  const body = document.createElement("div");
  const action = document.createElement("strong");
  action.textContent = activity.summary || labelAction(activity.action);
  const meta = document.createElement("small");
  meta.textContent = formatTime(activity.created_at);
  body.append(action, meta);

  item.append(icon, body, createBadge(labelType(activity.entity_type), badgeForActivity(activity.action)));
  return item;
}

async function loadSystemStatus() {
  const [apiResult, sessionResult] = await Promise.allSettled([getApiStatus(), getSession()]);
  const apiStatus = apiResult.status === "fulfilled" ? apiResult.value : { state: "disconnected" };
  const statusData = apiStatus.data || {};
  const apiConnected = apiStatus.state === "connected" && statusData.status === "ok";
  const databaseConnected = apiConnected && statusData.database === "connected";
  const sessionActive = sessionResult.status === "fulfilled";

  renderSystemStatus([
    statusItem("API", apiConnected ? "Conectada" : "Instavel", apiConnected ? "ok" : "warn"),
    statusItem("Banco", databaseConnected ? "Conectado" : apiConnected ? "Verificar" : "Indisponivel", databaseConnected ? "ok" : "warn"),
    statusItem("Storage", apiConnected ? "OK" : "Verificar", apiConnected ? "ok" : "warn"),
    statusItem("Sessao", sessionActive ? "Autenticado" : "Expirada", sessionActive ? "ok" : "off")
  ]);
}

function renderSystemStatus(items) {
  const list = document.querySelector("[data-system-status]");
  if (!list) return;
  clearChildren(list);
  items.forEach((item) => {
    const row = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = item.label;
    row.append(label, createBadge(item.value, `admin-badge--${item.modifier}`));
    list.append(row);
  });
}

function statusItem(label, value, modifier) {
  return { label, value, modifier };
}

function totalFromPage(data) {
  return data?.pagination?.total ?? data?.items?.length ?? 0;
}

function labelAction(action) {
  return {
    login: "Login",
    logout: "Logout",
    create: "Criacao",
    update: "Atualizacao",
    delete: "Exclusao",
    export: "Exportacao",
    settings_update: "Configuracao atualizada",
    import_preview: "Importacao criada",
    import_review: "Revisao atualizada",
    import_publish: "Produto publicado",
    image_ingestion: "Imagem armazenada"
  }[action] || action || "Atividade";
}

function labelType(type) {
  return {
    product: "Produto",
    products: "Produto",
    brand: "Marca",
    brands: "Marca",
    category: "Categoria",
    categories: "Categoria",
    collection: "Colecao",
    collections: "Colecao",
    import: "Importacao",
    imports: "Importacao",
    settings: "Sistema",
    auth: "Sessao"
  }[type] || type || "Sistema";
}

function iconForActivity(action) {
  return {
    login: "L",
    logout: "S",
    create: "+",
    update: "E",
    delete: "!",
    export: "X",
    settings_update: "C",
    import_preview: "I",
    import_review: "R",
    import_publish: "P",
    image_ingestion: "G"
  }[action] || "A";
}

function badgeForActivity(action) {
  if (action === "delete") return "admin-badge--off";
  if (action === "login" || action === "logout") return "admin-badge--info";
  if (action === "create" || action === "import_publish") return "admin-badge--ok";
  return "admin-badge--success";
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}
