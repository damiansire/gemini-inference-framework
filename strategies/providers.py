"""Abstraccion de proveedor de inferencia (Fase 3).

Capa fina de adaptador para no acoplar el framework directo al SDK de Gemini.
El resto del codigo habla con un ``InferenceProvider`` (protocolo), no con
``google.genai`` directamente, de modo que correr el benchmark contra otro
backend (otro modelo, un mock, un proxy) sea cuestion de inyectar otro adapter
en ``utils`` sin tocar los runners.

Diseno deliberadamente acotado: solo se abstrae lo que el framework realmente
usa hoy —una llamada no-streaming y una streaming, ambas async, con timeout y un
``config`` opaco—. No se inventa un contrato generico de "todo proveedor LLM";
eso seria gold-plating sobre un artefacto de benchmark.

El ``GeminiProvider`` ademas resuelve el *connection pooling* (H9): cachea un
unico ``genai.Client`` async por proceso en vez de construir uno nuevo en cada
llamada.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from google import genai


@runtime_checkable
class InferenceProvider(Protocol):
    """Contrato minimo que el framework necesita de un backend de inferencia.

    Las implementaciones devuelven el objeto-respuesta nativo del SDK; la
    normalizacion a payload (texto/usage/parsed) la hace ``utils`` para no
    filtrar la forma del SDK fuera de este modulo.
    """

    async def generate_content(self, *, model: str, contents: Any, config: Any) -> Any: ...

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        """Devuelve un async-iterator de chunks (el stream nativo del SDK)."""
        ...


class GeminiProvider:
    """Adapter sobre ``google.genai`` con cliente pooleado (un solo Client/proceso).

    Reusa un unico ``genai.Client`` async (H9: antes se creaba uno por llamada).
    La API key se lee de ``GOOGLE_API_KEY`` al construir el cliente, igual que
    antes; nunca se loguea ni se persiste.
    """

    def __init__(self, *, model_hint: str | None = None):
        self._model_hint = model_hint
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            api_key = os.environ.get("GOOGLE_API_KEY")
            self._client = genai.Client(api_key=api_key)
        return self._client

    async def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        client = self._get_client()
        return await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        client = self._get_client()
        return await client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )
