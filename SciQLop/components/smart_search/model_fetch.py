"""Thin wrapper around fastembed's own caching (TextEmbedding(cache_dir=...,
local_files_only=...) delegates to huggingface_hub.snapshot_download, which
already honors HTTP_PROXY/HTTPS_PROXY -- see docs/superpowers/specs/
2026-07-17-smart-search-component-design.md, decision 9, for why this
doesn't route through Speasy's HTTP cache instead.

`fastembed` is imported lazily inside each function rather than at module
scope: it eagerly initializes the onnxruntime backend, and this module is
imported unconditionally at startup (register_smart_search_domain()) even
when SmartSearchSettings.enabled defaults to False."""


def download_model(model_name: str, cache_dir: str) -> None:
    """Runs inside a JobsBackend submit_function job. Network-capable."""
    from fastembed import TextEmbedding
    TextEmbedding(model_name=model_name, cache_dir=cache_dir)


def load_model(model_name: str, cache_dir: str):
    """Never touches the network -- raises if download_model() hasn't
    populated cache_dir yet. Called both in the main process (query
    embedding) and inside the index_worker subprocess (corpus embedding)."""
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=model_name, cache_dir=cache_dir, local_files_only=True)
