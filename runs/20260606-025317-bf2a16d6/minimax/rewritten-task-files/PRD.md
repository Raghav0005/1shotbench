# PRD

## Title
MS MARCO Passage Search App

## Summary
Construct a local search application composed of a Next.js frontend that communicates with an Anserini REST API backend. The application searches the MS MARCO passage corpus and, on each page load, presents a small set of randomly selected sample queries drawn from the MS MARCO passage dev query set so that users can immediately try realistic searches.

## Problem
A simple end-to-end application for exploring MS MARCO passage retrieval through Anserini does not currently exist. Retrieval functionality is available through backend tools, but there is no lightweight web application that lets users search the corpus and try example queries directly from a browser.

## Goals
- Search the MS MARCO passage corpus by querying the Anserini REST API server.
- Provide a Next.js frontend where users can enter queries and view ranked results.
- On each page load, display randomly selected sample queries sourced from the MS MARCO passage dev queries.
- Keep the application straightforward to run locally for both development and demo purposes.

## Non-Goals
- Training or fine-tuning of models.
- Building a custom search backend.
- Authentication or user accounts.
- Production deployment infrastructure.
- Multi-corpus support.

## Users
- Developers and researchers who want to explore retrieval behavior.
- Demo users who want to try realistic benchmark queries.
- Local operators who run the frontend and backend together.

## Core Requirements
- The repo-local Anserini skills — `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction` — are the source of truth and must be consulted.
- Begin by installing the Anserini fatjar using the `install-anserini-fatjar` skill and confirm that the installation completed successfully.
- Use the Anserini REST API server as the backend. Do not guess the routes or the shape of the responses; read the relevant repo-local Anserini skill documentation first, with particular attention to `anserini-cli` for REST examples.
- The corpus to search over is the MS MARCO passage corpus.
- The frontend must be built in Next.js.
- The application must display several randomly selected sample queries from the MS MARCO passage dev set.
- Users must be able to click a sample query to run it.
- The application must display ranked search results.
- The application must handle the following cases clearly: empty queries, no-results states, and backend errors.
- Default backend port: `8080`. Default frontend port: `3000`. Both ports must be configurable through environment variables, and the application must not pause to ask the user for port choices.

## UX
When the page loads, the user sees a search input together with a set of sample queries. The user can either type a query into the input or click one of the sample queries. The application sends the query to the Anserini backend and renders the ranked passage results.

## Success Criteria
- Users can submit queries and receive ranked MS MARCO passage results.
- Sample queries are visible on load and are usable to trigger searches.
- The application works end-to-end in a local environment with clear frontend and backend configuration.
