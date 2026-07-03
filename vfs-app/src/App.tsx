/* eslint-disable react-refresh/only-export-components */
import { StrictMode } from "react"
import { Outlet } from "react-router-dom"
import type { RouteRecord } from "vite-react-ssg"
import { ThemeProvider } from "@/components/theme-provider"
import { RootLayout } from "@/components/layout/RootLayout"
import { Home } from "@/routes/Home"
import { About } from "@/routes/About"
import { Blog } from "@/routes/Blog"
import { Terminal } from "@/routes/Terminal"
import { NotFound } from "@/routes/NotFound"
import { RouteError } from "@/routes/RouteError"

// Pathless root so ThemeProvider wraps the layout AND its errorElement — a
// thrown route still renders RouteError with theme context available.
function ThemeRoot() {
  return (
    <StrictMode>
      <ThemeProvider>
        <Outlet />
      </ThemeProvider>
    </StrictMode>
  )
}

export const routes: RouteRecord[] = [
  {
    element: <ThemeRoot />,
    children: [
      {
        element: <RootLayout />,
        // Catches render-time throws from the layout and any child route, so an
        // error renders the branded page instead of React Router's default.
        errorElement: <RouteError />,
        children: [
          { index: true, element: <Home /> },
          { path: "about", element: <About /> },
          { path: "blog", element: <Blog /> },
          { path: "terminal", element: <Terminal /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]
