"""Load the normalized, read-only catalog generated from the user's source files."""
from functools import lru_cache
import gzip
import json
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).with_name("user_dataset_catalog.json.gz")


@lru_cache(maxsize=1)
def load_user_dataset() -> dict[str, list[dict[str, Any]]]:
    if DATA_PATH.exists():
        source = DATA_PATH
    else:
        parts = sorted(DATA_PATH.parent.glob(DATA_PATH.name + ".part-*"))
        if not parts:
            return {"offers": [], "catalog": []}
        # Large deployments may carry the gzip snapshot in content-addressed
        # chunks; concatenated gzip members decode as one stream.
        import io
        source = io.BytesIO(b"".join(part.read_bytes() for part in parts))
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {"offers": payload.get("offers", []), "catalog": payload.get("catalog", [])}
