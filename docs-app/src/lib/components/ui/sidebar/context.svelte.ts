import { getContext, setContext } from "svelte";
import { IsMobile } from "#lib/hooks/is-mobile.svelte.js";
import { SIDEBAR_KEYBOARD_SHORTCUT } from "./constants";

type Getter<T> = () => T;

export type SidebarStateProps = {
  /** A getter for the open state, so `bind:open` on the provider stays the one source. */
  open: Getter<boolean>;
  /** Sets the open state; the provider writes the cookie here. */
  setOpen: (open: boolean) => void;
  /** The id of the sidebar's nav, which the trigger's aria-controls names. */
  navId: string;
};

/**
 * True when the key was pressed inside something that edits text: a text
 * field, a contenteditable region, or CodeMirror's content, where Ctrl+B is
 * the editor's own (cursorCharLeft on a Mac) or means bold.
 */
function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return !!target.closest(
    "input, textarea, select, [contenteditable]:not([contenteditable='false']), .cm-content",
  );
}

class SidebarState {
  readonly props: SidebarStateProps;
  open = $derived.by(() => this.props.open());
  openMobile = $state(false);
  /** The sidebar's collapse mode, set by `Sidebar`; the inset reads it for its groove. */
  collapsible = $state<"offcanvas" | "icon" | "none">("offcanvas");
  setOpen: SidebarStateProps["setOpen"];
  #isMobile: IsMobile;
  state = $derived.by(() => (this.open ? "expanded" : "collapsed"));

  constructor(props: SidebarStateProps) {
    this.setOpen = props.setOpen;
    this.#isMobile = new IsMobile();
    this.props = props;
  }

  /** Below 768 px, where the sidebar is a sheet. False on the server. */
  get isMobile() {
    return this.#isMobile.current;
  }

  get navId() {
    return this.props.navId;
  }

  /** True while a sidebar is beside the page: open, as icons, or never collapsing; not off-canvas, not on a phone. */
  get beside(): boolean {
    if (this.#isMobile.current) return false;
    return this.open || this.collapsible !== "offcanvas";
  }

  /** The shortcut, on the window: it yields to a handled event and to an editable target. */
  handleShortcutKeydown = (e: KeyboardEvent) => {
    if (e.defaultPrevented) return;
    if (e.key !== SIDEBAR_KEYBOARD_SHORTCUT || !(e.metaKey || e.ctrlKey))
      return;
    if (isEditable(e.target)) return;
    e.preventDefault();
    this.toggle();
  };

  setOpenMobile = (value: boolean) => {
    this.openMobile = value;
  };

  toggle = () => {
    return this.#isMobile.current
      ? (this.openMobile = !this.openMobile)
      : this.setOpen(!this.open);
  };
}

const SYMBOL_KEY = "scn-sidebar";

/** Creates the sidebar's state and sets it in the context. */
export function setSidebar(props: SidebarStateProps): SidebarState {
  return setContext(Symbol.for(SYMBOL_KEY), new SidebarState(props));
}

/** The sidebar's state from the context: a class instance, not to be destructured. */
export function useSidebar(): SidebarState {
  return getContext(Symbol.for(SYMBOL_KEY));
}
