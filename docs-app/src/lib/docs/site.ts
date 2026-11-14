/** The facts about the site that more than one page states. */
export const SITE_NAME = "VFS";
export const SITE_DESCRIPTION = "Governed data access for AI agents.";
export const REPOSITORY = "https://github.com/ClayGendron/vfs";

/** Where the site is served: the start of every page's one address, in its head and in the sitemap. */
export const SITE_URL = "https://docs.vfs.dev";

/** The id of the element that holds a page's content: where the skip link lands. */
export const CONTENT_ID = "content";

/** The id of the one hidden sentence, in the layout, that says a link opens in a new tab. */
export const NEW_TAB_ID = "vfs-new-tab";

/** What a link that leaves the site carries: a new tab, no handle on this one, and the sentence that says so. */
export const NEW_TAB = { target: "_blank", rel: "noopener", "aria-describedby": NEW_TAB_ID } as const;
