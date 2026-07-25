"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, FileText, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function CaseDocumentReview({
  caseId,
  caseVersion,
}: {
  caseId: string;
  caseVersion: number;
}) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState("");
  const [editingField, setEditingField] = useState("");
  const [correction, setCorrection] = useState("");
  const [reason, setReason] = useState("");
  const documents = useQuery({
    queryKey: ["documents", caseId],
    queryFn: () => api.listCaseDocuments(caseId),
  });
  const selected = useMemo(
    () =>
      (documents.data ?? []).find((item) => item.document_id === selectedId)
      ?? documents.data?.[0],
    [documents.data, selectedId],
  );
  const pages = useQuery({
    queryKey: ["document-pages", selected?.document_id],
    queryFn: () => api.listDocumentPages(selected!.document_id),
    enabled: Boolean(selected?.document_id),
  });
  const fields = useQuery({
    queryKey: ["document-fields", selected?.document_id],
    queryFn: () => api.listDocumentFields(selected!.document_id),
    enabled: Boolean(selected?.document_id),
  });
  const content = useQuery({
    queryKey: ["document-content", selected?.document_id],
    queryFn: () => api.downloadDocument(selected!.document_id),
    enabled: selected?.processing_status === "READY",
    staleTime: Number.POSITIVE_INFINITY,
  });
  const objectUrl = useMemo(
    () => (content.data ? URL.createObjectURL(content.data) : ""),
    [content.data],
  );
  useEffect(
    () => () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    },
    [objectUrl],
  );
  const correct = useMutation({
    mutationFn: (fieldId: string) =>
      api.correctDocumentField(
        selected!.document_id,
        fieldId,
        correction,
        reason,
        caseVersion,
      ),
    onSuccess: async () => {
      setEditingField("");
      setCorrection("");
      setReason("");
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["document-fields", selected?.document_id],
        }),
        queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["events", caseId] }),
      ]);
    },
  });

  return (
    <Card>
      <div className="mb-6 flex items-center gap-3">
        <FileText className="h-6 w-6 text-[var(--color-accent)]" />
        <div>
          <h2 className="font-display text-xl font-bold">Document evidence</h2>
          <p className="text-sm text-[var(--color-muted)]">
            Authorized source rendering, masked extraction, and versioned correction.
          </p>
        </div>
      </div>
      {documents.isLoading && <p aria-live="polite">Loading documents…</p>}
      {!documents.isLoading && !selected && (
        <p className="text-sm text-[var(--color-muted)]">No documents uploaded.</p>
      )}
      {selected && (
        <>
          <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Case documents">
            {(documents.data ?? []).map((document) => (
              <button
                key={document.document_id}
                type="button"
                role="tab"
                aria-selected={document.document_id === selected.document_id}
                onClick={() => setSelectedId(document.document_id)}
                className={`rounded-full px-4 py-2 text-sm font-bold ${
                  document.document_id === selected.document_id
                    ? "bg-slate-900 text-white"
                    : "bg-slate-200 text-slate-800"
                }`}
              >
                {document.original_filename}
              </button>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="font-bold">{selected.original_filename}</p>
                  <p className="text-xs text-[var(--color-muted)]">
                    {selected.processing_status} · malware {selected.malware_status}
                  </p>
                </div>
                {objectUrl && (
                  <a href={objectUrl} download={selected.original_filename}>
                    <Button variant="secondary" className="gap-2">
                      <Download className="h-4 w-4" /> Download
                    </Button>
                  </a>
                )}
              </div>
              {objectUrl ? (
                <iframe
                  src={objectUrl}
                  title={`Source document ${selected.original_filename}`}
                  className="h-[36rem] w-full rounded-2xl border border-slate-300 bg-white"
                />
              ) : (
                <div className="grid h-64 place-items-center rounded-2xl bg-slate-100 text-sm text-slate-600">
                  {content.isError
                    ? "Authorized content could not be loaded."
                    : "Source rendering becomes available after malware scan and parsing."}
                </div>
              )}
            </div>
            <div className="space-y-4">
              <h3 className="font-bold">Extracted fields and source locations</h3>
              {(fields.data ?? []).map((field) => (
                <article
                  key={field.extracted_field_id}
                  className="rounded-2xl p-4 shadow-[var(--shadow-inset-sm)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold">{field.field_name.replaceAll("_", " ")}</p>
                      <p className="text-sm">{field.field_value_masked ?? "Not extracted"}</p>
                      <p className="mt-1 text-xs text-[var(--color-muted)]">
                        Page {field.source_page ?? "?"} · confidence{" "}
                        {field.confidence == null
                          ? "unknown"
                          : `${Math.round(field.confidence * 100)}%`}
                        {" · "}
                        {field.human_verified ? "human verified" : field.extractor_type}
                      </p>
                      {Object.keys(field.source_bbox).length > 0 && (
                        <code className="mt-2 block break-all text-xs text-[var(--color-muted)]">
                          box {JSON.stringify(field.source_bbox)}
                        </code>
                      )}
                    </div>
                    <Button
                      type="button"
                      variant="icon"
                      aria-label={`Correct ${field.field_name}`}
                      onClick={() => {
                        setEditingField(field.extracted_field_id);
                        setCorrection("");
                        setReason("");
                      }}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </div>
                  {editingField === field.extracted_field_id && (
                    <div className="mt-4 space-y-3">
                      <Input
                        value={correction}
                        onChange={(event) => setCorrection(event.target.value)}
                        placeholder="Correct value"
                        aria-label={`Correct value for ${field.field_name}`}
                      />
                      <Input
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                        placeholder="Reason for correction"
                        aria-label="Correction reason"
                      />
                      {correct.isError && (
                        <p role="alert" className="text-sm text-red-800">
                          {correct.error.message}
                        </p>
                      )}
                      <Button
                        type="button"
                        variant="primary"
                        className="gap-2"
                        disabled={
                          correct.isPending
                          || correction.trim().length === 0
                          || reason.trim().length < 3
                        }
                        onClick={() => correct.mutate(field.extracted_field_id)}
                      >
                        <Check className="h-4 w-4" /> Save correction
                      </Button>
                    </div>
                  )}
                </article>
              ))}
              {(fields.data ?? []).length === 0 && (
                <p className="text-sm text-[var(--color-muted)]">
                  No structured fields are available yet.
                </p>
              )}
              <details className="rounded-2xl border border-slate-200 p-4">
                <summary className="cursor-pointer font-bold">
                  Masked page text ({pages.data?.length ?? 0} pages)
                </summary>
                <div className="mt-4 space-y-4">
                  {(pages.data ?? []).map((page) => (
                    <section key={page.page_id}>
                      <p className="mb-1 text-xs font-bold">
                        Page {page.page_number} · OCR{" "}
                        {page.ocr_confidence == null
                          ? "native"
                          : `${Math.round(page.ocr_confidence * 100)}%`}
                      </p>
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-3 text-xs text-slate-100">
                        {page.text_content}
                      </pre>
                    </section>
                  ))}
                </div>
              </details>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
