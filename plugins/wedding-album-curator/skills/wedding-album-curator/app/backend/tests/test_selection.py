"""Album selection engine: scoring, allocations, locks, rejections, diversity, shortfalls."""
import numpy as np
import pytest

from wac.selection import Candidate, SelectionConfig, base_score, select


def make_pool(n_per_cat=40, seed=0):
    rng = np.random.default_rng(seed)
    cats = ["getting_ready", "couple_portraits", "family_portraits", "ceremony", "reception", "party_dancing"]
    cands, i = [], 0
    for c in cats:
        for _ in range(n_per_cat):
            i += 1
            e = rng.normal(size=16)
            cands.append(Candidate(id=i, technical=float(rng.uniform(0.3, 0.95)), sharpness=0.7, category=c,
                                   category_conf=0.8, embedding=(e / np.linalg.norm(e)).astype(np.float32)))
    return cands


def test_target_respected_and_no_duplicates():
    res = select(make_pool(), SelectionConfig(target=60))
    ids = [p.id for p in res.picks]
    assert len(ids) == 60 and len(set(ids)) == 60
    assert res.summary["shortfall"] == 0


def test_category_allocation_is_followed_softly():
    cfg = SelectionConfig(target=100)
    res = select(make_pool(), cfg)
    got = res.summary["bucket_achieved"]
    want = res.summary["bucket_target"]
    for b in ("getting_ready", "couple", "family_friends", "ceremony", "reception_dancing"):
        assert abs(got[b] - want[b]) <= max(3, want[b] * 0.25), (b, got, want)


def test_not_simply_top_technical():
    pool = make_pool()
    # make all ceremony photos technically perfect; the engine must still cover other moments
    for c in pool:
        if c.category == "ceremony":
            c.technical = 1.0
    res = select(pool, SelectionConfig(target=50))
    cats = {next(c.category for c in pool if c.id == p.id) for p in res.picks}
    assert len(cats) >= 5


def test_locked_always_included_and_rejected_never():
    pool = make_pool()
    worst = min(pool, key=lambda c: c.technical)
    best = max(pool, key=lambda c: c.technical)
    worst.decision = "selected"
    best.decision = "rejected"
    res = select(pool, SelectionConfig(target=30))
    ids = {p.id for p in res.picks}
    assert worst.id in ids and best.id not in ids
    locked_pick = next(p for p in res.picks if p.id == worst.id)
    assert locked_pick.reasons == ["Selected by you (locked)"]


def test_regeneration_preserves_locks():
    pool = make_pool()
    locked = [pool[3], pool[77], pool[150]]
    for c in locked:
        c.decision = "selected"
    for target in (10, 50, 120):
        ids = {p.id for p in select(pool, SelectionConfig(target=target)).picks}
        assert all(c.id in ids for c in locked)


def test_shortfall_is_reported_not_padded():
    pool = make_pool(n_per_cat=3)  # 18 photos
    for c in pool[:5]:
        c.decision = "rejected"
    res = select(pool, SelectionConfig(target=500))
    assert len(res.picks) == 13
    assert res.summary["shortfall"] == 487
    assert any("not enough eligible photos" in n for n in res.summary["notes"])


def test_near_duplicate_groups_limited():
    pool = make_pool()
    for c in pool[:20]:  # one long burst of strong photos
        c.group_id = 1
        c.technical = 0.99
        c.group_size = 20
    res = select(pool, SelectionConfig(target=40, max_per_group=1))
    in_group = sum(1 for p in res.picks if p.id <= 20)
    assert in_group <= 2


def test_bride_and_groom_prioritized():
    pool = make_pool()
    for c in pool[::5]:
        c.persons = [1]
        c.person_weights = {1: 1.0}
        c.has_bride = True
    res = select(pool, SelectionConfig(target=40), important_persons={1})
    couple = sum(1 for p in res.picks if next(c for c in pool if c.id == p.id).has_bride)
    assert couple / 40 >= 0.4


def test_closed_eyes_penalized_not_excluded():
    c = Candidate(id=1, technical=0.9, sharpness=0.9, couple_eyes_closed=True)
    d = Candidate(id=2, technical=0.9, sharpness=0.9)
    assert base_score(c, SelectionConfig())[0] < base_score(d, SelectionConfig())[0]
    res = select([c], SelectionConfig(target=1))
    assert res.picks and "please review" in " ".join(res.picks[0].reasons)


def test_every_pick_is_explained():
    res = select(make_pool(), SelectionConfig(target=30))
    assert all(p.reasons for p in res.picks)
    assert all(set(p.components) >= {"technical", "faces", "people", "moment", "preference"} for p in res.picks)
