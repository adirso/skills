"""Integration: analysis -> selection -> export, interruption recovery, preferences, API security."""
import hashlib
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from wac import export, preferences, selection
from wac.jobs import Cancelled, JobContext, JobManager
from wac.pipeline import run_analysis
from tests.conftest import run_job


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_full_flow_and_export_is_byte_identical(project, tmp_path):
    p, manifest = project
    originals_before = {f: sha(p.source_dir / f) for f in manifest["files"]}
    run_job(p, run_analysis)
    summary = selection.generate(p.db, {"target": 12})
    assert summary["selected"] == 12
    ids = export.approved_photo_ids(p.db)
    dest = tmp_path / "album"
    rep = export.export_selection(p.db, p.source_dir, dest, ids, category_subfolders=True)
    assert rep["exported"] == 12 and not rep["missing"] and not rep["failed"]
    files = json.loads((dest / "album_manifest.json").read_text())["files"]
    for f in files:
        assert sha(dest / f["exported_as"]) == sha(p.source_dir / f["source"])
    assert (dest / "album_manifest.csv").exists()
    # originals untouched
    assert originals_before == {f: sha(p.source_dir / f) for f in manifest["files"]}


def test_export_reports_missing_and_respects_rejections(project, tmp_path):
    p, manifest = project
    run_job(p, run_analysis)
    selection.generate(p.db, {"target": 8})
    ids = export.approved_photo_ids(p.db)
    with p.db.tx() as con:
        p.db.touch_user_state(con, ids[0], decision="rejected")
        rel = con.execute("SELECT rel_path FROM photos WHERE id=?", (ids[1],)).fetchone()[0]
    (p.source_dir / rel).unlink()
    ids2 = export.approved_photo_ids(p.db)
    assert ids[0] not in ids2
    rep = export.export_selection(p.db, p.source_dir, tmp_path / "out", ids2)
    assert [m["photo_id"] for m in rep["missing"]] == [ids[1]]
    assert rep["exported"] == len(ids2) - 1


def test_export_destination_validation(project, tmp_path):
    p, _ = project
    from wac.scanner import PathError

    with pytest.raises(PathError):
        export.validate_destination(str(p.source_dir / "album"), p.source_dir)
    nonempty = tmp_path / "full"
    nonempty.mkdir()
    (nonempty / "x").write_text("x")
    with pytest.raises(PathError):
        export.validate_destination(str(nonempty), p.source_dir)
    assert export.validate_destination(str(tmp_path / "fresh"), p.source_dir)


def test_interrupted_analysis_resumes(project, monkeypatch):
    from wac import pipeline

    monkeypatch.setattr(pipeline, "CHUNK", 4)
    p, manifest = project
    with p.db.tx() as con:
        jid = con.execute("INSERT INTO jobs(kind, state) VALUES ('analyze','running')").lastrowid
    ctx = JobContext(job_id=jid, db=p.db, params={})
    calls = {"n": 0}
    real_check = ctx.check

    def check():
        calls["n"] += 1
        if calls["n"] == 3:  # cancel partway through per-photo analysis
            ctx._cancel.set()
        real_check()

    ctx.check = check
    with pytest.raises(Cancelled):
        run_analysis(p, ctx)
    with p.db.connect() as con:
        partial = con.execute("SELECT COUNT(*) FROM photos WHERE stage_quality=1").fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM photos WHERE status!='error'").fetchone()[0]
    assert 0 < partial < total
    # a new process marks the running job interrupted
    JobManager(p.db)
    with p.db.connect() as con:
        assert con.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "interrupted"
    res = run_job(p, run_analysis)
    assert res["processed"] == total - partial  # only the remaining photos
    with p.db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM photos WHERE status='ok' AND stage_quality=0").fetchone()[0] == 0


def test_preferences_reset(project):
    p, _ = project
    run_job(p, run_analysis)
    with p.db.tx() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM photos WHERE status='ok' LIMIT 4")]
        for i in ids:
            p.db.touch_user_state(con, i, favorite=1)
    m = preferences.build(p.db)
    assert m.positives == 4  # counted even when the visual model is not installed
    time.sleep(0.01)
    preferences.reset(p.db)
    assert preferences.build(p.db).positives == 0
    with p.db.connect() as con:  # explicit choices are kept
        assert con.execute("SELECT COUNT(*) FROM user_state WHERE favorite=1").fetchone()[0] == 4


def test_user_category_never_overwritten(project):
    from wac import events

    p, _ = project
    run_job(p, run_analysis)
    with p.db.connect() as con:
        pid = con.execute("SELECT id FROM photos WHERE status='ok' LIMIT 1").fetchone()[0]
    events.set_user_category(p.db, [pid], "rings")
    events.classify_all(p.db)
    with p.db.connect() as con:
        assert con.execute("SELECT category, source FROM events WHERE photo_id=?", (pid,)).fetchone()[:] == ("rings", "user")


# ---------------- API ----------------

@pytest.fixture()
def client(data_dir):
    from wac.api import app

    return TestClient(app)


def test_api_requires_session_and_local_host(client):
    assert client.get("/api/status").status_code == 401
    client.get("/api/session")
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/status", headers={"host": "evil.example.com"}).status_code == 403
    assert client.post("/api/projects", json={}, headers={"origin": "http://evil.example.com"}).status_code == 403


def test_api_project_lifecycle(client, sample_dir, tmp_path):
    src, _ = sample_dir
    client.get("/api/session")
    pid = client.post("/api/projects", json={"name": "Test", "source_dir": str(src)}).json()["id"]
    jid = client.post(f"/api/projects/{pid}/analyze").json()["job_id"]
    for _ in range(300):
        jobs = client.get(f"/api/projects/{pid}/jobs").json()
        if jobs[0]["state"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert jobs[0]["state"] == "done", jobs[0]
    photos = client.get(f"/api/projects/{pid}/photos").json()
    assert photos["count"] > 20
    first = photos["rows"][0][0]
    assert client.get(f"/api/projects/{pid}/photos/{first}/thumb").headers["content-type"] == "image/jpeg"
    assert client.post(f"/api/projects/{pid}/photos/state", json={"ids": [first], "decision": "selected"}).status_code == 200
    client.put(f"/api/projects/{pid}/album/config", json={"target": 10})
    s = client.post(f"/api/projects/{pid}/album/generate").json()
    assert s["selected"] == 10 and s["locked"] == 1
    album = client.get(f"/api/projects/{pid}/album").json()
    assert any(i["photo_id"] == first for i in album["items"])
    # cloud run refused without consent
    client.put(f"/api/projects/{pid}/ai/provider", json={"id": "anthropic_api", "model": "claude-haiku-5-5"})
    r = client.post(f"/api/projects/{pid}/ai/run", json={"scope": "album", "confirm_upload": True})
    assert r.status_code == 409 and r.json()["consent_required"]
    # model download requires explicit approval
    assert client.post("/api/models/download", json={"ids": ["yunet"]}).status_code == 400
    # export
    dest = tmp_path / "export"
    prev = client.post(f"/api/projects/{pid}/export/preview", json={"destination": str(dest)}).json()
    assert prev["count"] == 10
    client.post(f"/api/projects/{pid}/export", json={"destination": str(dest)})
    for _ in range(100):
        rep = client.get(f"/api/projects/{pid}/export/last").json()["report"]
        if rep:
            break
        time.sleep(0.1)
    assert rep["exported"] == 10
    assert client.delete(f"/api/projects/{pid}").json()["originals_untouched"]
    assert src.exists()
