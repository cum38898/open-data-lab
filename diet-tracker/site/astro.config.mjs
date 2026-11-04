import { defineConfig } from "astro/config";

// GitHub Pages では open-data-lab サイトの /diet-tracker/ 以下に置く。
// GitHub Actions では SITE_URL / BASE_PATH を渡す。BASE_PATH が空文字のときはルートに置く。
const basePath = process.env.BASE_PATH;

export default defineConfig({
  site: process.env.SITE_URL || "https://cum38898.github.io",
  base: basePath === undefined ? "/open-data-lab/diet-tracker" : basePath || "/",
  trailingSlash: "always",
  build: { format: "directory" },
});
