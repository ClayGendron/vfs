import { ViteReactSSG } from "vite-react-ssg"

import "./index.css"
import { routes } from "./App"

// Single entry for both sides: ViteReactSSG hydrates in the browser and drives
// the static render at build time. StrictMode + ThemeProvider live in `routes`.
export const createRoot = ViteReactSSG({ routes })
