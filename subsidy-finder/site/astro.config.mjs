import { defineConfig } from "astro/config";

// GitHub Pages では open-data-lab サイトの /subsidy-finder/ 以下に置く。
// GitHub Actions では actions/configure-pages の値を SITE_URL / BASE_PATH で渡す。
// 独自ドメインなどで BASE_PATH が空文字のときはルート（/）に置く。
const basePath = process.env.BASE_PATH;

export default defineConfig({
  site: process.env.SITE_URL || "https://cum38898.github.io",
  base: basePath === undefined ? "/open-data-lab/subsidy-finder" : basePath || "/",
  trailingSlash: "always",
  build: { format: "directory" },
});
