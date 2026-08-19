const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");

const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8"
};

function headerValue(value) {
  return Array.isArray(value) ? value.join(", ") : value;
}

function send(response, status, body, type = "text/plain; charset=utf-8", headers = {}) {
  response.writeHead(status, { "Content-Type": type, ...headers });
  response.end(body);
}

function safeResolve(root, pathname) {
  const target = path.resolve(root, `.${pathname}`);
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  return target;
}

function serveFile(response, target, cacheControl = "no-cache") {
  if (fs.existsSync(target) && fs.statSync(target).isDirectory()) {
    target = path.join(target, "index.html");
  }
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) return false;

  response.writeHead(200, {
    "Content-Type": types[path.extname(target).toLowerCase()] || "application/octet-stream",
    "Cache-Control": cacheControl
  });
  fs.createReadStream(target).pipe(response);
  return true;
}

function parseProxyTargets(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim().replace(/\/+$/, ""))
    .filter(Boolean);
}

function hasEncodedTraversal(rawUrl = "") {
  const pathOnly = String(rawUrl).split("?")[0].toLowerCase();
  return /(?:^|\/)(?:%2e|\.){2}(?:\/|$)/i.test(pathOnly);
}

function proxyRequest(targetBase, request, response, pathname, onMiss, { forwardBody = false } = {}) {
  const targetUrl = new URL(pathname, `${targetBase}/`);
  const client = targetUrl.protocol === "https:" ? https : http;
  const headers = {
    "User-Agent": "DripZoneLocalStaticServer/1.0",
    Accept: request.headers.accept || "*/*"
  };
  for (const name of ["content-type", "cookie", "x-csrf-token"]) {
    if (request.headers[name]) headers[name] = request.headers[name];
  }
  const proxy = client.request(
    targetUrl,
    {
      method: forwardBody ? request.method : "GET",
      headers,
      timeout: 5000
    },
    (proxyResponse) => {
      if (proxyResponse.statusCode === 404) {
        proxyResponse.resume();
        onMiss();
        return;
      }
      response.writeHead(proxyResponse.statusCode || 502, {
        "Content-Type": headerValue(proxyResponse.headers["content-type"]) || "application/octet-stream",
        "Cache-Control": headerValue(proxyResponse.headers["cache-control"]) || "public, max-age=604800"
      });
      proxyResponse.pipe(response);
    }
  );
  proxy.on("timeout", () => proxy.destroy(new Error("proxy_timeout")));
  proxy.on("error", onMiss);
  if (forwardBody) {
    request.pipe(proxy);
  } else {
    proxy.end();
  }
}

function createServer({
  root = process.cwd(),
  apiProxyTarget = (process.env.API_PROXY_TARGET || "http://127.0.0.1:8080").replace(/\/+$/, ""),
  uploadsRoot = process.env.UPLOADS_ROOT || path.resolve(process.cwd(), "..", "backend", "storage", "uploads"),
  uploadsProxyTargets = parseProxyTargets(process.env.UPLOADS_PROXY_TARGETS || process.env.UPLOADS_PROXY_TARGET || "http://127.0.0.1:8080,http://127.0.0.1:3000")
} = {}) {
  const resolvedRoot = path.resolve(root);
  const resolvedUploadsRoot = path.resolve(uploadsRoot);

  return http.createServer((request, response) => {
    if (hasEncodedTraversal(request.url)) return send(response, 403, "Forbidden");

    const url = new URL(request.url, "http://127.0.0.1");
    let pathname;
    try {
      pathname = decodeURIComponent(url.pathname);
    } catch {
      return send(response, 400, "Bad request");
    }

    if (pathname === "/api" || pathname.startsWith("/api/")) {
      if (!["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"].includes(request.method)) {
        return send(response, 405, "Method not allowed");
      }
      try {
        const targetUrl = new URL(apiProxyTarget);
        const ownPort = process.env.PORT || "4173";
        if (targetUrl.origin === `http://127.0.0.1:${ownPort}` || targetUrl.origin === `http://localhost:${ownPort}`) {
          return send(response, 502, "Invalid API proxy target");
        }
      } catch {
        return send(response, 502, "Invalid API proxy target");
      }
      return proxyRequest(apiProxyTarget, request, response, `${pathname}${url.search}`, () => send(response, 502, "API proxy unavailable"), { forwardBody: true });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return send(response, 405, "Method not allowed");
    }

    if (pathname === "/uploads" || pathname.startsWith("/uploads/")) {
      const relativeUploadsPath = pathname.replace(/^\/uploads\/?/, "/");
      const localTarget = safeResolve(resolvedUploadsRoot, relativeUploadsPath);
      const serveLocal = () => {
        if (!localTarget) return send(response, 403, "Forbidden");
        if (fs.existsSync(localTarget) && fs.statSync(localTarget).isDirectory()) {
          return send(response, 404, "Not found");
        }
        if (serveFile(response, localTarget, "public, max-age=604800")) return;
        send(response, 404, "Not found");
      };
      const candidates = uploadsProxyTargets.filter((target) => {
        try {
          const targetUrl = new URL(target);
          return targetUrl.origin !== `http://127.0.0.1:${process.env.PORT || "4173"}` && targetUrl.origin !== `http://localhost:${process.env.PORT || "4173"}`;
        } catch {
          return false;
        }
      });
      const tryProxy = (index = 0) => {
        if (index >= candidates.length) return serveLocal();
        proxyRequest(candidates[index], request, response, pathname, () => tryProxy(index + 1));
      };
      return tryProxy();
    }

    const target = safeResolve(resolvedRoot, pathname);
    if (!target) return send(response, 403, "Forbidden");
    if (serveFile(response, target)) return;
    return send(response, 404, "Not found");
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || "4173");
  createServer().listen(port, "127.0.0.1", () => {
    console.log(`DripZone static server: http://127.0.0.1:${port}/`);
  });
}

module.exports = { createServer, safeResolve };
