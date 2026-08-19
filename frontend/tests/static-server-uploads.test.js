const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const os = require("node:os");
const test = require("node:test");

const { createServer } = require("../../scripts/static-server.js");

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
}

function request(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        resolve({
          statusCode: response.statusCode,
          contentType: response.headers["content-type"],
          body: Buffer.concat(chunks)
        });
      });
    }).on("error", reject);
  });
}

function requestPath(port, requestPathValue) {
  return new Promise((resolve, reject) => {
    const request = http.request({ hostname: "127.0.0.1", port, path: requestPathValue, method: "GET" }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        resolve({
          statusCode: response.statusCode,
          contentType: response.headers["content-type"],
          body: Buffer.concat(chunks)
        });
      });
    });
    request.on("error", reject);
    request.end();
  });
}

test("development static server serves uploads from safe local root", async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "dripzone-static-"));
  const frontendRoot = path.join(temp, "frontend");
  const uploadsRoot = path.join(temp, "uploads");
  fs.mkdirSync(path.join(frontendRoot, "pages"), { recursive: true });
  fs.mkdirSync(path.join(uploadsRoot, "products", "public-id"), { recursive: true });
  fs.writeFileSync(path.join(frontendRoot, "index.html"), "<h1>ok</h1>");
  fs.writeFileSync(path.join(uploadsRoot, "products", "public-id", "image.png"), Buffer.from([0x89, 0x50, 0x4e, 0x47]));

  const server = createServer({ root: frontendRoot, uploadsRoot, uploadsProxyTargets: [] });
  const port = await listen(server);
  try {
    const image = await request(`http://127.0.0.1:${port}/uploads/products/public-id/image.png`);
    const directory = await request(`http://127.0.0.1:${port}/uploads/products/public-id/`);
    const traversal = await requestPath(port, "/uploads/%2e%2e/index.html");

    assert.equal(image.statusCode, 200);
    assert.equal(image.contentType, "image/png");
    assert.equal(image.body.length, 4);
    assert.equal(directory.statusCode, 404);
    assert.equal(traversal.statusCode, 403);
  } finally {
    await close(server);
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test("development static server can proxy uploads without exposing frontend files", async () => {
  const upstream = http.createServer((request, response) => {
    if (request.url === "/uploads/products/p/image.jpg") {
      response.writeHead(200, { "Content-Type": "image/jpeg" });
      response.end("image");
      return;
    }
    response.writeHead(404, { "Content-Type": "text/plain" });
    response.end("missing");
  });
  const upstreamPort = await listen(upstream);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "dripzone-static-"));
  const server = createServer({
    root: temp,
    uploadsRoot: path.join(temp, "missing-uploads"),
    uploadsProxyTargets: [`http://127.0.0.1:${upstreamPort}`]
  });
  const port = await listen(server);
  try {
    const image = await request(`http://127.0.0.1:${port}/uploads/products/p/image.jpg`);

    assert.equal(image.statusCode, 200);
    assert.equal(image.contentType, "image/jpeg");
    assert.equal(image.body.toString(), "image");
  } finally {
    await close(server);
    await close(upstream);
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test("development static server proxies admin API to configured Docker target", async () => {
  const upstream = http.createServer((request, response) => {
    if (request.url === "/api/status" && request.method === "GET") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ status: "ok", environment: "production" }));
      return;
    }
    response.writeHead(404, { "Content-Type": "text/plain" });
    response.end("missing");
  });
  const upstreamPort = await listen(upstream);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "dripzone-static-"));
  const server = createServer({
    root: temp,
    apiProxyTarget: `http://127.0.0.1:${upstreamPort}`,
    uploadsProxyTargets: []
  });
  const port = await listen(server);
  try {
    const status = await request(`http://127.0.0.1:${port}/api/status`);

    assert.equal(status.statusCode, 200);
    assert.equal(status.contentType, "application/json");
    assert.equal(JSON.parse(status.body.toString()).environment, "production");
  } finally {
    await close(server);
    await close(upstream);
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
