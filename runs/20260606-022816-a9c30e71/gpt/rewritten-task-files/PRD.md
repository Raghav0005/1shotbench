# PRD

## Title
Local MS MARCO Passage Search Application

## Summary
Create a locally runnable search app consisting of a Next.js frontend and an Anserini REST API backend. The application must retrieve over the MS MARCO passage corpus and present randomly chosen example queries from the MS MARCO passage development query set so users can immediately try realistic searches.

## Problem
An end-to-end, lightweight web interface is needed for exploring MS MARCO passage retrieval with Anserini. Although retrieval functionality exists through backend tooling, there is not currently a simple local web app for searching the corpus and experimenting with example queries.

## Goals
- Query the MS MARCO passage corpus using the Anserini REST API server.
- Implement a Next.js frontend where users can enter queries and inspect ranked results.
- Display random sample queries from the MS MARCO passage dev queries whenever the page loads.
- Keep local development and demo setup straightforward.

## Non-Goals
- Model training or fine-tuning
- Implementing a custom search backend
- Authentication or user account functionality
- Production deployment infrastructure
- Support for multiple corpora

## Users
- Developers and researchers examining retrieval behavior
- Demo users interested in trying realistic benchmark queries
- Local operators running both the frontend and backend services

## Core Requirements
- Treat the repo-local Anserini skills as authoritative: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- First install the Anserini fatjar using `install-anserini-fatjar`, then verify that the installation succeeded.
- Use the Anserini REST API server for the backend. Do not infer API routes or response formats; first read the relevant repo-local Anserini skill documentation, especially `anserini-cli` for REST examples.
- Perform searches against the MS MARCO passage corpus.
- Build the frontend with Next.js.
- Show multiple randomly selected sample queries from the MS MARCO passage dev set.
- Allow a sample query click to execute that query.
- Render ranked search results.
- Clearly handle empty query submissions, no-results responses, and backend errors.
- Use backend port `8080` and frontend port `3000` as defaults. Both ports must be configurable through environment variables, and the implementation must not pause to ask the user which ports to use.

## UX
When the page loads, it should show a search input along with sample queries. The user may type a query or select a sample query. The app sends the chosen query to the Anserini backend and then displays ranked passage results.

## Success Criteria
- Users can submit queries and get ranked MS MARCO passage results.
- Sample queries appear on load and can be used to run searches.
- The full app functions locally end-to-end with clear frontend and backend configuration.
