terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # No backend block — state is stored locally in terraform.tfstate.
  # Run `terraform init` and keep terraform.tfstate out of source control.
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "project_id" {
  description = "ID of the existing GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "Default GCP region."
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
  project = var.project_id
  service = "calendar-json.googleapis.com"

  # Keep the API enabled even if this Terraform module is destroyed.
  disable_on_destroy = false
}

# ── Service account ────────────────────────────────────────────────────────────

resource "google_service_account" "daily_briefing" {
  project      = var.project_id
  account_id   = "daily-briefing-agent"
  display_name = "Daily Briefing Agent"
  description  = "Read-only Google Calendar access for the daily briefing ADK agent."

  depends_on = [google_project_service.calendar_api]
}

# ── Service account key ────────────────────────────────────────────────────────
# Exported as base64-encoded JSON (google provider default format).
# Retrieve with: terraform output -raw service_account_key_base64

resource "google_service_account_key" "daily_briefing" {
  service_account_id = google_service_account.daily_briefing.name
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "service_account_email" {
  description = "Share your private Google Calendar with this address (Viewer role)."
  value       = google_service_account.daily_briefing.email
}

output "service_account_key_base64" {
  description = "Base64-encoded service account JSON key. Retrieve with: terraform output -raw service_account_key_base64"
  value     = google_service_account_key.daily_briefing.private_key
  sensitive = true
}
