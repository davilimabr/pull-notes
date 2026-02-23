"""Tests for config module (load_config, validate_config)."""

import json
import pytest

from pullnotes.config import load_config, validate_config, _is_empty


# ---------------------------------------------------------------------------
# _is_empty
# ---------------------------------------------------------------------------

class TestIsEmpty:
    def test_none_is_empty(self):
        assert _is_empty(None) is True

    def test_empty_string_is_empty(self):
        assert _is_empty("") is True

    def test_whitespace_only_is_empty(self):
        assert _is_empty("   ") is True

    def test_non_empty_string(self):
        assert _is_empty("hello") is False

    def test_empty_list_is_empty(self):
        assert _is_empty([]) is True

    def test_non_empty_list(self):
        assert _is_empty([1]) is False

    def test_empty_dict_is_empty(self):
        assert _is_empty({}) is True

    def test_non_empty_dict(self):
        assert _is_empty({"a": 1}) is False

    def test_zero_is_not_empty(self):
        assert _is_empty(0) is False

    def test_false_is_not_empty(self):
        assert _is_empty(False) is False


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_loads_valid_json(self, config_file):
        config = load_config(str(config_file))
        assert isinstance(config, dict)
        assert "commit_types" in config

    def test_raises_on_none_path(self):
        with pytest.raises(SystemExit):
            load_config(None)

    def test_raises_on_empty_path(self):
        with pytest.raises(SystemExit):
            load_config("")

    def test_raises_on_nonexistent_file(self):
        with pytest.raises(SystemExit):
            load_config("/nonexistent/path/config.json")

    def test_raises_on_non_object_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text('["not", "an", "object"]', encoding="utf-8")
        with pytest.raises(SystemExit):
            load_config(str(path))

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_config(str(path))


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_valid_config_for_pr(self, sample_config):
        validate_config(sample_config, generate="pr")

    def test_valid_config_for_release(self, sample_config):
        validate_config(sample_config, generate="release")

    def test_valid_config_for_both(self, sample_config):
        validate_config(sample_config, generate="both")

    def test_missing_other_label(self, sample_config):
        del sample_config["other_label"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_missing_importance_weight_lines(self, sample_config):
        del sample_config["importance"]["weight_lines"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_missing_output_dir(self, sample_config):
        del sample_config["output"]["dir"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_missing_pr_template_for_pr(self, sample_config):
        del sample_config["templates"]["pr"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_missing_release_template_for_release(self, sample_config):
        del sample_config["templates"]["release"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="release")

    def test_missing_language(self, sample_config):
        del sample_config["language"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_missing_llm_model(self, sample_config):
        del sample_config["llm_model"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_empty_commit_types(self, sample_config):
        sample_config["commit_types"] = {}
        with pytest.raises(SystemExit, match="Empty config values"):
            validate_config(sample_config, generate="pr")

    def test_commit_type_missing_label(self, sample_config):
        del sample_config["commit_types"]["feat"]["label"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_commit_type_empty_patterns(self, sample_config):
        sample_config["commit_types"]["feat"]["patterns"] = []
        with pytest.raises(SystemExit, match="Empty config values"):
            validate_config(sample_config, generate="pr")

    def test_empty_importance_bands(self, sample_config):
        sample_config["importance_bands"] = []
        with pytest.raises(SystemExit, match="Empty config values"):
            validate_config(sample_config, generate="pr")

    def test_importance_band_missing_name(self, sample_config):
        sample_config["importance_bands"][0] = {"min": 0.0}
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_importance_band_missing_min(self, sample_config):
        sample_config["importance_bands"][0] = {"name": "low"}
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="pr")

    def test_release_without_domain_config(self, sample_config):
        del sample_config["domain"]["model"]
        with pytest.raises(SystemExit, match="Missing config keys"):
            validate_config(sample_config, generate="release")

    def test_pr_does_not_require_domain(self, sample_config):
        del sample_config["domain"]
        validate_config(sample_config, generate="pr")
