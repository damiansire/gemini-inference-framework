import json

FULL_LEVELS = ("a1", "a2", "b1", "b2", "c1", "c2")
LAZY_LEVELS = ("a1", "a2", "b1")

MORPHOLOGICAL_FORM_MARKERS = (
    "possessive form",
    "inflected form",
    "genitive form",
    "partitive form",
    "plural form",
    "illative form",
    "elative form",
    "inessive form",
)


def _strip_code_fence(text: str) -> str:  # Eliminar bloques de código
    stripped = text.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        return stripped[7:-3].strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped[3:-3].strip()
    return stripped


def parse_payload(payload):
    if isinstance(payload, (dict, list)):
        return payload, []

    if not isinstance(payload, str) or not payload.strip():
        return None, ["missing text_output"]

    try:
        return json.loads(_strip_code_fence(payload)), []
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON output: {exc.msg}"]


def validate_dictionary_output(payload, expected_levels=FULL_LEVELS):  # Validar salida del diccionario
    data, errors = parse_payload(payload)
    if errors:
        return {"ok": False, "errors": errors, "normalized": None}

    if isinstance(data, dict) and isinstance(data.get("meanings"), list):
        meanings = data["meanings"]
    elif isinstance(data, list):
        meanings = data
    else:
        return {
            "ok": False,
            "errors": ["root must be a JSON array or an object with a 'meanings' array"],
            "normalized": None,
        }

    if not meanings:
        return {"ok": False, "errors": ["meanings array is empty"], "normalized": None}

    normalized = []

    for index, meaning in enumerate(meanings, start=1):
        prefix = f"meaning[{index}]"

        if not isinstance(meaning, dict):
            errors.append(f"{prefix} must be an object")
            continue

        english_definition = meaning.get("englishDefinition")
        if not isinstance(english_definition, str) or not english_definition.strip():
            errors.append(f"{prefix}.englishDefinition must be a non-empty string")
            continue

        definiendum_value = meaning.get("definiendum")
        if isinstance(definiendum_value, dict):
            definiendum_en = definiendum_value.get("en")
        elif isinstance(definiendum_value, str):
            definiendum_en = definiendum_value
        else:
            definiendum_en = None

        if not isinstance(definiendum_en, str) or not definiendum_en.strip():
            errors.append(f"{prefix}.definiendum must be a string or an object with 'en'")
            continue

        synonyms = meaning.get("synonyms")
        if synonyms is None:
            synonyms = []
        if not isinstance(synonyms, list) or any(not isinstance(item, str) for item in synonyms):
            errors.append(f"{prefix}.synonyms must be a list of strings")
            continue

        antonyms = meaning.get("antonyms")
        if antonyms is None:
            antonyms = []
        if not isinstance(antonyms, list) or any(not isinstance(item, str) for item in antonyms):
            errors.append(f"{prefix}.antonyms must be a list of strings")
            continue

        examples = meaning.get("examples")
        if not isinstance(examples, list) or not examples:
            errors.append(f"{prefix}.examples must be a non-empty list")
            continue

        level_map = {}
        normalized_examples = []

        for example_index, example in enumerate(examples, start=1):
            example_prefix = f"{prefix}.examples[{example_index}]"
            if not isinstance(example, dict):
                errors.append(f"{example_prefix} must be an object")
                continue

            source_fi = example.get("sourceFi")
            if not isinstance(source_fi, str) or not source_fi.strip():
                errors.append(f"{example_prefix}.sourceFi must be a non-empty string")
                continue

            level = example.get("level", example.get("cefrLevel", example.get("cefr")))
            if not isinstance(level, str) or not level.strip():
                errors.append(f"{example_prefix}.level must be a non-empty string")
                continue

            normalized_level = level.lower()
            if normalized_level in level_map:
                errors.append(f"{prefix}.examples contains duplicate level '{normalized_level}'")
                continue

            spoken_fi = example.get("spokenFi")
            if spoken_fi is not None and not isinstance(spoken_fi, str):
                errors.append(f"{example_prefix}.spokenFi must be a string or null")
                continue

            level_map[normalized_level] = True
            normalized_examples.append(
                {
                    "sourceFi": source_fi.strip(),
                    "spokenFi": spoken_fi.strip() if isinstance(spoken_fi, str) else None,
                    "level": normalized_level,
                }
            )

        if tuple(sorted(level_map.keys())) != tuple(sorted(expected_levels)):
            errors.append(
                f"{prefix}.examples must contain exactly these levels: {', '.join(expected_levels)}"
            )

        lower_definition = english_definition.lower()
        lower_definiendum = definiendum_en.lower()
        if any(marker in lower_definition for marker in MORPHOLOGICAL_FORM_MARKERS):
            errors.append(f"{prefix} describes a grammatical form instead of a headword sense")
        if any(marker in lower_definiendum for marker in MORPHOLOGICAL_FORM_MARKERS):
            errors.append(f"{prefix}.definiendum describes a grammatical form instead of a headword sense")

        normalized.append(
            {
                "englishDefinition": english_definition.strip(),
                "definiendum": {"en": definiendum_en.strip()},
                "synonyms": synonyms,
                "antonyms": antonyms,
                "examples": normalized_examples,
            }
        )

    return {"ok": not errors, "errors": errors, "normalized": normalized if not errors else None}
