from SciQLop.components.smart_search.domain import NodeSnapshot, SearchDomain


def test_node_snapshot_fields():
    n = NodeSnapshot(path_key="root/speasy/a", raw_text="mms1 fgm b_gse")
    assert n.path_key == "root/speasy/a"
    assert n.raw_text == "mms1 fgm b_gse"


class _FakeDomain:
    name = "fake"

    def snapshot(self):
        return [NodeSnapshot("a", "text a")]


def test_search_domain_protocol_accepts_conforming_object():
    domain: SearchDomain = _FakeDomain()
    assert domain.name == "fake"
    assert list(domain.snapshot()) == [NodeSnapshot("a", "text a")]
