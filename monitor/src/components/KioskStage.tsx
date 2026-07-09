"use client";

import { useEffect, useState } from "react";
import styles from "./KioskStage.module.css";

const STAGE_WIDTH = 1024;
const STAGE_HEIGHT = 600;

/**
 * The design is a fixed 1024x600 canvas (the target 7" kiosk panel's native
 * resolution). This wrapper scales it to fill whatever viewport it actually
 * renders in — letterboxing rather than reflowing — so the layout stays
 * pixel-identical to the source design regardless of minor resolution or
 * browser-chrome differences on the real hardware.
 */
export function KioskStage({ children }: { children: React.ReactNode }) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    function updateScale() {
      setScale(
        Math.min(window.innerWidth / STAGE_WIDTH, window.innerHeight / STAGE_HEIGHT),
      );
    }
    updateScale();
    window.addEventListener("resize", updateScale);
    return () => window.removeEventListener("resize", updateScale);
  }, []);

  return (
    <div className={styles.viewport}>
      <div className={styles.stage} style={{ transform: `scale(${scale})` }}>
        {children}
      </div>
    </div>
  );
}
