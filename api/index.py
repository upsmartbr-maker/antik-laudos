import sys
import os

# Adiciona a raiz do projeto ao sys.path para garantir que o FastAPI carregue main.py e serviços
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from main import app

# Exporta app para o runtime serverless da Vercel
__all__ = ["app"]
