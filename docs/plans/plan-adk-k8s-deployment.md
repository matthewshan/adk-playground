# Plan: Deploy ADK Agent Service to k3s Homelab

Deploy the Google ADK Python agent from `adk-playground` as a long-running HTTP service inside the `matthewshan/k3s-homelab` cluster, managed by Argo CD, exposed at `adk.mattshan.dev` through the existing internal Gateway, and backed by a cloud LLM (Gemini API) with secrets stored in Infisical.

---

## Background and Goals

The `adk-playground` repo proves the ADK stack locally with Ollama. The goal here is to promote that agent to a first-class homelab service so it is:

- Always-on and reachable at `adk.mattshan.dev` from any Twingate-connected device
- Managed by Argo CD the same way n8n and Temporal are
- Backed by `gemini-2.0-flash` (or another Gemini model) via a Gemini API key held in Infisical instead of a local Ollama server
- Optionally wired to n8n workflows or Temporal workers in a later phase

The service will initially expose the ADK `adk web` HTTP interface (port 8000 by default) behind the internal gateway. No external (Cloudflare) exposure is planned for the first deployment.

---

## Phase 1 — Containerize the ADK Agent

### 1.1  Add a `Dockerfile` to `adk-playground`

Create a minimal, non-root `Dockerfile` in the repository root:

- Base image: `python:3.12-slim`
- Install `google-adk[extensions]` and `python-dotenv` from `requirements.txt`
- Copy `minimal_ollama_adk/` (rename or add a new agent module for the cloud-model version)
- Expose port `8000`
- Entrypoint: `adk web` so the ADK web server starts automatically
- Run as a non-root user (`uid=1000`)

### 1.2  Add a new agent module for the Gemini-backed agent

Add `gemini_adk/agent.py` alongside the existing `minimal_ollama_adk/` directory:

- Use `google-genai` model string `gemini-2.0-flash` (read from `GEMINI_MODEL` env var, default `gemini-2.0-flash`)
- Read `GOOGLE_API_KEY` from environment (injected by Kubernetes Secret)
- Keep the system instruction short and purposeful — this can evolve

### 1.3  Add a GitHub Actions workflow to build and push the image

Add `.github/workflows/docker-publish.yml` that:

- Triggers on push to `main`
- Builds the `Dockerfile`
- Pushes to `ghcr.io/matthewshan/adk-agent:<sha>` and `:latest`
- Uses `GITHUB_TOKEN` (no extra secrets needed for ghcr.io on a public repo)

This gives Argo CD a stable image reference to pull.

---

## Phase 2 — Kubernetes Manifests in k3s-homelab

Add a new service directory `services/adk-agent/` following the same file pattern as `services/n8n/`.

### 2.1  `services/adk-agent/ns.yaml`

Namespace `adk-agent`.

### 2.2  `services/adk-agent/external-secret.yaml`

An `ExternalSecret` (sync wave `-1`) that reads from the `infisical` `ClusterSecretStore` and creates `adk-agent-secret` in the `adk-agent` namespace. Keys to pull from Infisical:

| Infisical key | Kubernetes secret key |
|---|---|
| `google-api-key` | `GOOGLE_API_KEY` |

### 2.3  `services/adk-agent/deployment.yaml`

A `Deployment` with:

- `replicas: 1`
- Image: `ghcr.io/matthewshan/adk-agent:latest` (update to SHA-pinned tag after first build)
- Container port `8000`
- Env var `GOOGLE_API_KEY` from `secretKeyRef` → `adk-agent-secret`
- Env var `GEMINI_MODEL` with value `gemini-2.0-flash` (or your preferred model)
- `resources.requests`: `cpu: 50m`, `memory: 128Mi`
- `resources.limits`: `cpu: 500m`, `memory: 512Mi`
- No PVC needed for the stateless web UI
- `securityContext.runAsNonRoot: true`, `runAsUser: 1000`

### 2.4  `services/adk-agent/service.yaml`

A `ClusterIP` `Service` on port `8000` → container port `8000`.

### 2.5  `services/adk-agent/httproute.yaml`

An `HTTPRoute` matching host `adk.mattshan.dev`, referencing `gateway-internal` in the `gateway` namespace (same as n8n), forwarding to the `adk-agent` service on port `8000`.

### 2.6  `services/adk-agent/kustomization.yaml`

List all resources:

```
resources:
  - ns.yaml
  - external-secret.yaml
  - deployment.yaml
  - service.yaml
  - httproute.yaml
namespace: adk-agent
```

### 2.7  DNS and access

Add `adk.mattshan.dev` to AdGuard Home (or wherever `mattshan.dev` subdomains are added) pointing to the internal gateway IP `192.168.1.194`. The Twingate wildcard `*.mattshan.dev` resource already covers this hostname once DNS resolves.

---

## Phase 3 — Infisical Secret Bootstrap

Before the first Argo CD sync, add one key to Infisical:

| Key | Value |
|---|---|
| `google-api-key` | Your Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey) |

No `kubectl create secret` command is needed — External Secrets handles creation automatically once the key exists in Infisical and the `ExternalSecret` is applied.

---

## Phase 4 — Argo CD Sync

The existing `services/services-appset.yaml` `ApplicationSet` uses a `git` generator that discovers all `services/*` directories automatically. No changes to the ApplicationSet are needed. Once `services/adk-agent/` is committed to `main`, Argo CD will detect and sync the new application.

Sync order matters only for the ExternalSecret dependency on the `external-secrets` infrastructure component — that is already healthy in the cluster.

---

## Relevant Files

**In `adk-playground`:**

- `Dockerfile` — new, builds the containerized ADK web server
- `gemini_adk/agent.py` — new agent module using `gemini-2.0-flash`
- `gemini_adk/__init__.py` — new, empty init
- `.github/workflows/docker-publish.yml` — new CI/CD to publish image to ghcr.io
- `requirements.txt` — may need `google-generativeai` or check that `google-adk` already vendors the Gemini transport; add if needed

**In `k3s-homelab`:**

- `services/adk-agent/ns.yaml` — new
- `services/adk-agent/external-secret.yaml` — new (model: n8n's `external-secret.yaml`)
- `services/adk-agent/deployment.yaml` — new (model: n8n's `deployment.yaml`)
- `services/adk-agent/service.yaml` — new (model: n8n's `service.yaml`)
- `services/adk-agent/httproute.yaml` — new (model: n8n's `httproute.yaml`)
- `services/adk-agent/kustomization.yaml` — new
- `services/adk-agent/README.md` — new, document the Infisical key contract and model config

**Infrastructure (no changes required):**

- `services/services-appset.yaml` — unchanged, autodiscovers `services/adk-agent/`
- `infrastructure/networking/gateway/gw-internal.yaml` — unchanged
- `infrastructure/controllers/external-secrets/` — unchanged

---

## Verification Checklist

1. **Local container test** — `docker build -t adk-agent . && docker run -e GOOGLE_API_KEY=<key> -p 8000:8000 adk-agent` — confirm the ADK web UI loads at `http://localhost:8000`
2. **Image push** — confirm `ghcr.io/matthewshan/adk-agent:latest` is visible in GitHub Packages after the Actions workflow runs
3. **kustomize render** — `kubectl kustomize services/adk-agent` produces valid YAML with no missing refs
4. **ExternalSecret sync** — after Argo CD sync, verify `kubectl get externalsecret -n adk-agent` shows `Ready` and `kubectl get secret adk-agent-secret -n adk-agent` exists
5. **Pod health** — `kubectl get pods -n adk-agent` shows `Running`; check logs for ADK startup output
6. **HTTP smoke test** — from a Twingate-connected device, `curl https://adk.mattshan.dev` should return the ADK web UI HTML

---

## Decisions

- **Cloud model over local Ollama** — Ollama works for local smoke tests but a homelab container cannot reliably run a capable model with acceptable latency. A Gemini API key is cheaper per-call and produces far better agent behavior.
- **ADK web server** — `adk web` exposes a chat UI and API; this is the simplest first deployment. A headless `adk run` or custom FastAPI wrapper can replace it later if only a programmatic API is needed.
- **Internal gateway only** — No Cloudflare public exposure; Twingate VPN already covers remote access for authorized users.
- **No PVC** — The ADK web server is stateless. If session history or tool state persistence is needed later, add a PostgreSQL-backed session store (the cluster already has `infrastructure/storage/postgresql`).
- **ghcr.io** — Free for public repos, no extra registry secrets needed in the cluster for pull since the image is public.

---

## Further Considerations

1. **Agent capability expansion** — Once the base service is running, add ADK tools (e.g., `google_search`, a custom REST tool calling homelab APIs) by extending `gemini_adk/agent.py`. Each tool addition requires only a code change and image rebuild, no infra changes.
2. **n8n integration** — n8n can POST to the ADK API endpoint as an HTTP action node, enabling prompt-triggered automation from n8n workflows without any code changes.
3. **Temporal integration** — If durable, retriable ADK sessions are needed (e.g., long research workflows), wrap ADK calls in a Temporal activity. The `temporal-frontend` gRPC service is already reachable at `temporal-frontend.temporal.svc.cluster.local:7233`.
4. **Image tag pinning** — After initial validation, pin the deployment to a specific image SHA rather than `:latest` so Argo CD drift detection is meaningful.
5. **Resource tuning** — The initial resource requests are conservative. Monitor actual usage through Grafana after a week and adjust limits.
6. **Multi-agent expansion** — If multiple specialized agents are needed, each can be its own service directory (`services/adk-research-agent/`, `services/adk-code-agent/`) following the same pattern, or a single deployment can route to sub-agents using ADK's multi-agent orchestration features.
