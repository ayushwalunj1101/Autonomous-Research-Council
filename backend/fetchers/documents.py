"""Text extraction for uploaded files: mode-3 proposals (PDF/DOCX/TXT) and user-added PDF papers."""

import io
import re
from pathlib import Path

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class UnsupportedDocument(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedDocument("File is larger than 15 MB.")
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages[:40]]
        except Exception as exc:
            raise UnsupportedDocument(f"Could not read the PDF: {exc}") from exc
        text = "\n".join(pages)
    elif suffix == ".docx":
        from docx import Document

        try:
            doc = Document(io.BytesIO(data))
        except Exception as exc:
            raise UnsupportedDocument(f"Could not read the DOCX file: {exc}") from exc
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix in (".txt", ".md"):
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnsupportedDocument("Upload a PDF, DOCX, TXT or MD file.")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise UnsupportedDocument("No text could be extracted (is the PDF scanned?).")
    return text


def paper_from_upload(filename: str, data: bytes) -> dict:
    """Builds a paper record from an uploaded PDF: first meaningful line = title, abstract section if found."""
    text = extract_text(filename, data)
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    title = lines[0][:200] if lines else Path(filename).stem

    match = re.search(r"\babstract\b[:.\s]*(.{200,2500}?)(?:\n\s*\n|\b(?:1\.?\s+)?introduction\b)", text, re.I | re.S)
    abstract = match.group(1) if match else text[:2000]
    abstract = re.sub(r"\s+", " ", abstract).strip()
    return {
        "title": title,
        "abstract": abstract,
        "authors": [],
        "url": "",
        "source": "upload",
        "user_added": True,
    }
