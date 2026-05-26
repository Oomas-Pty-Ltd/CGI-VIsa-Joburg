import React from "react";
import { AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

/**
 * ConfirmDialog — replacement for `window.confirm` in destructive flows.
 *
 * Two ways to use it:
 *
 *   1. Controlled with `open` + `onOpenChange` — pair it with a state
 *      variable that holds the row being confirmed:
 *
 *        const [confirming, setConfirming] = useState(null);
 *        ...
 *        <Button onClick={() => setConfirming(row)}>Delete</Button>
 *        <ConfirmDialog
 *          open={!!confirming}
 *          onOpenChange={(o) => !o && setConfirming(null)}
 *          title="Delete service?"
 *          description={`This removes "${confirming?.name}". Existing applications keep working.`}
 *          confirmLabel="Delete"
 *          destructive
 *          onConfirm={async () => { await doDelete(confirming); setConfirming(null); }}
 *        />
 *
 *   2. Imperative via `useConfirm()` hook (below) for simple flows.
 *
 * Always prefer this over `window.confirm`: styled, focus-trapped, escape-
 * closeable, doesn't block the event loop, and the operator can read the
 * description without a cramped browser native chrome.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title = "Are you sure?",
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  loading = false,
}) {
  const handleConfirm = async () => {
    try {
      await onConfirm?.();
    } finally {
      // Caller closes via onOpenChange in their onConfirm — leave it
      // there so async errors can keep the dialog open if needed.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <div className="flex items-start gap-3">
            {destructive && (
              <div className="h-8 w-8 rounded-full bg-destructive/10 flex items-center justify-center shrink-0">
                <AlertTriangle className="h-4 w-4 text-destructive" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <DialogTitle>{title}</DialogTitle>
              {description && (
                <DialogDescription className="mt-1.5 text-sm leading-relaxed">
                  {description}
                </DialogDescription>
              )}
            </div>
          </div>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange?.(false)}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={handleConfirm}
            disabled={loading}
          >
            {loading ? "Working…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
