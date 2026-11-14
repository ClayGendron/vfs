import { navigation } from "#lib/docs/content.server";

/** The navigation every page draws, and the two facts of this build the footer prints. */
export function load() {
  return {
    tabs: navigation(),
    commit: (process.env.GITHUB_SHA ?? "").slice(0, 7),
    built: new Date().toISOString().slice(0, 10),
  };
}
