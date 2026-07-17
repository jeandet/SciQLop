"""The reindex job's entry point -- runs inside a spawned subprocess via
JobsBackend.submit_function. Must stay a real module-level function: the
spawn context re-imports it by dotted path in the child."""
from typing import Sequence

from SciQLop.components.smart_search import model_fetch
from SciQLop.components.smart_search.domain import NodeSnapshot


def run(snapshot: Sequence[NodeSnapshot], model_name: str, cache_dir: str) -> dict:
    if not snapshot:
        return {}
    model = model_fetch.load_model(model_name, cache_dir)
    texts = [n.raw_text for n in snapshot]
    embeddings = model.embed(texts)
    return {n.path_key: vec for n, vec in zip(snapshot, embeddings)}
