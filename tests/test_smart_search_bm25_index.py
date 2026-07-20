from SciQLop.components.smart_search import bm25_index
from SciQLop.components.smart_search.domain import NodeSnapshot


def test_score_ranks_rare_term_match_above_common_term_match():
    snapshot = [
        NodeSnapshot("rareword", "rareword"),
        NodeSnapshot("commonword", "commonword"),
        NodeSnapshot("entry2", "entry2 commonword"),
        NodeSnapshot("entry3", "entry3 commonword"),
    ]
    index = bm25_index.build(snapshot)
    scores = bm25_index.score(index, "rareword commonword")
    assert scores["rareword"] > scores["commonword"]


def test_score_weights_path_field_match_above_meta_field_match():
    snapshot = [
        NodeSnapshot("mms1", "mms1 CATDESC: instrument reading"),
        NodeSnapshot("goes", "goes CATDESC: mms1 calibration note"),
    ]
    index = bm25_index.build(snapshot)
    scores = bm25_index.score(index, "mms1")
    assert scores["mms1"] > scores["goes"]


def test_score_ignores_query_terms_absent_from_corpus():
    snapshot = [NodeSnapshot("mms1 fgm", "mms1 fgm")]
    index = bm25_index.build(snapshot)
    with_absent_term = bm25_index.score(index, "mms1 nonexistentterm")
    without_it = bm25_index.score(index, "mms1")
    assert with_absent_term == without_it


def test_build_and_score_handle_empty_snapshot():
    index = bm25_index.build([])
    assert bm25_index.score(index, "anything") == {}


def test_score_with_empty_query_returns_empty_dict():
    snapshot = [NodeSnapshot("mms1 fgm", "mms1 fgm")]
    index = bm25_index.build(snapshot)
    assert bm25_index.score(index, "") == {}
