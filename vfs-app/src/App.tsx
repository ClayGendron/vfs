import { createBrowserRouter, RouterProvider } from "react-router-dom"
import { RootLayout } from "@/components/layout/RootLayout"
import { Home } from "@/routes/Home"
import { About } from "@/routes/About"
import { Blog } from "@/routes/Blog"
import { Terminal } from "@/routes/Terminal"
import { NotFound } from "@/routes/NotFound"

const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: "/", element: <Home /> },
      { path: "/about", element: <About /> },
      { path: "/blog", element: <Blog /> },
      { path: "/terminal", element: <Terminal /> },
      { path: "*", element: <NotFound /> },
    ],
  },
])

export function App() {
  return <RouterProvider router={router} />
}

export default App
