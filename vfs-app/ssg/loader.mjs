// vite-react-ssg imports the react-router static handler from
// `react-router-dom/server.js`, a subpath react-router v7 dropped. Redirect it
// to `react-router`, where createStaticHandler/Router + StaticRouterProvider live.
export async function resolve(specifier, context, next) {
  if (
    specifier === "react-router-dom/server.js" ||
    specifier === "react-router-dom/server"
  ) {
    return next("react-router", context)
  }
  return next(specifier, context)
}
