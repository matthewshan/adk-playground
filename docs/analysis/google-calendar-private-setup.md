# Google Calendar — Private Calendar Setup Guide

This guide walks through creating a GCP project and granting the daily briefing agent read-only access to a private Google Calendar using a service account. Terraform provisions everything; one manual step shares the calendar with the service account email.

---

## Architecture overview

```
Terraform (matthewshan/cloud-infrastructure)  Google Cloud (project: adk-agents-496905)
  └─ google_service_account  →    daily-briefing-agent@adk-agents-496905.iam.gserviceaccount.com
  └─ google_service_account_key → JSON key (base64) → stored in .env locally

Google Calendar (manual step)
  └─ Share calendar with service account email (Viewer)

daily_briefing/tools.py
  └─ Loads key from GOOGLE_SERVICE_ACCOUNT_JSON_BASE64
  └─ Authenticates via google-auth library
  └─ Calls Calendar API v3 → list today's events
```

The agent never asks for user consent at runtime — the service account is trusted directly by the calendar.

> **Infrastructure repo:** The Terraform module that manages the service account lives in
> [`matthewshan/cloud-infrastructure`](https://github.com/matthewshan/cloud-infrastructure)
> under `terraform-adk-agents/`. State is managed by HCP Terraform.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Google account | Any personal Google account works |
| Access to `matthewshan/cloud-infrastructure` | Terraform changes go here, not in this repo |
| HCP Terraform access | Runs are triggered automatically via VCS on push to `main` |

---

## Step 1 — Note the service account details

The GCP project and service account are already provisioned by Terraform in
[`matthewshan/cloud-infrastructure`](https://github.com/matthewshan/cloud-infrastructure).
No local Terraform run is needed.

| Value | Details |
|---|---|
| GCP project | `adk-agents-496905` |
| Service account email | `daily-briefing-agent@adk-agents-496905.iam.gserviceaccount.com` |

To retrieve the base64-encoded JSON key, go to the HCP Terraform workspace
`terraform-adk-agents` → **Outputs** → `service_account_key_base64` → **Reveal**.
Copy the value and add it to `.env` as `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.

> If you need to re-provision or rotate the key, make changes in
> `matthewshan/cloud-infrastructure/terraform-adk-agents/` and merge to `main` —
> HCP Terraform will plan and apply automatically.

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

1. In `matthewshan/cloud-infrastructure/terraform-adk-agents/main.tf`, taint the key
   resource or use `terraform taint` locally (speculative plan only — trigger a destroy/recreate
   via the HCP Terraform UI: **Actions → Start new run → Destroy and recreate**).
2. After apply, retrieve the new key from the HCP Terraform workspace:
   **Outputs** → `service_account_key_base64` → **Reveal**.
3. Update `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` in `.env` and in any deployed Kubernetes Secrets.
