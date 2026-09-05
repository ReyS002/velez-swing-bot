import { createReadStream } from "node:fs";
import { access, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));
const dashboardRoot = join(repositoryRoot, "bot/static/dashboard");
const port = Number(process.env.PORT || 4173);

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
};

function dashboardFile(pathname) {
  if (pathname === "/dashboard" || pathname === "/dashboard/") {
    return join(dashboardRoot, "index.html");
  }
  const prefix = "/dashboard/assets/";
  if (!pathname.startsWith(prefix)) return null;
  const relativePath = normalize(pathname.slice(prefix.length));
  if (!relativePath || relativePath.startsWith("..") || relativePath.includes("/../")) return null;
  return join(dashboardRoot, relativePath);
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host || "127.0.0.1"}`);
  const filePath = dashboardFile(url.pathname);
  if (!filePath) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  try {
    await access(filePath);
    const fileStats = await stat(filePath);
    if (!fileStats.isFile()) throw new Error("Not a file");
    response.writeHead(200, {
      "Cache-Control": "no-store",
      "Content-Length": fileStats.size,
      "Content-Type": contentTypes[extname(filePath)] || "application/octet-stream",
    });
    if (request.method === "HEAD") response.end();
    else createReadStream(filePath).pipe(response);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`Dashboard visual-test server listening on http://127.0.0.1:${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
