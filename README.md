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

## Frontend UI Previews

The frontend is built with a modern, high-fidelity Next.js interface optimized for enterprise AP and Procurement teams.

### 1. Active Dashboard & Agent Trace Feed
![Dashboard](apps/web/public/frontend%20screenshots/1.png)

### 2. Multi-Flow Case Intake Form
![Case Intake Form](apps/web/public/frontend%20screenshots/2.png)

### 3. Human Exceptions Approval Queue
![Approval Queue](apps/web/public/frontend%20screenshots/3.png)

### 4. Human-In-The-Loop Document Viewer
![HITL Verification](apps/web/public/frontend%20screenshots/4.png)

### 5. Enterprise Performance Analytics
![Analytics Dashboard](apps/web/public/frontend%20screenshots/5.png)

### 6. Compliance Reports Export
![Reports Export](apps/web/public/frontend%20screenshots/6.png)

### 7. Global Navigation & Dropdowns
![Navigation](apps/web/public/frontend%20screenshots/7.png)

## Local Setup

### 1. Prerequisites
- Docker and Docker Compose installed.
- Python 3.11+
- Node.js 18+

### 2. Environment Configuration
Copy the sample environment file and add your actual API keys:

**For macOS/Linux:**
```bash
cp .env.example .env
```

**For Windows (PowerShell):**
```powershell
Copy-Item .env.example -Destination .env
```
Make sure to add your `GEMINI_API_KEY` and your OCR API keys to the `.env` file.

### 3. Start Infrastructure
Run the following command to spin up PostgreSQL, Qdrant, Redis, MinIO, and Langfuse:
```bash
docker compose up -d
```

### 4. Start the Web App (Frontend)
To see the UI and interact with the application, start the Next.js development server. Open a new terminal and run:

```bash
cd apps/web
npm install
npm run dev
```
The application will be available at [http://localhost:3000](http://localhost:3000).

### 5. Start the Core API (Backend)
To start the FastAPI backend for the system, open another terminal and run:

**For macOS/Linux:**
```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**For Windows:**
```powershell
cd services\api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
The API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 6. Start the Agent Worker
To start the LangGraph agent orchestrator, open another terminal and run:

**For macOS/Linux:**
```bash
cd services/agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.graph
```

**For Windows:**
```powershell
cd services\agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.graph
```

### 7. Database Initialization
*(Database migration scripts via Alembic pending implementation)*

## Implementation Status
See [`CURRENT_STATUS.md`](./CURRENT_STATUS.md) for the active log of completed modules and pending tasks.

## License
Proprietary / Competition Submission for NeuroX 1.0. All Rights Reserved by Team GMora.
