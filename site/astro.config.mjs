import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import fs from "node:fs";

// Serve pagefind index from build output during dev
function pagefindDevPlugin() {
  return {
    name: "pagefind-dev",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.includes("/pagefind/")) {
          const urlPath = req.url.split("?")[0].replace(/^\/forgebook/, "");
          const filePath = path.join(process.cwd(), "dist", urlPath);
          if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
            const ext = path.extname(filePath);
            const types = { ".js": "application/javascript", ".css": "text/css", ".json": "application/json", ".wasm": "application/wasm", ".pf_meta": "application/octet-stream", ".pf_fragment": "application/octet-stream", ".pf_index": "application/octet-stream" };
            res.setHeader("Content-Type", types[ext] || "application/octet-stream");
            res.setHeader("Cache-Control", "no-cache");
            fs.createReadStream(filePath).pipe(res);
            return;
          }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  site: "https://nicholasdbrady.github.io",
  base: "/forgebook",
  vite: {
    plugins: [tailwindcss(), pagefindDevPlugin()],
  },
  output: "static",
});
