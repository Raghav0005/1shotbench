# Product Requirements Document

## Project Name
MS MARCO Passage Search App

## Overview
Create a locally-runnable search application composed of a Next.js frontend paired with an Anserini REST API backend. The application performs retrieval over the MS MARCO passage corpus and surfaces randomly chosen example queries drawn from the MS MARCO passage dev query set, allowing users to immediately try realistic searches.

## Motivation
A simple, end-to-end app for exploring MS MARCO passage retrieval via Anserini does not currently exist. Retrieval functionality is reachable through backend tooling, but there is no lightweight web interface for searching the corpus or experimenting with sample queries.

## Objectives
- Perform searches over the MS MARCO passage corpus by way of the Anserini REST API server.
- Offer a Next.js-based frontend where users can submit queries and review ranked results.
- Display a fresh set of randomly selected sample queries from the MS MARCO passage dev queries on every page load.
- Keep the app straightforward to run locally for development purposes and demonstrations.

## Out of Scope
- Model training or fine-tuning
- Implementing a custom search backend
- Any form of authentication or user accounts
- Infrastructure for production deployment
- Supporting multiple corpora

## Target Users
- Developers and researchers investigating retrieval behavior
- Demo audiences who want to try realistic benchmark-style queries
- Local operators who run both the frontend and backend themselves

## Functional Requirements
- Treat the repo-local Anserini skills as authoritative: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing the Anserini fatjar through `install-anserini-fatjar`, and verify the install succeeded.
- Use the Anserini REST API server as the backend. Do not invent endpoints or guess response shapes — consult the repo-local Anserini skill docs first, in particular `anserini-cli` for REST usage examples.
- Search must target the MS MARCO passage corpus.
- The frontend must be built with Next.js.
- Render a handful of sample queries selected at random from the MS MARCO passage dev set.
- Clicking a sample query should execute that query.
- Show ranked search results.
- Provide clear handling for empty queries, the no-results case, and backend errors.
- Default ports: backend on `8080`, frontend on `3000`. Both must be overridable via environment variables, but do not pause to ask the user which ports to use.

## User Experience
When the page loads, the user is presented with a search input together with a list of sample queries. They can either type their own query or click one of the samples. The query is sent to the Anserini backend, and the ranked passage results are displayed.

## Acceptance Criteria
- Users are able to submit a query and receive ranked MS MARCO passage results.
- Sample queries are visible and clickable upon page load.
- The application functions end-to-end in a local environment, with clearly configurable frontend and backend settings.
