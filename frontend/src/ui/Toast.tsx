import {
  createContext, useCallback, useContext, useMemo, useRef, useState,
} from "react";
import type { ReactNode } from "react";
import { IconAlert, IconCheck, IconClose, IconInfo } from "../icons";
import { Button } from "./Button";
import { cn } from "./cn";

/* Toasts.
 *
 * Replaces two things: the error banner that used to push the whole layout
 * down when a request failed, and the "last action" panel that reported the
 * outcome of a System Control operation several hundred pixels away from the
 * button that caused it.
 *
 * Errors do not auto-dismiss. A failed commit that vanishes after four seconds
 * is a failed commit nobody can quote back.
 */

export type ToastTone = "info" | "ok" | "warn" | "danger";

interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  detail?: string;
  /** One way onward. A toast that reports something is now pending has to be
   *  able to hand the reviewer the thing that is pending. */
  action?: { label: string; onClick: () => void };
}

interface ToastContextValue {
  push: (t: Omit<Toast, "id">) => void;
  notify: (title: string, detail?: string) => void;
  error: (title: string, detail?: string) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 5200;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = nextId.current++;
      // Cap the stack. Four is what fits above the status strip without the
      // oldest scrolling off behind it.
      setToasts((prev) => [...prev.slice(-3), { ...t, id }]);
      if (t.tone !== "danger") {
        setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      }
    },
    [dismiss]
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      dismiss,
      notify: (title, detail) => push({ tone: "info", title, detail }),
      error: (title, detail) => push({ tone: "danger", title, detail }),
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        // Assertive would interrupt a screen reader mid-sentence for what is
        // usually a confirmation. Errors are still read, just not barged in.
        role="status"
        aria-live="polite"
        className={cn(
          "pointer-events-none fixed bottom-[calc(var(--shell-strip-h)+12px)]",
          "right-3 z-[var(--z-toast)] flex w-[min(380px,calc(100vw-24px))]",
          "flex-col gap-2"
        )}
      >
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const TONE: Record<ToastTone, { cls: string; Icon: typeof IconInfo }> = {
  info: { cls: "border-strong text-fg", Icon: IconInfo },
  ok: { cls: "border-ok-border text-ok-text", Icon: IconCheck },
  warn: { cls: "border-warn-border text-warn-text", Icon: IconAlert },
  danger: { cls: "border-danger-border text-danger-text", Icon: IconAlert },
};

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const { cls, Icon } = TONE[toast.tone];
  return (
    <div
      className={cn(
        "pointer-events-auto flex items-start gap-2.5 rounded-md border",
        "bg-overlay p-2.5 shadow-e3 animate-slide-in",
        cls
      )}
    >
      <Icon size={15} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-base font-medium text-fg">{toast.title}</div>
        {toast.detail && (
          <div className="mt-0.5 break-words font-mono text-xs text-muted">
            {toast.detail}
          </div>
        )}
        {toast.action && (
          <Button
            size="xs"
            className="mt-1.5"
            onClick={() => {
              toast.action?.onClick();
              onDismiss();
            }}
          >
            {toast.action.label}
          </Button>
        )}
      </div>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded-xs p-0.5 text-faint transition-colors hover:bg-hover hover:text-fg"
      >
        <IconClose size={13} />
      </button>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
