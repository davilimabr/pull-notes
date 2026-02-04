"""Config loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def load_config(path: Optional[str]) -> Dict:
    """Load configuration JSON file."""
    if not path:
        raise SystemExit("Config path is required. Use --config to provide a JSON file.")
    config_path = Path(path)
    if not config_path.exists():
        raise SystemExit(f"Config not found: {config_path}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("Config must be a JSON object.")
    return raw


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def validate_config(config: Dict, *, generate: str) -> None:
    """Validate required configuration keys."""
    missing: List[str] = []
    empty: List[str] = []

    def require(path: Tuple[str, ...], allow_empty: bool = False) -> Optional[object]:
        current: object = config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                missing.append(".".join(path))
                return None
            current = current[key]
        if current is None:
            empty.append(".".join(path))
            return current
        if not allow_empty and _is_empty(current):
            empty.append(".".join(path))
        return current

    require(("other_label",))
    require(("importance", "weight_lines"))
    require(("importance", "weight_files"))
    keyword_bonus = require(("importance", "keyword_bonus"), allow_empty=True)
    require(("output", "dir"))

    if generate in {"pr", "both"}:
        require(("templates", "pr"))
        require(("alerts", "none_text"))

    if generate in {"release", "both"}:
        require(("templates", "release"))
        require(("domain", "output_path"))
        require(("release", "version_template"))
        require(("release", "date_format"))
        require(("domain", "model"))
        require(("domain", "max_total_bytes"))
        require(("domain", "max_file_bytes"))

    require(("diff", "max_anchors_keywords"))
    require(("diff", "max_anchors_artifacts"))
    require(("language",))
    require(("llm_model",))

    if keyword_bonus is not None and not isinstance(keyword_bonus, dict):
        empty.append("importance.keyword_bonus")

    commit_types = require(("commit_types",))
    if isinstance(commit_types, dict):
        if not commit_types:
            empty.append("commit_types")
        for type_name, type_cfg in commit_types.items():
            if not isinstance(type_cfg, dict):
                empty.append(f"commit_types.{type_name}")
                continue
            if "label" not in type_cfg:
                missing.append(f"commit_types.{type_name}.label")
            elif _is_empty(type_cfg["label"]):
                empty.append(f"commit_types.{type_name}.label")
            if "patterns" not in type_cfg:
                missing.append(f"commit_types.{type_name}.patterns")
            else:
                patterns = type_cfg["patterns"]
                if not isinstance(patterns, list) or not patterns:
                    empty.append(f"commit_types.{type_name}.patterns")

    importance_bands = require(("importance_bands",))
    if isinstance(importance_bands, list):
        if not importance_bands:
            empty.append("importance_bands")
        for idx, band in enumerate(importance_bands):
            if not isinstance(band, dict):
                empty.append(f"importance_bands[{idx}]")
                continue
            if "name" not in band:
                missing.append(f"importance_bands[{idx}].name")
            elif _is_empty(band["name"]):
                empty.append(f"importance_bands[{idx}].name")
            if "min" not in band:
                missing.append(f"importance_bands[{idx}].min")
            elif band["min"] is None:
                empty.append(f"importance_bands[{idx}].min")

    if missing or empty:
        parts = []
        if missing:
            parts.append("Missing config keys: " + ", ".join(missing))
        if empty:
            parts.append("Empty config values: " + ", ".join(empty))
        raise SystemExit("Config validation failed. " + " ".join(parts))
