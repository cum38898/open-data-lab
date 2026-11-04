import { defineConfig } from "astro/config";

// 既定は GitHub Pages のプロジェクトサイト（https://<user>.github.io/<repo>/）。
// GitHub Actions では actions/configure-pages の値を SITE_URL / BASE_PATH で渡す。
// 独自ドメインなどで BASE_PATH が空文字のときはルート（/）に置く。
const basePath = process.env.BASE_PATH;

export default defineConfig({
  site: process.env.SITE_URL || "https://cum38898.github.io",
  base: basePath === undefined ? "/open-data-lab" : basePath || "/",
  trailingSlash: "always",
  build: { format: "directory" },
});
