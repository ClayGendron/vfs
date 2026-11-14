import { error } from "@sveltejs/kit";
import { navigation, routes } from "#lib/docs/content.server";
import { renderPage } from "#lib/docs/markdown.server";

/** Every page the navigation lists is prerendered, whether or not another page links to it. */
export function entries() {
  return routes().map((route) => ({ route: route.slice(1) }));
}

export async function load({ params }: { params: { route: string } }) {
  const route = `/${params.route}`;
  const tabs = navigation();
  const order = routes(tabs);
  const at = order.indexOf(route);
  if (at === -1) error(404, "Not found");
  const titles = new Map(tabs.flatMap((tab) => tab.groups.flatMap((group) => group.pages.map((p) => [p.route, p.title]))));
  const link = (target: string | undefined) => (target ? { route: target, title: titles.get(target) ?? target } : null);
  return {
    page: await renderPage(route),
    tab: tabs.findIndex((tab) => tab.groups.some((group) => group.pages.some((p) => p.route === route))),
    previous: link(order[at - 1]),
    next: link(order[at + 1]),
  };
}
