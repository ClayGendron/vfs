// Registered via NODE_OPTIONS=--import during `vite-react-ssg build` so the
// resolve hook is active before any page module loads.
import { register } from "node:module"

register("./loader.mjs", import.meta.url)
