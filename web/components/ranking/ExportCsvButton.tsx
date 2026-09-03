"use client";

import type { Place } from "@/lib/types";
import { downloadCsv, rankingToCsv } from "@/lib/csv";
import { formatInt } from "@/lib/format";
import Button from "../ui/Button";

export default function ExportCsvButton({ places }: { places: Place[] }) {
  return (
    <Button
      variant="secondary"
      size="sm"
      iconLeft={
        <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M8 1v9m0 0L4.5 6.5M8 10l3.5-3.5M2 12v2h12v-2"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      }
      onClick={() => downloadCsv("paris_pain_au_chocolat_ranking.csv", rankingToCsv(places))}
    >
      Take the receipts ({formatInt(places.length)} rows, CSV)
    </Button>
  );
}
