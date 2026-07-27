"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
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

import {
  useAssistanceRegistry,
} from "@/components/assistance-registry";
import { Button } from "@/components/ui/button";
import {
  api,
  type CopilotMessage,
  type CopilotSession,
} from "@/lib/api";

const SESSION_STORAGE_KEY = "neurox-copilot-session";

interface TourState {
  group: string;
  targetIds: string[];
  index: number;
}

function caseIdFromPath(pathname: string): string | undefined {
  const match = pathname.match(
    /^\/cases\/([0-9a-f]{8}-[0-9a-f-]{27,})/i,
  );
  return match?.[1];
}

function friendlyError(error: unknown): string {
  const message =
    error instanceof Error ? error.message : "COPILOT_UNAVAILABLE";
  if (
    message.toLowerCase().includes("failed to fetch")
    || message.includes("ECONNREFUSED")
  ) {
    return (
      "NeuroX services are not reachable yet. Start the product "
      + "runtime, then retry."
    );
  }
  if (message.includes("LLM_AUTH_INVALID")) {
    return "Gemini rejected the configured key. Ask an administrator to verify it.";
  }
  if (message.includes("LLM_QUOTA_EXCEEDED")) {
    return "Gemini quota is exhausted. Deterministic work is preserved for retry.";
  }
  return message.replaceAll("_", " ");
}

export function ApplicationCopilot() {
  const pathname = usePathname();
  const router = useRouter();
  const assistance = useAssistanceRegistry();
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<CopilotSession | null>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tour, setTour] = useState<TourState | null>(null);
  const [feedbackSent, setFeedbackSent] = useState<Set<string>>(
    () => new Set(),
  );
  const scrollAnchor = useRef<HTMLDivElement>(null);
  const caseId = useMemo(() => caseIdFromPath(pathname), [pathname]);
  const tourTarget = tour
    ? assistance.get(tour.targetIds[tour.index])
    : undefined;

  async function ensureSession(): Promise<CopilotSession> {
    if (session) return session;
    const stored =
      typeof window === "undefined"
        ? null
        : window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (stored) {
      try {
        const history = await api.listCopilotMessages(stored);
        const restored: CopilotSession = {
          copilot_session_id: stored,
          context_case_id: caseId ?? null,
          title: "Application help",
          help_pack_version:
            history.at(-1)?.citations.at(0)?.help_pack_version ?? "current",
          status: "ACTIVE",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setSession(restored);
        setMessages(history);
        return restored;
      } catch {
        window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      }
    }
    const created = await api.createCopilotSession(pathname, caseId);
    window.sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      created.copilot_session_id,
    );
    setSession(created);
    setMessages([]);
    return created;
  }

  async function openCopilot() {
    setOpen(true);
    setError("");
    setLoading(true);
    try {
      await ensureSession();
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = question.trim();
    if (!normalized || loading) return;
    setQuestion("");
    setError("");
    setLoading(true);
    try {
      const activeSession = await ensureSession();
      setMessages((current) => [
        ...current,
        {
          copilot_message_id: crypto.randomUUID(),
          copilot_session_id: activeSession.copilot_session_id,
          role: "USER",
          content: normalized,
          citations: [],
          ui_actions: [],
          provider: "LOCAL_INPUT",
          model_version: null,
          latency_ms: null,
          error_code: null,
          created_at: new Date().toISOString(),
        },
      ]);
      const response = await api.sendCopilotMessage(
        activeSession.copilot_session_id,
        normalized,
        pathname,
        assistance.context(),
        caseId,
      );
      setMessages((current) => [...current, response]);
      window.requestAnimationFrame(() =>
        scrollAnchor.current?.scrollIntoView({ behavior: "smooth" }),
      );
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setLoading(false);
    }
  }

  function endTour() {
    assistance.clearSpotlight();
    setTour(null);
  }

  function moveTour(index: number) {
    if (!tour) return;
    const bounded = Math.max(
      0,
      Math.min(index, tour.targetIds.length - 1),
    );
    if (!assistance.spotlight(tour.targetIds[bounded])) {
      setError("That guided control is no longer visible.");
      endTour();
      return;
    }
    setTour({ ...tour, index: bounded });
  }

  function runAction(action: CopilotMessage["ui_actions"][number]) {
    setError("");
    if (action.action_type === "NAVIGATE") {
      router.push(action.target);
      return;
    }
    if (action.action_type === "SPOTLIGHT") {
      if (!assistance.spotlight(action.target)) {
        setError("That control is not visible in the current screen state.");
        return;
      }
      setOpen(false);
      return;
    }
    if (action.action_type === "START_TOUR") {
      const targets = assistance.list(action.target);
      if (targets.length === 0) {
        setError("Open a matching workflow screen before starting this guide.");
        return;
      }
      const nextTour = {
        group: action.target,
        targetIds: targets.map((target) => target.id),
        index: 0,
      };
      setTour(nextTour);
      assistance.spotlight(nextTour.targetIds[0]);
      setOpen(false);
      return;
    }
    if (action.action_type === "OPEN_PANEL") {
      if (action.target === "notifications") {
        if (pathname !== "/") router.push("/");
        window.setTimeout(
          () =>
            window.dispatchEvent(
              new CustomEvent("neurox:open-panel", {
                detail: { panel: "notifications" },
              }),
            ),
          pathname === "/" ? 0 : 500,
        );
      }
      return;
    }
    window.dispatchEvent(
      new CustomEvent("neurox:set-filter", {
        detail: { target: action.target },
      }),
    );
  }

  async function sendFeedback(
    messageId: string,
    rating: "HELPFUL" | "NOT_HELPFUL",
  ) {
    if (feedbackSent.has(messageId)) return;
    setError("");
    try {
      await api.sendCopilotFeedback(messageId, rating);
      setFeedbackSent(
        (current) => new Set(current).add(messageId),
      );
    } catch (requestError) {
      setError(friendlyError(requestError));
    }
  }

  const visibleMessages = messages.slice(-20);
  return (
    <>
      <Button
        type="button"
        variant="primary"
        className="fixed bottom-20 right-5 z-40 gap-2 rounded-full px-5 py-4 shadow-2xl md:bottom-7 md:right-7"
        aria-label="Open NeuroX application copilot"
        aria-expanded={open}
        onClick={() => void openCopilot()}
      >
        <Sparkles className="h-5 w-5" aria-hidden="true" />
        <span className="hidden sm:inline">Ask NeuroX</span>
      </Button>

      {open && (
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="copilot-title"
          className="fixed inset-2 z-50 flex flex-col overflow-hidden rounded-3xl border border-white/60 bg-[var(--color-clay)] shadow-2xl md:inset-auto md:bottom-7 md:right-7 md:max-h-[82vh] md:w-[430px]"
        >
          <header className="flex items-start justify-between gap-4 border-b border-white/50 bg-slate-950 p-5 text-white">
            <div className="flex gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-violet-500/20 text-violet-200">
                <Bot className="h-6 w-6" aria-hidden="true" />
              </span>
              <div>
                <h2 id="copilot-title" className="font-bold">
                  NeuroX application copilot
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
              <div className="rounded-2xl bg-white/50 p-4 shadow-[var(--shadow-inset-sm)]">
                <p className="flex items-center gap-2 font-bold">
                  <CircleHelp className="h-4 w-4 text-violet-700" />
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
                      className="rounded-full border border-violet-200 bg-violet-50 px-3 py-2 text-left text-xs font-bold text-violet-950 hover:bg-violet-100"
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
                    ? "ml-10 rounded-2xl bg-violet-700 p-4 text-sm text-white"
                    : "mr-5 rounded-2xl bg-white/60 p-4 text-sm shadow-[var(--shadow-inset-sm)]"
                }
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.role === "ASSISTANT" && (
                  <>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-[var(--color-muted)]">
                      <span className="flex items-center gap-1">
                        <ShieldCheck className="h-3 w-3" />
                        {message.provider === "GEMINI"
                          ? "Gemini + CAG"
                          : "Local CAG fallback"}
                      </span>
                      {message.latency_ms !== null && (
                        <span>{message.latency_ms} ms</span>
                      )}
                      {message.error_code && (
                        <span>{message.error_code}</span>
                      )}
                    </div>
                    {message.citations.length > 0 && (
                      <p className="mt-2 text-xs text-[var(--color-muted)]">
                        Sources:{" "}
                        {message.citations
                          .map((citation) => citation.title)
                          .join(" · ")}
                      </p>
                    )}
                    {message.ui_actions.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {message.ui_actions.map((action) => (
                          <button
                            key={`${action.action_type}-${action.target}`}
                            type="button"
                            className="flex w-full items-center justify-between rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-left text-xs font-bold text-violet-950 hover:bg-violet-100"
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
                    <div className="mt-3 flex items-center justify-end gap-1 border-t border-slate-200 pt-2">
                      <span className="mr-1 text-[10px] text-[var(--color-muted)]">
                        {feedbackSent.has(message.copilot_message_id)
                          ? "Feedback recorded"
                          : "Helpful?"}
                      </span>
                      <button
                        type="button"
                        aria-label="Mark answer helpful"
                        disabled={feedbackSent.has(
                          message.copilot_message_id,
                        )}
                        className="rounded-lg p-1.5 hover:bg-emerald-100 disabled:opacity-40"
                        onClick={() =>
                          void sendFeedback(
                            message.copilot_message_id,
                            "HELPFUL",
                          )
                        }
                      >
                        <ThumbsUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label="Mark answer not helpful"
                        disabled={feedbackSent.has(
                          message.copilot_message_id,
                        )}
                        className="rounded-lg p-1.5 hover:bg-red-100 disabled:opacity-40"
                        onClick={() =>
                          void sendFeedback(
                            message.copilot_message_id,
                            "NOT_HELPFUL",
                          )
                        }
                      >
                        <ThumbsDown className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </>
                )}
              </article>
            ))}
            {loading && (
              <p
                className="flex items-center gap-2 text-sm text-[var(--color-muted)]"
                aria-live="polite"
              >
                <LoaderCircle className="h-4 w-4 animate-spin" />
                Assembling permitted context…
              </p>
            )}
            {error && (
              <div
                role="alert"
                className="rounded-xl bg-red-50 p-3 text-sm text-red-900"
              >
                <p>{error}</p>
                {error.includes("not reachable") && (
                  <button
                    type="button"
                    className="mt-2 inline-flex items-center gap-1 rounded-lg bg-red-100 px-2 py-1 font-bold hover:bg-red-200"
                    onClick={() => void openCopilot()}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Retry connection
                  </button>
                )}
              </div>
            )}
            <div ref={scrollAnchor} />
          </div>

          <form
            onSubmit={(event) => void submit(event)}
            className="border-t border-slate-300 bg-slate-50 p-4"
          >
            <label htmlFor="copilot-question" className="sr-only">
              Ask about NeuroX
            </label>
            <div className="flex items-end gap-2">
              <textarea
                id="copilot-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={2}
                maxLength={1200}
                placeholder="Ask what happened, why, or how to use this screen…"
                className="min-h-12 flex-1 resize-none rounded-2xl border border-slate-200 bg-white p-3 text-sm shadow-[var(--shadow-inset-sm)] outline-none focus:ring-2 focus:ring-violet-600"
              />
              <Button
                type="submit"
                variant="primary"
                title="Send question"
                aria-label="Send question"
                disabled={loading || question.trim().length < 2}
                className="h-12 w-12 shrink-0 rounded-full p-0 disabled:bg-slate-300 disabled:text-slate-700 disabled:shadow-none"
              >
                <span
                  className="text-xl leading-none"
                  aria-hidden="true"
                >
                  ➤
                </span>
              </Button>
            </div>
          </form>
        </section>
      )}

      {tour && tourTarget && (
        <aside
          role="dialog"
          aria-label="Guided application tour"
          className="fixed bottom-4 left-1/2 z-[70] w-[min(94vw,560px)] -translate-x-1/2 rounded-2xl bg-slate-950 p-5 text-white shadow-2xl"
        >
          <p className="text-xs font-bold uppercase tracking-wider text-violet-300">
            Guided workflow · step {tour.index + 1} of{" "}
            {tour.targetIds.length}
          </p>
          <p className="mt-2 font-bold">{tourTarget.title}</p>
          <p className="mt-1 text-sm text-slate-300">
            {tourTarget.description}
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              className="rounded-xl px-3 py-2 text-sm hover:bg-white/10"
              onClick={endTour}
            >
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
                className="inline-flex items-center gap-1 rounded-xl bg-violet-600 px-4 py-2 text-sm font-bold hover:bg-violet-500"
                onClick={() =>
                  tour.index === tour.targetIds.length - 1
                    ? endTour()
                    : moveTour(tour.index + 1)
                }
              >
                {tour.index === tour.targetIds.length - 1
                  ? "Finish"
                  : "Next"}
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
