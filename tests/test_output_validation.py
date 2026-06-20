"""Tests adversariales para el validador de salida del modelo.

El validador (`strategies/output_validation.py`) es el motor de asserts del
framework: decide si la respuesta del modelo es aceptable. Un assert que "pasa
por accidente" es un falso negativo silencioso -> el peor bug posible en un
evaluador. Por eso cubrimos cada rama de error adversarialmente y comparamos el
dict de salida completo (incluyendo el texto exacto de cada error), no solo
`ok`.
"""

from strategies.output_validation import (
    FULL_LEVELS,
    LAZY_LEVELS,
    parse_payload,
    validate_dictionary_output,
)


def _example(level, source_fi="esimerkki", **extra):
    return {"sourceFi": source_fi, "level": level, **extra}


def _meaning(levels=FULL_LEVELS, **overrides):
    base = {
        "englishDefinition": "a domestic animal",
        "definiendum": {"en": "dog"},
        "synonyms": ["hound"],
        "antonyms": [],
        "examples": [_example(level) for level in levels],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# parse_payload
# --------------------------------------------------------------------------- #


def test_parse_payload_passes_through_dict():
    payload = {"meanings": []}
    assert parse_payload(payload) == (payload, [])


def test_parse_payload_passes_through_list():
    payload = [1, 2, 3]
    assert parse_payload(payload) == (payload, [])


def test_parse_payload_none_is_missing_text():
    assert parse_payload(None) == (None, ["missing text_output"])


def test_parse_payload_empty_string_is_missing_text():
    assert parse_payload("   ") == (None, ["missing text_output"])


def test_parse_payload_invalid_json_reports_message():
    data, errors = parse_payload("not json at all")
    assert data is None
    assert errors == ["invalid JSON output: Expecting value"]


def test_parse_payload_strips_json_code_fence():
    assert parse_payload("```json\n[1, 2]\n```") == ([1, 2], [])


def test_parse_payload_strips_bare_code_fence():
    assert parse_payload("```\n{\"a\": 1}\n```") == ({"a": 1}, [])


def test_parse_payload_unterminated_fence_is_invalid_json():
    # Empieza con fence pero no termina: NO se stripea -> JSON invalido.
    data, errors = parse_payload("```json\n[1, 2]")
    assert data is None
    assert errors and errors[0].startswith("invalid JSON output:")


# --------------------------------------------------------------------------- #
# Estructura raiz
# --------------------------------------------------------------------------- #


def test_root_must_be_array_or_meanings_object():
    result = validate_dictionary_output('{"foo": "bar"}')
    assert result == {
        "ok": False,
        "errors": ["root must be a JSON array or an object with a 'meanings' array"],
        "normalized": None,
    }


def test_empty_meanings_array_rejected():
    assert validate_dictionary_output([]) == {
        "ok": False,
        "errors": ["meanings array is empty"],
        "normalized": None,
    }


def test_empty_meanings_object_rejected():
    assert validate_dictionary_output({"meanings": []}) == {
        "ok": False,
        "errors": ["meanings array is empty"],
        "normalized": None,
    }


def test_invalid_json_short_circuits_before_structure():
    result = validate_dictionary_output("{not valid")
    assert result["ok"] is False
    assert result["normalized"] is None
    assert result["errors"][0].startswith("invalid JSON output:")


# --------------------------------------------------------------------------- #
# Happy path (lista directa y objeto con meanings; full y lazy)
# --------------------------------------------------------------------------- #


def test_valid_full_levels_as_meanings_object():
    result = validate_dictionary_output({"meanings": [_meaning()]})
    assert result["ok"] is True
    assert result["errors"] == []
    assert len(result["normalized"]) == 1


def test_valid_full_levels_as_bare_array():
    result = validate_dictionary_output([_meaning()])
    assert result["ok"] is True


def test_valid_lazy_levels_with_expected_override():
    result = validate_dictionary_output(
        {"meanings": [_meaning(levels=LAZY_LEVELS)]},
        expected_levels=LAZY_LEVELS,
    )
    assert result["ok"] is True


def test_normalized_strips_and_lowercases_levels():
    meaning = _meaning(
        englishDefinition="  spaced  ",
        examples=[_example(level.upper(), source_fi="  raw  ") for level in FULL_LEVELS],
    )
    result = validate_dictionary_output({"meanings": [meaning]})
    assert result["ok"] is True
    first_example = result["normalized"][0]["examples"][0]
    assert first_example["level"] == "a1"
    assert first_example["sourceFi"] == "raw"
    assert result["normalized"][0]["englishDefinition"] == "spaced"


def test_definiendum_accepts_plain_string():
    result = validate_dictionary_output({"meanings": [_meaning(definiendum="dog")]})
    assert result["ok"] is True
    assert result["normalized"][0]["definiendum"] == {"en": "dog"}


# --------------------------------------------------------------------------- #
# Validacion por meaning (cada rama de error)
# --------------------------------------------------------------------------- #


def test_meaning_not_object():
    result = validate_dictionary_output(["just a string"])
    assert result["ok"] is False
    assert "meaning[1] must be an object" in result["errors"]


def test_missing_english_definition():
    result = validate_dictionary_output({"meanings": [_meaning(englishDefinition="")]})
    assert "meaning[1].englishDefinition must be a non-empty string" in result["errors"]


def test_definiendum_wrong_type():
    result = validate_dictionary_output({"meanings": [_meaning(definiendum=123)]})
    assert "meaning[1].definiendum must be a string or an object with 'en'" in result["errors"]


def test_synonyms_must_be_list_of_strings():
    result = validate_dictionary_output({"meanings": [_meaning(synonyms=[1, 2])]})
    assert "meaning[1].synonyms must be a list of strings" in result["errors"]


def test_synonyms_none_defaults_to_empty():
    result = validate_dictionary_output({"meanings": [_meaning(synonyms=None)]})
    assert result["ok"] is True
    assert result["normalized"][0]["synonyms"] == []


def test_antonyms_must_be_list_of_strings():
    result = validate_dictionary_output({"meanings": [_meaning(antonyms=["ok", 7])]})
    assert "meaning[1].antonyms must be a list of strings" in result["errors"]


def test_examples_empty_rejected():
    result = validate_dictionary_output({"meanings": [_meaning(examples=[])]})
    assert "meaning[1].examples must be a non-empty list" in result["errors"]


def test_examples_not_list_rejected():
    result = validate_dictionary_output({"meanings": [_meaning(examples="nope")]})
    assert "meaning[1].examples must be a non-empty list" in result["errors"]


# --------------------------------------------------------------------------- #
# Validacion por example
# --------------------------------------------------------------------------- #


def test_example_not_object():
    result = validate_dictionary_output({"meanings": [_meaning(examples=["x"])]})
    assert "meaning[1].examples[1] must be an object" in result["errors"]


def test_example_missing_source_fi():
    bad = [_example(level, source_fi=" ") for level in FULL_LEVELS]
    result = validate_dictionary_output({"meanings": [_meaning(examples=bad)]})
    assert "meaning[1].examples[1].sourceFi must be a non-empty string" in result["errors"]


def test_example_missing_level():
    bad = [{"sourceFi": "x"}]
    result = validate_dictionary_output({"meanings": [_meaning(examples=bad)]})
    assert "meaning[1].examples[1].level must be a non-empty string" in result["errors"]


def test_example_level_accepts_cefr_alias():
    examples = [{"sourceFi": "x", "cefrLevel": level} for level in FULL_LEVELS]
    result = validate_dictionary_output({"meanings": [_meaning(examples=examples)]})
    assert result["ok"] is True


def test_example_duplicate_level_rejected():
    dup = [_example("a1"), _example("a1")]
    result = validate_dictionary_output({"meanings": [_meaning(examples=dup)]})
    assert "meaning[1].examples contains duplicate level 'a1'" in result["errors"]


def test_example_spoken_fi_wrong_type():
    examples = [_example(level, spokenFi=123) for level in FULL_LEVELS]
    result = validate_dictionary_output({"meanings": [_meaning(examples=examples)]})
    assert "meaning[1].examples[1].spokenFi must be a string or null" in result["errors"]


def test_levels_must_match_exactly():
    partial = [_example(level) for level in ("a1", "a2")]
    result = validate_dictionary_output({"meanings": [_meaning(examples=partial)]})
    assert any("must contain exactly these levels" in err for err in result["errors"])


# --------------------------------------------------------------------------- #
# Marcadores morfologicos (rechaza formas gramaticales, no acepciones)
# --------------------------------------------------------------------------- #


def test_morphological_marker_in_definition_rejected():
    result = validate_dictionary_output(
        {"meanings": [_meaning(englishDefinition="the plural form of cat")]}
    )
    assert "meaning[1] describes a grammatical form instead of a headword sense" in result["errors"]


def test_morphological_marker_in_definiendum_rejected():
    result = validate_dictionary_output(
        {"meanings": [_meaning(definiendum={"en": "genitive form of talo"})]}
    )
    assert (
        "meaning[1].definiendum describes a grammatical form instead of a headword sense"
        in result["errors"]
    )


def test_failure_returns_no_normalized_payload():
    result = validate_dictionary_output({"meanings": [_meaning(englishDefinition="")]})
    assert result["ok"] is False
    assert result["normalized"] is None
