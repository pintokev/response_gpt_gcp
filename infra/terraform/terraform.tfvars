project_id                      = "reponse-gpt"
region                          = "europe-west1"
artifact_registry_repository_id = "response-gpt"
cloud_run_service_name          = "response-gpt"
service_account_id              = "gpt-prod"

container_image = "europe-west1-docker.pkg.dev/reponse-gpt/response-gpt/response-gpt:latest"

authorized_members = [
  "user:toi@tondomaine.com"
]
