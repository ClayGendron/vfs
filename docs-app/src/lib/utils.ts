export { cn } from "cn";

/** `T` without its `child` snippet prop. */
export type WithoutChild<T> = T extends { child?: unknown }
  ? Omit<T, "child">
  : T;

/** `T` without its `children` snippet prop. */
export type WithoutChildren<T> = T extends { children?: unknown }
  ? Omit<T, "children">
  : T;

/** `T` without either snippet prop. */
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;

/** `T` plus an optional, bindable reference to the element it renders. */
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & {
  ref?: U | null;
};
