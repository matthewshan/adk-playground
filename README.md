# Minimal ADK + Ollama Test

This project is a deliberately small Python ADK smoke test wired to a local Ollama server.

It is optimized for the lightest possible local model first, not for quality. The default model is `smollm2:135m`.

On this machine, `smollm2:135m` proved that the stack is connected, while `qwen2.5:0.5b` gave noticeably better short-chat behavior.

## What is here

- `minimal_ollama_adk/agent.py`: the root ADK agent
- `minimal_ollama_adk/main.py`: a programmatic smoke test using `InMemoryRunner`
- `docs/context-engineering.md`: notes on how to keep prompts and context small for weak local models
- `requirements.txt`: Python dependencies for a non-venv install

## Install

### Install Ollama

This repo is set up to work with a workspace-local Ollama binary so you do not need a root install.

Rootless local install:

```bash
mkdir -p .tools/ollama
curl -L https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst -o .tools/ollama/ollama-linux-amd64.tar.zst
tar --zstd -xf .tools/ollama/ollama-linux-amd64.tar.zst -C .tools/ollama
./.tools/ollama/bin/ollama --version
```

If you prefer a system install instead:

- Arch / CachyOS: `sudo pacman -S ollama`
- Other Linux distributions: use the package manager or install instructions from the Ollama docs

### Install Python dependencies

Install the Python dependencies with your system Python:

```bash
python3 -m pip install --user -r requirements.txt
```

If `adk` is not on your shell `PATH` afterwards, add:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Note: on Arch-like systems, you may need to add `--break-system-packages` because the system Python environment is externally managed.

This project already includes a local `.env` file. The Python entrypoint loads it automatically.

## Run

Start the local Ollama server from this workspace:

```bash
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$PWD/.ollama/models"
./.tools/ollama/bin/ollama serve
```

In another shell, point ADK to the server:

```bash
export OLLAMA_API_BASE=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5:0.5b
```

If you want the more usable small-model path immediately, use:

```bash
export OLLAMA_MODEL=qwen2.5:0.5b
```

Pull the smallest model:

```bash
./.tools/ollama/bin/ollama pull smollm2:135m
```

## Smoke tests

Direct Ollama test:

```bash
./.tools/ollama/bin/ollama run smollm2:135m "Reply with exactly: ollama is working"
```

Programmatic ADK test:

```bash
python -m minimal_ollama_adk.main "Reply with exactly: adk is working"
```

Interactive prompt mode:

```bash
python -m minimal_ollama_adk.main
```

Type your own prompts at `prompt>` and use `exit` or `quit` to stop.

ADK CLI test:

```bash
export OLLAMA_API_BASE=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5:0.5b
adk run minimal_ollama_adk "Say hello in one short sentence."
```

## Notes

- `smollm2:135m` is tiny and useful mainly for proving the plumbing works.
- If output quality is too weak, switch to `qwen2.5:0.5b` by changing `OLLAMA_MODEL`.
- On this machine, `qwen2.5:0.5b` behaved better for short chat prompts, but tiny local models still did not follow exact-string prompts perfectly.
- This repo keeps the Ollama binary and model cache local to the workspace to avoid needing a root install.
