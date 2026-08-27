import sys
from pathlib import Path

# Vercel ejecuta este archivo como funcion aislada; nos aseguramos de que la raiz
# del proyecto (donde viven app/, templates/, static/) este en el path de Python.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

# Vercel (@vercel/python) detecta automaticamente esta variable ASGI y la sirve.
