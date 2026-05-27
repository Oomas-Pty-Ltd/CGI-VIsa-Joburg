import React from "react";
import { Check, ChevronRight, X, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * OnboardingCard — first-run setup guide rendered at the top of a
 * dashboard Overview, or re-opened later via a topbar "Setup guide" link.
 *
 * Steps auto-mark complete from backend signals (e.g. `services_count > 0`)
 * — operators don't have to manually check things off. The card also
 * shows progress via a tiny counter ("2 of 3 complete").
 *
 * Props:
 *   title?       — heading text          (default: "Set up your bot")
 *   description? — sub-heading copy
 *   steps        — [{
 *     key:        string,        unique
 *     title:      string,        short imperative
 *     description: string,       one-line elaboration
 *     done:       boolean,       completion state
 *     actionLabel?: string,      defaults to "Open" / "Done" by state
 *     onAction?:  () => void     called when the step CTA is clicked
 *   }]
 *   onDismiss?   — () => void    hides the card and remembers the choice
 *                                in the parent (typically localStorage)
 *   compact?     — bool          render in modal/dialog mode (no dismiss
 *                                button, tighter padding)
 */
export function OnboardingCard({
  title = "Set up your bot",
  description = "Three quick steps and your assistant is live.",
  steps = [],
  onDismiss,
  compact = false,
}) {
  const doneCount = steps.filter((s) => s.done).length;
  const allDone = doneCount === steps.length;

  return (
    <section
      className={cn(
        "rounded-lg border border-border bg-card shadow-sm",
        // The inline (Overview) variant gets a subtle indigo halo so it
        // stands out as a "do this first" cue against the regular cards.
        // The compact (modal) variant inherits the dialog's own framing.
        !compact && "ring-1 ring-primary/15",
      )}
    >
      <header
        className={cn(
          "flex items-start justify-between gap-4 border-b border-border",
          compact ? "px-5 py-4" : "px-5 py-4",
        )}
      >
        <div className="flex items-start gap-3 min-w-0">
          <div className="h-9 w-9 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
            <Sparkles className="h-4 w-4 text-primary" aria-hidden />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold tracking-tight text-foreground">
              {title}
            </h3>
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
              {description}
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
              {doneCount} of {steps.length} complete
            </p>
          </div>
        </div>
        {!compact && onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss setup guide"
            title="Dismiss — you can re-open from the top bar"
            className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </header>

      <ol className="divide-y divide-border">
        {steps.map((step, idx) => (
          <li
            key={step.key}
            className={cn(
              "flex items-center gap-3 px-5 py-3",
              step.done && "opacity-70",
            )}
          >
            <span
              className={cn(
                "shrink-0 h-7 w-7 rounded-full flex items-center justify-center text-xs font-semibold",
                step.done
                  ? "bg-success/15 text-success"
                  : "bg-muted text-muted-foreground border border-border",
              )}
              aria-hidden
            >
              {step.done ? <Check className="h-3.5 w-3.5" /> : idx + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn("text-sm font-medium", step.done ? "text-muted-foreground line-through" : "text-foreground")}>
                {step.title}
              </p>
              {step.description && (
                <p className="text-xs text-muted-foreground leading-snug mt-0.5">
                  {step.description}
                </p>
              )}
            </div>
            {step.onAction && (
              <Button
                size="sm"
                variant={step.done ? "ghost" : "outline"}
                onClick={step.onAction}
                className="shrink-0"
              >
                {step.actionLabel || (step.done ? "Review" : "Open")}
                <ChevronRight className="h-3.5 w-3.5 ml-1" />
              </Button>
            )}
          </li>
        ))}
      </ol>

      {allDone && (
        <div className="px-5 py-3 border-t border-border bg-success/5 text-xs text-success font-medium">
          You're all set — your bot is live.
        </div>
      )}
    </section>
  );
}
