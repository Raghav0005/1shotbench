# PRD

## Title
MS MARCO Passage Search App

## Summary
Create a locally-runnable web application that pairs a Next.js frontend with an Anserini REST API backend. The system searches the MS MARCO passage corpus and, on every page load, presents a random selection of sample queries drawn from the MS MARCO passage dev set so that users can immediately try realistic searches.

## Problem
There is currently no lightweight web interface for exploring MS MARCO passage retrieval through Anserini. Retrieval capabilities exist as backend tools, but users lack a simple front-end to submit queries, browse ranked results, and experiment with representative benchmark topics in a single application.

## Goals
- Enable passage-level search over the MS MARCO corpus via the Anserini REST API server.
- Provide a Next.js-based front-end where users enter queries and view ranked results.
- Display a randomly chosen set of sample queries from the MS MARCO passage dev split each time the page loads.
- Keep local setup straightforward for development and demonstration purposes.

## Non-Goals
- Model training or fine-tuning
- Implementing a custom search backend
- Authentication, authorization, or user accounts
- Production deployment or infrastructure automation
- Support for multiple corpora

## Users
- Developers and researchers investigating retrieval behavior
- Demo users exploring realistic benchmark queries
- Local operators who start and configure the frontend and backend services

## Core Requirements
- Rely on the repo-local Anserini skills as the authoritative reference: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- First, install the Anserini fatjar using the `install-anserini-fatjar` skill and verify the installation succeeded.
- Use the Anserini REST API server as the backend. Before implementing API calls, consult the relevant repo-local Anserini skill documentation—particularly `anserini-cli` for REST API examples—to determine the correct routes and response shapes; do not assume or guess them.
- Perform retrieval over the MS MARCO passage corpus.
- Implement the frontend with Next.js.
- Show several randomly selected sample queries sourced from the MS MARCO passage dev query set.
- Allow users to click a sample query to execute it as a search.
- Render ranked search results.
- Handle empty queries, zero-result responses, and backend errors with clear user-facing feedback.
- Default the backend to port `8080` and the frontend to port `3000`. Both ports must be overridable through environment variables. Do not pause to prompt the user for port selection.

## UX
When the page loads, the user sees a search input field alongside a set of sample queries. The user may type a query manually or click one of the sample queries. The application sends the query to the Anserini backend and displays the resulting ranked passages.

## Success Criteria
- Users can submit queries and receive ranked MS MARCO passage results.
- Sample queries are visible on page load and are clickable to trigger a search.
- The application runs end-to-end in a local environment with clearly configurable frontend and backend settings.
