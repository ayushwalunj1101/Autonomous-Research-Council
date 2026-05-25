"""
ReportLab PDF report generator.
Input:  Chairman evaluation_json (single source of truth)
Output: sessions/{session_id}.pdf
"""

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SESSIONS_DIR = Path("sessions")

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


def _score_color(score: int) -> colors.Color:
    if score > 75:
        return _C_GREEN
    if score >= 50:
        return _C_AMBER
    return _C_RED


def _build_styles() -> dict:
    base = getSampleStyleSheet()
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
            textColor=_C_DARK, spaceAfter=2, leading=12,
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

def _header(ev: dict, styles: dict, mode_labels: dict) -> list:
    mode_label = mode_labels.get(ev.get("mode", 2), "Hypothesis")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return [
        Paragraph("Autonomous Research Council", styles["title"]),
        Paragraph("Research Evaluation Report", styles["subtitle"]),
        Spacer(1, 2 * mm),
        HRFlowable(width="100%", thickness=1, color=_C_ACCENT),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Mode:</b> {mode_label} &nbsp;&nbsp; <b>Generated:</b> {timestamp}", styles["body"]),
        Spacer(1, 4 * mm),
    ]


def _low_confidence_warning(styles: dict) -> list:
    return [
        Paragraph(
            "WARNING: Low Confidence Output — RAGAS faithfulness score did not reach "
            "the 0.7 threshold after 2 retry attempts. Treat findings with additional scrutiny.",
            styles["warning"],
        ),
        Spacer(1, 4 * mm),
    ]


def _executive_summary(ev: dict, styles: dict) -> list:
    return [
        Paragraph("Executive Summary", styles["section"]),
        Paragraph(ev.get("refined_hypothesis", ""), styles["body"]),
        Spacer(1, 4 * mm),
    ]


def _scores_table(ev: dict, styles: dict) -> list:
    scores = [
        ("Novelty",         ev.get("novelty_score", 0)),
        ("Feasibility",     ev.get("feasibility_score", 0)),
        ("Research Gap",    ev.get("research_gap_score", 0)),
        ("Overall Conf.",   ev.get("overall_confidence", 0)),
    ]
    ragas = ev.get("ragas_score", 0.0)

    header_row = [Paragraph(f"<b>{label}</b>", styles["body"]) for label, _ in scores]
    value_row  = [Paragraph(f"<b>{val}</b>", styles["body"]) for _, val in scores]

    score_table = Table(
        [header_row, value_row],
        colWidths=[42 * mm] * 4,
    )
    cell_colors = [_score_color(val) for _, val in scores]
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _C_LIGHT_GREY),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",       (0, 0), (-1, -1), 0.5, _C_MID_GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, 1), [_C_WHITE]),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ])
    for col, c in enumerate(cell_colors):
        ts.add("TEXTCOLOR", (col, 1), (col, 1), c)
        ts.add("FONTNAME",  (col, 1), (col, 1), "Helvetica-Bold")
    score_table.setStyle(ts)

    ragas_color = _C_GREEN if ragas >= 0.7 else _C_RED
    ragas_table = Table(
        [[
            Paragraph("<b>RAGAS Faithfulness Score</b>", styles["body"]),
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

    return [
        Paragraph("Evaluation Scores", styles["section"]),
        score_table,
        Spacer(1, 3 * mm),
        ragas_table,
        Spacer(1, 4 * mm),
    ]


def _bullet_section(title: str, items: list[str], bullet: str, styles: dict) -> list:
    elems: list = [Paragraph(title, styles["section"])]
    for item in items:
        elems.append(Paragraph(f"{bullet}  {item}", styles["bullet"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _chaos_summary(ev: dict, styles: dict) -> list:
    constraint = ev.get("chaos_constraint", "")
    summary    = ev.get("chaos_response_summary", "")
    return [
        Paragraph("Chaos Constraint", styles["section"]),
        Paragraph(f"<b>Injected constraint:</b> {constraint}", styles["chaos_label"]),
        Paragraph(summary, styles["body"]),
        Spacer(1, 4 * mm),
    ]


def _methodology(ev: dict, styles: dict) -> list:
    steps = ev.get("proposed_methodology", [])
    elems: list = [Paragraph("Proposed Methodology", styles["section"])]
    for i, step in enumerate(steps, 1):
        elems.append(Paragraph(f"{i}.  {step}", styles["bullet"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _literature_table(ev: dict, styles: dict) -> list:
    papers = ev.get("top_papers", [])[:5]
    header = [
        Paragraph("<b>Title</b>", styles["body"]),
        Paragraph("<b>Score</b>", styles["body"]),
        Paragraph("<b>Summary</b>", styles["body"]),
    ]
    rows = [header]
    for p in papers:
        score = p.get("relevance_score", 0)
        rows.append([
            Paragraph(p.get("title", ""), styles["small"]),
            Paragraph(str(score), ParagraphStyle(
                "lit_score", fontSize=9, fontName="Helvetica-Bold",
                textColor=_score_color(score), alignment=TA_CENTER,
            )),
            Paragraph(p.get("summary", ""), styles["small"]),
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


def _references(ev: dict, styles: dict) -> list:
    refs = ev.get("references", [])
    elems: list = [
        Paragraph("References", styles["section"]),
        HRFlowable(width="100%", thickness=0.5, color=_C_MID_GREY),
        Spacer(1, 2 * mm),
    ]
    for i, ref in enumerate(refs, 1):
        elems.append(Paragraph(f"[{i}]  {ref}", styles["small"]))
    return elems


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

def generate_pdf(session_id: str, evaluation_json: dict, mode: int = 2) -> str:
    """
    Generates a PDF report from the Chairman's evaluation_json.
    Saves to sessions/{session_id}.pdf.
    Returns the absolute file path.
    """
    SESSIONS_DIR.mkdir(exist_ok=True)
    out_path = SESSIONS_DIR / f"{session_id}.pdf"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="ARC Research Evaluation Report",
    )

    mode_labels = {1: "Topic", 2: "Hypothesis", 3: "Partial Proposal"}
    ev = evaluation_json
    styles = _build_styles()

    # Attach mode to ev for header (if not present)
    if "mode" not in ev:
        ev = dict(ev)
        ev["mode"] = mode

    story: list = []
    story += _header(ev, styles, mode_labels)

    if ev.get("low_confidence_flag"):
        story += _low_confidence_warning(styles)

    story += _executive_summary(ev, styles)
    story += _scores_table(ev, styles)
    story += _bullet_section("Strengths", ev.get("strengths", []), "✓", styles)
    story += _bullet_section("Weaknesses & Risks", ev.get("weaknesses", []), "✗", styles)
    story += _chaos_summary(ev, styles)
    story += _methodology(ev, styles)
    story += _literature_table(ev, styles)
    story += _references(ev, styles)

    doc.build(story)
    return str(out_path)
