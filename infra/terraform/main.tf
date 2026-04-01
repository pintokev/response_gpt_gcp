data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iap" {
  project            = var.project_id
  service            = "iap.googleapis.com"
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "docker_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  description   = "Docker repository for response_gpt"
  format        = "DOCKER"

  depends_on = [
    google_project_service.artifactregistry
  ]
}

resource "google_service_account" "cloud_run_sa" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "Cloud Run runtime service account"
}

resource "google_secret_manager_secret" "token_gpt" {
  project   = var.project_id
  secret_id = var.token_gpt_secret_id

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.secretmanager
  ]
}

resource "google_secret_manager_secret_iam_member" "token_gpt_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.token_gpt.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_artifact_registry_repository_iam_member" "cloud_run_repo_reader" {
  project    = var.project_id
  location   = google_artifact_registry_repository.docker_repo.location
  repository = google_artifact_registry_repository.docker_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# IAP a besoin que son service agent puisse invoquer Cloud Run
resource "google_cloud_run_service_iam_member" "iap_invoker" {
  service  = google_cloud_run_v2_service.app.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

resource "google_cloud_run_v2_service" "app" {
  name                = var.cloud_run_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account = google_service_account.cloud_run_sa.email
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name = "tokenGPT"
        value_source {
          secret_key_ref {
            secret  = "projects/${var.project_id}/secrets/${google_secret_manager_secret.token_gpt.secret_id}"
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_project_service.iap,
    google_artifact_registry_repository_iam_member.cloud_run_repo_reader,
    google_secret_manager_secret_iam_member.token_gpt_accessor
  ]
}

# Surtout pas de allUsers ici : service non public
resource "google_iap_web_cloud_run_service_iam_member" "authorized" {
  for_each = toset(var.authorized_members)

  project  = var.project_id
  location = var.region
  service  = google_cloud_run_v2_service.app.name
  role     = "roles/iap.httpsResourceAccessor"
  member   = each.value
}
