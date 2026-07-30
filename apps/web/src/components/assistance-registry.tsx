"use client";

import {
  createContext,
  type RefCallback,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from "react";

export interface AssistanceTargetDefinition {
  id: string;
  title: string;
  description: string;
  tour?: string;
  order?: number;
}

export interface RegisteredAssistanceTarget
  extends AssistanceTargetDefinition {
  element: HTMLElement;
}

export interface AssistanceTargetContext {
  target_id: string;
  title: string;
  description: string;
}

interface AssistanceRegistryValue {
  register: (
    definition: AssistanceTargetDefinition,
    element: HTMLElement,
  ) => () => void;
  list: (tour?: string) => RegisteredAssistanceTarget[];
  get: (id: string) => RegisteredAssistanceTarget | undefined;
  spotlight: (id: string) => boolean;
  clearSpotlight: () => void;
  context: () => AssistanceTargetContext[];
}

const AssistanceRegistryContext =
  createContext<AssistanceRegistryValue | null>(null);

function isVisible(target: RegisteredAssistanceTarget): boolean {
  return (
    target.element.isConnected
    && target.element.getClientRects().length > 0
    && target.element.getAttribute("aria-hidden") !== "true"
  );
}

export function AssistanceProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const targets = useRef(
    new Map<string, RegisteredAssistanceTarget>(),
  );
  const spotlighted = useRef<{
    element: HTMLElement;
    previousTabIndex: string | null;
  } | null>(null);
  const spotlightTimer = useRef<number | null>(null);

  const clearSpotlight = useCallback(() => {
    if (spotlightTimer.current !== null) {
      window.clearTimeout(spotlightTimer.current);
      spotlightTimer.current = null;
    }
    const current = spotlighted.current;
    if (!current) return;
    current.element.classList.remove("copilot-spotlight");
    if (current.previousTabIndex === null) {
      current.element.removeAttribute("tabindex");
    } else {
      current.element.setAttribute(
        "tabindex",
        current.previousTabIndex,
      );
    }
    spotlighted.current = null;
  }, []);

  const register = useCallback(
    (
      definition: AssistanceTargetDefinition,
      element: HTMLElement,
    ) => {
      const registered = { ...definition, element };
      targets.current.set(definition.id, registered);
      return () => {
        if (targets.current.get(definition.id)?.element === element) {
          targets.current.delete(definition.id);
          if (spotlighted.current?.element === element) {
            clearSpotlight();
          }
        }
      };
    },
    [clearSpotlight],
  );

  const list = useCallback(
    (tour?: string) =>
      [...targets.current.values()]
        .filter(
          (target) =>
            isVisible(target)
            && (tour === undefined || target.tour === tour),
        )
        .sort(
          (left, right) =>
            (left.order ?? Number.MAX_SAFE_INTEGER)
              - (right.order ?? Number.MAX_SAFE_INTEGER)
            || left.id.localeCompare(right.id),
        ),
    [],
  );

  const get = useCallback(
    (id: string) => {
      const target = targets.current.get(id);
      return target && isVisible(target) ? target : undefined;
    },
    [],
  );

  const spotlight = useCallback(
    (id: string) => {
      const target = targets.current.get(id);
      if (!target || !isVisible(target)) return false;
      clearSpotlight();
      const previousTabIndex =
        target.element.getAttribute("tabindex");
      if (previousTabIndex === null) {
        target.element.setAttribute("tabindex", "-1");
      }
      target.element.classList.add("copilot-spotlight");
      target.element.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      target.element.focus({ preventScroll: true });
      spotlighted.current = {
        element: target.element,
        previousTabIndex,
      };
      spotlightTimer.current = window.setTimeout(
        clearSpotlight,
        10_000,
      );
      return true;
    },
    [clearSpotlight],
  );

  const context = useCallback(
    () =>
      list().slice(0, 40).map((target) => ({
        target_id: target.id,
        title: target.title,
        description: target.description,
      })),
    [list],
  );

  useEffect(() => clearSpotlight, [clearSpotlight]);

  const value = useMemo(
    () => ({
      register,
      list,
      get,
      spotlight,
      clearSpotlight,
      context,
    }),
    [
      clearSpotlight,
      context,
      get,
      list,
      register,
      spotlight,
    ],
  );

  return (
    <AssistanceRegistryContext.Provider value={value}>
      {children}
    </AssistanceRegistryContext.Provider>
  );
}

export function useAssistanceRegistry(): AssistanceRegistryValue {
  const registry = useContext(AssistanceRegistryContext);
  if (!registry) {
    throw new Error(
      "useAssistanceRegistry requires AssistanceProvider",
    );
  }
  return registry;
}

export function useAssistanceTarget<
  T extends HTMLElement = HTMLDivElement,
>(
  definition: AssistanceTargetDefinition,
): {
  ref: RefCallback<T>;
  "data-assist-id": string;
  "data-assist-title": string;
} {
  const registry = useAssistanceRegistry();
  const {
    id,
    title,
    description,
    tour,
    order,
  } = definition;
  const stableDefinition = useMemo(
    () => ({ id, title, description, tour, order }),
    [description, id, order, title, tour],
  );
  const cleanup = useRef<(() => void) | null>(null);
  const ref = useCallback<RefCallback<T>>(
    (element) => {
      cleanup.current?.();
      cleanup.current = element
        ? registry.register(stableDefinition, element)
        : null;
    },
    [registry, stableDefinition],
  );
  useEffect(
    () => () => {
      cleanup.current?.();
      cleanup.current = null;
    },
    [],
  );
  return {
    ref,
    "data-assist-id": stableDefinition.id,
    "data-assist-title": stableDefinition.title,
  };
}
