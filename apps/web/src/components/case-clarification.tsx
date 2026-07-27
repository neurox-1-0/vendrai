"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleHelp, Send } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAssistanceTarget } from "@/components/assistance-registry";

export function CaseClarification({
  caseId,
  caseVersion,
}: {
  caseId: string;
  caseVersion: number;
}) {
  const queryClient = useQueryClient();
  const assistance = useAssistanceTarget({
    id: "case.clarification",
    title: "Clarification request",
    description:
      "Answer only the missing or contradictory fields requested by the workflow, then resume from the durable checkpoint.",
    tour: "case.review-tour",
    order: 20,
  });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const tasks = useQuery({
    queryKey: ["clarifications"],
    queryFn: api.listClarifications,
  });
  const task = useMemo(
    () => (tasks.data ?? []).find((item) => item.case_id === caseId),
    [caseId, tasks.data],
  );
  const respond = useMutation({
    mutationFn: () => api.respondToClarification(task!, answers, caseVersion),
    onSuccess: async () => {
      setAnswers({});
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["clarifications"] }),
        queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["events", caseId] }),
      ]);
    },
  });
  if (!task) return null;
  const answerable = task.questions.filter(
    (question) => question.field_name && question.field_name !== "document",
  );

  return (
    <Card
      {...assistance}
      className="border border-amber-300 bg-amber-50/70"
    >
      <div className="mb-5 flex items-center gap-3">
        <CircleHelp className="h-6 w-6 text-amber-800" />
        <div>
          <h2 className="font-display text-xl font-bold">Clarification required</h2>
          <p className="text-sm text-slate-700">
            Answer only the requested fields. Sensitive answers are encrypted and masked.
          </p>
        </div>
      </div>
      <div className="space-y-4">
        {task.questions.map((question, index) => {
          const key = question.field_name ?? question.question_id ?? `answer-${index}`;
          return (
            <div key={question.question_id ?? `${key}-${index}`}>
              <label htmlFor={`clarification-${key}`} className="mb-2 block text-sm font-bold">
                {question.text ?? `Provide ${key.replaceAll("_", " ")}`}
              </label>
              {question.field_name === "document" ? (
                <p className="rounded-xl bg-white p-3 text-sm">
                  Upload the requested document from the intake flow, then resubmit.
                </p>
              ) : (
                <Input
                  id={`clarification-${key}`}
                  value={answers[key] ?? ""}
                  onChange={(event) =>
                    setAnswers((current) => ({ ...current, [key]: event.target.value }))
                  }
                />
              )}
            </div>
          );
        })}
      </div>
      {respond.isError && (
        <p role="alert" className="mt-4 text-sm text-red-900">
          {respond.error.message}
        </p>
      )}
      {answerable.length > 0 && (
        <Button
          type="button"
          variant="primary"
          className="mt-5 gap-2"
          disabled={
            respond.isPending
            || answerable.some(
              (question, index) =>
                !answers[
                  question.field_name ?? question.question_id ?? `answer-${index}`
                ]?.trim(),
            )
          }
          onClick={() => respond.mutate()}
        >
          <Send className="h-4 w-4" /> Submit clarification
        </Button>
      )}
    </Card>
  );
}
