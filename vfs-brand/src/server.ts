import index from "./index.html";

const port = Number(process.env.PORT ?? 3000);

Bun.serve({
  port,
  routes: {
    "/": index,
    "/depot": index,
    "/archive": index,
    "/protocol": index,
  },
  development: process.env.NODE_ENV !== "production",
  fetch() {
    return new Response("Not found", { status: 404 });
  },
});

console.log(`VFS brand lookbook → http://localhost:${port}`);
