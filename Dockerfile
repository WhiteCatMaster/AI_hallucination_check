# Dockerfile
# Imagen de contenedor para la Action "ai-hallucination-detector".

# Imagen base ligera de Python.
FROM python:3.11-slim

# Buenas prácticas para Python en contenedores:
# - PYTHONUNBUFFERED: los logs salen inmediatamente (importante en Actions).
# - PYTHONDONTWRITEBYTECODE: evita generar archivos .pyc innecesarios.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Directorio de trabajo dentro del contenedor.
WORKDIR /app

# Copiamos primero las dependencias para aprovechar la caché de capas de Docker:
# si requirements.txt no cambia, no se reinstalan las dependencias.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copiamos el resto del código fuente de la Action.
COPY main.py /app/main.py

# Punto de entrada: ejecuta el script principal cuando arranca el contenedor.
ENTRYPOINT ["python", "/app/main.py"]
