# Product Requirements Document

## Project Name
MS MARCO Passage Search Application

## Overview
Develop a local web-based search application utilizing a Next.js frontend integrated with an Anserini REST API backend. The system will enable searching across the MS MARCO passage corpus. Upon loading, the interface must display a randomized selection of sample queries derived from the MS MARCO passage dev query set to facilitate immediate testing.

## Context
Currently, MS MARCO passage retrieval via Anserini is only accessible through backend utilities. There is a need for a streamlined, end-to-end web interface that allows users to easily search the corpus and execute example queries.

## Objectives
- Execute searches against the MS MARCO passage corpus using the Anserini REST API.
- Create a Next.js frontend interface for inputting search queries and displaying ranked results.
- Present a random selection of sample queries from the MS MARCO passage dev set on initial page load.
- Ensure the application is straightforward to run locally for development and demonstration purposes.

## Out of Scope
- Model training or fine-tuning.
- Development of a custom search backend engine.
- Implementation of user authentication or accounts.
- Setup of production deployment infrastructure.
- Support for multiple corpora.

## Target Audience
- Developers and researchers analyzing retrieval performance.
- Users seeking to demonstrate realistic benchmark queries.
- Individuals operating the frontend and backend locally.

## Key Requirements
- Refer to the repository-local Anserini skills as the primary documentation: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin the process by installing the Anserini fatjar using the `install-anserini-fatjar` instructions and verify the installation's success.
- Implement the backend using the Anserini REST API server. Consult the relevant local Anserini skill documentation (particularly `anserini-cli` for REST usage) to determine the correct routes and response structures; do not make assumptions.
- Perform searches exclusively over the MS MARCO passage corpus.
- Implement the frontend using Next.js.
- Display a randomized list of sample queries sourced from the MS MARCO passage dev set.
- Allow users to execute a sample query by clicking on it.
- Render ranked search results.
- Gracefully manage and communicate states involving empty queries, zero results, and backend errors.
- Default to port `8080` for the backend and port `3000` for the frontend. Ensure both ports are configurable via environment variables. Do not prompt the user to select ports.

## User Experience Design
When the page loads, the interface should present a search input field alongside a collection of sample queries. Users can either manually enter a query or select a sample query. The application will then transmit the query to the Anserini backend and display the resulting ranked passages.

## Acceptance Criteria
- Users successfully submit search queries and receive ranked results from the MS MARCO passage corpus.
- Sample queries are displayed and functional upon initial page load.
- The complete application operates successfully in a local environment, featuring clearly defined configurations for both frontend and backend components.