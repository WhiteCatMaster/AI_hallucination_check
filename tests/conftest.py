"""Configuración de pytest para la suite de tests.

`main.py` importa en su nivel superior las librerías de runtime (`github`,
`requests`, `openai`). Para poder testear las funciones puras sin instalar esas
dependencias —y sin riesgo de tocar la red— las sustituimos por stubs ligeros
en `sys.modules` antes de que se importe `main`.
"""

from __future__ import annotations

import os
import sys
import types

# Hace que `import main` funcione ejecutando pytest desde la raíz del repo.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _install_stub(name: str, **attributes: object) -> types.ModuleType:
    """Registra un módulo falso en sys.modules con los atributos indicados."""
    module = types.ModuleType(name)
    for attr, value in attributes.items():
        setattr(module, attr, value)
    sys.modules[name] = module
    return module


# --- Stub de `requests` (cualquier llamada real fallaría la intención del test) ---
class _StubRequestException(Exception):
    """Sustituto de requests.RequestException."""


def _forbidden_get(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("Los tests no deben realizar llamadas de red reales.")


_install_stub("requests", RequestException=_StubRequestException, get=_forbidden_get)


# --- Stub del paquete `github` y sus submódulos usados por main ---
class _StubGithubException(Exception):
    """Sustituto de github.GithubException."""


class _StubGithub:  # pragma: no cover - solo se instancia en runtime real.
    def __init__(self, *_args: object, **_kwargs: object) -> None: ...


_install_stub("github", Github=_StubGithub, GithubException=_StubGithubException)
_install_stub("github.File", File=type("File", (), {}))
_install_stub("github.PullRequest", PullRequest=type("PullRequest", (), {}))

# `openai` se importa de forma diferida dentro de main, pero lo stubeamos por
# seguridad para que un import accidental no falle.
_install_stub("openai", OpenAI=type("OpenAI", (), {}))
