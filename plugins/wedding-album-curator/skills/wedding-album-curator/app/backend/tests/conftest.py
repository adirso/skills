import os
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "appdata"
    d.mkdir()
    monkeypatch.setenv("WAC_DATA_DIR", str(d))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Optional: reuse already-downloaded models for integration tests (never downloads)
    models_src = os.environ.get("WAC_TEST_MODELS_DIR")
    if models_src and Path(models_src).is_dir():
        (d / "models").symlink_to(Path(models_src).resolve())
    return d


@pytest.fixture()
def sample_dir(tmp_path):
    from wac.sample import generate

    dest = tmp_path / "photos"
    manifest = generate(dest, n_scenes=14, faces_dir=FIXTURES)
    return dest, manifest


@pytest.fixture()
def project(data_dir, sample_dir):
    from wac.pipeline import Project

    src, manifest = sample_dir
    p = Project("t1", "Test", src, data_dir / "projects" / "t1")
    return p, manifest


def run_job(project, fn, params=None):
    from wac.jobs import JobContext

    with project.db.tx() as con:
        jid = con.execute("INSERT INTO jobs(kind, state) VALUES ('test','running')").lastrowid
    ctx = JobContext(job_id=jid, db=project.db, params=params or {})
    return fn(project, ctx)


def models_available() -> bool:
    d = os.environ.get("WAC_TEST_MODELS_DIR")
    return bool(d) and (Path(d) / "face_detection_yunet_2023mar.onnx").exists() and \
        (Path(d) / "face_recognition_sface_2021dec.onnx").exists()
