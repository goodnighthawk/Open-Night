from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portable_paths import shared_issue_reports_root


def main() -> int:
    root = shared_issue_reports_root()
    source = root / "issue_reports.csv"
    out = root / "next_version_fixlist.csv"
    if not source.exists():
        print(f"No issue reports yet: {source}")
        return 0
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if str(r.get("status", "open")).strip().lower() != "fixed"]
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("chunk_id", "UNK"), row.get("category", "other"))].append(row)
    fields = ["priority", "chunk_id", "category", "report_count", "latest_note", "latest_world_x", "latest_world_y", "latest_screenshot", "build_versions"]
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        ordered = sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0][0], kv[0][1]))
        for rank, ((chunk, category), items) in enumerate(ordered, start=1):
            latest = max(items, key=lambda row: row.get("timestamp_utc", ""))
            versions = sorted({r.get("build_version", "") for r in items if r.get("build_version")})
            writer.writerow({
                "priority": rank,
                "chunk_id": chunk,
                "category": category,
                "report_count": len(items),
                "latest_note": latest.get("note", ""),
                "latest_world_x": latest.get("world_x", ""),
                "latest_world_y": latest.get("world_y", ""),
                "latest_screenshot": latest.get("screenshot", ""),
                "build_versions": ";".join(versions),
            })
    counts = Counter(r.get("category", "other") for r in rows)
    print(f"Open reports: {len(rows)}")
    for category, count in sorted(counts.items()):
        print(f"  {category}: {count}")
    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
