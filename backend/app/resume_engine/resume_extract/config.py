"""JSON is a YAML 1.2 subset: config.yaml needs no extra YAML runtime library."""
from pathlib import Path
import json
from typing import Any

def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the single versioned rule/threshold registry."""
    return json.loads(Path(path or Path(__file__).with_name('config.yaml')).read_text('utf-8'))
