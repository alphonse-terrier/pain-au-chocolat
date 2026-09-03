import type { ReactNode } from "react";
import Logo from "./Logo";
import styles from "./EmptyState.module.css";

/** `icon` defaults to a muted watermark of the site's own mark rather than
 * nothing -- `detail={false}` matters here: a fully-detailed mark at low
 * opacity turns to noise, the reduced two-baton silhouette stays legible
 * as a shape. Pass `icon={null}` explicitly to suppress it entirely. */
export default function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  const shownIcon = icon === undefined ? <Logo size={44} tone="duo" detail={false} className={styles.logo} /> : icon;
  return (
    <div className={styles.wrap}>
      {shownIcon && (
        <div className={styles.icon} aria-hidden="true">
          {shownIcon}
        </div>
      )}
      <p className={styles.title}>{title}</p>
      {body && <p className={styles.body}>{body}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
