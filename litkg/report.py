from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

from .queries import annotated_bibliography
from .store import LitStore


def _text(value: object | None, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    return escape(str(value))


def _badge(label: str, class_name: str) -> str:
    return f'<span class="badge {class_name}">{escape(label)}</span>'


def _stat_cards(rows: list[dict]) -> str:
    counts = Counter(str(row.get("status") or "unknown") for row in rows)
    labels = ["resolved", "duplicate", "partial", "unresolved"]
    total = len(rows)
    cards = [
        f"""
        <div class="stat-card">
          <div class="stat-value">{total}</div>
          <div class="stat-label">entries</div>
        </div>
        """
    ]
    for label in labels:
        cards.append(
            f"""
            <div class="stat-card">
              <div class="stat-value">{counts.get(label, 0)}</div>
              <div class="stat-label">{escape(label)}</div>
            </div>
            """
        )
    return "\n".join(cards)


def _normalize_statuses(statuses: Iterable[str] | None) -> set[str]:
    if not statuses:
        return set()
    return {str(status).strip().lower() for status in statuses if str(status).strip()}


def _entry_summary(row: dict) -> str:
    parts: list[str] = []
    if row.get("entryTitle"):
        parts.append(str(row["entryTitle"]))
    elif row.get("entryKey"):
        parts.append(str(row["entryKey"]))
    if row.get("entryYear"):
        parts.append(str(row["entryYear"]))
    if row.get("entryVenue"):
        parts.append(str(row["entryVenue"]))
    if row.get("entryDoi"):
        parts.append(f"DOI {row['entryDoi']}")
    return " · ".join(parts) if parts else "-"


def _entry_meta(row: dict) -> str:
    parts: list[str] = []
    if row.get("entryAuthors"):
        parts.append(str(row["entryAuthors"]))
    if row.get("entryKey"):
        parts.append(f"key: {row['entryKey']}")
    if row.get("entryDoi"):
        parts.append(f"doi: {row['entryDoi']}")
    return " | ".join(parts) if parts else "-"


def _status_rank(status: str) -> int:
    order = {"resolved": 0, "duplicate": 1, "partial": 2, "unresolved": 3}
    return order.get(status, 99)


def _sort_key(row: dict, sort_by: str) -> tuple:
    status = str(row.get("status") or "unknown").lower()
    bibliography = str(row.get("bibliographyName") or "").lower()
    entry_order = int(row.get("entryOrder") or 0)
    entry_text = str(row.get("entryText") or "").lower()
    entry_title = str(row.get("entryTitle") or row.get("entryKey") or row.get("entryText") or "").lower()
    target = str(row.get("refersToTitle") or row.get("refersTo") or "").lower()
    duplicate_count = int(row.get("duplicateCount") or 0)

    if sort_by == "status":
        return (_status_rank(status), bibliography, entry_order, entry_text)
    if sort_by == "entry":
        return (entry_title, bibliography, entry_order, entry_text)
    if sort_by == "target":
        return (target, bibliography, entry_order, entry_text)
    if sort_by == "duplicate-count":
        return (duplicate_count, bibliography, entry_order, entry_text)
    if sort_by == "order":
        return (bibliography, entry_order, entry_text)
    return (bibliography, entry_order, entry_text)


def _select_annotated_rows(
    store: LitStore,
    pattern: str = "",
    *,
    statuses: Iterable[str] | None = None,
    sort_by: str = "order",
    descending: bool = False,
) -> tuple[list[dict], set[str]]:
    rows = annotated_bibliography(store, pattern)
    status_filter = _normalize_statuses(statuses)
    if status_filter:
        rows = [row for row in rows if str(row.get("status") or "").lower() in status_filter]
    rows = sorted(rows, key=lambda row: _sort_key(row, sort_by), reverse=descending)
    return rows, status_filter


def _report_library_name(store: LitStore, library_name: str | None) -> str:
    if library_name:
        return library_name.strip() or "LitKG Library"
    if store.path is not None:
        candidate = Path(store.path).stem.strip()
        if candidate and not candidate.startswith("."):
            return candidate
    return "LitKG Library"


def _report_filter_text(pattern: str, status_filter: set[str], sort_by: str, descending: bool) -> str:
    parts: list[str] = []
    if pattern:
        parts.append(f"pattern: {pattern}")
    if status_filter:
        parts.append(f"statuses: {', '.join(sorted(status_filter))}")
    else:
        parts.append("statuses: all")
    direction = "descending" if descending else "ascending"
    parts.append(f"sort: {sort_by} ({direction})")
    return " | ".join(parts)


def _report_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _rows(rows: Iterable[dict]) -> str:
    chunks: list[str] = []
    for row in rows:
        status = str(row.get("status") or "unknown")
        match_status = str(row.get("matchStatus") or "-")
        duplicate_count = row.get("duplicateCount")
        target = row.get("refersToTitle") or row.get("refersTo") or "-"
        chunks.append(
            f"""
            <tr class="status-{escape(status)}">
              <td>{_badge(status, f"status-{status}")}</td>
              <td>{_badge(match_status, f"match-{match_status}")}</td>
              <td>
                <div class="bibliography">{_text(row.get("bibliographyName"))}</div>
                <div class="secondary">{_text(row.get("bibliographyFormat"))}</div>
              </td>
              <td>
                <div class="entry-summary">{_text(_entry_summary(row))}</div>
                <div class="secondary">{_text(_entry_meta(row))}</div>
              </td>
              <td>{_text(target)}</td>
              <td>{_text(duplicate_count)}</td>
              <td>{_text(row.get("entryOrder"))}</td>
              <td><pre>{_text(row.get("entryText"))}</pre></td>
            </tr>
            """
        )
    return "\n".join(chunks)


def annotated_bibliography_html(
    store: LitStore,
    pattern: str = "",
    *,
    statuses: Iterable[str] | None = None,
    sort_by: str = "order",
    descending: bool = False,
) -> str:
    rows, status_filter = _select_annotated_rows(
        store,
        pattern,
        statuses=statuses,
        sort_by=sort_by,
        descending=descending,
    )
    title = "Annotated Bibliography Report"
    subtitle = "All indexed bibliography entries"
    if pattern:
        subtitle = f"Filtered by: {pattern}"
    if status_filter:
        status_list = ", ".join(sorted(status_filter))
        subtitle = f"{subtitle} | Status filter: {status_list}"
    if sort_by:
        direction = "descending" if descending else "ascending"
        subtitle = f"{subtitle} | Sorted by: {sort_by} ({direction})"

    body = _rows(rows)
    empty_state = (
        '<div class="empty-state">No bibliography entries matched the filter.</div>'
        if not rows
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --panel-alt: #f1eadf;
      --text: #1e1a17;
      --muted: #6f6258;
      --border: #d8cbbc;
      --accent: #8b5e34;
      --good: #1f7a4d;
      --warn: #ab6d00;
      --bad: #9a4b2f;
      --dup: #8b3fa7;
      --shadow: 0 18px 50px rgba(70, 46, 27, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Noto Sans", Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(139, 94, 52, 0.08), transparent 28%),
        radial-gradient(circle at top right, rgba(31, 122, 77, 0.08), transparent 26%),
        linear-gradient(180deg, #faf7f1 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    header {{
      display: grid;
      gap: 12px;
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.4rem);
      letter-spacing: -0.04em;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.5;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 6px;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255, 253, 248, 0.85);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
      margin: 22px 0 24px;
    }}
    .stat-card {{
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
    }}
    .stat-value {{
      font-size: 2rem;
      font-weight: 700;
      line-height: 1;
    }}
    .stat-label {{
      margin-top: 6px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.76rem;
    }}
    .table-wrap {{
      overflow-x: auto;
      border-radius: 20px;
      box-shadow: var(--shadow);
      border: 1px solid var(--border);
      background: rgba(255, 253, 248, 0.92);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1200px;
    }}
    thead {{
      background: var(--panel-alt);
      text-align: left;
    }}
    th, td {{
      padding: 14px 12px;
      vertical-align: top;
      border-bottom: 1px solid var(--border);
      font-size: 0.95rem;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    tr:hover td {{
      background: rgba(139, 94, 52, 0.03);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 84px;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .status-resolved, .match-resolved {{ color: var(--good); background: rgba(31, 122, 77, 0.12); }}
    .status-duplicate, .match-duplicate {{ color: var(--dup); background: rgba(139, 63, 167, 0.12); }}
    .status-partial, .match-partial {{ color: var(--warn); background: rgba(171, 109, 0, 0.12); }}
    .status-unresolved, .match-unresolved {{ color: var(--bad); background: rgba(154, 75, 47, 0.12); }}
    .bibliography, .entry-summary {{
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .secondary {{
      color: var(--muted);
      font-size: 0.86rem;
      line-height: 1.4;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font: inherit;
      color: var(--text);
    }}
    .empty-state {{
      margin-top: 18px;
      padding: 22px;
      border: 1px dashed var(--border);
      border-radius: 16px;
      background: rgba(255, 253, 248, 0.92);
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{escape(title)}</h1>
      <div class="subtitle">{escape(subtitle)}</div>
      <div class="toolbar">
        <div class="chip">status chips show entry state</div>
        <div class="chip">sorts are applied before rendering</div>
      </div>
    </header>
    <section class="stats">
      {_stat_cards(rows)}
    </section>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Match</th>
            <th>Bibliography</th>
            <th>Entry</th>
            <th>Target</th>
            <th>Duplicates</th>
            <th>Order</th>
            <th>Reference Text</th>
          </tr>
        </thead>
        <tbody>
          {body}
        </tbody>
      </table>
    </section>
    {empty_state}
  </div>
</body>
</html>
"""


def export_annotated_bibliography_bundle(
    store: LitStore,
    *,
    output_dir: str | Path = ".",
    prefix: str = "annotated-bibliography",
    pattern: str = "",
    statuses: Iterable[str] | None = None,
    sort_by: str = "order",
    descending: bool = False,
    library_name: str | None = None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    html_path = output_path / f"{prefix}.html"
    pdf_path = output_path / f"{prefix}.pdf"
    html_path.write_text(
        annotated_bibliography_html(
            store,
            pattern,
            statuses=statuses,
            sort_by=sort_by,
            descending=descending,
        ),
        encoding="utf-8",
    )
    pdf_path.write_bytes(
        annotated_bibliography_pdf(
            store,
            pattern,
            statuses=statuses,
            sort_by=sort_by,
            descending=descending,
            library_name=library_name,
        )
    )
    return {"html": str(html_path), "pdf": str(pdf_path)}


def annotated_bibliography_pdf(
    store: LitStore,
    pattern: str = "",
    *,
    statuses: Iterable[str] | None = None,
    sort_by: str = "order",
    descending: bool = False,
    library_name: str | None = None,
) -> bytes:
    rows, status_filter = _select_annotated_rows(
        store,
        pattern,
        statuses=statuses,
        sort_by=sort_by,
        descending=descending,
    )
    report_library_name = _report_library_name(store, library_name)
    filter_text = _report_filter_text(pattern, status_filter, sort_by, descending)
    generated_at = _report_timestamp()

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            LongTable,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("reportlab is required for PDF export. Install the project requirements.") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Annotated Bibliography Report",
        author="LitKG-RDF",
        subject="Annotated bibliography report",
        creator="LitKG-RDF",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LitKGTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#1e1a17"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "LitKGSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#6f6258"),
    )
    stat_value_style = ParagraphStyle(
        "LitKGStatValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1e1a17"),
    )
    body_style = ParagraphStyle(
        "LitKGBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.6,
        leading=9.2,
        textColor=colors.HexColor("#1e1a17"),
    )
    body_bold_style = ParagraphStyle(
        "LitKGBold",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    header_style = ParagraphStyle(
        "LitKGHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.8,
        leading=9.5,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#6f6258"),
    )
    cover_label_style = ParagraphStyle(
        "LitKGCoverLabel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6f6258"),
        alignment=TA_CENTER,
    )
    cover_value_style = ParagraphStyle(
        "LitKGCoverValue",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1e1a17"),
    )

    def pdf_text(value: object | None, default: str = "-") -> str:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
        return escape(str(value)).replace("\n", "<br/>")

    def paragraph(value: object | None, style=body_style) -> Paragraph:
        return Paragraph(pdf_text(value), style)

    total = len(rows)
    counts = Counter(str(row.get("status") or "unknown") for row in rows)
    status_list = ", ".join(sorted(status_filter)) if status_filter else "all statuses"
    direction = "descending" if descending else "ascending"

    title_text = "Annotated Bibliography Report"
    subtitle = "All indexed bibliography entries"
    if pattern:
        subtitle = f"Filtered by: {pattern}"
    if status_filter:
        subtitle = f"{subtitle} | Status filter: {status_list}"
    if sort_by:
        subtitle = f"{subtitle} | Sorted by: {sort_by} ({direction})"

    story: list[object] = [
        Paragraph("Annotated Bibliography Report", cover_value_style),
        Spacer(1, 10),
        Paragraph(pdf_text(report_library_name), cover_value_style),
        Spacer(1, 12),
        Paragraph(pdf_text(filter_text), cover_label_style),
        Paragraph(pdf_text(f"Generated: {generated_at}"), cover_label_style),
        Spacer(1, 18),
        Paragraph(
            "This report summarizes bibliography entries, match status, and resolved target papers.",
            cover_label_style,
        ),
        PageBreak(),
        Paragraph(title_text, title_style),
        Paragraph(pdf_text(subtitle), subtitle_style),
        Spacer(1, 6),
    ]

    summary_cells = [
        Paragraph(f"{total}<br/><font size='7'>entries</font>", stat_value_style),
        Paragraph(f"{counts.get('resolved', 0)}<br/><font size='7'>resolved</font>", stat_value_style),
        Paragraph(f"{counts.get('duplicate', 0)}<br/><font size='7'>duplicate</font>", stat_value_style),
        Paragraph(f"{counts.get('partial', 0)}<br/><font size='7'>partial</font>", stat_value_style),
        Paragraph(f"{counts.get('unresolved', 0)}<br/><font size='7'>unresolved</font>", stat_value_style),
    ]
    summary_table = Table([summary_cells], colWidths=[doc.width / 5.0] * 5)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffdf8")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d8cbbc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8cbbc")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 10)])

    if rows:
        header = [
            paragraph("Status", header_style),
            paragraph("Match", header_style),
            paragraph("Bibliography", header_style),
            paragraph("Entry", header_style),
            paragraph("Target", header_style),
            paragraph("Duplicates", header_style),
            paragraph("Order", header_style),
            paragraph("Reference Text", header_style),
        ]
        table_rows: list[list[Paragraph]] = [header]
        for row in rows:
            target = row.get("refersToTitle") or row.get("refersTo") or "-"
            entry_line = _entry_summary(row)
            meta_line = _entry_meta(row)
            status = str(row.get("status") or "unknown")
            match_status = str(row.get("matchStatus") or "-")
            status_style = ParagraphStyle(
                f"LitKGStatus-{status}",
                parent=body_bold_style,
                textColor=colors.HexColor({
                    "resolved": "#1f7a4d",
                    "duplicate": "#8b3fa7",
                    "partial": "#ab6d00",
                    "unresolved": "#9a4b2f",
                }.get(status, "#1e1a17")),
            )
            match_style = ParagraphStyle(
                f"LitKGMatch-{match_status}",
                parent=body_style,
                textColor=colors.HexColor({
                    "resolved": "#1f7a4d",
                    "duplicate": "#8b3fa7",
                    "partial": "#ab6d00",
                    "unresolved": "#9a4b2f",
                }.get(match_status, "#1e1a17")),
            )
            entry_text = Paragraph(f"{pdf_text(entry_line)}<br/>{pdf_text(meta_line)}", body_style)
            table_rows.append(
                [
                    paragraph(status.title(), status_style),
                    paragraph(match_status, match_style),
                    Paragraph(
                        f"<b>{pdf_text(row.get('bibliographyName'))}</b><br/>{pdf_text(row.get('bibliographyFormat'))}",
                        body_style,
                    ),
                    entry_text,
                    paragraph(target, body_style),
                    paragraph(row.get("duplicateCount"), body_style),
                    paragraph(row.get("entryOrder"), body_style),
                    paragraph(row.get("entryText"), body_style),
                ]
            )

        fixed_widths = [42, 52, 108, 160, 110, 48, 38]
        text_width = max(150, doc.width - sum(fixed_widths))
        col_widths = fixed_widths + [text_width]
        table = LongTable(table_rows, colWidths=col_widths, repeatRows=1)
        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1eadf")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6f6258")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8cbbc")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8cbbc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for index, row in enumerate(rows, start=1):
            status = str(row.get("status") or "unknown").lower()
            bg = {
                "resolved": colors.HexColor("#eef8f1"),
                "duplicate": colors.HexColor("#f6effa"),
                "partial": colors.HexColor("#fff6e6"),
                "unresolved": colors.HexColor("#fceee8"),
            }.get(status, colors.HexColor("#ffffff"))
            style_commands.append(("BACKGROUND", (0, index), (-1, index), bg))
        table.setStyle(TableStyle(style_commands))
        story.append(table)
    else:
        empty_style = ParagraphStyle(
            "LitKGEmpty",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#6f6258"),
        )
        story.append(Paragraph("No bibliography entries matched the filter.", empty_style))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Generated by LitKG-RDF.", subtitle_style))

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6f6258"))
        footer_left = f"{report_library_name} | {filter_text} | {generated_at}"
        footer_right = f"Page {canvas.getPageNumber()}"
        canvas.drawString(doc.leftMargin, 8 * mm, footer_left[:180])
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, footer_right)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()
