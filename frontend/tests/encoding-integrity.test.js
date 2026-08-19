const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "..", "..");
const SCAN_ROOTS = ["frontend", "backend/app", "backend/scripts", "backend/tests", "docs", "deploy", "scripts"];
const TEXT_EXTENSIONS = new Set([".html", ".js", ".css", ".json", ".md", ".py", ".txt", ".yml", ".yaml", ".ps1"]);
const SKIP_DIRS = new Set([".git", ".venv", "node_modules", "__pycache__"]);

const MOJIBAKE_PATTERN = /(?:\u00c3[\u0080-\u00ff]|\u00c2[\u0080-\u00ff]|\u00e2[\u0080-\uffff]{1,2}|\u00ef\u00bf\u00bd|\ufffd|\u00f0\u0178)/u;

const ALLOWLIST = new Set([
]);

function walk(directory) {
  const entries = fs.readdirSync(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(fullPath));
    } else if (TEXT_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      files.push(fullPath);
    }
  }
  return files;
}

function normalizedRelativePath(filePath) {
  return path.relative(ROOT, filePath).replaceAll(path.sep, "/");
}

test("public and backend text files do not contain unallowlisted mojibake", () => {
  const findings = [];

  for (const root of SCAN_ROOTS) {
    const absoluteRoot = path.join(ROOT, root);
    if (!fs.existsSync(absoluteRoot)) continue;

    for (const filePath of walk(absoluteRoot)) {
      const relativePath = normalizedRelativePath(filePath);
      const content = fs.readFileSync(filePath, "utf8");
      const lines = content.split(/\r?\n/);

      lines.forEach((line, index) => {
        const lineNumber = index + 1;
        if (!MOJIBAKE_PATTERN.test(line)) return;
        const key = `${relativePath}:${lineNumber}`;
        if (ALLOWLIST.has(key)) return;
        findings.push(`${key}: ${line.trim().slice(0, 160)}`);
      });
    }
  }

  assert.deepEqual(findings, []);
});
