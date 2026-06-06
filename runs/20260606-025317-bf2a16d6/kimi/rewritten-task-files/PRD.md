# PRD

## Title
MS MARCO Passage Search App

## Summary
Create a local search application consisting of a Next.js frontend and an Anserini REST API backend. The application must search the MS MARCO passage corpus and present randomly chosen sample queries drawn from the MS MARCO passage dev query set, enabling users to try realistic searches immediately upon loading the page.

## Problem
A lightweight end-to-end web application for exploring MS MARCO passage retrieval via Anserini does not currently exist. Retrieval capabilities are accessible only through backend tools, and there is no simple way for users to run searches against the corpus or test example queries through a web interface.

## Goals
- Enable searching the MS MARCO passage corpus through the Anserini REST API server.
- Deliver a Next.js frontend that accepts queries and presents ranked results.
- On each page load, display a random selection of sample queries from the MS MARCO passage dev queries.
- Keep the application straightforward to run locally for development and demonstration purposes.

## Non-Goals
- Training or fine-tuning any models.
- Implementing a custom search backend.
- Adding authentication or user accounts.
- Providing production deployment infrastructure.
- Supporting multiple corpora.

## Users
- Developers and researchers investigating retrieval behavior.
- Demonstration users who want to try realistic benchmark queries.
- Local operators running both the frontend and the backend.

## Core Requirements
- Treat the following repo-local Anserini skills as authoritative sources: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing the Anserini fatjar using `install-anserini-fatjar` and verify that the installation completed successfully.
- Use the Anserini REST API server as the backend. Before defining routes or interpreting response shapes, consult the relevant repo-local Anserini skill documentation—particularly `anserini-cli` for REST examples—rather than assuming them.
- Perform searches against the MS MARCO passage corpus.
- Implement the frontend with Next.js.
- Present several randomly selected sample queries from the MS MARCO passage dev set.
- Allow users to click any displayed sample query to execute it.
- Render ranked search results in the interface.
- Surface clear feedback for empty queries, no-results states, and backend errors.
- Default the backend to port `8080` and the frontend to port `3000`. Both ports must be overridable through environment variables. Do not pause to request port selections from the user.

## UX
When the page loads, the interface displays a search input field alongside a collection of sample queries. The user may type a custom query or select a sample query. The application forwards the query to the Anserini backend and then renders the returned ranked passage results.

## Success Criteria
- Users can submit queries and obtain ranked passage results from the MS MARCO corpus.
- Sample queries are shown on load and are actionable.
- The application operates end-to-end in a local environment with transparent frontend and backend configuration.
