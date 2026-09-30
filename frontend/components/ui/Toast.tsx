"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

type ToastVariant = "success" | "error";
type ToastItem = { id: number; message: string; variant: ToastVariant };
type ToastContextValue = { toast: (message: string, variant?: ToastVariant) => void };

const TOAST_DURATION_MS = 4000;
const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const toast = useCallback((message: string, variant: ToastVariant = "success") => {
    const id = nextId.current++;
    setItems((current) => [...current, { id, message, variant }]);
    window.setTimeout(() => {
      setItems((current) => current.filter((item) => item.id !== id));
    }, TOAST_DURATION_MS);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col gap-3 sm:right-6 sm:bottom-6"
      >
        {items.map((item) => (
          <div
            key={item.id}
            role="status"
            className={cn(
              "pointer-events-auto min-w-64 rounded-lg border border-l-4 border-simtis-border bg-simtis-card px-4 py-3 text-sm text-simtis-text shadow-simtis",
              item.variant === "success" ? "border-l-simtis-success" : "border-l-simtis-danger",
            )}
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast doit être utilisé dans un <ToastProvider>.");
  return context;
}
