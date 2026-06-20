"""Ensamblado puro de las etapas multi-stage (cascade/pipeline).

Esta logica toma la salida ya parseada de Stage 2 (ejemplos CEFR) y Stage 3
(transformacion a puhekieli) y arma la lista final de `examples`. Se extrae aca
como funcion pura (sin dependencias de red ni del SDK) para poder ejercitar
adversarialmente sus ramas: stage-3 malformado/duplicado/incompleto, merge por
level y la regla `spoken == sourceFi -> None`.
"""


def build_spoken_map(spoken_examples):
    """Mapa level (lower) -> spokenFi a partir de la salida de Stage 3.

    Ignora entradas sin `level`. Si un level se repite, gana el ultimo
    (comportamiento del dict-comprehension original).
    """
    spoken_map = {}
    for example in spoken_examples:
        level = example.get("level")
        if not isinstance(level, str) or not level.strip():
            continue
        spoken_map[level.lower()] = example.get("spokenFi")
    return spoken_map


def assemble_examples(cefr_examples, spoken_map):
    """Combina los ejemplos CEFR de Stage 2 con el spoken_map de Stage 3.

    - merge por `level` (normalizado a lower).
    - regla: si `spokenFi` coincide (tras strip) con `sourceFi`, se anula a None
      porque no aporta una forma hablada distinta.
    - un level sin entrada en `spoken_map` queda con `spokenFi=None`.
    """
    examples = []
    for example in cefr_examples:
        level = example["level"].lower()
        spoken = spoken_map.get(level)
        if isinstance(spoken, str) and spoken.strip() == example["sourceFi"].strip():
            spoken = None
        examples.append(
            {
                "sourceFi": example["sourceFi"],
                "spokenFi": spoken,
                "level": level,
            }
        )
    return examples
