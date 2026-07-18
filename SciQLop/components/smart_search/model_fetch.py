"""Wraps model2vec's StaticModel. model2vec's own from_pretrained has no
cache_dir parameter and defaults to force_download=True, so model files are
fetched via huggingface_hub.snapshot_download directly, then loaded from
the resulting local path -- see docs/superpowers/specs/
2026-07-19-smart-search-model2vec-incremental-indexing-design.md.

huggingface_hub/model2vec are imported lazily inside each function rather
than at module scope: this module is imported unconditionally at startup
(register_smart_search_domain()) even when SmartSearchSettings.enabled
defaults to False."""


def download_model(model_name: str, cache_dir: str) -> None:
    """Runs inside a JobsBackend submit_function job. Network-capable."""
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=model_name, cache_dir=cache_dir)


def load_model(model_name: str, cache_dir: str):
    """Never touches the network -- raises if download_model() hasn't
    populated cache_dir yet. Called both in the main process (query
    embedding) and inside the index_worker subprocess (corpus embedding).
    local_files_only=True on the snapshot_download call is what enforces
    "no network" -- resolving the local path still goes through
    snapshot_download, just told not to reach out."""
    from huggingface_hub import snapshot_download
    from model2vec import StaticModel
    local_path = snapshot_download(repo_id=model_name, cache_dir=cache_dir, local_files_only=True)
    return StaticModel.from_pretrained(local_path, force_download=False)
