"""Run configs load, validate, and refuse to hide mistakes."""

import pytest
import yaml
from pydantic import ValidationError

from stockagent.config import RunConfig

MINIMAL = {
    "name": "t",
    "model": {"name": "some/model"},
    "eval": {"version": "v1", "as_of": "2026-01-02"},
    "agent": {"kind": "closed_book"},
}


def write(tmp_path, data):
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_loads_the_shipped_smoke_config():
    config = RunConfig.from_yaml("configs/smoke.yaml")
    assert config.name == "smoke"
    assert config.agent.kind == "closed_book"
    assert config.eval.as_of == "2026-09-26"


def test_defaults_suit_a_t4():
    config = RunConfig.model_validate(MINIMAL)
    # T4 has no bfloat16, and a moving temperature makes small gains
    # unmeasurable. Both defaults are load-bearing, so they are pinned here.
    assert config.model.dtype == "float16"
    assert config.model.temperature == 0.0


def test_a_misspelled_key_is_an_error_not_a_silent_default():
    bad = {**MINIMAL, "model": {"name": "m", "temparature": 0.7}}
    with pytest.raises(ValidationError, match="temparature"):
        RunConfig.model_validate(bad)


def test_an_unknown_agent_kind_is_rejected():
    bad = {**MINIMAL, "agent": {"kind": "magic"}}
    with pytest.raises(ValidationError):
        RunConfig.model_validate(bad)


def test_yaml_that_is_not_a_mapping_is_rejected(tmp_path):
    path = tmp_path / "run.yaml"
    path.write_text("- just\n- a list\n")
    with pytest.raises(ValueError, match="mapping"):
        RunConfig.from_yaml(path)


def test_fingerprint_is_stable_across_loads(tmp_path):
    path = write(tmp_path, MINIMAL)
    assert RunConfig.from_yaml(path).fingerprint() == RunConfig.from_yaml(path).fingerprint()


def test_fingerprint_changes_when_any_setting_changes(tmp_path):
    base = RunConfig.from_yaml(write(tmp_path, MINIMAL)).fingerprint()
    hotter = {**MINIMAL, "model": {"name": "some/model", "temperature": 0.7}}
    assert RunConfig.model_validate(hotter).fingerprint() != base


def test_fingerprint_ignores_key_order(tmp_path):
    reversed_keys = dict(reversed(list(MINIMAL.items())))
    assert (
        RunConfig.model_validate(reversed_keys).fingerprint()
        == RunConfig.model_validate(MINIMAL).fingerprint()
    )
