# Google Calendar — Private Calendar Setup Guide

This guide walks through granting the daily briefing agent read-only access to a private Google Calendar using a GCP service account. Terraform provisions the service account and key; one manual step shares the calendar with the service account email.

---

## Architecture overview

```
Terraform                         Google Cloud
  └─ google_service_account  →    daily-briefing-agent@<project>.iam.gserviceaccount.com
  └─ google_service_account_key → JSON key (base64) → stored in Infisical

Google Calendar (manual step)
  └─ Share calendar with service account email (Viewer)

daily_briefing/tools.py
  └─ Loads key from GOOGLE_SERVICE_ACCOUNT_JSON_BASE64
  └─ Authenticates via google-auth library
  └─ Calls Calendar API v3 → list today's events
```

The agent never asks for user consent at runtime — the service account is trusted directly by the calendar.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| GCP project | Any project works; free tier is fine |
| Terraform ≥ 1.6 | [Install guide](https://developer.hashicorp.com/terraform/install) |
| `gcloud` CLI authenticated | `gcloud auth application-default login` |
| Google Calendar API enabled | Terraform enables it automatically |

---

## Step 1 — Run Terraform

The Terraform configuration lives in `terraform/google-calendar-sa/`.

```bash
cd terraform/google-calendar-sa

# Initialise providers
terraform init

# Preview what will be created
terraform plan -var="project_id=<your-gcp-project-id>"

# Apply
terraform apply -var="project_id=<your-gcp-project-id>"
```

After `apply` completes, note the two outputs:

| Output | What to do with it |
|---|---|
| `service_account_email` | Copy this — you will paste it into Google Calendar |
| `service_account_key_base64` | Run `terraform output -raw service_account_key_base64` and store in Infisical |

> The key is marked `sensitive` in Terraform state. Run the command above to retrieve it — it will not appear in plan/apply output.

---

## Step 2 — Share the calendar with the service account

The Calendar API does not use IAM for per-calendar access. You share the calendar exactly as you would share it with another person.

1. Open [Google Calendar](https://calendar.google.com) in a browser.
2. In the left sidebar, hover over the calendar you want to use, click the three-dot menu → **Settings and sharing**.
3. Scroll to **Share with specific people or groups**.
4. Click **+ Add people**, paste the service account email from Step 1:
   ```
   daily-briefing-agent@<your-gcp-project-id>.iam.gserviceaccount.com
   ```
5. Set permissions to **See all event details** (read-only).
6. Click **Send**.

> Google sends a sharing invite to the service account address, but service accounts cannot accept invites. The share takes effect immediately without acceptance — no action needed.

---

## Step 3 — Get your Calendar ID

1. In Google Calendar, go to **Settings** for the shared calendar.
2. Scroll to **Integrate calendar**.
3. Copy the **Calendar ID** — it looks like:
   - `primary` (for your main calendar), or
   - `abc123xyz@group.calendar.google.com` (for secondary/shared calendars)

---

## Step 4 — Store secrets in Infisical

Store the following two secrets in your Infisical project (same project used by the k8s ExternalSecret):

| Infisical key | Value |
|---|---|
| `google-calendar-service-account-json` | Output of `terraform output -raw service_account_key_base64` |
| `google-calendar-id` | Calendar ID from Step 3 |

These map to the environment variables `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` and `GOOGLE_CALENDAR_ID` via the `external-secret.yaml` in the k8s deployment.

---

## Step 5 — Test locally

Add the values to your local `.env`:

```dotenv
GOOGLE_CALENDAR_ID=abc123xyz@group.calendar.google.com
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=<paste terraform output here>
```

Then run the calendar tool in isolation:

```bash
python - <<'EOF'
import os
from dotenv import load_dotenv
load_dotenv()
from daily_briefing.tools import get_calendar_events
print(get_calendar_events())
EOF
```

Expected output examples:
- `• Team standup @ 9:00 AM` (events found)
- `Nothing scheduled` (no events today — still means auth worked)

If you see `Calendar unavailable: GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 not set.`, the env var is not loaded.

If you see a `403 Forbidden` from the Google API, the calendar has not been shared with the service account yet (re-check Step 2).

---

## Rotating the service account key

Service account keys should be rotated periodically. To rotate:

```bash
cd terraform/google-calendar-sa

# Terraform will destroy the old key resource and create a new one
terraform apply -var="project_id=<your-gcp-project-id>"

# Retrieve new key and update Infisical
terraform output -raw service_account_key_base64
```

After updating Infisical, the next ExternalSecret sync (or a manual `kubectl annotate externalsecret ...`) will push the new value to the k8s Secret.

---

## Terraform resource summary

| Resource | Purpose |
|---|---|
| `google_project_service.calendar_api` | Enables the Google Calendar API on your project |
| `google_service_account.daily_briefing` | Creates the `daily-briefing-agent` service account |
| `google_service_account_key.daily_briefing` | Generates and exports the JSON key |
