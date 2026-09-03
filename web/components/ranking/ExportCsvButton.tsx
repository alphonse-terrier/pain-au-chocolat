"use client";

import type { Place } from "@/lib/types";
import { downloadCsv, rankingToCsv } from "@/lib/csv";
import { formatInt } from "@/lib/format";
import Button from "../ui/Button";
import { Download } from "../ui/icons";

export default function ExportCsvButton({ places }: { places: Place[] }) {
  return (
    <Button
      variant="secondary"
      size="sm"
      iconLeft={<Download size={13} />}
      onClick={() => downloadCsv("paris_pain_au_chocolat_ranking.csv", rankingToCsv(places))}
    >
      Take the receipts ({formatInt(places.length)} rows, CSV)
    </Button>
  );
}
