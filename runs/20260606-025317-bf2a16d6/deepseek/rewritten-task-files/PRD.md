# PRD

## Title
MS MARCO Passage Search App

## Summary
Construct a locally-runnable search tool composed of a Next.js frontend and an Anserini REST API backend. The application searches the MS MARCO passage corpus and, on each page load, presents a handful of randomly drawn sample queries taken from the MS MARCO passage dev query collection, so users can immediately try realistic searches.

## Problem
There is currently no lightweight web interface for interactively exploring MS MARCO passage retrieval through Anserini. While backend tooling supports retrieval workflows, a simple end-to-end app that lets users search the corpus and exercise example queries is absent.

## Goals
- Query the MS MARCO passage corpus by sending requests to the Anserini REST API server.
- Supply a Next.js frontend where users can type queries and inspect ranked result lists.
- On every page load, surface several randomly selected sample queries drawn from the MS MARCO passage dev queries.
- Keep the app straightforward to start and run locally for development and demonstrations.

## Non-Goals
- Model training, fine-tuning, or reranking.
- Building a custom search engine or index backend.
- Authentication, user accounts, or session management.
- Infrastructure for production hosting.
- Support for multiple corpora.

## Users
- Developers and researchers who want to examine retrieval behavior interactively.
- Demo audiences who want to try out real benchmark queries.
- Local operators running both the frontend and backend processes.

## Core Requirements
- Treat the repo-local Anserini skills as the definitive reference: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing the Anserini fatjar through the `install-anserini-fatjar` skill and verify that the installation succeeded.
- Use the Anserini REST API server as the backend. Do not guess the API routes or response shapes; read the repo-local Anserini skill documentation first — paying special attention to `anserini-cli`, which documents REST examples.
- Search over the MS MARCO passage corpus.
- Build the frontend with Next.js.
- Display several randomly selected sample queries from the MS MARCO passage dev set.
- Allow users to click a sample query to issue that search.
- Show ranked search results in the UI.
- Handle the following edge conditions clearly in the frontend:
  - Empty query input
  - Zero results returned from the backend
  - Backend errors or unavailability
- Use backend port `8080` and frontend port `3000` as defaults. Make both ports configurable through environment variables. Do not pause execution to prompt the user for port choices.

## UX
When the page loads, the user sees a search input field alongside a set of sample queries. The user may either type a query manually or click one of the sample queries. The application forwards the query to the Anserini backend and renders a ranked list of matching passage results.

## Success Criteria
- Users can submit queries and receive ranked results drawn from the MS MARCO passage corpus.
- Sample queries are visible and clickable on page load.
- The complete application functions end-to-end in a local environment, with clear separation between frontend configuration and backend configuration.
