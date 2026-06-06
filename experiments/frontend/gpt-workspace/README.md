# Local MS MARCO Passage Search

A local Next.js frontend for searching MS MARCO passage through the Anserini REST API.

## Configuration

Defaults match the PRD and can be overridden with environment variables:

- Backend: `BACKEND_PORT` or `ANSERINI_PORT` (default `8080`)
- Frontend: `FRONTEND_PORT` or `PORT` (default `3000`)
- Anserini jar: `ANSERINI_JAR` (defaults to a local `anserini-*-fatjar.jar`)
- Anserini REST URL used by Next.js: `ANSERINI_API_BASE_URL` (default `http://localhost:${BACKEND_PORT}`)
- Search index: `ANSERINI_INDEX` (default `msmarco-v1-passage`)

## Run locally

```bash
npm install
npm run backend
```

In a second terminal:

```bash
npm run dev
```

Then open <http://localhost:3000>.

The backend command starts Anserini's documented REST server:

```bash
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```

The first MS MARCO search may download Anserini's `msmarco-v1-passage` prebuilt index.

## Sample queries

`src/data/msmarco-passage-dev-queries.json` contains the MS MARCO passage dev query set exported from Anserini's `TopicsRegistry`. The app samples this data randomly on each page load.

Regenerate it after changing Anserini versions with:

```bash
npm run samples:generate
```
