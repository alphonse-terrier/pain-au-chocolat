"use client";

import Button from "./ui/Button";
import styles from "./ErrorState.module.css";

export default function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const offline = typeof navigator !== "undefined" && !navigator.onLine;
  return (
    <div className={styles.wrap}>
      <div className={styles.icon} aria-hidden="true">
        🥐💥
      </div>
      <p className={styles.title}>The croissant hit the fan</p>
      <p className={styles.body}>
        {offline
          ? "Looks like you're offline. Reconnect and we'll pick up right where we left off."
          : "The server tripped over something. Not the pastries' fault, we promise."}
      </p>
      <Button variant="primary" onClick={onRetry}>
        Give it another shot
      </Button>
      <p className={styles.detail}>{message}</p>
    </div>
  );
}
