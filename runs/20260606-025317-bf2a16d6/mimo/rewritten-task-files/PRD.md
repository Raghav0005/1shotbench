# MS MARCO Passage Search Application

## Overview
Create a local search tool combining a Next.js web interface with an Anserini REST API backend. The application enables searching the MS MARCO passage collection and presents randomly chosen sample queries from the MS MARCO passage development set to help users immediately test realistic searches.

## Problem Statement
Currently, retrieval functionality exists through backend tools, but there's no simple web application allowing users to search the corpus and experiment with example queries in a user-friendly way.

## Project Objectives
- Enable searching the MS MARCO passage collection via the Anserini REST API server
- Provide a Next.js web interface for query input and viewing ranked results
- Display random sample queries from the MS MARCO passage dev queries on each page load
- Ensure the application runs easily in a local environment for development and demonstrations

## Scope Limitations
- No model training or fine-tuning
- No custom search backend development
- No authentication or user account systems
- No production deployment infrastructure
- No support for multiple corpora

## Target Users
- Developers and researchers analyzing retrieval performance
- Users wanting to test realistic benchmark queries
- Local operators managing the frontend and backend systems

## Technical Requirements

### Implementation Approach
- Utilize the repository's local Anserini skill files as the authoritative reference: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`
- Begin by installing the Anserini fatjar using the `install-anserini-fatjar` skill and verify successful installation
- Implement the Anserini REST API server as the backend; consult the repo-local Anserini skill documentation (especially `anserini-cli` for REST examples) for accurate routes and response formats
- Search functionality must operate over the MS MARCO passage collection
- Frontend must be built using Next.js

### Core Functionality
- Display multiple randomly selected sample queries from the MS MARCO passage development set
- Allow users to click sample queries to execute them
- Present ranked search results to users
- Handle edge cases: empty queries, no-results scenarios, and backend errors with clear user feedback

### Configuration
- Default ports: backend on `8080`, frontend on `3000`
- Both ports must be configurable via environment variables
- Do not pause implementation to request port configuration from the user

## User Experience Flow
When the page loads, users see a search input field alongside a collection of sample queries. Users can either type their own query or select a sample query. The application forwards the query to the Anserini backend and displays the ranked passage results.

## Success Indicators
- Users can submit queries and receive ranked MS MARCO passage results
- Sample queries are visible and functional upon page load
- The complete application works locally with clear frontend and backend configuration options