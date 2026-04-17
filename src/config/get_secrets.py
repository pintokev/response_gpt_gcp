import os
from functools import lru_cache
from dotenv import load_dotenv
from google.cloud import secretmanager

load_dotenv()

client = secretmanager.SecretManagerServiceClient()


@lru_cache(maxsize=128)
def get_gcp_secret(secret_name: str, version: str = "latest") -> str:
    project_id = os.environ["GCP_PROJECT_ID"]
    name = f"projects/{project_id}/secrets/{secret_name}/versions/{version}"

    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def get_config(env_var_name: str, gcp_secret_name: str | None = None, required: bool = True) -> str | None:
    value = os.getenv(env_var_name)
    if value is not None and value != "":
        return value

    if gcp_secret_name:
        try:
            return get_gcp_secret(gcp_secret_name)
        except Exception as e:
            if required:
                raise RuntimeError(
                    f"Impossible de récupérer '{env_var_name}' depuis .env/env et GCP Secret Manager ('{gcp_secret_name}')"
                ) from e

    if required:
        raise RuntimeError(
            f"Configuration manquante: '{env_var_name}'"
        )

    return None