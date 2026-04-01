output "cloud_run_url" {
  value       = google_cloud_run_v2_service.app.uri
  description = "URL Cloud Run du service"
}

output "service_account_email" {
  value       = google_service_account.cloud_run_sa.email
  description = "Service account runtime Cloud Run"
}

output "artifact_registry_repository" {
  value       = google_artifact_registry_repository.docker_repo.name
  description = "Nom complet du repository Artifact Registry"
}

output "token_gpt_secret_name" {
  value       = google_secret_manager_secret.token_gpt.secret_id
  description = "Nom du secret Secret Manager"
}
