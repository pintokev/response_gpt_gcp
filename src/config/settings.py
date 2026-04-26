import os
from src.config.get_secrets import get_config

DATA_DIR = os.environ.get("DATA_DIR", "data/")
PORT = os.environ.get("PORT", "8080")
PROXY = os.environ.get("PROXY", None)
INTERNAL_API_TOKEN = get_config("INTERNAL_API_TOKEN", required=False)

tokenGPT = get_config("tokenGPT", "tokenGPT-prd")
