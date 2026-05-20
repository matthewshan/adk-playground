# TODO: This is a WIP - I have yet to set up google service accounts at this time. I may want to also consider setting up the gemini API key with terraform if it is possible.

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
  description = "Desired GCP project ID (globally unique, lowercase letters/numbers/hyphens, max 30 chars)."
  type        = string
}

variable "project_name" {
  description = "Human-readable display name for the GCP project."
  type        = string
  default     = "Daily Briefing"
}

variable "billing_account" {
  description = "GCP billing account ID to link to the new project (format: XXXXXX-XXXXXX-XXXXXX). Find yours at https://console.cloud.google.com/billing."
  type        = string
}

variable "region" {
  description = "Default GCP region."
  type        = string
  default     = "us-central1"
}

# ── Provider ───────────────────────────────────────────────────────────────────
# No project set here — resources reference the created project directly.

provider "google" {
  region = var.region
}

# ── GCP project ────────────────────────────────────────────────────────────────

resource "google_project" "daily_briefing" {
  project_id      = var.project_id
  name            = var.project_name
  billing_account = var.billing_account
}

# ── Enable Calendar API ────────────────────────────────────────────────────────

resource "google_project_service" "calendar_api" {
  project = google_project.daily_briefing.project_id
  service = "calendar-json.googleapis.com"

  # Keep the API enabled even if this Terraform module is destroyed.
  disable_on_destroy = false

  depends_on = [google_project.daily_briefing]
}

# ── Service account ────────────────────────────────────────────────────────────

resource "google_service_account" "daily_briefing" {
  project      = google_project.daily_briefing.project_id
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
