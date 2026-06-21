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
from strategies.stage_assembly import assemble_examples, build_spoken_map


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
    assert parse_payload('```\n{"a": 1}\n```') == ({"a": 1}, [])


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


# --------------------------------------------------------------------------- #
# Ensamblado multi-stage (cascade/pipeline): build_spoken_map + assemble_examples
#
# cascade/pipeline parsean y transforman salida del modelo. Su logica de
# ensamblado (merge por level, regla spoken==sourceFi->None, fallback con
# spoken_map vacio) nunca se ejercitaba. Estos tests alimentan stage-output
# malformado/duplicado/incompleto al ensamblador y afirman el comportamiento.
# --------------------------------------------------------------------------- #


def test_build_spoken_map_happy_path_lowercases_level():
    spoken = [{"level": "A1", "spokenFi": "moi"}, {"level": "b1", "spokenFi": "tuus"}]
    assert build_spoken_map(spoken) == {"a1": "moi", "b1": "tuus"}


def test_build_spoken_map_duplicate_level_last_wins():
    spoken = [{"level": "a1", "spokenFi": "primero"}, {"level": "a1", "spokenFi": "ultimo"}]
    assert build_spoken_map(spoken) == {"a1": "ultimo"}


def test_build_spoken_map_skips_entry_without_level():
    # Stage 3 malformado: una entrada sin 'level' no debe romper el ensamblado.
    spoken = [{"spokenFi": "huerfano"}, {"level": "a2", "spokenFi": "ok"}]
    assert build_spoken_map(spoken) == {"a2": "ok"}


def test_build_spoken_map_skips_entry_with_blank_level():
    spoken = [{"level": "  ", "spokenFi": "x"}, {"level": "a1", "spokenFi": "ok"}]
    assert build_spoken_map(spoken) == {"a1": "ok"}


def test_build_spoken_map_preserves_missing_spoken_as_none():
    # spokenFi ausente (nullable en el schema) se mapea a None, no rompe.
    spoken = [{"level": "a1"}]
    assert build_spoken_map(spoken) == {"a1": None}


def test_assemble_examples_merges_spoken_by_level():
    cefr = [
        {"sourceFi": "Koira juoksee.", "level": "A1"},
        {"sourceFi": "Hana vuotaa.", "level": "b1"},
    ]
    spoken_map = {"a1": "Koira juoksee.", "b1": "Hana vuotaa puhekielessa."}
    result = assemble_examples(cefr, spoken_map)
    # a1: spoken == sourceFi -> se anula a None.
    assert result[0] == {"sourceFi": "Koira juoksee.", "spokenFi": None, "level": "a1"}
    # b1: spoken distinto -> se conserva; level normalizado a lower.
    assert result[1] == {
        "sourceFi": "Hana vuotaa.",
        "spokenFi": "Hana vuotaa puhekielessa.",
        "level": "b1",
    }


def test_assemble_examples_level_missing_from_spoken_map_is_none():
    # Stage 3 incompleto: falta el level -> spokenFi None, no KeyError.
    cefr = [{"sourceFi": "Esimerkki.", "level": "c2"}]
    result = assemble_examples(cefr, {})
    assert result == [{"sourceFi": "Esimerkki.", "spokenFi": None, "level": "c2"}]


def test_assemble_examples_fallback_empty_map_keeps_all_examples():
    # Rama de fallback (except -> spoken_map={}): todos los ejemplos sobreviven
    # con spokenFi=None, ninguno se pierde.
    cefr = [{"sourceFi": s, "level": lvl} for lvl, s in zip(FULL_LEVELS, "abcdef", strict=True)]
    result = assemble_examples(cefr, {})
    assert len(result) == len(FULL_LEVELS)
    assert all(item["spokenFi"] is None for item in result)
    assert [item["level"] for item in result] == list(FULL_LEVELS)


def test_assemble_examples_spoken_equal_after_strip_is_nulled():
    # La regla compara tras strip: whitespace alrededor no debe "salvar" el spoken.
    cefr = [{"sourceFi": "Talo on iso.", "level": "a1"}]
    result = assemble_examples(cefr, {"a1": "  Talo on iso.  "})
    assert result[0]["spokenFi"] is None
