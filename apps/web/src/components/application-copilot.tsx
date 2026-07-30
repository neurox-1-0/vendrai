"use client";

import {
  Bot,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  LoaderCircle,
  MapPin,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCopilotContext } from "@/components/copilot-provider";

/**
 * Floating launcher + anchored popover, present on every route. All session
 * and conversation state lives in CopilotProvider (see copilot-provider.tsx)
 * so this panel and the dashboard's docked assistant card share one
 * conversation rather than keeping two disconnected copies.
 */
export function ApplicationCopilot() {
  const {
    open,
    setOpen,
    openCopilot,
    messages,
    question,
    setQuestion,
    loading,
    error,
    submit,
    runAction,
    sendFeedback,
    feedbackSent,
    tour,
    tourTarget,
    moveTour,
    endTour,
    scrollAnchor,
  } = useCopilotContext();

  const visibleMessages = messages.slice(-20);
  return (
    <>
      <Button
        type="button"
        variant="primary"
        className="fixed bottom-20 right-5 z-40 gap-2 rounded-full px-5 py-4 shadow-[var(--shadow-lg)] md:bottom-7 md:right-7"
        aria-label="Open Vendrai application copilot"
        aria-expanded={open}
        onClick={openCopilot}
      >
        <Sparkles className="h-5 w-5" aria-hidden="true" />
        <span className="hidden sm:inline">Ask Vendrai</span>
      </Button>

      {open && (
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="copilot-title"
          className="fixed inset-2 z-50 flex flex-col overflow-hidden rounded-3xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-lg)] md:inset-auto md:bottom-7 md:right-7 md:max-h-[82vh] md:w-[430px]"
        >
          <header className="flex items-start justify-between gap-4 border-b border-white/10 bg-[var(--color-ink)] p-5 text-white">
            <div className="flex gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[var(--color-accent)]/25 text-blue-200">
                <Bot className="h-6 w-6" aria-hidden="true" />
              </span>
              <div>
                <h2 id="copilot-title" className="font-bold">
                  Vendrai application copilot
                </h2>
                <p className="mt-1 text-xs text-slate-300">
                  Explains and guides. Cannot progress or approve work.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-full p-2 hover:bg-white/10"
              aria-label="Close copilot"
            >
              <X className="h-5 w-5" />
            </button>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {visibleMessages.length === 0 && !loading && (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
                <p className="flex items-center gap-2 font-bold">
                  <CircleHelp className="h-4 w-4 text-[var(--color-accent)]" />
                  What would you like to understand?
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    "How does this agent choose tools?",
                    "Show the execution path and latency",
                    "What should I do next?",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="rounded-full border border-[var(--color-accent)]/25 bg-[var(--color-accent-light)] px-3 py-2 text-left text-xs font-bold text-[var(--color-accent-dark)] hover:brightness-95"
                      onClick={() => setQuestion(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {visibleMessages.map((message) => (
              <article
                key={message.copilot_message_id}
                className={
                  message.role === "USER"
                    ? "ml-10 rounded-2xl bg-[var(--color-accent)] p-4 text-sm text-white"
                    : "mr-5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4 text-sm"
                }
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.role === "ASSISTANT" && (
                  <>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-[var(--color-muted)]">
                      <span className="flex items-center gap-1">
                        <ShieldCheck className="h-3 w-3" />
                        {message.provider === "GEMINI" ? "Gemini + CAG" : "Local CAG fallback"}
                      </span>
                      {message.latency_ms !== null && <span>{message.latency_ms} ms</span>}
                      {message.error_code && <span>{message.error_code}</span>}
                    </div>
                    {message.citations.length > 0 && (
                      <p className="mt-2 text-xs text-[var(--color-muted)]">
                        Sources: {message.citations.map((citation) => citation.title).join(" · ")}
                      </p>
                    )}
                    {message.ui_actions.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {message.ui_actions.map((action) => (
                          <button
                            key={`${action.action_type}-${action.target}`}
                            type="button"
                            className="flex w-full items-center justify-between rounded-xl border border-[var(--color-accent)]/25 bg-[var(--color-accent-light)] px-3 py-2 text-left text-xs font-bold text-[var(--color-accent-dark)] hover:brightness-95"
                            onClick={() => runAction(action)}
                          >
                            <span className="flex items-center gap-2">
                              <MapPin className="h-3.5 w-3.5" />
                              {action.label}
                            </span>
                            <ChevronRight className="h-4 w-4" />
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="mt-3 flex items-center justify-end gap-1 border-t border-[var(--color-border)] pt-2">
                      <span className="mr-1 text-[10px] text-[var(--color-muted)]">
                        {feedbackSent.has(message.copilot_message_id) ? "Feedback recorded" : "Helpful?"}
                      </span>
                      <button
                        type="button"
                        aria-label="Mark answer helpful"
                        disabled={feedbackSent.has(message.copilot_message_id)}
                        className="rounded-lg p-1.5 hover:bg-emerald-100 disabled:opacity-40"
                        onClick={() => sendFeedback(message.copilot_message_id, "HELPFUL")}
                      >
                        <ThumbsUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label="Mark answer not helpful"
                        disabled={feedbackSent.has(message.copilot_message_id)}
                        className="rounded-lg p-1.5 hover:bg-rose-100 disabled:opacity-40"
                        onClick={() => sendFeedback(message.copilot_message_id, "NOT_HELPFUL")}
                      >
                        <ThumbsDown className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </>
                )}
              </article>
            ))}
            {loading && (
              <p className="flex items-center gap-2 text-sm text-[var(--color-muted)]" aria-live="polite">
                <LoaderCircle className="h-4 w-4 animate-spin" />
                Assembling permitted context…
              </p>
            )}
            {error && (
              <div role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-900">
                <p>{error}</p>
                {error.includes("not reachable") && (
                  <button
                    type="button"
                    className="mt-2 inline-flex items-center gap-1 rounded-lg bg-rose-100 px-2 py-1 font-bold hover:bg-rose-200"
                    onClick={openCopilot}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Retry connection
                  </button>
                )}
              </div>
            )}
            <div ref={scrollAnchor} />
          </div>

          <form onSubmit={submit} className="border-t border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
            <label htmlFor="copilot-question" className="sr-only">
              Ask about Vendrai
            </label>
            <div className="flex items-end gap-2">
              <textarea
                id="copilot-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={2}
                maxLength={1200}
                placeholder="Ask what happened, why, or how to use this screen…"
                className="min-h-12 flex-1 resize-none rounded-xl border border-[var(--color-border)] bg-white p-3 text-sm shadow-[var(--shadow-xs)] outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/25"
              />
              <Button
                type="submit"
                variant="primary"
                title="Send question"
                aria-label="Send question"
                disabled={loading || question.trim().length < 2}
                className="h-12 w-12 shrink-0 rounded-full p-0"
              >
                <span className="text-xl leading-none" aria-hidden="true">➤</span>
              </Button>
            </div>
          </form>
        </section>
      )}

      {tour && tourTarget && (
        <aside
          role="dialog"
          aria-label="Guided application tour"
          className="fixed bottom-4 left-1/2 z-[70] w-[min(94vw,560px)] -translate-x-1/2 rounded-2xl bg-[var(--color-ink)] p-5 text-white shadow-[var(--shadow-lg)]"
        >
          <p className="text-xs font-bold uppercase tracking-wider text-blue-300">
            Guided workflow · step {tour.index + 1} of {tour.targetIds.length}
          </p>
          <p className="mt-2 font-bold">{tourTarget.title}</p>
          <p className="mt-1 text-sm text-slate-300">{tourTarget.description}</p>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <button type="button" className="rounded-xl px-3 py-2 text-sm hover:bg-white/10" onClick={endTour}>
              Skip tour
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={tour.index === 0}
                className="inline-flex items-center gap-1 rounded-xl px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-40"
                onClick={() => moveTour(tour.index - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-xl bg-[var(--color-accent)] px-4 py-2 text-sm font-bold hover:bg-[var(--color-accent-dark)]"
                onClick={() => (tour.index === tour.targetIds.length - 1 ? endTour() : moveTour(tour.index + 1))}
              >
                {tour.index === tour.targetIds.length - 1 ? "Finish" : "Next"}
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
