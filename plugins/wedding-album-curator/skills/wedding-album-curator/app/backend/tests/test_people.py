"""Face clustering and the correction workflows (merge, split/move, confirm, ignore)."""
import json
import time

import numpy as np
import pytest

from wac import clustering
from wac.db import ProjectDB, to_blob
from tests.conftest import models_available, run_job


def _identity_embeddings(rng, n_people=3, per=8, dim=128, noise=0.35):
    centers = rng.normal(size=(n_people, dim))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    out = []
    for p in range(n_people):
        for _ in range(per):
            v = centers[p] + rng.normal(scale=noise / np.sqrt(dim), size=dim) * 3
            out.append((p, v / np.linalg.norm(v)))
    return out


@pytest.fixture()
def face_db(tmp_path):
    db = ProjectDB(tmp_path / "p.db")
    rng = np.random.default_rng(0)
    data = _identity_embeddings(rng)
    with db.tx() as con:
        for i, (person, emb) in enumerate(data):
            pid = con.execute("INSERT INTO photos(rel_path, size, mtime, status, created_at) VALUES (?,1,1,'ok',0)",
                              (f"p{i}.jpg",)).lastrowid
            con.execute("INSERT INTO faces(photo_id, det_score, size_px, embedding, sharpness, frontal) VALUES (?,0.95,200,?,0.8,0.9)",
                        (pid, to_blob(emb)))
    truth = {i + 1: person for i, (person, _) in enumerate(data)}  # face id -> true identity
    return db, truth


def _persons_of(db):
    with db.connect() as con:
        return {r["id"]: r["person_id"] for r in con.execute("SELECT id, person_id FROM faces")}


def test_clusters_match_identities(face_db):
    db, truth = face_db
    stats = clustering.recluster(db)
    assignment = _persons_of(db)
    assert stats.persons == 3
    for ident in set(truth.values()):
        persons = {assignment[f] for f, t in truth.items() if t == ident}
        assert len(persons) == 1 and None not in persons


def test_bursts_do_not_split_a_person():
    """40 near-identical copies of person A's face in one burst + 40 of a different photo of A."""
    rng = np.random.default_rng(1)
    a = rng.normal(size=128)
    a /= np.linalg.norm(a)
    other = rng.normal(size=128)
    shot2 = a * 0.82 + np.sqrt(1 - 0.82**2) * (other - (other @ a) * a) / np.linalg.norm(other - (other @ a) * a)
    def copies(v, n):
        out = v + rng.normal(scale=0.01, size=(n, 128))
        return out / np.linalg.norm(out, axis=1, keepdims=True)
    stranger = rng.normal(size=128)
    stranger /= np.linalg.norm(stranger)
    emb = np.vstack([copies(a, 40), copies(shot2, 40), copies(stranger, 10)]).astype(np.float32)
    labels = clustering.cluster_embeddings(emb)
    assert len(set(labels[:80])) == 1
    assert labels[85] != labels[0]


def test_recluster_is_stable_and_keeps_names(face_db):
    db, truth = face_db
    clustering.recluster(db)
    first = _persons_of(db)
    pid = first[1]
    with db.tx() as con:
        con.execute("UPDATE persons SET name='Dana', role='bride', user_touched=1 WHERE id=?", (pid,))
    clustering.recluster(db)
    assert _persons_of(db) == first
    with db.connect() as con:
        assert con.execute("SELECT name FROM persons WHERE id=?", (pid,)).fetchone()[0] == "Dana"


def test_merge_survives_recluster(face_db):
    db, truth = face_db
    clustering.recluster(db)
    a = _persons_of(db)
    pa, pb = a[1], a[9]  # two different identities
    assert pa != pb
    clustering.merge_persons(db, pa, [pb])
    clustering.recluster(db)
    after = _persons_of(db)
    assert after[1] == after[9] == pa


def test_split_moves_faces_and_prevents_reassignment(face_db):
    db, truth = face_db
    clustering.recluster(db)
    before = _persons_of(db)
    old = before[2]
    new_pid = clustering.move_faces(db, [2, 3], None, new_person=True)
    clustering.recluster(db)
    after = _persons_of(db)
    assert after[2] == after[3] == new_pid
    with db.connect() as con:
        row = con.execute("SELECT assignment, excluded_person_ids FROM faces WHERE id=2").fetchone()
    assert row["assignment"] == "user" and old in json.loads(row["excluded_person_ids"])


def test_removed_face_not_auto_assigned_back(face_db):
    db, truth = face_db
    clustering.recluster(db)
    p = _persons_of(db)[4]
    # "not this person": move to unassigned
    clustering.move_faces(db, [4], None)
    with db.tx() as con:
        con.execute("UPDATE faces SET assignment='auto' WHERE id=4")  # back to automatic, but excluded
    clustering.recluster(db)
    assert _persons_of(db)[4] != p


def test_ignore_and_uncertain(face_db):
    db, truth = face_db
    clustering.recluster(db)
    clustering.ignore_faces(db, [5])
    clustering.mark_uncertain(db, [6])
    clustering.recluster(db)
    with db.connect() as con:
        f5 = con.execute("SELECT person_id, assignment FROM faces WHERE id=5").fetchone()
    assert f5["person_id"] is None and f5["assignment"] == "ignored"


@pytest.mark.skipif(not models_available(), reason="set WAC_TEST_MODELS_DIR to run real face-model tests")
def test_real_faces_group_same_person(project):
    from wac.pipeline import run_analysis

    p, manifest = project
    run_job(p, run_analysis)
    with p.db.connect() as con:
        rows = con.execute(
            "SELECT p.rel_path, f.person_id FROM faces f JOIN photos p ON p.id=f.photo_id WHERE p.rel_path LIKE '%FACE_1_%' "
            "OR p.rel_path LIKE '%FACE_2_%'").fetchall()
        n_people = con.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    by_file = {}
    for r in rows:
        by_file.setdefault(r["rel_path"].split("/")[-1][:6], set()).add(r["person_id"])
    # each single-portrait fixture (3 variants) maps to exactly one person
    assert all(len(v) == 1 for v in by_file.values())
    assert n_people == 7  # the 7 crew members; portraits merge into them


def test_rescan_faces_keeps_people_and_corrections(tmp_path):
    """Re-detecting faces (redo=faces) must not lose names, roles or user corrections."""
    from wac.faces import FaceResult
    from wac.pipeline import write_result

    db = ProjectDB(tmp_path / "p.db")
    rng = np.random.default_rng(2)
    with db.tx() as con:
        pid = con.execute("INSERT INTO photos(rel_path, size, mtime, status, created_at) VALUES ('a.jpg',1,1,'ok',0)").lastrowid
        bride = con.execute("INSERT INTO persons(name, role, importance, user_touched, created_at) VALUES ('Dana','bride','couple',1,0)").lastrowid
        con.execute("INSERT INTO faces(photo_id, x, y, w, h, det_score, person_id, assignment, excluded_person_ids) "
                    "VALUES (?,0.1,0.1,0.2,0.2,0.95,?,'user','[]')", (pid, bride))
        con.execute("INSERT INTO faces(photo_id, x, y, w, h, det_score, assignment, excluded_person_ids) "
                    "VALUES (?,0.6,0.1,0.2,0.2,0.95,'ignored','[]')", (pid,))

    def face(box):
        v = rng.normal(size=128).astype(np.float32)
        return FaceResult(box=box, det_score=0.96, size_px=200, landmarks=[], embedding=v / np.linalg.norm(v),
                          sharpness=0.8, frontal=0.9, blink_left=None, blink_right=None, eyes_closed=None,
                          eyes_reliable=False, landmarker_found=None, edge_cut=False)

    # same two faces, slightly shifted boxes, plus one newly detected face
    write_result(db, {"id": pid, "faces": [face((0.11, 0.1, 0.2, 0.2)), face((0.6, 0.11, 0.2, 0.2)),
                                           face((0.4, 0.6, 0.1, 0.1))]}, True)
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT x, person_id, assignment FROM faces ORDER BY x")]
        name = con.execute("SELECT name, role FROM persons WHERE id=?", (bride,)).fetchone()
    assert rows[0] == {"x": 0.11, "person_id": bride, "assignment": "user"}
    assert rows[1]["assignment"] == "auto" and rows[1]["person_id"] is None  # new face
    assert rows[2]["assignment"] == "ignored"
    assert tuple(name) == ("Dana", "bride")


def test_people_photographed_together_are_not_merged():
    """Bride and groom look alike to the descriptor (cos 0.6) and share every photo:
    they must still end up as two people (a person appears once per photo)."""
    rng = np.random.default_rng(3)
    a = rng.normal(size=128); a /= np.linalg.norm(a)
    o = rng.normal(size=128); o -= (o @ a) * a; o /= np.linalg.norm(o)
    b = 0.6 * a + 0.8 * o
    def noisy(v):
        x = v + rng.normal(scale=0.02, size=128)
        return x / np.linalg.norm(x)
    emb, photos = [], []
    for ph in range(40):
        emb += [noisy(a), noisy(b)]
        photos += [ph, ph]
    emb = np.array(emb, dtype=np.float32)
    photos = np.array(photos)
    assert len(set(clustering.cluster_embeddings(emb))) == 1  # without the constraint: merged
    labels = clustering.cluster_embeddings(emb, photo_ids=photos)
    assert len(set(labels[0::2])) == 1 and len(set(labels[1::2])) == 1
    assert labels[0] != labels[1]
