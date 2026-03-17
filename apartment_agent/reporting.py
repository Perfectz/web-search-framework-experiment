from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apartment_agent.utils import ensure_parent


def write_report(output_dir: str | Path, report: dict[str, Any]) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    run_id = report["run_id"]
    json_path = ensure_parent(directory / f"{run_id}.json")
    md_path = ensure_parent(directory / f"{run_id}.md")

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Apartment Agent Report",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Started At: `{report['started_at']}`",
        f"- Total Collected: `{report['total_collected']}`",
        f"- Unique Listings: `{report['total_unique']}`",
        f"- Alert Listings: `{len(report['alerts'])}`",
        f"- Watch Listings: `{len(report['watch'])}`",
        "",
        "## Alerts",
        "",
    ]

    if not report["alerts"]:
        lines.append("No alert listings in this run.")
        lines.append("")
    else:
        for item in report["alerts"]:
            lines.extend(
                [
                    f"### {item['title']}",
                    "",
                    f"- URL: {item['url']}",
                    f"- Score: {item['match_score']}",
                    f"- Price: {item.get('price_baht')}",
                    f"- Size: {item.get('size_sqm')}",
                    f"- Fit: {item['fit_label']}",
                    f"- Reasons: {', '.join(item.get('match_reasons', [])) or 'n/a'}",
                    f"- Red Flags: {', '.join(item.get('red_flags', [])) or 'n/a'}",
                    "",
                ]
            )

    lines.extend(["## Watch", ""])
    if not report["watch"]:
        lines.append("No watch listings in this run.")
        lines.append("")
    else:
        for item in report["watch"]:
            lines.extend(
                [
                    f"- {item['title']} ({item['match_score']})",
                    f"  URL: {item['url']}",
                ]
            )
    return "\n".join(lines).strip() + "\n"

