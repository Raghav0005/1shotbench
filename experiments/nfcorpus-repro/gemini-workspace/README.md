# NFCorpus Live Retrieval Diagnostics Workbench

This project provides a live retrieval diagnostics workbench for NFCorpus, powered by Anserini. 
It meets all the requirements to run as a Docker web service on Render.

## Deployment Specifications

- **Docker:** A `Dockerfile` is provided at the root of the project.
- **Port Binding:** The application binds the HTTP server to `0.0.0.0` and utilizes the `PORT` environment variable (default: 10000).
- **Persistent Storage (Optional):** If deployed on Render and you wish to cache the Anserini indices and fatjar to avoid downloading them across container restarts, you can mount a persistent disk to `/root/.cache/pyserini` and `/app/backend/anserini`.
- **Health Check:** A `/health` endpoint is exposed and outputs JSON containing system readiness state.

## Local Development

```bash
# Install dependencies
npm install
cd frontend && npm install && npm run build && cd ..

# Start server
npm start
```

## Running Tests

```bash
npm test
```
