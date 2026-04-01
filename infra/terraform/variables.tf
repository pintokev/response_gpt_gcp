variable "project_id" {
  type        = string
  description = "ID du projet GCP existant"
  default     = "reponse-gpt"
}

variable "region" {
  type        = string
  description = "Région GCP"
  default     = "europe-west1"
}

variable "artifact_registry_repository_id" {
  type        = string
  description = "Nom du repository Artifact Registry"
  default     = "response-gpt"
}

variable "cloud_run_service_name" {
  type        = string
  description = "Nom du service Cloud Run"
  default     = "response-gpt"
}

variable "service_account_id" {
  type        = string
  description = "Nom court du service account runtime"
  default     = "gpt-prod"
}

variable "container_image" {
  type        = string
  description = "Image complète Artifact Registry à déployer"
}

variable "token_gpt_secret_id" {
  type        = string
  description = "Nom du secret Secret Manager injecté dans tokenGPT"
  default     = "tokenGPT"
}

variable "authorized_members" {
  type        = list(string)
  description = "Liste des membres autorisés via IAP, ex: user:toi@gmail.com ou group:gpt-users@domaine.com"
  default     = []
}
