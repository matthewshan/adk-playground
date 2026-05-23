# ADK Playground

This repository is a Python / Google ADK playground with two projects:

- `minimal_ollama_adk/`: a tiny local ADK smoke test backed by Ollama
- `daily_briefing/`: a morning digest agent that gathers weather, news, sports, and calendar data, then sends the briefing to Discord

## Repository layout

```text
minimal_ollama_adk/   Minimal local Ollama example
daily_briefing/       Main daily briefing agent
docs/                 Architecture, setup, prompt, and deployment notes
terraform/            Google Calendar service-account provisioning
requirements.txt      Shared Python dependencies
```

## Install

Install Python dependencies:

```bash
python3 -m pip install --user -r requirements.txt
```

If `adk` is not on your `PATH` afterwards:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

On Arch-like systems you may also need `--break-system-packages`.

## Project 1: `minimal_ollama_adk`

This is the smallest local smoke test in the repo. It is optimized for proving the stack is wired up, not for output quality.

### Install Ollama locally

The repo supports a workspace-local Ollama install so you do not need a root install:

```bash
mkdir -p .tools/ollama
curl -L https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst -o .tools/ollama/ollama-linux-amd64.tar.zst
tar --zstd -xf .tools/ollama/ollama-linux-amd64.tar.zst -C .tools/ollama
./.tools/ollama/bin/ollama --version
```

### Run the local smoke test

Start Ollama:

```bash
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$PWD/.ollama/models"
./.tools/ollama/bin/ollama serve
```

In another shell:

```bash
export OLLAMA_API_BASE=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5:0.5b
```

Pull a small model:

```bash
./.tools/ollama/bin/ollama pull smollm2:135m
```

Smoke test the Ollama server directly:

```bash
./.tools/ollama/bin/ollama run smollm2:135m "Reply with exactly: ollama is working"
```

Run the ADK example:

```bash
python3 -m minimal_ollama_adk.main "Reply with exactly: adk is working"
```

Interactive mode:

```bash
python3 -m minimal_ollama_adk.main
```

## Project 2: `daily_briefing`

The daily briefing agent supports two model backends:

- `BACKEND=gemini` (default)
- `BACKEND=ollama`

Environment variables are loaded from `/home/runner/work/adk-playground/adk-playground/daily_briefing/.env`, not from the repo root.

### Configure environment

Copy the example file and fill in the values you need:

```bash
cp daily_briefing/.env.example daily_briefing/.env
```

Key variables:

- `BACKEND`
- `GEMINI_API_KEY` and optional `GEMINI_MODEL`
- `OLLAMA_API_BASE` and `OLLAMA_MODEL` when using Ollama
- `GNEWS_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`

### Run the daily briefing agent

```bash
python3 -m daily_briefing.main
```

### Run local smoke tests

Tool smoke tests:

```bash
python3 daily_briefing/test_apis.py
```

Agent test runner that prints the digest locally instead of posting to Discord:

```bash
python3 daily_briefing/test_agent.py
```

### Docker

Build the daily briefing container:

```bash
docker build -t daily-briefing -f daily_briefing/Dockerfile .
```

## Google Calendar service account (Terraform)

The private Google Calendar integration uses Terraform in `terraform/modules/google-calendar-sa/`.

```bash
cd terraform/modules/google-calendar-sa
gcloud auth application-default login
terraform init
terraform plan -var="project_id=<your-project-id>"
terraform apply -var="project_id=<your-project-id>"
terraform output -raw service_account_key_base64
```

After `apply`, share your Google Calendar with the `service_account_email` output.

## Docs

- [`docs/architecture/daily-briefing-design.md`](docs/architecture/daily-briefing-design.md)
- [`docs/analysis/api-setup-guide.md`](docs/analysis/api-setup-guide.md)
- [`docs/analysis/google-calendar-private-setup.md`](docs/analysis/google-calendar-private-setup.md)
- [`docs/plans/plan-adk-k8s-deployment.md`](docs/plans/plan-adk-k8s-deployment.md)
- [`docs/context-engineering.md`](docs/context-engineering.md)

## Notes

- `smollm2:135m` is useful mainly for proving the minimal Ollama path works.
- `qwen2.5:0.5b` produced better short-chat behavior in earlier local testing.
- The repo keeps Ollama binaries and model cache local to the workspace to avoid requiring a root install.
