terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "project_id" {
  description = "GCP project ID in which to create the service account."
  type        = string
}

variable "region" {
  description = "Default GCP region (used for provider configuration)."
  type        = string
  default     = "us-central1"
}

# ── Provider ───────────────────────────────────────────────────────────────────

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable Calendar API ────────────────────────────────────────────────────────

resource "google_project_service" "calendar_api" {
  service = "calendar-json.googleapis.com"

  # Keep the API enabled even if this Terraform module is destroyed,
  # so other resources that depend on it are not broken.
  disable_on_destroy = false
}

# ── Service account ────────────────────────────────────────────────────────────

resource "google_service_account" "daily_briefing" {
  account_id   = "daily-briefing-agent"
  display_name = "Daily Briefing Agent"
  description  = "Read-only Google Calendar access for the daily briefing ADK agent."

  depends_on = [google_project_service.calendar_api]
}

# ── Service account key ────────────────────────────────────────────────────────
# The key is exported as base64-encoded JSON (google provider default format).
# Store the output value in Infisical as `google-calendar-service-account-json`.

resource "google_service_account_key" "daily_briefing" {
  service_account_id = google_service_account.daily_briefing.name
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "service_account_email" {
  description = "Share your private Google Calendar with this address (Viewer role)."
  value       = google_service_account.daily_briefing.email
}

output "service_account_key_base64" {
  description = <<-EOT
    Base64-encoded service account JSON key.
    Retrieve with: terraform output -raw service_account_key_base64
    Store this value in Infisical as: google-calendar-service-account-json
    Map to env var: GOOGLE_SERVICE_ACCOUNT_JSON_BASE64
  EOT
  value     = google_service_account_key.daily_briefing.private_key
  sensitive = true
}
