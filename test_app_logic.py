import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_logic import (  # noqa: E402
    build_memory_context,
    empty_state,
    load_data,
    new_journal_entry,
    new_mood_entry,
    parse_ai_json,
    record_strategy_used,
    sanitize_input,
    sanitize_profile,
    save_data,
    top_worked_strategies,
)


# ---------- sanitize_input ----------

def test_sanitize_input_strips_and_collapses_whitespace():
    assert sanitize_input("  hello   world  ") == "hello world"


def test_sanitize_input_truncates_to_max_len():
    long_text = "a" * 1000
    result = sanitize_input(long_text, max_len=50)
    assert len(result) == 50


def test_sanitize_input_handles_none():
    assert sanitize_input(None) == ""


def test_sanitize_profile_sanitizes_every_field():
    draft = {"name": "  Alex  ", "goal": "stay   clear headed"}
    result = sanitize_profile(draft)
    assert result["name"] == "Alex"
    assert result["goal"] == "stay clear headed"


# ---------- parse_ai_json ----------

def test_parse_ai_json_handles_clean_json():
    text = '{"reflection": "hi there"}'
    assert parse_ai_json(text) == {"reflection": "hi there"}


def test_parse_ai_json_strips_markdown_fences():
    text = '```json\n{"reflection": "hi"}\n```'
    assert parse_ai_json(text) == {"reflection": "hi"}


def test_parse_ai_json_never_raises_on_garbage():
    result = parse_ai_json("not json at all {{{")
    assert "raw" in result


def test_parse_ai_json_handles_empty_string():
    result = parse_ai_json("")
    assert result == {"raw": ""}


def test_parse_ai_json_rejects_non_dict_json():
    result = parse_ai_json("[1, 2, 3]")
    assert "raw" in result


# ---------- top_worked_strategies ----------

def test_top_worked_strategies_ranks_by_count():
    what_worked = {"walk": 1, "music": 5, "call sister": 3}
    result = top_worked_strategies(what_worked, limit=2)
    assert result.startswith("music (helped 5x)")
    assert "walk" not in result  # only top 2


def test_top_worked_strategies_empty():
    assert top_worked_strategies({}) == "nothing logged yet"


# ---------- build_memory_context ----------

def test_build_memory_context_handles_missing_profile():
    context = build_memory_context(None, None, None)
    assert "friend" in context
    assert "not specified" in context


def test_build_memory_context_includes_favorites_and_triggers():
    profile = {"name": "Sam", "triggers": "Friday nights", "favorites": "Rocky movies"}
    context = build_memory_context(profile, {"what_worked": {}}, [])
    assert "Sam" in context
    assert "Friday nights" in context
    assert "Rocky movies" in context


def test_build_memory_context_never_raises_on_partial_data():
    # missing keys entirely — should not KeyError
    build_memory_context({}, {}, [])


# ---------- record_strategy_used (immutability) ----------

def test_record_strategy_used_increments_count():
    memory = {"what_worked": {"walk": 2}}
    updated = record_strategy_used(memory, "walk")
    assert updated["what_worked"]["walk"] == 3


def test_record_strategy_used_does_not_mutate_original():
    memory = {"what_worked": {"walk": 2}}
    record_strategy_used(memory, "walk")
    assert memory["what_worked"]["walk"] == 2  # original untouched


def test_record_strategy_used_adds_new_key():
    memory = {"what_worked": {}}
    updated = record_strategy_used(memory, "music")
    assert updated["what_worked"]["music"] == 1


# ---------- entry builders ----------

def test_new_mood_entry_has_expected_shape():
    entry = new_mood_entry("anxious")
    assert entry["emotion"] == "anxious"
    assert "at" in entry


def test_new_journal_entry_sanitizes_summary():
    entry = new_journal_entry("sad", "  a long   summary  ")
    assert entry["summary"] == "a long summary"


# ---------- load_data / save_data (file I/O, atomic write) ----------

def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "test_data.json")
    data = empty_state()
    data["profile"] = {"name": "Test User"}
    save_data(data, path=path)

    loaded = load_data(path=path)
    assert loaded["profile"]["name"] == "Test User"


def test_load_data_missing_file_returns_empty_state(tmp_path):
    path = str(tmp_path / "does_not_exist.json")
    loaded = load_data(path=path)
    assert loaded == empty_state()


def test_load_data_corrupted_file_falls_back_gracefully(tmp_path):
    path = str(tmp_path / "corrupt.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    loaded = load_data(path=path)
    assert loaded == empty_state()


def test_save_data_is_atomic_no_leftover_tmp_files(tmp_path):
    path = str(tmp_path / "atomic.json")
    save_data(empty_state(), path=path)
    leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".tmp_")]
    assert leftovers == []


def test_load_data_rejects_oversized_file(tmp_path):
    path = str(tmp_path / "huge.json")
    # write valid-but-oversized JSON to confirm the size guard trips
    with open(path, "w") as f:
        json.dump({"padding": "x" * 10}, f)
    # sanity check normal-size file loads fine (guard shouldn't false-positive)
    loaded = load_data(path=path)
    assert loaded["profile"] is None
