"""Tests de los parsers y de las reglas regex de detección.

Ninguno de estos tests realiza llamadas de red: solo ejercitan lógica pura de
parseo y de coincidencia de patrones.
"""

from __future__ import annotations

import pytest

import main
from main import (
    AnalysisResult,
    Severity,
    _parse_npm_packages,
    _parse_python_package_name,
    check_outdated_code,
)


# --------------------------------------------------------------------------- #
# _parse_python_package_name
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "line, expected",
    [
        ("requests==2.32.3", "requests"),
        ("PyGithub>=2.0", "PyGithub"),
        ("openai", "openai"),
        ("uvicorn[standard]==0.30.0", "uvicorn"),
        ("scikit-learn~=1.5", "scikit-learn"),
        ("  flask == 3.0.0  ", "flask"),
    ],
)
def test_parse_python_package_name_valid(line: str, expected: str) -> None:
    assert _parse_python_package_name(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "# esto es un comentario",
        "-r requirements-base.txt",
        "--extra-index-url https://example.com",
    ],
)
def test_parse_python_package_name_ignored(line: str) -> None:
    assert _parse_python_package_name(line) is None


# --------------------------------------------------------------------------- #
# _parse_npm_packages
# --------------------------------------------------------------------------- #

def test_parse_npm_packages_extracts_dependencies() -> None:
    added_lines = [
        '"react": "^18.2.0",',
        '"left-pad": "1.3.0",',
        '"typescript": "~5.4.0"',
    ]
    assert _parse_npm_packages(added_lines) == ["react", "left-pad", "typescript"]


def test_parse_npm_packages_skips_metadata_keys() -> None:
    # Las claves de metadatos no deben confundirse con dependencias.
    added_lines = [
        '"name": "mi-proyecto",',
        '"version": "1.0.0",',
        '"description": "demo",',
        '"axios": "^1.7.0"',
    ]
    assert _parse_npm_packages(added_lines) == ["axios"]


def test_parse_npm_packages_ignores_non_dependency_lines() -> None:
    added_lines = ["{", "  // un comentario", '"scripts": {']
    assert _parse_npm_packages(added_lines) == []


# --------------------------------------------------------------------------- #
# check_outdated_code (reglas regex)
# --------------------------------------------------------------------------- #

def _diff_with_added(code: str) -> str:
    """Construye un diff mínimo con `code` como línea añadida."""
    return f"+++ b/app.js\n+{code}\n context sin cambios"


def test_check_outdated_code_detects_deprecated_react_api() -> None:
    result = AnalysisResult()
    diff = _diff_with_added("componentWillReceiveProps(nextProps) {")
    check_outdated_code(diff, result)

    assert result.has_any
    assert len(result.findings) == 1
    assert result.findings[0].severity is Severity.WARNING
    assert "componentWillReceiveProps" in result.findings[0].detail


def test_check_outdated_code_detects_reactdom_render() -> None:
    result = AnalysisResult()
    check_outdated_code(_diff_with_added("ReactDOM.render(<App />, el);"), result)
    assert len(result.findings) == 1


def test_check_outdated_code_ignores_removed_lines() -> None:
    # Una API deprecada en una línea ELIMINADA (-) no debe marcarse.
    result = AnalysisResult()
    diff = "+++ b/app.js\n-componentWillMount() {}\n+componentDidMount() {}"
    check_outdated_code(diff, result)
    assert not result.has_any


def test_check_outdated_code_clean_diff_has_no_findings() -> None:
    result = AnalysisResult()
    check_outdated_code(_diff_with_added("const root = createRoot(el);"), result)
    assert not result.has_any


def test_check_outdated_code_detects_multiple_rules() -> None:
    result = AnalysisResult()
    diff = (
        "+++ b/component.jsx\n"
        "+componentWillMount() {}\n"
        "+ReactDOM.render(<A/>, n);\n"
        "+df.ix[0]"
    )
    check_outdated_code(diff, result)
    assert len(result.findings) == 3


# --------------------------------------------------------------------------- #
# Garantía de aislamiento de red
# --------------------------------------------------------------------------- #

def test_network_get_is_stubbed() -> None:
    # Confirma que cualquier intento de llamada HTTP real fallaría.
    with pytest.raises(AssertionError):
        main.requests.get("https://pypi.org/pypi/requests/json")
