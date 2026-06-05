# Deploying Anserini NFCorpus Benchmark Images

This runbook explains how to build and push the NFCorpus benchmark demo
containers to GitHub Container Registry (GHCR), then trigger Render deploys.

The benchmark outputs to deploy are:

- Main run, all models except the first GPT attempt:
  `20260604-195631-698d5dac`
- Successful GPT-only rerun:
  `20260604-202345-c2acbb5c`

The main run contains a failed GPT attempt caused by missing `openai-codex`
auth. The later GPT-only run is the successful GPT result.

## 1. Install Docker

Install Docker Desktop for macOS:

```sh
brew install --cask docker
```

Open Docker Desktop once from Applications and wait until it says Docker is
running.

Verify from a terminal:

```sh
docker --version
docker run --rm hello-world
```

If `docker` is still not found, quit and reopen the terminal.

## 2. Create A GHCR Token

Go to GitHub:

```text
Settings -> Developer settings -> Personal access tokens
```

Create a token with package publishing permissions:

```text
write:packages
read:packages
```

If using a classic token, include `repo` only if your org/account requires it
for private package access.

Keep this token private.

## 3. Create Render Services

Create one Render Web Service per model:

```text
pi-bench-anserini-nfcorpus-gpt
pi-bench-anserini-nfcorpus-claude
pi-bench-anserini-nfcorpus-gemini
pi-bench-anserini-nfcorpus-glm
pi-bench-anserini-nfcorpus-kimi
pi-bench-anserini-nfcorpus-minimax
```

Use Render image-backed web services, not Git-backed services.

Attach a GitHub Container Registry credential in Render so Render can pull
images from GHCR.

Images may be private. In that case Render needs a GHCR registry credential
with a token that can read packages. A read-only package token is sufficient
for Render pulls; keep the write-capable token local for Docker pushes.

For each service, copy its deploy hook URL. The deploy harness will call those
hooks after pushing images.

The deployed NFCorpus services used the following public URLs:

```text
https://pi-bench-anserini-nfcorpus-gpt.onrender.com
https://pi-bench-anserini-nfcorpus-claude.onrender.com
https://pi-bench-anserini-nfcorpus-gemini.onrender.com
https://pi-bench-anserini-nfcorpus-glm.onrender.com
https://pi-bench-anserini-nfcorpus-kimi.onrender.com
https://pi-bench-anserini-nfcorpus-minimax.onrender.com
```

For this run, moving the services from Render's starter/free-ish instance type
to `standard` made the Anserini-backed containers much more usable. The apps
can start on smaller instances, but Java startup, prebuilt index download, and
live search can be slow or flaky when memory/CPU are tight.

If you create or update services through the Render API, the registry
credential ID must be included in the image deploy details. For this account,
the GHCR credential was:

```text
pi-bench-ghcr-read-packages
```

Do not commit the Render API key or GHCR tokens.

## 4. Configure Local Deploy Secrets

Create `.codex-private/render.env` from the repo root:

```sh
mkdir -p .codex-private
cat > .codex-private/render.env <<'EOF'
GHCR_USERNAME=YOUR_GITHUB_USERNAME
GHCR_TOKEN=YOUR_GHCR_TOKEN
GHCR_OWNER=YOUR_GITHUB_ORG_OR_USERNAME

RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_GPT=https://api.render.com/deploy/srv-...
RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_CLAUDE=https://api.render.com/deploy/srv-...
RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_GEMINI=https://api.render.com/deploy/srv-...
RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_GLM=https://api.render.com/deploy/srv-...
RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_KIMI=https://api.render.com/deploy/srv-...
RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_MINIMAX=https://api.render.com/deploy/srv-...

RENDER_SERVICE_URL_ANSERINI_NFCORPUS_GPT=https://pi-bench-anserini-nfcorpus-gpt.onrender.com
RENDER_SERVICE_URL_ANSERINI_NFCORPUS_CLAUDE=https://pi-bench-anserini-nfcorpus-claude.onrender.com
RENDER_SERVICE_URL_ANSERINI_NFCORPUS_GEMINI=https://pi-bench-anserini-nfcorpus-gemini.onrender.com
RENDER_SERVICE_URL_ANSERINI_NFCORPUS_GLM=https://pi-bench-anserini-nfcorpus-glm.onrender.com
RENDER_SERVICE_URL_ANSERINI_NFCORPUS_KIMI=https://pi-bench-anserini-nfcorpus-kimi.onrender.com
RENDER_SERVICE_URL_ANSERINI_NFCORPUS_MINIMAX=https://pi-bench-anserini-nfcorpus-minimax.onrender.com
EOF
```

Do not put these values in `.env`. The benchmark runner passes `.env` to model
agents, but `.codex-private/render.env` is only read by the deploy harness.

If using the Render API directly, `.codex-private/.env` may also contain:

```text
RENDER_API_KEY=...
GHCR_READ_ONLY_TOKEN=...
```

Keep those in `.codex-private/` only.

## 5. Deploy The Main Run

From the repo root:

```sh
python -m bench.deploy \
  --run-id 20260604-195631-698d5dac \
  --provider render
```

This builds and pushes images like:

```text
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-claude:20260604-195631-698d5dac
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-gemini:20260604-195631-698d5dac
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-glm:20260604-195631-698d5dac
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-kimi:20260604-195631-698d5dac
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-minimax:20260604-195631-698d5dac
```

The harness may also build a GPT image for this run because it deploys every
workspace listed in the summary. That first run's GPT benchmark result failed,
so deploy the GPT rerun next.

## 6. Deploy The Successful GPT Rerun

```sh
python -m bench.deploy \
  --run-id 20260604-202345-c2acbb5c \
  --provider render
```

This pushes the successful GPT image:

```text
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-gpt:20260604-202345-c2acbb5c
```

It also triggers the GPT Render deploy hook with that image URL.

## 7. Check Deployment Artifacts

After each deploy command, inspect:

```sh
cat runs/20260604-195631-698d5dac/deployments.json
cat runs/20260604-202345-c2acbb5c/deployments.json
```

Each model also gets:

```text
runs/<run-id>/<model>/deployment.json
runs/<run-id>/<model>/deployment.stdout.log
runs/<run-id>/<model>/deployment.stderr.log
```

Successful records should have:

```json
"status": "completed"
```

If a deploy fails, check the model's `deployment.stderr.log` first.

## 8. Verify Live Services

For each Render service URL, check:

```sh
curl -s https://SERVICE_URL/health | jq .
```

The exact health path may differ by agent implementation. If `/health` fails,
open the service URL in a browser and check the workspace README for its health
endpoint.

At minimum, verify:

- the service starts without Render crash loops;
- NFCorpus is identified as the active dataset;
- the UI shows Anserini readiness/search/evaluation status;
- a sample NFCorpus query returns ranked results;
- evaluation metrics or cached evaluation status appear.

For services exposing a search API, verify search itself, not only health. A
service can report `/health` as ready while its internal Anserini RestServer is
stuck. Example probe:

```sh
curl -sS "https://pi-bench-anserini-nfcorpus-claude.onrender.com/api/search?q=diet&hits=10" | jq .
curl -sS "https://pi-bench-anserini-nfcorpus-claude.onrender.com/api/search?q=Are%20Avocados%20Good%20for%20You%3F&hits=10" | jq .
```

Use a bounded client timeout when probing from scripts so one wedged service
does not hang the whole verification run.

## 9. Common Failures

`docker: command not found`

Install Docker Desktop and reopen the terminal.

`GHCR/Render configuration is missing`

Create `.codex-private/render.env` with `GHCR_USERNAME`, `GHCR_TOKEN`,
`GHCR_OWNER`, and the `RENDER_DEPLOY_HOOK_*` values.

`docker login exited with code 1`

Check that `GHCR_USERNAME` matches the token owner and that `GHCR_TOKEN` has
`write:packages`.

`Render deploy hook is not configured`

The variable name must match the task and model:

```text
RENDER_DEPLOY_HOOK_ANSERINI_NFCORPUS_<MODEL>
```

where `<MODEL>` is one of:

```text
GPT
CLAUDE
GEMINI
GLM
KIMI
MINIMAX
```

`docker build exited with code ...`

Open the corresponding deployment stderr log. The build context is staged under:

```text
runs/<run-id>/deploy-staging/pi-bench-anserini-nfcorpus-<model>/
```

You can rerun the printed Docker build command manually from the repo root.

`Render returns 502 but /health previously passed`

Do not assume the container image is bad. Check whether the same image works
locally first:

```sh
docker run --rm -p 18100:10000 \
  -e PORT=10000 \
  -e APP_CACHE_DIR=/data \
  -e ANSERINI_REST_PORT=18083 \
  ghcr.io/<owner>/pi-bench-anserini-nfcorpus-claude:20260604-195631-698d5dac

curl -sS "http://127.0.0.1:18100/api/search?q=diet&hits=10" | jq .
```

During the Claude deployment, the exact same image returned search results
locally, but the Render service's internal Java `io.anserini.api.RestServer`
became wedged. Render logs showed normal startup and no Flask traceback, while
external requests either hung or returned Render's own 502 page. A Render
redeploy/restart of the original service cleared the stuck runtime state.

After redeploying Claude, the following searches returned quickly with HTTP
200:

```text
/health
/api/status
/api/search?q=diet&hits=10
/api/search?q=Are%20Avocados%20Good%20for%20You%3F&hits=10
/api/search?q=cancer&hits=10
```

Temporary debug Render services are useful for isolating whether a failure is
service-instance-specific, but delete them after verification to avoid paying
for extra `standard` instances.

`MiniMax starts but search/evaluation are unavailable`

MiniMax required a deployment-only staged image fix because its original root
route did not work correctly under the deployed Flask version. The original
benchmark workspace was not patched; the fix was applied in deployment staging
and pushed as:

```text
ghcr.io/<owner>/pi-bench-anserini-nfcorpus-minimax:20260604-195631-698d5dac-renderfix
```

Even with that renderfix image, MiniMax still did not satisfy the full Anserini
workflow: the deployed UI reported Java present, but Anserini was not found,
the NFCorpus index was not ready, and search/evaluation were unavailable. Treat
that as an implementation/container defect, not a Render routing issue.

`Claude or Gemini search is much slower than the REST API should be`

Check the Render instance type and internal app architecture. These apps often
run a Python web process plus a Java Anserini RestServer child process, and may
also download/unpack the NFCorpus prebuilt index during startup. On undersized
instances, the app can look ready before live search is comfortable. Standard
instances were a reasonable baseline for this benchmark.
