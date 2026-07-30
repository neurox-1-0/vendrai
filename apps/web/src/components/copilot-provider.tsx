"use client";

import {
  createContext,
  useContext,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAssistanceRegistry, type RegisteredAssistanceTarget } from "@/components/assistance-registry";
import { api, type CopilotMessage, type CopilotSession } from "@/lib/api";

const SESSION_STORAGE_KEY = "neurox-copilot-session";

export interface TourState {
  group: string;
  targetIds: string[];
  index: number;
}

function caseIdFromPath(pathname: string): string | undefined {
  const match = pathname.match(/^\/cases\/([0-9a-f]{8}-[0-9a-f-]{27,})/i);
  return match?.[1];
}

function friendlyError(error: unknown): string {
  const message = error instanceof Error ? error.message : "COPILOT_UNAVAILABLE";
  if (message.toLowerCase().includes("failed to fetch") || message.includes("ECONNREFUSED")) {
    return "Vendrai services are not reachable yet. Start the product runtime, then retry.";
  }
  if (message.includes("LLM_AUTH_INVALID")) {
    return "Gemini rejected the configured key. Ask an administrator to verify it.";
  }
  if (message.includes("LLM_QUOTA_EXCEEDED")) {
    return "Gemini quota is exhausted. Deterministic work is preserved for retry.";
  }
  return message.replaceAll("_", " ");
}

interface CopilotContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  openCopilot: () => void;
  messages: CopilotMessage[];
  question: string;
  setQuestion: (question: string) => void;
  loading: boolean;
  error: string;
  submit: (event: FormEvent) => void;
  /** Fire a canned question directly (quick actions), bypassing the textarea. */
  ask: (text: string) => void;
  runAction: (action: CopilotMessage["ui_actions"][number]) => void;
  sendFeedback: (messageId: string, rating: "HELPFUL" | "NOT_HELPFUL") => void;
  feedbackSent: ReadonlySet<string>;
  tour: TourState | null;
  tourTarget: RegisteredAssistanceTarget | undefined;
  moveTour: (index: number) => void;
  endTour: () => void;
  scrollAnchor: RefObject<HTMLDivElement | null>;
}

const CopilotContext = createContext<CopilotContextValue | null>(null);

export function useCopilotContext(): CopilotContextValue {
  const context = useContext(CopilotContext);
  if (!context) throw new Error("useCopilotContext must be used within CopilotProvider");
  return context;
}

/**
 * Owns the copilot's session/message/tour state exactly once, so the
 * floating panel and the dashboard's docked assistant card share one live
 * conversation instead of each keeping its own disconnected copy.
 */
export function CopilotProvider({ children }: { children: React.ReactNode }) {
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
  const [feedbackSent, setFeedbackSent] = useState<Set<string>>(() => new Set());
  const scrollAnchor = useRef<HTMLDivElement>(null);
  const caseId = useMemo(() => caseIdFromPath(pathname), [pathname]);
  const tourTarget = tour ? assistance.get(tour.targetIds[tour.index]) : undefined;

  async function ensureSession(): Promise<CopilotSession> {
    if (session) return session;
    const stored = typeof window === "undefined" ? null : window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (stored) {
      try {
        const history = await api.listCopilotMessages(stored);
        const restored: CopilotSession = {
          copilot_session_id: stored,
          context_case_id: caseId ?? null,
          title: "Application help",
          help_pack_version: history.at(-1)?.citations.at(0)?.help_pack_version ?? "current",
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
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, created.copilot_session_id);
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

  async function sendQuestion(text: string) {
    const normalized = text.trim();
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
      window.requestAnimationFrame(() => scrollAnchor.current?.scrollIntoView({ behavior: "smooth" }));
    } catch (requestError) {
      setError(friendlyError(requestError));
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendQuestion(question);
  }

  function ask(text: string) {
    void sendQuestion(text);
  }

  function endTour() {
    assistance.clearSpotlight();
    setTour(null);
  }

  function moveTour(index: number) {
    if (!tour) return;
    const bounded = Math.max(0, Math.min(index, tour.targetIds.length - 1));
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
      const nextTour = { group: action.target, targetIds: targets.map((target) => target.id), index: 0 };
      setTour(nextTour);
      assistance.spotlight(nextTour.targetIds[0]);
      setOpen(false);
      return;
    }
    if (action.action_type === "OPEN_PANEL") {
      // The notification bell is now global (mounted in the top nav on every
      // route), so opening its panel no longer needs to navigate home first.
      if (action.target === "notifications") {
        window.dispatchEvent(new CustomEvent("neurox:open-panel", { detail: { panel: "notifications" } }));
      }
      return;
    }
    window.dispatchEvent(new CustomEvent("neurox:set-filter", { detail: { target: action.target } }));
  }

  async function sendFeedback(messageId: string, rating: "HELPFUL" | "NOT_HELPFUL") {
    if (feedbackSent.has(messageId)) return;
    setError("");
    try {
      await api.sendCopilotFeedback(messageId, rating);
      setFeedbackSent((current) => new Set(current).add(messageId));
    } catch (requestError) {
      setError(friendlyError(requestError));
    }
  }

  const value: CopilotContextValue = {
    open,
    setOpen,
    openCopilot: () => void openCopilot(),
    messages,
    question,
    setQuestion,
    loading,
    error,
    submit,
    ask,
    runAction,
    sendFeedback: (id, rating) => void sendFeedback(id, rating),
    feedbackSent,
    tour,
    tourTarget,
    moveTour,
    endTour,
    scrollAnchor,
  };

  return <CopilotContext.Provider value={value}>{children}</CopilotContext.Provider>;
}
