"use client";

import Button from "./ui/Button";
import styles from "./ErrorState.module.css";

export default function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const offline = typeof navigator !== "undefined" && !navigator.onLine;
  return (
    <div className={styles.wrap}>
      <div className={styles.icon} aria-hidden="true">
        ⚠️
      </div>
      <p className={styles.title}>Couldn&apos;t load the bakery data</p>
      <p className={styles.body}>
        {offline ? "You appear to be offline. Check your connection and try again." : "Something went wrong talking to the server."}
      </p>
      <Button variant="primary" onClick={onRetry}>
        Try again
      </Button>
      <p className={styles.detail}>{message}</p>
    </div>
  );
}
