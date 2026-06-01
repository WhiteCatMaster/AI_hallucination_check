# 🕵️‍♂️ AI Hallucination Detector 🤖

> **Caza alucinaciones de IA en tus Pull Requests antes de que lleguen a producción.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Marketplace](https://img.shields.io/badge/GitHub%20Marketplace-AI%20Hallucination%20Detector-2ea44f?logo=github)](https://github.com/marketplace)
[![Made with Python](https://img.shields.io/badge/Made%20with-Python%203.11-blue?logo=python&logoColor=white)](https://www.python.org/)

---

Copilot, ChatGPT y Claude escriben código increíble... hasta que **se lo inventan**. 🪄
Importan paquetes que no existen, usan APIs que llevan años deprecadas y escriben
"tests" que solo pasan porque repiten el mismo bug que deberían cazar. Esos errores
son sutiles, pasan el code review humano y revientan en CI (o peor, en producción).

**AI Hallucination Detector** se engancha a tus Pull Requests y actúa como un revisor
escéptico que nunca duerme. Detecta los tres patrones más peligrosos del código
generado por IA y deja un comentario claro en el PR explicando exactamente qué falla.

## ✨ ¿Qué detecta?

- 👻 **Dependencias fantasma** — Paquetes alucinados que no existen en PyPI o npm (404).
- 🕰️ **Código obsoleto (knowledge cutoff)** — APIs deprecadas que el modelo aprendió hace años (React, Pandas, scikit-learn...).
- 🎭 **Tests tautológicos** — Tests complacientes que pasan sin probar nada real, evaluados por un LLM que actúa como "Juez de QA" estricto.

## 🚀 Quickstart

Copia y pega este workflow en `.github/workflows/hallucination-check.yml` y listo:

```yaml
name: AI Hallucination Detector

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write   # Necesario para comentar en el PR

jobs:
  detect-hallucinations:
    runs-on: ubuntu-latest
    steps:
      - uses: tu-usuario/ai-hallucination-detector@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          # Opcional: activa la detección de tests tautológicos
          llm_api_key: ${{ secrets.OPENAI_API_KEY }}
```

> 💡 El `GITHUB_TOKEN` lo proporciona GitHub automáticamente. La `llm_api_key`
> solo es necesaria si quieres activar el análisis de tests tautológicos.

## ⚙️ Inputs

| Input | Obligatorio | Por defecto | Descripción |
| :--- | :---: | :---: | :--- |
| `github_token` | ✅ Sí | — | Token para leer el PR y publicar comentarios. Normalmente `${{ secrets.GITHUB_TOKEN }}`. |
| `llm_api_key` | ❌ No | `''` | Clave de API de OpenAI para evaluar tests tautológicos. Si se omite, ese análisis se salta. |
| `fail_on_warning` | ❌ No | `'false'` | Si es `'true'`, la Action falla también ante hallazgos leves (no solo los críticos). |

## 🧠 ¿Cómo funciona?

1. Se dispara en cada Pull Request y lee los archivos modificados vía la API de GitHub.
2. Verifica cada nueva dependencia contra los registros de **PyPI** y **npm**.
3. Escanea el diff buscando firmas de APIs deprecadas (reglas de bajo ratio de falsos positivos).
4. Envía el diff de los tests a un LLM con un *system prompt* de Juez de QA que responde en JSON estricto.
5. Publica un comentario resumen en el PR y **falla el check** si encuentra alucinaciones graves.

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Si conoces una API deprecada que deberíamos
detectar, abre un PR añadiendo una regla en `DEPRECATED_API_RULES` dentro de `main.py`.
Issues, ideas y feedback son siempre bienvenidos. ⭐ Si te resulta útil, deja una estrella.

## 📄 Licencia

Distribuido bajo la **Licencia MIT**. Consulta el archivo [`LICENSE`](./LICENSE) para más detalles.
