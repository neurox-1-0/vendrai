# Vendrai: Master Engineering TODO & Dependency Flow

> **🚨 CRITICAL RULE FOR ALL DEVELOPERS & AGENTS:**
> **YOU MUST ALWAYS UPDATE `CURRENT_STATUS.md` AFTER ANY WORK IS DONE.** 
> This is the central source of truth for the project's state. If you complete a feature from this list, immediately check off the corresponding box in `CURRENT_STATUS.md` and commit it.

---

## Dependency Flow & Execution Sequence

To ensure stable architecture, tasks MUST be executed in this sequence:
1. **Agent Logic (Python/LangGraph)**: The core intelligence must exist before the frontend can display it.
2. **Backend API (FastAPI)**: Routes must exist to trigger the agents and serve the data.
3. **Frontend UI (Next.js)**: The UI consumes the API and displays the neumorphic interface.
4. **End-to-End Integration**: Wiring the UI forms to the API, and handling real-time Server-Sent Events (SSE).

---

## 1. Agent & AI Core (LangGraph)
*Dependency: None. Relies on existing Database Schema and LangGraph Scaffold.*

- [ ] **Document Extraction Agent**: Integrate Docling / free-tier OCR to parse uploaded supplier documents and extract `SupplierDocumentFields`.
- [ ] **Duplicate Detection Agent**: Use PostgreSQL `pg_trgm` to search for existing vendors and return confidence scores.
- [ ] **Risk Agent**: Implement mocked/simulated sanctions checking and country-risk matching.
- [ ] **Policy Agent**: Connect Qdrant vector DB to retrieve procurement policies based on vendor category.
- [ ] **Reasoning & Clarification Node**: Build the LLM reasoning loop to evaluate evidence, handle contradictions, and trigger Clarification.
- [ ] **Evidence Builder & Verifier**: Aggregate the run into an immutable "Evidence Packet" and ensure it's safe for human review.

## 2. Backend API (FastAPI)
*Dependency: Agent Core.*

- [ ] **SSE (Server-Sent Events) Implementation**: Build an endpoint that streams LangGraph execution events in real-time so the frontend can display an active "Agent Trace".
- [ ] **Approval Queue Endpoints**: `GET /approvals` (fetch pending cases) and `POST /approvals/{id}` (approve/reject with HITL signature).
- [ ] **Document Upload Endpoints**: Finalize multipart form-data parsing, virus scan simulation, and MinIO storage saving.

## 3. Frontend Application (Next.js)
*Dependency: Existing Neumorphic Atoms (Card, Button, Input).*

- [ ] **Case Intake Form**: Build the initial "New Supplier" form allowing users to input basic vendor metadata and upload PDF documents. Must use Neumorphic inputs.
- [ ] **Agent Trace & Audit Viewer**: Build a live timeline UI that connects to the FastAPI SSE endpoint to show the LangGraph agents thinking in real-time.
- [ ] **Human Approval Dashboard**: Build a detailed view for "Pending Approval" cases, showing the Evidence Packet side-by-side with the uploaded document.
- [ ] **API Integration (React Query / Fetch)**: Replace the hardcoded mock data in the Dashboard with real data fetched from FastAPI `/cases` and `/metrics`.
- [ ] **Responsive Navigation**: Implement the mobile-first Hamburger menu for the sidebar.

## 4. End-to-End Testing & Polish
*Dependency: Frontend + Backend + Agents complete.*

- [ ] **Simulated ERP Sync**: Implement the final step where an approved case writes the vendor master data to a mock ERP.
- [ ] **E2E Demo Walkthrough**: Run a complete test: Upload Document -> Agents Think -> Flag Duplicate -> Human Overrides -> ERP Syncs.
- [ ] **Verify Authentication**: Ensure the system handles missing API keys gracefully and fails closed.
