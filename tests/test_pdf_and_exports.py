import io

from pypdf import PdfReader

from backend.export.exporters import to_bibtex, to_docx, to_markdown
from backend.pdf.report_generator import generate_pdf

HOSTILE = {
    "novelty_score": "80",
    "feasibility_score": 55,
    "research_gap_score": "n/a",
    "overall_confidence": 30,
    "ragas_score": 0.5,
    "low_confidence_flag": True,
    # Each of these raised ReportLab "Parse error" / was silently dropped before escaping
    "refined_hypothesis": "Models using List<String> inputs beat <b>baselines when p < 0.05 & n > 100",
    "strengths": ["uses <b>bold without close", "a </i> stray tag", "tag <a href=x>link"],
    "weaknesses": "- <br\n- R&D budget",
    "chaos_constraint": "Assume <sub>budget</sub> is cut",
    "chaos_response_summary": "Adapted.",
    "proposed_methodology": ["Step 1: Collect <data>", {"step": "Step 2: Train"}],
    "top_papers": [{"title": "Paper <1>", "relevance_score": "71", "summary": "x < y", "url": "https://a.org/?q=1&r=2"}],
    "claim_audit": [{"claim": "Claim <x>", "round": 1, "verdict": "contradicted", "paper_title": "P",
                     "paper_url": "https://p", "quote": "q & a"}],
    "references_meta": [{"title": "Ref & <Title>", "authors_full": "Ann Lee, Bo Chen", "year": "2023",
                         "url": "https://doi.org/10.1/x", "doi": "10.1/x"}],
    "references": ["Ref & <Title>"],
}


def _record():
    return {"session_id": "abcdef12-0000", "mode": 2, "created_at": "2026-09-30T10:00:00+00:00",
            "evaluation_json": HOSTILE,
            "transcript": {"round_outputs": [{"agent": "Innovator", "round": 1, "content": "Hi <there>",
                                              "claims": ["c1"]}]}}


def test_pdf_survives_markup_in_llm_text():
    path = generate_pdf("pdf-hostile-test", HOSTILE, mode=2)
    text = "".join(page.extract_text() for page in PdfReader(path).pages)
    # Escaped text is rendered literally instead of being parsed or dropped
    assert "List<String>" in text
    assert "<b>bold without close" in text
    assert "R&D budget" in text


def test_pdf_with_empty_evaluation():
    path = generate_pdf("pdf-empty-test", {}, mode=1)
    assert PdfReader(path).pages


def test_markdown_export():
    md = to_markdown(_record())
    assert md.startswith("# Research Evaluation Report")
    assert "## Claim Evidence Audit" in md
    assert "## Debate Transcript" in md
    assert "| Novelty | 80 |" in md


def test_bibtex_export():
    bib = to_bibtex(_record())
    assert "@article{" in bib
    assert "author = {Ann Lee and Bo Chen}" in bib
    assert "doi = {10.1/x}" in bib


def test_docx_export():
    from docx import Document

    data = to_docx(_record())
    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Research Evaluation Report" in text
    assert "List<String>" in text
