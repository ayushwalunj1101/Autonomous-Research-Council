import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FAKE_PAPERS

TERMINAL_EVENTS = {"report_ready", "pipeline_error", "cancelled", "session_status"}


@pytest.fixture
def api(monkeypatch):
    from backend.agents import librarian

    monkeypatch.setattr(librarian, "_fetch_all",
                        lambda keywords, domain, broad=False: {"arxiv": [dict(p) for p in FAKE_PAPERS]})
    monkeypatch.setattr(librarian, "fetch_arxiv_by_id", lambda identifier: {
        "title": "User added paper on federated clinical models",
        "abstract": "Federated learning improves clinical prediction on standard benchmarks.",
        "authors": ["Added Author"], "url": "https://arxiv.org/abs/2402.00001",
        "arxiv_id": "2402.00001", "published": "2024-02-01", "source": "arxiv",
    })
    from backend.main import app

    with TestClient(app) as client:
        yield client


def _status(api, sid) -> str:
    resp = api.get(f"/api/session/{sid}/result")
    if resp.status_code == 202:
        return resp.json()["status"]
    return {200: "complete", 409: "cancelled", 500: "error"}[resp.status_code]


def _wait_for(api, sid, statuses, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _status(api, sid)
        if status in statuses:
            return status
        time.sleep(0.2)
    raise AssertionError(f"session {sid} never reached {statuses} (last: {status})")


def _read_stream(api, sid, last_event_id=None) -> list[dict]:
    url = f"/api/session/{sid}/stream" + (f"?last_event_id={last_event_id}" if last_event_id is not None else "")
    events, current = [], {}
    with api.stream("GET", url) as resp:
        for line in resp.iter_lines():
            if not line.strip():
                if current.get("event") and current["event"] != "keepalive":
                    events.append(current)
                    if current["event"] in TERMINAL_EVENTS:
                        break
                current = {}
                continue
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "data":
                current["data"] = json.loads(value)
            elif field in ("event", "id"):
                current[field] = value
    return events


def _prepare(api, text="Federated learning improves clinical prediction models without sharing patient data."):
    resp = api.post("/api/session/prepare", json={"mode": 2, "user_input": text})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health(api):
    body = api.get("/api/health").json()
    assert body["status"] == "ok" and body["provider"] == "mock"


def test_two_step_flow_with_paper_review_and_exports(api):
    prepared = _prepare(api)
    sid = prepared["session_id"]
    assert prepared["keywords"] and prepared["hypothesis"]

    resp = api.post(f"/api/session/{sid}/start", json={
        "hypothesis": prepared["hypothesis"], "keywords": ["federated learning", "clinical prediction"],
        "review_papers": True,
    })
    assert resp.status_code == 202
    # Starting twice is rejected
    assert api.post(f"/api/session/{sid}/start", json={}).status_code == 409

    _wait_for(api, sid, {"awaiting_review"})
    papers = api.get(f"/api/session/{sid}/papers").json()["papers"]
    assert len(papers) == len(FAKE_PAPERS)

    added = api.post(f"/api/session/{sid}/papers", json={"identifier": "arXiv:2402.00001"})
    assert added.status_code == 200 and added.json()["paper"]["user_added"]
    bad = api.post(f"/api/session/{sid}/papers", json={"identifier": "not an id"})
    assert bad.status_code == 422

    remove = [papers[-1]["id"]]
    assert api.post(f"/api/session/{sid}/papers/confirm", json={"remove_ids": remove}).status_code == 200
    assert _wait_for(api, sid, {"complete", "error"}) == "complete"

    events = _read_stream(api, sid)
    ids = [int(e["id"]) for e in events if "id" in e]
    assert ids == sorted(ids) and len(ids) == len(set(ids)), "event ids are unique and ordered"
    kinds = [e["event"] for e in events]
    for expected in ("session_info", "papers_loaded", "papers_confirmed", "round_start", "round_complete",
                     "claims_verified", "citation_flag", "chaos_injection", "ragas_score", "retry", "report_ready"):
        assert expected in kinds, f"missing {expected}"
    loaded = next(e for e in events if e["event"] == "papers_loaded")["data"]
    assert loaded["count"] == len(FAKE_PAPERS) and loaded["awaiting_review"] and loaded["papers"][0]["title"]
    assert next(e for e in events if e["event"] == "papers_confirmed")["data"]["count"] == len(FAKE_PAPERS)
    complete = [e for e in events if e["event"] == "round_complete"]
    assert all(e["data"]["content"] for e in complete), "full text is streamed, not only summaries"

    # Reconnect replay: only events after the given id
    replay = _read_stream(api, sid, last_event_id=ids[4])
    assert int(replay[0]["id"]) == ids[5] and replay[-1]["event"] == "report_ready"
    assert len(replay) == len([i for i in ids if i > ids[4]])

    result = api.get(f"/api/session/{sid}/result").json()
    ev = result["evaluation_json"]
    assert result["status"] == "complete" and ev["ragas_score"] == 1.0
    assert ev["claim_audit"] and ev["references_meta"] and len(ev["attempts"]) == 2
    assert not any(m["id"] == remove[0] for m in ev["references_meta"]), "removed paper is gone"

    transcript = api.get(f"/api/session/{sid}/transcript").json()
    assert len(transcript["round_outputs"]) == 6

    pdf = api.get(f"/api/session/{sid}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    for fmt, marker in (("markdown", b"# Research Evaluation Report"), ("bibtex", b"% Autonomous"), ("docx", b"PK")):
        resp = api.get(f"/api/session/{sid}/export/{fmt}")
        assert resp.status_code == 200 and resp.content.startswith(marker), fmt
        assert "attachment" in resp.headers["content-disposition"]
    assert b"\n@" in api.get(f"/api/session/{sid}/export/bibtex").content
    assert api.get(f"/api/session/{sid}/export/xml").status_code == 404

    history = api.get("/api/sessions").json()["sessions"]
    assert any(s["session_id"] == sid and s["ragas_score"] == 1.0 for s in history)


def test_adding_at_capacity_drops_unticked_papers_first(api, monkeypatch):
    from backend.agents import librarian

    twenty = [dict(FAKE_PAPERS[i % len(FAKE_PAPERS)], title=f"Distinct paper {i} on federated clinical models",
                   arxiv_id=f"2403.{i:05d}", url=f"https://arxiv.org/abs/2403.{i:05d}")
              for i in range(20)]
    monkeypatch.setattr(librarian, "_fetch_all", lambda keywords, domain, broad=False: {"arxiv": [dict(p) for p in twenty]})
    sid = _prepare(api)["session_id"]
    api.post(f"/api/session/{sid}/start", json={"review_papers": True})
    _wait_for(api, sid, {"awaiting_review"})
    papers = api.get(f"/api/session/{sid}/papers").json()["papers"]
    assert len(papers) == 20

    full = api.post(f"/api/session/{sid}/papers", json={"identifier": "2402.00001"})
    assert full.status_code == 422 and "at most 20" in full.json()["detail"]

    ok = api.post(f"/api/session/{sid}/papers", json={"identifier": "2402.00001", "remove_ids": [papers[-1]["id"]]})
    assert ok.status_code == 200
    after = ok.json()["papers"]
    assert len(after) == 20 and papers[-1]["id"] not in {p["id"] for p in after}
    api.post(f"/api/session/{sid}/cancel")


def test_cancel_during_review(api):
    sid = _prepare(api)["session_id"]
    api.post(f"/api/session/{sid}/start", json={"review_papers": True})
    _wait_for(api, sid, {"awaiting_review"})
    assert api.post(f"/api/session/{sid}/cancel").status_code == 200
    assert _wait_for(api, sid, {"cancelled", "complete", "error"}) == "cancelled"
    kinds = [e["event"] for e in _read_stream(api, sid)]
    assert "cancelled" in kinds and "report_ready" not in kinds
    assert api.post(f"/api/session/{sid}/cancel").status_code == 409


def test_no_papers_fails_fast_with_clear_message(api, monkeypatch):
    from backend.agents import librarian

    monkeypatch.setattr(librarian, "_fetch_all", lambda keywords, domain, broad=False: {"arxiv": []})
    sid = api.post("/api/session", json={"mode": 1, "user_input": "an obscure topic nobody studies"}).json()["session_id"]
    assert _wait_for(api, sid, {"complete", "error"}) == "error"
    detail = api.get(f"/api/session/{sid}/result").json()["detail"]
    assert "No papers were found" in detail
    events = _read_stream(api, sid)
    assert events[-1]["event"] == "pipeline_error"
    # No LLM debate rounds were spent on an empty corpus
    assert "round_start" not in [e["event"] for e in events]


def test_one_shot_flow_completes(api):
    sid = api.post("/api/session", json={
        "mode": 1, "user_input": "Federated learning in hospitals", "chaos_constraint": "Assume no GPUs.",
    }).json()["session_id"]
    assert _wait_for(api, sid, {"complete", "error"}) == "complete"
    ev = api.get(f"/api/session/{sid}/result").json()["evaluation_json"]
    assert ev["chaos_constraint"] == "Assume no GPUs."


def test_unknown_session_and_bad_event_id(api):
    assert api.get("/api/session/does-not-exist/result").status_code == 404
    assert api.get("/api/session/does-not-exist/stream").status_code == 404
    sid = _prepare(api)["session_id"]
    events = _read_stream(api, sid, last_event_id="abc")  # non-numeric id no longer 500s
    assert events[-1]["event"] == "session_status" and events[-1]["data"]["status"] == "awaiting_confirmation"


def test_extract_text_upload(api):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Our proposal studies federated learning for readmission prediction.")
    buffer = io.BytesIO()
    doc.save(buffer)
    resp = api.post("/api/extract-text", files={"file": ("proposal.docx", buffer.getvalue(), "application/octet-stream")})
    assert resp.status_code == 200 and "readmission" in resp.json()["text"]

    bad = api.post("/api/extract-text", files={"file": ("image.png", b"\x89PNG", "image/png")})
    assert bad.status_code == 422


def test_report_keeps_full_attempt_history_when_an_earlier_attempt_wins(api, monkeypatch):
    """Review finding: the report's attempts stopped at the best attempt while the transcript went on."""
    from backend.agents import chairman

    scores = iter([0.6, 0.4])
    monkeypatch.setattr(chairman, "compute_ragas_score", lambda outputs, flags: next(scores))
    sid = api.post("/api/session", json={"mode": 2, "user_input": "Federated learning helps hospitals"}).json()["session_id"]
    assert _wait_for(api, sid, {"complete", "error"}) == "complete"
    ev = api.get(f"/api/session/{sid}/result").json()["evaluation_json"]
    assert ev["ragas_score"] == 0.6
    assert [a["ragas_score"] for a in ev["attempts"]] == [0.6, 0.4]


def test_prepared_sessions_survive_restart_and_stay_out_of_history(api):
    from backend.main import store

    sid = _prepare(api)["session_id"]
    store().mark_interrupted()  # what a server restart does
    assert store().get(sid)["status"] == "awaiting_confirmation"
    assert api.post(f"/api/session/{sid}/start", json={}).status_code == 202  # still startable
    api.post(f"/api/session/{sid}/cancel")
    sid = _prepare(api)["session_id"]
    history_ids = {s["session_id"] for s in api.get("/api/sessions").json()["sessions"]}
    assert sid not in history_ids
    assert api.post(f"/api/session/{sid}/cancel").json()["status"] == "discarded"
    history_ids = {s["session_id"] for s in api.get("/api/sessions").json()["sessions"]}
    assert sid not in history_ids
    assert api.get(f"/api/session/{sid}/result").json()["detail"] == "This session was never started."
