"""Compare Telethon vs TDLib download benchmark results and write RESULTS.md.

Live usage:
    uv run python benchmark/compare.py
"""

from pathlib import Path
from statistics import mean

from benchmark.models import DownloadResult, load_results

POC_ROOT = Path(__file__).resolve().parent.parent
TELETHON_RESULTS_PATH = POC_ROOT / "data" / "results_telethon.json"
TDLIB_RESULTS_PATH = POC_ROOT / "data" / "results_tdlib.json"
REPORT_PATH = POC_ROOT / "data" / "RESULTS.md"


def build_report(telethon_results: list[DownloadResult], tdlib_results: list[DownloadResult]) -> str:
    lines = [
        "# TDLib vs Telethon: media download latency/resumability POC results",
        "",
        "| label | backend | ok | elapsed_seconds | bytes_downloaded | resumed |",
        "|---|---|---|---|---|---|",
    ]
    for result in [*telethon_results, *tdlib_results]:
        lines.append(
            f"| {result.label} | {result.backend} | {result.ok} | {result.elapsed_seconds:.2f} "
            f"| {result.bytes_downloaded} | {result.resumed} |"
        )

    telethon_ok = [r for r in telethon_results if r.ok]
    tdlib_ok = [r for r in tdlib_results if r.ok]
    lines.append("")
    if telethon_ok and tdlib_ok:
        telethon_avg = mean(r.elapsed_seconds for r in telethon_ok)
        tdlib_avg = mean(r.elapsed_seconds for r in tdlib_ok)
        delta_pct = ((telethon_avg - tdlib_avg) / telethon_avg) * 100
        lines.append(
            f"Average elapsed: telethon={telethon_avg:.2f}s, tdlib={tdlib_avg:.2f}s "
            f"({delta_pct:+.1f}% telethon vs tdlib)."
        )
    else:
        lines.append("Not enough successful runs on both backends to compare averages.")

    tdlib_resumed = any(r.resumed and r.ok for r in tdlib_results)
    lines.append(f"TDLib demonstrated successful resume after interruption: {tdlib_resumed}.")

    lines.append("")
    lines.append("## ADR kill-criteria checklist (manual assessment)")
    lines.append("- [ ] Required sharing/converting Telethon session files? (must be No)")
    lines.append("- [ ] Auth/DB/update-loop code became the main work? (must be No)")
    lines.append("- [ ] No clear measured advantage over telegram-mcp? (see averages above)")
    lines.append("- [ ] Read behavior diverged from telegram-mcp in a way agents would need to understand? (must be No)")
    lines.append("- [ ] Required new persistent daemon management before proving value? (must be No)")

    return "\n".join(lines)


def main() -> None:
    telethon_results = load_results(TELETHON_RESULTS_PATH)
    tdlib_results = load_results(TDLIB_RESULTS_PATH)
    report = build_report(telethon_results, tdlib_results)
    REPORT_PATH.write_text(report)
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
