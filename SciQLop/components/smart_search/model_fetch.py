"""Thin wrapper around fastembed's own caching (TextEmbedding(cache_dir=...,
local_files_only=...) delegates to huggingface_hub.snapshot_download, which
already honors HTTP_PROXY/HTTPS_PROXY -- see docs/superpowers/specs/
2026-07-17-smart-search-component-design.md, decision 9, for why this
doesn't route through Speasy's HTTP cache instead."""
from fastembed import TextEmbedding


def download_model(model_name: str, cache_dir: str) -> None:
    """Runs inside a JobsBackend submit_function job. Network-capable."""
    TextEmbedding(model_name=model_name, cache_dir=cache_dir)


def load_model(model_name: str, cache_dir: str) -> TextEmbedding:
    """Never touches the network -- raises if download_model() hasn't
    populated cache_dir yet. Called both in the main process (query
    embedding) and inside the index_worker subprocess (corpus embedding)."""
    return TextEmbedding(model_name=model_name, cache_dir=cache_dir, local_files_only=True)
