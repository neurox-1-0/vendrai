# Vendrai: Vendor-to-Pay Multi-Agent Exception System

## Overview
This repository contains the implementation of the **Vendor-to-Pay Multi-Agent Exception System** built for the NeuroX 1.0 National Level Buildathon. 

The system leverages a parallel multi-agent B2B agentic workflow for Procurement and Finance operations. It automates supplier onboarding and invoice exception handling using a stateful LangGraph orchestrator, specialist AI agents, and a strictly enforced human-in-the-loop (HITL) approval mechanism.

## System Architecture

The project is structured as a **modular monorepo** with the following core layers:
- **Web App (`apps/web`)**: Next.js & TypeScript frontend for procurement, finance, approval, and audit interfaces.
- **Core API (`services/api`)**: FastAPI backend for case management, documents, authentication, and structured tool access.
- **Agent Worker (`services/agent`)**: LangGraph orchestrator (Python) handling dynamic reasoning, tool calling, specialist agent routing, and verification.
- **Knowledge & Database (`db/`)**: PostgreSQL (with pgvector) as the main relational and hybrid database, paired with Qdrant for policy embeddings.

## Technical Stack
- **Agent Orchestration:** LangGraph
- **LLM Engine:** Gemini 2.5 Flash API
- **Vector DB:** Qdrant
- **Relational DB:** PostgreSQL (with `pgvector` and `pg_trgm`)
- **Document Processing:** Docling + Free-Tier OCR API
- **Observability:** Langfuse + OpenTelemetry

## Local Setup

### 1. Prerequisites
- Docker and Docker Compose installed.
- Python 3.11+
- Node.js 18+

### 2. Environment Configuration
Copy the sample environment file and add your actual API keys:
```bash
cp .env.example .env
```
Make sure to add your `GEMINI_API_KEY` and your OCR API keys to the `.env` file.

### 3. Start Infrastructure
Run the following command to spin up PostgreSQL, Qdrant, Redis, MinIO, and Langfuse:
```bash
docker compose up -d
```

### 4. Database Initialization
*(Database migration scripts via Alembic pending implementation)*

## Implementation Status
See [`CURRENT_STATUS.md`](./CURRENT_STATUS.md) for the active log of completed modules and pending tasks.

## License
Proprietary / Competition Submission for NeuroX 1.0. All Rights Reserved by Team GMora.
