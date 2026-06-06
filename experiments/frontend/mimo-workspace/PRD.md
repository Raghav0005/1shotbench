# PRD

## Title
MS MARCO Passage Search App

## Summary
Build a local search application with a Next.js frontend and an Anserini REST API backend. The app will search over the MS MARCO passage corpus and show randomly selected sample queries from the MS MARCO passage dev query set so users can try realistic searches immediately.

## Problem
We need a simple end-to-end application for exploring MS MARCO passage retrieval through Anserini. Today, retrieval is available through backend tools, but there is no lightweight web app that lets users search the corpus and test example queries easily.

## Goals
- Search the MS MARCO passage corpus through the Anserini REST API server.
- Provide a Next.js frontend for entering queries and viewing ranked results.
- Show random sample queries from the MS MARCO passage dev queries on each page load.
- Make the app easy to run locally for development and demos.

## Non-Goals
- Training or fine-tuning models
- Building a custom search backend
- Authentication or user accounts
- Production deployment infrastructure
- Multi-corpus support

## Users
- Developers and researchers exploring retrieval behavior
- Demo users who want to try realistic benchmark queries
- Local operators running the frontend and backend

## Core Requirements
- Use the repo-local Anserini skills as the source of truth: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Start by installing the Anserini fatjar via `install-anserini-fatjar` and confirm that it has been correctly installed.
- Use the Anserini REST API server as the backend. Do not guess the routes or the shape of the responses; read the relevant repo-local Anserini skill docs first, especially `anserini-cli` for REST examples.
- Search over the MS MARCO passage corpus.
- Build the frontend in Next.js.
- Show several randomly selected sample queries from the MS MARCO passage dev set.
- Let users click a sample query to run it.
- Display ranked search results.
- Handle empty queries, no-results states, and backend errors clearly.
- Use backend port `8080` and frontend port `3000` by default. Make both ports configurable through environment variables, but do not stop to ask the user for port choices.

## UX
On page load, the user sees a search input and a set of sample queries. The user can type a query or click a sample query. The app sends the query to the Anserini backend and displays ranked passage results.

## Success Criteria
- Users can submit queries and receive ranked MS MARCO passage results.
- Sample queries are visible and usable on load.
- The app works end-to-end in a local environment with clear frontend/backend configuration.
