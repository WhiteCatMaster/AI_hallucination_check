# 🤝 Guía de Contribución

¡Gracias por tu interés en mejorar **AI Hallucination Detector**! 🎉
Cada idea, issue y Pull Request ayuda a que más equipos atrapen alucinaciones de
IA antes de que lleguen a producción. Contribuir es fácil y siempre eres bienvenido.

## 🚀 Configurar el entorno local

Necesitas **Python 3.11+** y `git`.

```bash
# 1. Haz un fork y clónalo (sustituye TU-USUARIO)
git clone https://github.com/TU-USUARIO/ai-hallucination-detector.git
cd ai-hallucination-detector

# 2. Crea y activa un entorno virtual
python3 -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate

# 3. Instala las dependencias de desarrollo (runtime + pytest)
pip install -r requirements-dev.txt
```

> 💡 `requirements-dev.txt` incluye las dependencias de runtime y además `pytest`,
> así que con un solo comando tienes todo lo necesario para desarrollar y testear.

## ✅ Ejecutar los tests

Antes de enviar un Pull Request, asegúrate de que **todos los tests pasan**:

```bash
pytest -q
```

Los tests son rápidos y **no realizan llamadas de red reales** (las librerías
externas se sustituyen por stubs en `tests/conftest.py`). Si añades una nueva
funcionalidad, acompáñala de su test correspondiente. 🧪

## 🧭 Flujo de trabajo para un Pull Request

1. Crea una rama descriptiva: `git checkout -b feat/mi-mejora`.
2. Haz tus cambios y añade tests si aplica.
3. Verifica que la suite pasa con `pytest -q`.
4. Haz commit con un mensaje claro y abre el Pull Request contra `main`.

## 💡 Ideas fáciles para empezar

¿Buscas una primera contribución sencilla? Añade una nueva regla de API
deprecada en el diccionario `DEPRECATED_API_RULES` de [`main.py`](./main.py).
Usa firmas distintivas (p. ej. `ReactDOM.render`) para mantener bajo el ratio
de falsos positivos, e incluye un test en `tests/test_parsers.py`.

## 📜 Código de conducta

Sé amable y respetuoso. Queremos una comunidad acogedora para todos. 💛

¡Gracias por contribuir! ⭐
