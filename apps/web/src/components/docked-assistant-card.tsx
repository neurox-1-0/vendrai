"use client";

import { LoaderCircle, MapPin, MessagesSquare, Search, ShieldAlert, Sparkles } from "lucide-react";
import { useAuth } from "@/app/providers";
import { Card } from "@/components/ui/card";
import { useCopilotContext } from "@/components/copilot-provider";

const QUICK_ACTIONS = [
  {
    label: "Summarize this queue",
    icon: MessagesSquare,
    color: "bg-emerald-100 text-emerald-700",
    run: (ask: (text: string) => void) => ask("Summarize today's work queue"),
  },
  {
    label: "Explain a status",
    icon: Search,
    // Sky, not blue: brand blue is reserved for the tour action below, and two
    // adjacent blues would stop reading as distinct affordances.
    color: "bg-sky-100 text-sky-700",
    run: (ask: (text: string) => void) => ask("What does DUPLICATE_REVIEW mean?"),
  },
  {
    label: "Find risk cases",
    icon: ShieldAlert,
    color: "bg-amber-100 text-amber-700",
    run: (ask: (text: string) => void) => ask("Which cases have open risk findings?"),
  },
  {
    label: "Guided tour",
    icon: MapPin,
    color: "bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-secondary)] text-white",
    run: (_ask: (text: string) => void, runAction: ReturnType<typeof useCopilotContext>["runAction"]) =>
      runAction({ action_type: "START_TOUR", target: "dashboard.orientation", label: "Guided tour" }),
  },
];

/**
 * Always-visible assistant card for the dashboard's right rail. Reuses
 * CopilotProvider's live conversation -- a question asked here shows up in
 * the floating panel too, and vice versa (see copilot-provider.tsx).
 */
export function DockedAssistantCard() {
  const { displayName } = useAuth();
  const { messages, question, setQuestion, loading, submit, ask, runAction } = useCopilotContext();
  const visibleMessages = messages.slice(-6);

  return (
    <Card tint="accent">
      <p className="font-display text-lg font-bold text-[var(--color-ink)]">Hi, {displayName} 👋</p>
      <p className="mt-1 text-sm text-[var(--color-muted)]">How can I help you?</p>

      <div className="mt-5 grid grid-cols-2 gap-3">
        {QUICK_ACTIONS.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => action.run(ask, runAction)}
            className="flex flex-col items-start gap-2 rounded-xl border border-white/60 bg-white/70 p-3 text-left transition-colors hover:bg-white"
          >
            <span className={`grid h-8 w-8 place-items-center rounded-lg ${action.color}`}>
              <action.icon className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="text-xs font-bold text-[var(--color-ink)]">{action.label}</span>
          </button>
        ))}
      </div>

      {visibleMessages.length > 0 && (
        <div className="mt-5 max-h-56 space-y-2 overflow-y-auto border-t border-white/60 pt-4">
          {visibleMessages.map((message) => (
            <p
              key={message.copilot_message_id}
              className={
                message.role === "USER"
                  ? "ml-6 rounded-xl bg-[var(--color-accent)] px-3 py-2 text-xs text-white"
                  : "mr-6 rounded-xl bg-white/80 px-3 py-2 text-xs text-[var(--color-ink)]"
              }
            >
              {message.content}
            </p>
          ))}
          {loading && (
            <p className="flex items-center gap-2 text-xs text-[var(--color-muted)]" aria-live="polite">
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              Thinking…
            </p>
          )}
        </div>
      )}

      <form onSubmit={submit} className="mt-5 flex items-center gap-2">
        <label htmlFor="docked-copilot-question" className="sr-only">Ask something</label>
        <input
          id="docked-copilot-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask something…"
          className="h-11 flex-1 rounded-full border border-white/60 bg-white/80 px-4 text-sm outline-none placeholder:text-[var(--color-muted)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/25"
        />
        <button
          type="submit"
          aria-label="Send question"
          disabled={loading || question.trim().length < 2}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--color-accent)] text-white transition-colors hover:bg-[var(--color-accent-dark)] disabled:opacity-40"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
        </button>
      </form>
      <p className="mt-3 text-[11px] text-[var(--color-muted)]">
        Explains and guides. Cannot progress or approve work.
      </p>
    </Card>
  );
}
