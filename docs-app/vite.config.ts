import adapter from "@sveltejs/adapter-static";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

// The pages live outside the app, in the repository's documentation folder; a test names another.
const documentation = resolve(process.env.DOCS_DIR ?? "../documentation");

/** Reloads the browser when a page, the navigation or a diagram changes, since the dev server reads them itself. */
function reloadOnPages(): Plugin {
  return {
    name: "vfs-docs-reload-on-pages",
    configureServer(server) {
      server.watcher.add(documentation);
      const reload = (file: string) => {
        if (file.startsWith(documentation)) server.ws.send({ type: "full-reload" });
      };
      server.watcher.on("change", reload).on("add", reload).on("unlink", reload);
    },
  };
}

// Where the static site is written; a test builds into a folder of its own.
const out = process.env.DOCS_OUT ?? "build";

export default defineConfig({
  plugins: [
    tailwindcss(),
    // The static adapter writes 404.html, the page a static host answers an unknown address with.
    sveltekit({ adapter: adapter({ pages: out, assets: out, fallback: "404.html" }) }),
    reloadOnPages(),
  ],
});
