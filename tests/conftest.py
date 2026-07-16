"""Fixtures compartidas de la suite.

``provider_sandbox`` garantiza que cualquier test que inyecte un provider lo
restaure (y resetee el Semaphore compartido) aunque falle a mitad de camino.
``replay_provider`` inyecta el ``ReplayProvider`` de ``benchmarks/`` con
``time_scale=0`` (sin sleeps): los tests por estrategia ejercitan exactamente
el mismo provider y las mismas fixtures versionadas que el harness de replay,
asi que un payload roto en la fixture rompe la suite, no solo el nightly.
"""

import pytest

from benchmarks.replay_provider import ReplayProvider, load_fixture
from strategies import utils


@pytest.fixture
def provider_sandbox():
    """Devuelve ``set_provider`` y restaura el provider original al salir."""
    original = utils.get_provider()
    yield utils.set_provider
    utils.set_provider(original)
    utils.reset_inference_semaphore()


@pytest.fixture
def replay_provider(provider_sandbox):
    provider = ReplayProvider(load_fixture(), time_scale=0)
    provider_sandbox(provider)
    return provider
