"""
Report exports besides the PDF: Markdown (report + full debate transcript), BibTeX
(every paper cited in the debate) and DOCX.

All exporters take a session record from the SessionStore and read the evaluation
through normalize_evaluation(), so partial or older evaluations still export cleanly.
"""

import io
import re
import unicodedata

from backend.pdf.report_generator import MODE_LABELS
from backend.scoring.evaluation import normalize_evaluation

_SCORES = (
    ("Novelty", "novelty_score", "novelty"),
    ("Feasibility", "feasibility_score", "feasibility"),
    ("Research gap", "research_gap_score", "research_gap"),
    ("Overall confidence", "overall_confidence", "overall"),
)


def _cell(text: str) -> str:
    """Markdown table cell: no pipes or newlines."""
    return re.sub(r"\s+", " ", (text or "").replace("|", "\\|")).strip()


def _round_label(output: dict) -> str:
    if output.get("stage") == "repair":
        return f"Repair {output.get('attempt', '')} — Innovator".replace("  ", " ")
    return f"Round {output.get('round')} — {output.get('agent')}"


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #

def to_markdown(record: dict) -> str:
    ev = normalize_evaluation(record.get("evaluation_json"))
    lines: list[str] = ["# Research Evaluation Report", ""]
    lines.append(f"**Refined hypothesis:** {ev['refined_hypothesis']}")
    if ev["original_hypothesis"] and ev["original_hypothesis"] != ev["refined_hypothesis"]:
        lines.append(f"\n*Original hypothesis:* {ev['original_hypothesis']}")
    lines.append("")
    meta = [
        f"Mode: {MODE_LABELS.get(record.get('mode'), 'Hypothesis')}",
        f"Session: {record.get('session_id', '')[:8]}",
        f"Created: {record.get('created_at', '')}",
    ]
    if ev["model"]:
        meta.append(f"Model: {ev['model']}")
    if ev["cost_usd"]:
        meta.append(f"LLM cost: ${ev['cost_usd']:.3f}")
    lines.append(" · ".join(meta))
    lines.append("")
    if ev["low_confidence_flag"]:
        lines += ["> **Low confidence:** the RAGAS faithfulness score stayed below 0.7 after repair attempts.", ""]

    lines += ["## Scores", "", "| Score | Value | Range | Rationale |", "|---|---|---|---|"]
    for label, key, rkey in _SCORES:
        lo, hi = ev["score_ranges"][rkey]
        lines.append(f"| {label} | {ev[key]} | {lo}–{hi} | {_cell(ev['score_rationale'].get(rkey, ''))} |")
    lines.append(f"| RAGAS faithfulness | {ev['ragas_score']:.2f} | | Share of Innovator claims backed by a retrieved paper |")
    lines.append("")

    for title, items in (("Strengths", ev["strengths"]), ("Weaknesses & Risks", ev["weaknesses"])):
        lines += [f"## {title}", ""] + [f"- {item}" for item in items] + [""]

    lines += ["## Chaos Constraint", "", f"> {ev['chaos_constraint']}", "", ev["chaos_response_summary"], ""]
    lines += ["## Proposed Methodology", ""] + [f"{i}. {s}" for i, s in enumerate(ev["proposed_methodology"], 1)] + [""]

    if ev["top_papers"]:
        lines += ["## Literature Snapshot", "", "| Paper | Relevance | Summary |", "|---|---|---|"]
        for p in ev["top_papers"]:
            title = f"[{_cell(p['title'])}]({p['url']})" if p["url"] else _cell(p["title"])
            lines.append(f"| {title} | {p['relevance_score']:.0f} | {_cell(p['summary'])} |")
        lines.append("")

    if ev["claim_audit"]:
        lines += ["## Claim Evidence Audit", "", "| Round | Claim | Verdict | Evidence |", "|---|---|---|---|"]
        for r in ev["claim_audit"]:
            verdict = r["verdict"] + (f" ({r['resolved']})" if r["resolved"] else "")
            evidence = f"[{_cell(r['paper_title'])}]({r['paper_url']})" if r["paper_url"] else _cell(r["paper_title"])
            if r["quote"]:
                evidence += f' — "{_cell(r["quote"])}"'
            if not evidence:
                evidence = _cell(r["reason"])
            claim = _cell(r["claim"]) + (f" → *{_cell(r['revised_to'])}*" if r["revised_to"] else "")
            lines.append(f"| R{r['round']} | {claim} | {verdict} | {evidence} |")
        lines.append("")

    lines += ["## References", ""]
    for i, ref in enumerate(ev["references"], 1):
        lines.append(f"{i}. {ref}")
    lines.append("")

    transcript = (record.get("transcript") or {}).get("round_outputs") or []
    if transcript:
        lines += ["## Debate Transcript", ""]
        for output in transcript:
            lines += [f"### {_round_label(output)}", "", output.get("content", ""), ""]
            if output.get("claims"):
                lines += ["**Claims:**", ""] + [f"- {c}" for c in output["claims"]] + [""]
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# BibTeX
# --------------------------------------------------------------------------- #

def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def _bib_value(text: str) -> str:
    return (text or "").replace("{", "").replace("}", "").replace("\n", " ").strip()


def _bib_key(meta: dict, used: set[str]) -> str:
    authors = meta.get("authors_full") or meta.get("authors") or ""
    first = authors.split(",")[0].strip().split(" ")[-1] if authors else "anon"
    word = next((w for w in re.findall(r"[A-Za-z]+", meta.get("title", "")) if len(w) > 3), "paper")
    base = re.sub(r"[^a-z0-9]", "", _ascii(f"{first}{meta.get('year', '')}{word}").lower()) or "ref"
    key, n = base, 2
    while key in used:
        key, n = f"{base}{n}", n + 1
    used.add(key)
    return key


def to_bibtex(record: dict) -> str:
    ev = normalize_evaluation(record.get("evaluation_json"))
    entries, used = [], set()
    for meta in ev["references_meta"]:
        authors = [a.strip() for a in (meta.get("authors_full") or "").split(",") if a.strip()]
        fields = [f"  title = {{{{{_bib_value(meta['title'])}}}}}"]
        if authors:
            fields.append(f"  author = {{{_bib_value(' and '.join(authors))}}}")
        if meta["year"]:
            fields.append(f"  year = {{{meta['year']}}}")
        if meta["doi"]:
            fields.append(f"  doi = {{{_bib_value(meta['doi'])}}}")
        if meta["arxiv_id"]:
            fields += [f"  eprint = {{{_bib_value(meta['arxiv_id'])}}}", "  archivePrefix = {arXiv}"]
        if meta["url"]:
            fields.append(f"  url = {{{_bib_value(meta['url'])}}}")
        kind = "misc" if meta["arxiv_id"] and not meta["doi"] else "article"
        entries.append(f"@{kind}{{{_bib_key(meta, used)},\n" + ",\n".join(fields) + "\n}")
    header = f"% Autonomous Research Council - references for session {record.get('session_id', '')[:8]}\n"
    return header + "\n\n".join(entries) + ("\n" if entries else "% No papers were cited in this debate.\n")


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #

def _para(doc, text: str, *, bold: bool = False, italic: bool = False, style: str | None = None):
    paragraph = doc.add_paragraph(style=style)
    run = paragraph.add_run(text or "")
    run.bold, run.italic = bold, italic
    return paragraph


def to_docx(record: dict) -> bytes:
    from docx import Document
    from docx.shared import Pt

    ev = normalize_evaluation(record.get("evaluation_json"))
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10.5)

    doc.add_heading("Research Evaluation Report", level=0)
    _para(doc, ev["refined_hypothesis"], bold=True)
    if ev["original_hypothesis"] and ev["original_hypothesis"] != ev["refined_hypothesis"]:
        _para(doc, f"Original hypothesis: {ev['original_hypothesis']}", italic=True)
    meta = f"Mode: {MODE_LABELS.get(record.get('mode'), 'Hypothesis')} · Created: {record.get('created_at', '')}"
    if ev["model"]:
        meta += f" · Model: {ev['model']}"
    doc.add_paragraph(meta)
    if ev["low_confidence_flag"]:
        doc.add_paragraph("Low confidence: the RAGAS faithfulness score stayed below 0.7 after repair attempts.")

    doc.add_heading("Scores", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    for cell, text in zip(table.rows[0].cells, ("Score", "Value", "Range", "Rationale")):
        cell.text = text
    for label, key, rkey in _SCORES:
        lo, hi = ev["score_ranges"][rkey]
        row = table.add_row().cells
        row[0].text, row[1].text, row[2].text = label, str(ev[key]), f"{lo}–{hi}"
        row[3].text = ev["score_rationale"].get(rkey, "")
    row = table.add_row().cells
    row[0].text, row[1].text = "RAGAS faithfulness", f"{ev['ragas_score']:.2f}"

    for title, items in (("Strengths", ev["strengths"]), ("Weaknesses & Risks", ev["weaknesses"])):
        doc.add_heading(title, level=1)
        for item in items:
            doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Chaos Constraint", level=1)
    _para(doc, ev["chaos_constraint"], italic=True)
    doc.add_paragraph(ev["chaos_response_summary"])

    doc.add_heading("Proposed Methodology", level=1)
    for step in ev["proposed_methodology"]:
        doc.add_paragraph(step, style="List Number")

    if ev["claim_audit"]:
        doc.add_heading("Claim Evidence Audit", level=1)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Light Grid Accent 1"
        for cell, text in zip(table.rows[0].cells, ("Round", "Claim", "Verdict", "Evidence")):
            cell.text = text
        for r in ev["claim_audit"]:
            row = table.add_row().cells
            row[0].text = f"R{r['round']}"
            row[1].text = r["claim"] + (f" → {r['revised_to']}" if r["revised_to"] else "")
            row[2].text = r["verdict"] + (f" ({r['resolved']})" if r["resolved"] else "")
            row[3].text = r["paper_title"] + (f' — "{r["quote"]}"' if r["quote"] else "") or r["reason"]

    doc.add_heading("References", level=1)
    for ref in ev["references"]:
        doc.add_paragraph(ref, style="List Number")

    transcript = (record.get("transcript") or {}).get("round_outputs") or []
    if transcript:
        doc.add_heading("Debate Transcript", level=1)
        for output in transcript:
            doc.add_heading(_round_label(output), level=2)
            doc.add_paragraph(output.get("content", ""))

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
