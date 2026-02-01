import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://your-org.github.io",
  base: "/forgebook",
  vite: {
    plugins: [tailwindcss()],
  },
  output: "static",
});
