import { useEffect } from "react";
import { Protocol } from "./directions/Protocol";

export function App() {
  useEffect(() => {
    document.body.className = "direction-body protocol";
  }, []);

  return (
    <div className="app direction protocol">
      <Protocol />
    </div>
  );
}
