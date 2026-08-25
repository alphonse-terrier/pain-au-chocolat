import fs from "node:fs";
import path from "node:path";
import { Suspense } from "react";
import type { PlacesFile } from "@/lib/types";
import AppShell from "@/components/AppShell";

// Read the static export at build time -- just the small `meta` block, not
// the ~260KB of rows (those are fetched client-side from /data/places.json
// so the browser can cache/reuse them across navigations).
function readBuildMeta() {
  const file = path.join(process.cwd(), "public", "data", "places.json");
  const raw = fs.readFileSync(file, "utf-8");
  const parsed = JSON.parse(raw) as PlacesFile;
  return parsed.meta;
}

export default function Home() {
  const buildMeta = readBuildMeta();
  return (
    // useAppState()'s nuqs useSearchParams() needs a Suspense boundary
    // to be statically prerenderable (App Router requirement).
    <Suspense fallback={<p style={{ padding: 24 }}>Loading…</p>}>
      <AppShell buildMeta={buildMeta} />
    </Suspense>
  );
}
