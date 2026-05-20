# Google Calendar — Private Calendar Setup Guide

This guide walks through creating a GCP project and granting the daily briefing agent read-only access to a private Google Calendar using a service account. Terraform provisions everything; one manual step shares the calendar with the service account email.

---

## Architecture overview

```
Terraform                         Google Cloud
  └─ google_project           →    New GCP project
  └─ google_service_account  →    daily-briefing-agent@<project>.iam.gserviceaccount.com
  └─ google_service_account_key → JSON key (base64) → stored in .env locally

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
| Google account | Any personal Google account works |
| GCP billing account | Required to enable APIs. Go to [https://console.cloud.google.com/billing](https://console.cloud.google.com/billing), create one if needed. Free tier / $0 credit card on file is sufficient. |
| Terraform ≥ 1.6 | [Install guide](https://developer.hashicorp.com/terraform/install) |
| `gcloud` CLI | Run `gcloud auth application-default login` to authenticate Terraform |

---

## Step 1 — Find your billing account ID

1. Go to [https://console.cloud.google.com/billing](https://console.cloud.google.com/billing).
2. Click your billing account.
3. The **Billing account ID** is shown in the format `XXXXXX-XXXXXX-XXXXXX`. Copy it.

---

## Step 2 — Run Terraform

The Terraform configuration lives in `terraform/google-calendar-sa/`. State is stored locally in `terraform.tfstate` — keep that file out of source control (it's already in `.gitignore`).

```bash
cd terraform/google-calendar-sa

# Authenticate with Google
gcloud auth application-default login

# Initialise providers
terraform init

# Preview what will be created (a new project, Calendar API enablement, service account + key)
terraform plan \
  -var="project_id=daily-briefing-<your-handle>" \
  -var="billing_account=XXXXXX-XXXXXX-XXXXXX"

# Apply
terraform apply \
  -var="project_id=daily-briefing-<your-handle>" \
  -var="billing_account=XXXXXX-XXXXXX-XXXXXX"
```

> `project_id` must be globally unique across all of Google Cloud, lowercase letters/numbers/hyphens, max 30 characters. Example: `daily-briefing-matthewshan`.

After `apply` completes, note the two outputs:

| Output | What to do with it |
|---|---|
| `service_account_email` | Copy this — you will paste it into Google Calendar |
| `service_account_key_base64` | Run `terraform output -raw service_account_key_base64` and save to `.env` |

> The key is marked `sensitive` in Terraform state. Run the command above to retrieve it — it will not appear in plan/apply output.

---

## Step 3 — Share the calendar with the service account

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

## Step 4 — Get your Calendar ID

1. In Google Calendar, go to **Settings** for the shared calendar.
2. Scroll to **Integrate calendar**.
3. Copy the **Calendar ID** — it looks like:
   - `primary` (for your main calendar), or
   - `abc123xyz@group.calendar.google.com` (for secondary/shared calendars)

---

## Step 5 — Add secrets to `.env` and test locally

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

# Terraform destroys the old key resource and creates a new one
terraform apply \
  -var="project_id=<your-project-id>" \
  -var="billing_account=XXXXXX-XXXXXX-XXXXXX"

# Retrieve the new key and update .env (and k8s Secret when deploying)
terraform output -raw service_account_key_base64
```
