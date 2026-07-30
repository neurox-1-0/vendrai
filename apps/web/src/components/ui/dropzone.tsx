"use client";

import * as React from "react"
import { FileCheck2, UploadCloud } from "lucide-react"

export interface DropzoneProps {
  id: string;
  label: string;
  accept: string;
  multiple?: boolean;
  files: File[];
  onFilesChange: (files: File[]) => void;
  hint: string;
}

/**
 * Shared file-upload control. Keeps the exact `<label htmlFor>` + `sr-only
 * <input type="file">` pairing the two intake forms used independently, so
 * click-to-browse, keyboard access, and Playwright's generic
 * `input[type="file"]` selector all keep working unchanged. Drag-and-drop is
 * additive on top of that -- browsing still works identically without it.
 */
function Dropzone({ id, label, accept, multiple = true, files, onFilesChange, hint }: DropzoneProps) {
  const [dragActive, setDragActive] = React.useState(false);

  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-bold">{label}</label>
      <label
        htmlFor={id}
        onDragOver={(event) => { event.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          const dropped = Array.from(event.dataTransfer.files);
          if (dropped.length) onFilesChange(multiple ? dropped : dropped.slice(0, 1));
        }}
        className={`flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed p-10 text-center transition-colors duration-200 focus-within:ring-2 focus-within:ring-[var(--color-accent)]/40 ${
          dragActive
            ? "border-[var(--color-accent)] bg-[var(--color-accent-light)]"
            : "border-[var(--color-border-strong)] hover:bg-[var(--color-surface-muted)]"
        }`}
      >
        <UploadCloud className="mb-3 h-10 w-10 text-[var(--color-accent)]" aria-hidden="true" />
        <span className="font-bold">Choose PDF documents</span>
        <span className="mt-1 text-sm text-[var(--color-muted)]">{hint}</span>
        <input
          id={id}
          type="file"
          accept={accept}
          multiple={multiple}
          className="sr-only"
          onChange={(event) => onFilesChange(Array.from(event.target.files ?? []))}
        />
      </label>
      <ul className="mt-4 space-y-2" aria-live="polite">
        {files.map((file) => (
          <li key={`${file.name}-${file.size}`} className="flex items-center gap-2 text-sm">
            <FileCheck2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
            {file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB
          </li>
        ))}
      </ul>
    </div>
  );
}

export { Dropzone };
