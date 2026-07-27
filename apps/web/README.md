# NeuroX web application

This Next.js application is the operational UI for supplier onboarding and
invoice-exception resolution. It uses the real FastAPI contract, TanStack Query,
durable event refresh, role-aware human controls, evidence views, execution
timing and a read-only application copilot.

## Local development

```bash
npm run dev
```

The API must be available at `NEXT_PUBLIC_API_URL` (by default
`http://localhost:8000/api/v1`). Starting only this process intentionally shows
service-unavailable states; it does not fabricate workflow data. For the whole
product use `./scripts/stack.sh product-up` from the repository root.

## Verification

```bash
npm ci
npm run lint
npx tsc --noEmit
npm run build
npm run api:check
```

The copilot receives a masked semantic registry of controls currently rendered
on the page. New components register an assistance ID, label, description and
optional tour group through `useAssistanceTarget`; tours therefore adapt to
visible UI state instead of relying on brittle DOM selectors. Guidance is
user-triggered and read-only.
