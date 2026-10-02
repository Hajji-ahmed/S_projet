"use client";

import { Check, FileSpreadsheet } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

// Deux étapes : le mapping des colonnes ne s'affiche qu'en secours, dans l'étape Fichier
export const STEPS = ["Fichier", "Validation"] as const;

/** Étapes de l'import : terminées (coche), en cours (teal), à venir (gris). */
export function ImportStepper({ current }: { current: number }) {
  return (
    <ol
      className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2"
      aria-label="Étapes de l'import"
    >
      {STEPS.map((label, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={label}
            className="flex items-center gap-2 text-sm"
            aria-current={active ? "step" : undefined}
          >
            <span
              className={cn(
                "grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-semibold",
                done && "bg-simtis-primary text-white",
                active && "bg-simtis-light text-simtis-primary ring-2 ring-simtis-primary",
                !done && !active && "bg-simtis-neutral-bg text-simtis-muted",
              )}
            >
              {done ? <Check className="h-4 w-4" aria-hidden /> : index + 1}
            </span>
            <span
              className={cn(
                "font-medium",
                active ? "text-simtis-primary" : done ? "text-simtis-text" : "text-simtis-muted",
              )}
            >
              {label}
            </span>
            {index < STEPS.length - 1 && (
              <span className="mx-1 hidden h-px w-8 bg-simtis-border sm:block" aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}

type FileDropzoneProps = {
  file: File | null;
  onFile: (file: File) => void;
  disabled?: boolean;
};

/** Zone de dépôt du relevé : glisser-déposer, ou bouton « Choisir un fichier ». */
export function FileDropzone({ file, onFile, disabled }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const dropped = event.dataTransfer.files[0];
        if (dropped && !disabled) onFile(dropped);
      }}
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-[12px] border-2 border-dashed px-4 py-8 text-center transition-colors duration-200",
        over
          ? "border-simtis-primary bg-simtis-light"
          : "border-simtis-border bg-simtis-background",
      )}
    >
      <FileSpreadsheet className="h-10 w-10 text-simtis-primary" strokeWidth={1.5} aria-hidden />
      {file ? (
        <p className="text-sm">
          <span className="font-medium text-simtis-text">{file.name}</span>
          <span className="text-simtis-muted">
            {" "}
            · {Math.max(1, Math.round(file.size / 1024))} Ko
          </span>
        </p>
      ) : (
        <p className="text-sm text-simtis-text">Glissez votre fichier Excel ici</p>
      )}
      <p className="text-xs text-simtis-muted">{file ? "ou remplacez-le" : "ou"}</p>
      <Button
        variant="secondary"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        aria-label={file ? "Choisir un autre fichier" : "Choisir un fichier"}
      >
        {file ? "Choisir un autre fichier" : "Choisir un fichier"}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="hidden"
        data-testid="releve-fichier"
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          if (chosen) onFile(chosen);
          event.target.value = ""; // permet de rechoisir le même fichier
        }}
      />
      <p className="text-xs text-simtis-muted">Excel .xlsx, 5 Mo au plus</p>
    </div>
  );
}
