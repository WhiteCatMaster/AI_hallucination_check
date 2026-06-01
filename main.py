#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai-hallucination-detector.

Punto de entrada de la GitHub Action. Analiza los archivos modificados en un
Pull Request para detectar tres patrones típicos del código generado por IA:

1. Dependencias fantasma: paquetes que no existen en el registro (PyPI / npm).
2. Código desactualizado: APIs deprecadas por el "knowledge cutoff" del modelo.
3. Tests tautológicos: tests que pasan porque repiten la lógica defectuosa.

El script lee el contexto desde las variables de entorno que GitHub Actions
expone, publica un comentario en el PR con los hallazgos y termina con un código
de salida coherente para que el check de la Action falle si procede.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional

import requests
from github import Github, GithubException
from github.File import File
from github.PullRequest import PullRequest

# --------------------------------------------------------------------------- #
# Constantes y configuración
# --------------------------------------------------------------------------- #

# Timeout (segundos) para las peticiones HTTP a los registros de paquetes.
HTTP_TIMEOUT: Final[int] = 10

# Modelo del LLM usado como juez de QA.
LLM_MODEL: Final[str] = "gpt-4o-mini"

# Archivos de dependencias que sabemos analizar.
PYTHON_DEP_FILES: Final[tuple[str, ...]] = ("requirements.txt", "requirements-dev.txt")
NPM_DEP_FILES: Final[tuple[str, ...]] = ("package.json",)

# Extensiones consideradas archivos de test.
TEST_FILE_PATTERNS: Final[tuple[str, ...]] = (
    "test_",
    "_test.py",
    ".test.js",
    ".test.ts",
    ".spec.js",
    ".spec.ts",
)

# Reglas de APIs deprecadas. La clave es una regex que se busca en el diff y el
# valor es el mensaje explicativo que se mostrará al usuario.
#
# NOTA: solo se incluyen reglas de muy baja tasa de falsos positivos: firmas
# distintivas y namespaced (p. ej. `ReactDOM.render`) o nombres que solo
# existen en la API deprecada (p. ej. `componentWillReceiveProps`). Se evitan
# patrones genéricos como `.append(` que colisionan con métodos de uso común.
DEPRECATED_API_RULES: Final[dict[str, str]] = {
    # React: métodos del ciclo de vida obsoletos (nombres exclusivos de la API).
    r"\bcomponentWillReceiveProps\b": (
        "`componentWillReceiveProps` está deprecado en React 16.3+. "
        "Usa `getDerivedStateFromProps` o hooks (`useEffect`)."
    ),
    r"\bcomponentWillMount\b": (
        "`componentWillMount` está deprecado. Usa `componentDidMount` "
        "o el hook `useEffect`."
    ),
    r"\bcomponentWillUpdate\b": (
        "`componentWillUpdate` está deprecado. Usa `getSnapshotBeforeUpdate` "
        "o `componentDidUpdate`."
    ),
    r"\bReactDOM\.render\b": (
        "`ReactDOM.render` quedó obsoleto en React 18. "
        "Usa `ReactDOM.createRoot(container).render(...)`."
    ),
    # Pandas: `.ix` es un indexador eliminado y su firma es distintiva.
    r"\.ix\[": (
        "El indexador `.ix` fue eliminado de Pandas. "
        "Usa `.loc` (por etiqueta) o `.iloc` (por posición)."
    ),
    # Librerías completamente deprecadas: import de un paquete reemplazado.
    r"\bimport\s+sklearn\.externals\.joblib\b": (
        "`sklearn.externals.joblib` fue eliminado. "
        "Importa `joblib` directamente como paquete independiente."
    ),
}


class Severity(Enum):
    """Gravedad de un hallazgo, usada para decidir el código de salida."""

    WARNING = "⚠️ Advertencia"
    CRITICAL = "🛑 Crítico"


@dataclass
class Finding:
    """Representa un único hallazgo detectado durante el análisis."""

    severity: Severity
    title: str
    detail: str
    location: Optional[str] = None


@dataclass
class AnalysisResult:
    """Acumula todos los hallazgos producidos por los validadores."""

    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def has_critical(self) -> bool:
        return any(f.severity is Severity.CRITICAL for f in self.findings)

    @property
    def has_any(self) -> bool:
        return bool(self.findings)


# --------------------------------------------------------------------------- #
# Utilidades de entorno y contexto de GitHub Actions
# --------------------------------------------------------------------------- #

def get_required_env(name: str) -> str:
    """Devuelve una variable de entorno obligatoria o aborta si falta."""
    value: Optional[str] = os.environ.get(name)
    if not value:
        print(f"::error::Falta la variable de entorno obligatoria '{name}'.")
        sys.exit(1)
    return value


def load_event_payload() -> dict:
    """Carga el payload del evento que disparó la Action.

    GitHub deja el JSON del evento en la ruta indicada por GITHUB_EVENT_PATH.
    """
    event_path: Optional[str] = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.isfile(event_path):
        print("::error::No se encontró GITHUB_EVENT_PATH; ¿se ejecuta en un PR?")
        sys.exit(1)

    with open(event_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_pr_number(event: dict) -> int:
    """Extrae el número del Pull Request desde el payload del evento."""
    # En eventos `pull_request` el número viene en la raíz.
    if "pull_request" in event and "number" in event["pull_request"]:
        return int(event["pull_request"]["number"])
    # En eventos `issue_comment` sobre un PR viene bajo `issue`.
    if "issue" in event and "number" in event["issue"]:
        return int(event["issue"]["number"])
    print("::error::El evento no contiene un Pull Request analizable.")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Módulo 1: detección de dependencias fantasma (paquetes alucinados)
# --------------------------------------------------------------------------- #

def _extract_added_lines(patch: Optional[str]) -> list[str]:
    """Devuelve solo las líneas añadidas (las que empiezan por '+') de un diff."""
    if not patch:
        return []
    added: list[str] = []
    for line in patch.splitlines():
        # Ignoramos la cabecera del diff ('+++ b/archivo').
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:].strip())
    return added


def _parse_python_package_name(line: str) -> Optional[str]:
    """Extrae el nombre del paquete de una línea de requirements.txt."""
    cleaned = line.strip()
    if not cleaned or cleaned.startswith("#") or cleaned.startswith("-"):
        return None
    # Separa el nombre de los especificadores de versión y extras.
    match = re.match(r"^([A-Za-z0-9_.\-]+)", cleaned)
    return match.group(1) if match else None


def _package_exists_on_pypi(package: str) -> bool:
    """Comprueba si un paquete existe en PyPI consultando su API JSON."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        # Ante un error de red no afirmamos que sea una alucinación.
        print(f"::warning::No se pudo verificar '{package}' en PyPI: {exc}")
        return True
    return response.status_code != 404


def _package_exists_on_npm(package: str) -> bool:
    """Comprueba si un paquete existe en el registro de npm."""
    url = f"https://registry.npmjs.org/{package}"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        print(f"::warning::No se pudo verificar '{package}' en npm: {exc}")
        return True
    return response.status_code != 404


def check_ghost_dependencies(files: list[File], result: AnalysisResult) -> None:
    """Analiza los archivos de dependencias buscando paquetes inexistentes.

    Solo se evalúan las líneas *añadidas* en el PR para no penalizar
    dependencias preexistentes.
    """
    for file in files:
        filename = os.path.basename(file.filename)
        added_lines = _extract_added_lines(file.patch)

        # --- Dependencias de Python (requirements.txt) ---
        if filename in PYTHON_DEP_FILES:
            for line in added_lines:
                package = _parse_python_package_name(line)
                if package and not _package_exists_on_pypi(package):
                    result.add(
                        Finding(
                            severity=Severity.CRITICAL,
                            title="Dependencia fantasma (PyPI)",
                            detail=(
                                f"El paquete **`{package}`** no existe en PyPI "
                                "(404). Posible alucinación del modelo de IA."
                            ),
                            location=file.filename,
                        )
                    )

        # --- Dependencias de Node (package.json) ---
        elif filename in NPM_DEP_FILES:
            for package in _parse_npm_packages(added_lines):
                if not _package_exists_on_npm(package):
                    result.add(
                        Finding(
                            severity=Severity.CRITICAL,
                            title="Dependencia fantasma (npm)",
                            detail=(
                                f"El paquete **`{package}`** no existe en el "
                                "registro de npm (404). Posible alucinación."
                            ),
                            location=file.filename,
                        )
                    )


def _parse_npm_packages(added_lines: list[str]) -> list[str]:
    """Extrae nombres de paquetes de líneas añadidas en un package.json.

    Busca pares "nombre": "version" típicos de las secciones de dependencias.
    """
    packages: list[str] = []
    dependency_pattern = re.compile(r'"([^"]+)"\s*:\s*"[~^]?[\dvx*.\-A-Za-z]+"')
    for line in added_lines:
        match = dependency_pattern.search(line)
        if match:
            name = match.group(1)
            # Filtra claves de metadatos que no son dependencias.
            if name not in {"name", "version", "description", "license", "main"}:
                packages.append(name)
    return packages


# --------------------------------------------------------------------------- #
# Módulo 2: detección de código desactualizado (knowledge cutoff)
# --------------------------------------------------------------------------- #

def check_outdated_code(diff: str, result: AnalysisResult) -> None:
    """Busca firmas de APIs deprecadas en el texto del diff.

    Usa el diccionario `DEPRECATED_API_RULES` para mapear patrones a mensajes
    explicativos. Solo inspecciona líneas añadidas.
    """
    added_text = "\n".join(
        line[1:] for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )

    for pattern, message in DEPRECATED_API_RULES.items():
        if re.search(pattern, added_text):
            result.add(
                Finding(
                    severity=Severity.WARNING,
                    title="Código desactualizado (knowledge cutoff)",
                    detail=message,
                )
            )


# --------------------------------------------------------------------------- #
# Módulo 3: detección de tests tautológicos mediante un LLM "Juez de QA"
# --------------------------------------------------------------------------- #

QA_JUDGE_SYSTEM_PROMPT: Final[str] = (
    "Eres un revisor de QA extremadamente estricto y escéptico. Tu única misión "
    "es detectar 'tests tautológicos' o complacientes: tests que pasan porque "
    "reimplementan la misma lógica (posiblemente defectuosa) del código que "
    "deberían verificar, que comparan un valor consigo mismo, que mockean "
    "justo aquello que pretenden probar, o que afirman trivialidades "
    "(p. ej. `assert True`, `assert x == x`).\n\n"
    "Analiza ÚNICAMENTE el diff de tests proporcionado. Responde SIEMPRE en "
    "formato JSON estricto con este esquema:\n"
    '{"tautological": <bool>, "confidence": <0.0-1.0>, '
    '"reasons": [<string>, ...]}\n'
    "No incluyas texto fuera del JSON. Si los tests son legítimos, "
    'devuelve {"tautological": false, "confidence": ..., "reasons": []}.'
)


def _extract_test_diff(files: list[File]) -> str:
    """Concatena los diffs de los archivos que parecen ser de testing."""
    chunks: list[str] = []
    for file in files:
        name = os.path.basename(file.filename)
        is_test = any(
            name.startswith(p) or file.filename.endswith(p)
            for p in TEST_FILE_PATTERNS
        )
        if is_test and file.patch:
            chunks.append(f"### {file.filename}\n{file.patch}")
    return "\n\n".join(chunks)


def evaluate_tautological_tests(
    files: list[File],
    api_key: Optional[str],
    result: AnalysisResult,
) -> None:
    """Evalúa con un LLM si los tests modificados son tautológicos.

    Si no hay clave de API o no hay diffs de test, el análisis se omite de forma
    silenciosa (no es un fallo).
    """
    test_diff = _extract_test_diff(files)
    if not test_diff:
        print("::notice::No se detectaron archivos de test que evaluar.")
        return

    if not api_key:
        print(
            "::warning::No se proporcionó 'llm_api_key'; "
            "se omite la evaluación de tests tautológicos."
        )
        return

    verdict = _query_qa_judge(test_diff, api_key)
    if verdict is None:
        return  # El error ya se registró dentro de _query_qa_judge.

    if verdict.get("tautological") is True:
        confidence = float(verdict.get("confidence", 0.0))
        reasons = verdict.get("reasons", [])
        bullet_reasons = "\n".join(f"- {r}" for r in reasons) or "- (sin detalle)"
        # Alta confianza => crítico; baja confianza => advertencia.
        severity = Severity.CRITICAL if confidence >= 0.7 else Severity.WARNING
        result.add(
            Finding(
                severity=severity,
                title="Test tautológico / complaciente",
                detail=(
                    f"El juez de QA marcó los tests como tautológicos "
                    f"(confianza {confidence:.0%}):\n{bullet_reasons}"
                ),
            )
        )


def _query_qa_judge(test_diff: str, api_key: str) -> Optional[dict]:
    """Realiza la llamada al LLM y parsea su veredicto JSON.

    Devuelve el dict del veredicto o None si la llamada falla.
    """
    try:
        # Importación diferida: el cliente solo se necesita si hay api_key.
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": QA_JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Diff de los tests a evaluar:\n\n{test_diff}",
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001 - registramos cualquier fallo del LLM.
        print(f"::warning::Falló la evaluación de tests con el LLM: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Publicación de resultados en el Pull Request
# --------------------------------------------------------------------------- #

def build_comment_body(result: AnalysisResult) -> str:
    """Construye el cuerpo Markdown del comentario para el PR."""
    if not result.has_any:
        return (
            "## 🤖 AI Hallucination Detector\n\n"
            "✅ No se detectaron alucinaciones, código desactualizado "
            "ni tests tautológicos. ¡Buen trabajo!"
        )

    lines: list[str] = ["## 🤖 AI Hallucination Detector\n"]
    lines.append(
        f"Se encontraron **{len(result.findings)}** posibles problemas:\n"
    )
    for finding in result.findings:
        location = f" (`{finding.location}`)" if finding.location else ""
        lines.append(f"### {finding.severity.value} — {finding.title}{location}")
        lines.append(finding.detail)
        lines.append("")  # Línea en blanco entre hallazgos.
    return "\n".join(lines)


def publish_comment(pull_request: PullRequest, body: str) -> None:
    """Publica (o intenta publicar) el comentario de resultados en el PR."""
    try:
        pull_request.create_issue_comment(body)
        print("::notice::Comentario publicado en el PR.")
    except GithubException as exc:
        print(f"::error::No se pudo publicar el comentario en el PR: {exc}")


# --------------------------------------------------------------------------- #
# Orquestación principal
# --------------------------------------------------------------------------- #

def main() -> None:
    """Punto de entrada: orquesta la carga del PR y los tres validadores."""
    token = get_required_env("INPUT_GITHUB_TOKEN")
    repository_name = get_required_env("GITHUB_REPOSITORY")
    llm_api_key = os.environ.get("INPUT_LLM_API_KEY") or None
    fail_on_warning = os.environ.get("INPUT_FAIL_ON_WARNING", "false").lower() == "true"

    # 1. Conexión con la API de GitHub y carga del PR.
    event = load_event_payload()
    pr_number = extract_pr_number(event)

    github = Github(token)
    try:
        repo = github.get_repo(repository_name)
        pull_request = repo.get_pull(pr_number)
    except GithubException as exc:
        print(f"::error::No se pudo cargar el PR #{pr_number}: {exc}")
        sys.exit(1)

    print(f"::notice::Analizando PR #{pr_number} de {repository_name}...")

    # 2. Obtención de archivos modificados y construcción del diff agregado.
    files: list[File] = list(pull_request.get_files())
    full_diff = "\n".join(f.patch for f in files if f.patch)

    # 3. Ejecución de los tres validadores.
    result = AnalysisResult()
    check_ghost_dependencies(files, result)
    check_outdated_code(full_diff, result)
    evaluate_tautological_tests(files, llm_api_key, result)

    # 4. Publicación del comentario en el PR.
    publish_comment(pull_request, build_comment_body(result))

    # 5. Resumen en los logs y código de salida.
    for finding in result.findings:
        print(f"::warning::[{finding.severity.name}] {finding.title}: {finding.detail}")

    if result.has_critical or (fail_on_warning and result.has_any):
        print("::error::Se detectaron problemas que bloquean el PR.")
        sys.exit(1)

    print("::notice::Análisis completado sin bloqueos.")
    sys.exit(0)


if __name__ == "__main__":
    main()
