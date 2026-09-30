"""
ReportLab PDF report generator.
Input:  Chairman evaluation_json (single source of truth)
Output: sessions/{session_id}.pdf

Every piece of LLM-written text is XML-escaped before it reaches a Paragraph:
ReportLab parses Paragraph text as markup, so an unclosed "<b>" or a stray "</i>"
in model output used to raise "Parse error" and fail the whole session.
"""

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.config import get_settings
from backend.scoring.evaluation import normalize_evaluation

# --------------------------------------------------------------------------- #
# Colour palette
# --------------------------------------------------------------------------- #
_C_DARK       = colors.HexColor("#1e293b")
_C_ACCENT     = colors.HexColor("#3b82f6")
_C_GREEN      = colors.HexColor("#22c55e")
_C_AMBER      = colors.HexColor("#f59e0b")
_C_RED        = colors.HexColor("#ef4444")
_C_WARNING_BG = colors.HexColor("#fef9c3")
_C_LIGHT_GREY = colors.HexColor("#f1f5f9")
_C_MID_GREY   = colors.HexColor("#94a3b8")
_C_WHITE      = colors.white

_VERDICT_COLORS = {
    "supported": _C_GREEN,
    "partial": _C_AMBER,
    "unsupported": _C_RED,
    "contradicted": _C_RED,
}


def esc(value) -> str:
    """Escapes arbitrary text for ReportLab Paragraph markup."""
    return _xml_escape("" if value is None else str(value))


def _link(url: str, label: str | None = None) -> str:
    if not url:
        return esc(label or "")
    href = _xml_escape(url, {'"': "&quot;"})
    return f'<a href="{href}" color="#3b82f6">{esc(label or url)}</a>'


def _score_color(score) -> colors.Color:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return _C_MID_GREY
    if value > 75:
        return _C_GREEN
    if value >= 50:
        return _C_AMBER
    return _C_RED


def _build_styles() -> dict:
    return {
        "title": ParagraphStyle(
            "title", fontSize=22, fontName="Helvetica-Bold",
            textColor=_C_DARK, spaceAfter=4, alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontSize=11, fontName="Helvetica-Oblique",
            textColor=_C_MID_GREY, spaceAfter=2, alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "section", fontSize=13, fontName="Helvetica-Bold",
            textColor=_C_ACCENT, spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", fontSize=10, fontName="Helvetica",
            textColor=_C_DARK, spaceAfter=4, leading=15,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontSize=10, fontName="Helvetica",
            textColor=_C_DARK, spaceAfter=3, leftIndent=12, leading=14,
        ),
        "small": ParagraphStyle(
            "small", fontSize=8, fontName="Helvetica",
            textColor=_C_DARK, spaceAfter=2, leading=11,
        ),
        "small_center": ParagraphStyle(
            "small_center", fontSize=8, fontName="Helvetica-Bold",
            textColor=_C_DARK, leading=11, alignment=TA_CENTER,
        ),
        "warning": ParagraphStyle(
            "warning", fontSize=10, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#92400e"), spaceAfter=4,
            backColor=_C_WARNING_BG, borderPadding=(6, 8, 6, 8),
        ),
        "chaos_label": ParagraphStyle(
            "chaos_label", fontSize=10, fontName="Helvetica-Bold",
            textColor=_C_ACCENT, spaceAfter=2,
        ),
    }


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #

def _header(ev: dict, styles: dict, mode_label: str) -> list:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = f"<b>Mode:</b> {esc(mode_label)} &nbsp;&nbsp; <b>Generated:</b> {timestamp}"
    if ev.get("model"):
        meta += f" &nbsp;&nbsp; <b>Model:</b> {esc(ev['model'])}"
    if ev.get("cost_usd"):
        meta += f" &nbsp;&nbsp; <b>LLM cost:</b> ${ev['cost_usd']:.3f}"
    return [
        Paragraph("Autonomous Research Council", styles["title"]),
        Paragraph("Research Evaluation Report", styles["subtitle"]),
        Spacer(1, 2 * mm),
        HRFlowable(width="100%", thickness=1, color=_C_ACCENT),
        Spacer(1, 3 * mm),
        Paragraph(meta, styles["body"]),
        Spacer(1, 4 * mm),
    ]


def _low_confidence_warning(styles: dict) -> list:
    return [
        Paragraph(
            "WARNING: Low Confidence Output - the RAGAS faithfulness score did not reach "
            "the 0.7 threshold, even after repair attempts. Treat findings with additional scrutiny.",
            styles["warning"],
        ),
        Spacer(1, 4 * mm),
    ]


def _executive_summary(ev: dict, styles: dict) -> list:
    elems = [
        Paragraph("Executive Summary", styles["section"]),
        Paragraph(esc(ev["refined_hypothesis"]), styles["body"]),
    ]
    original = ev.get("original_hypothesis")
    if original and original != ev["refined_hypothesis"]:
        elems.append(Paragraph(f"<i>Original hypothesis:</i> {esc(original)}", styles["small"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _scores_table(ev: dict, styles: dict) -> list:
    rows = [
        ("Novelty", "novelty_score", "novelty"),
        ("Feasibility", "feasibility_score", "feasibility"),
        ("Research Gap", "research_gap_score", "research_gap"),
        ("Overall Conf.", "overall_confidence", "overall"),
    ]
    ragas = ev["ragas_score"]

    header_row = [Paragraph(f"<b>{label}</b>", styles["body"]) for label, _, _ in rows]
    value_row = []
    for _, key, range_key in rows:
        lo, hi = ev["score_ranges"][range_key]
        spread = f"<br/><font size=7>range {lo}-{hi}</font>" if hi != lo else ""
        value_row.append(Paragraph(f"<b>{ev[key]}</b>{spread}", styles["body"]))

    score_table = Table([header_row, value_row], colWidths=[42 * mm] * 4)
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _C_LIGHT_GREY),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",       (0, 0), (-1, -1), 0.5, _C_MID_GREY),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ])
    for col, (_, key, _) in enumerate(rows):
        ts.add("TEXTCOLOR", (col, 1), (col, 1), _score_color(ev[key]))
    score_table.setStyle(ts)

    ragas_color = _C_GREEN if ragas >= 0.7 else _C_RED
    ragas_table = Table(
        [[
            Paragraph("<b>RAGAS Faithfulness Score</b> (share of the Innovator's claims backed by a retrieved paper)",
                      styles["body"]),
            Paragraph(f"<b>{ragas:.2f}</b>", ParagraphStyle(
                "ragas_val", fontSize=10, fontName="Helvetica-Bold",
                textColor=ragas_color, alignment=TA_CENTER,
            )),
        ]],
        colWidths=[130 * mm, 38 * mm],
    )
    ragas_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_LIGHT_GREY),
        ("GRID",       (0, 0), (-1, -1), 0.5, _C_MID_GREY),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    elems = [
        Paragraph("Evaluation Scores", styles["section"]),
        score_table,
        Spacer(1, 3 * mm),
        ragas_table,
    ]
    if ev.get("score_samples", 1) > 1:
        elems.append(Paragraph(
            f"Scores are the median of {ev['score_samples']} independent Chairman assessments; "
            "ranges show their spread.", styles["small"]))
    rationale = ev.get("score_rationale", {})
    for label, key in (("Novelty", "novelty"), ("Feasibility", "feasibility"),
                       ("Research gap", "research_gap"), ("Overall", "overall")):
        if rationale.get(key):
            elems.append(Paragraph(f"<b>{label}:</b> {esc(rationale[key])}", styles["small"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _bullet_section(title: str, items: list[str], bullet: str, styles: dict) -> list:
    elems: list = [Paragraph(esc(title), styles["section"])]
    for item in items:
        elems.append(Paragraph(f"{esc(bullet)}&nbsp;&nbsp;{esc(item)}", styles["bullet"]))
    if not items:
        elems.append(Paragraph("None recorded.", styles["small"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _chaos_summary(ev: dict, styles: dict) -> list:
    return [
        Paragraph("Chaos Constraint", styles["section"]),
        Paragraph(f"<b>Injected constraint:</b> {esc(ev['chaos_constraint'])}", styles["chaos_label"]),
        Paragraph(esc(ev["chaos_response_summary"]), styles["body"]),
        Spacer(1, 4 * mm),
    ]


def _methodology(ev: dict, styles: dict) -> list:
    elems: list = [Paragraph("Proposed Methodology", styles["section"])]
    for i, step in enumerate(ev["proposed_methodology"], 1):
        elems.append(Paragraph(f"{i}.&nbsp;&nbsp;{esc(step)}", styles["bullet"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _literature_table(ev: dict, styles: dict) -> list:
    papers = ev["top_papers"][:5]
    if not papers:
        return []
    header = [
        Paragraph("<b>Title</b>", styles["body"]),
        Paragraph("<b>Score</b>", styles["body"]),
        Paragraph("<b>Summary</b>", styles["body"]),
    ]
    rows = [header]
    for p in papers:
        score = p["relevance_score"]
        rows.append([
            Paragraph(_link(p["url"], p["title"]) if p["url"] else esc(p["title"]), styles["small"]),
            Paragraph(f"{score:.0f}", ParagraphStyle(
                "lit_score", fontSize=9, fontName="Helvetica-Bold",
                textColor=_score_color(score), alignment=TA_CENTER,
            )),
            Paragraph(esc(p["summary"]), styles["small"]),
        ])

    tbl = Table(rows, colWidths=[65 * mm, 18 * mm, 85 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _C_LIGHT_GREY),
        ("GRID",          (0, 0), (-1, -1), 0.5, _C_MID_GREY),
        ("ALIGN",         (1, 0), (1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_WHITE, _C_LIGHT_GREY]),
    ]))
    return [
        Paragraph("Literature Snapshot", styles["section"]),
        tbl,
        Spacer(1, 4 * mm),
    ]


def _claim_audit(ev: dict, styles: dict) -> list:
    records = ev["claim_audit"]
    if not records:
        return []
    header = [Paragraph(f"<b>{h}</b>", styles["small"]) for h in ("Claim", "Verdict", "Evidence")]
    rows = [header]
    verdict_colors = []
    for r in records:
        verdict = r["verdict"]
        label = verdict.upper()
        if r["resolved"]:
            label += f"<br/><font size=6>{esc(r['resolved'])}</font>"
        evidence = ""
        if r["paper_title"]:
            evidence = _link(r["paper_url"], r["paper_title"])
            if r["quote"]:
                evidence += f'<br/><i>"{esc(r["quote"])}"</i>'
        elif r["reason"]:
            evidence = esc(r["reason"])
        claim = esc(r["claim"])
        if r["resolved"] == "revised" and r["revised_to"]:
            claim += f"<br/><font size=7>Revised to: {esc(r['revised_to'])}</font>"
        rows.append([
            Paragraph(f"<font size=7>R{r['round']}</font> {claim}", styles["small"]),
            Paragraph(label, styles["small_center"]),
            Paragraph(evidence, styles["small"]),
        ])
        verdict_colors.append(_VERDICT_COLORS.get(verdict, _C_MID_GREY))

    tbl = Table(rows, colWidths=[78 * mm, 22 * mm, 68 * mm], repeatRows=1)
    style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _C_LIGHT_GREY),
        ("GRID",          (0, 0), (-1, -1), 0.5, _C_MID_GREY),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    for i, color in enumerate(verdict_colors, 1):
        style.add("TEXTCOLOR", (1, i), (1, i), color)
    tbl.setStyle(style)

    counts: dict[str, int] = {}
    for r in records:
        if not r["resolved"]:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    return [
        Paragraph("Claim Evidence Audit", styles["section"]),
        Paragraph(f"Every Innovator claim, checked against the retrieved abstracts. Standing claims: {esc(summary)}.",
                  styles["small"]),
        Spacer(1, 2 * mm),
        tbl,
        Spacer(1, 4 * mm),
    ]


def _attempts(ev: dict, styles: dict) -> list:
    attempts = ev["attempts"]
    if len(attempts) <= 1:
        return []
    parts = [f"attempt {a.get('attempt', i)}: {float(a.get('ragas_score') or 0):.2f}" for i, a in enumerate(attempts)]
    return [Paragraph(f"<b>RAGAS by attempt</b> (repair rounds): {esc('; '.join(parts))}", styles["small"]),
            Spacer(1, 3 * mm)]


def _references(ev: dict, styles: dict) -> list:
    elems: list = [
        Paragraph("References", styles["section"]),
        HRFlowable(width="100%", thickness=0.5, color=_C_MID_GREY),
        Spacer(1, 2 * mm),
    ]
    metas = ev["references_meta"]
    if metas:
        for i, meta in enumerate(metas, 1):
            head = ", ".join(x for x in (meta["authors"], f"({meta['year']})" if meta["year"] else "") if x)
            text = f"[{i}]&nbsp;&nbsp;{esc(head)}{'. ' if head else ''}{esc(meta['title'])}."
            if meta["url"]:
                text += f" {_link(meta['url'])}"
            elems.append(Paragraph(text, styles["small"]))
    else:
        for i, ref in enumerate(ev["references"], 1):
            elems.append(Paragraph(f"[{i}]&nbsp;&nbsp;{esc(ref)}", styles["small"]))
    return elems


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

MODE_LABELS = {1: "Topic", 2: "Hypothesis", 3: "Partial Proposal"}


def generate_pdf(session_id: str, evaluation_json: dict, mode: int = 2) -> str:
    """
    Generates a PDF report from the Chairman's evaluation_json.
    Saves to {ARC_SESSIONS_DIR}/{session_id}.pdf and returns the file path.
    """
    sessions_dir = get_settings().sessions_dir
    sessions_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(sessions_dir) / f"{session_id}.pdf"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="ARC Research Evaluation Report",
    )

    ev = normalize_evaluation(evaluation_json)
    styles = _build_styles()

    story: list = []
    story += _header(ev, styles, MODE_LABELS.get(mode, "Hypothesis"))

    if ev["low_confidence_flag"]:
        story += _low_confidence_warning(styles)

    story += _executive_summary(ev, styles)
    story += _scores_table(ev, styles)
    story += _attempts(ev, styles)
    story += _bullet_section("Strengths", ev["strengths"], "+", styles)
    story += _bullet_section("Weaknesses & Risks", ev["weaknesses"], "-", styles)
    story += _chaos_summary(ev, styles)
    story += _methodology(ev, styles)
    story += _literature_table(ev, styles)
    story += _claim_audit(ev, styles)
    story += _references(ev, styles)

    doc.build(story)
    return str(out_path)
