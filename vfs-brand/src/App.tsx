import { useEffect, useState } from "react";
import { Protocol } from "./directions/Protocol";
import { Colors } from "./directions/Colors";

function currentPath(): string {
  if (typeof window === "undefined") return "/";
  return window.location.pathname;
}

export function App() {
  const [path, setPath] = useState<string>(currentPath());

  useEffect(() => {
    const onPop = () => setPath(currentPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const isColors = path === "/colors";

  useEffect(() => {
    document.body.className = isColors
      ? "direction-body colors"
      : "direction-body protocol";
  }, [isColors]);

  if (isColors) {
    return (
      <div className="app direction colors">
        <Colors />
      </div>
    );
  }

  return (
    <div className="app direction protocol">
      <Protocol />
    </div>
  );
}
