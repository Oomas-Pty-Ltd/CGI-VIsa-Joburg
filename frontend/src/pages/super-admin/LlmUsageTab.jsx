/**
 * LLM Cost dashboard — per-tenant cost gauge + daily bars + model split.
 *
 * Visual model: a single horizontal bar shows MTD spend as a percentage
 * of the monthly budget, with a vertical tick that marks the *calendar*
 * percentage of the month (today / days-in-month). When the filled
 * portion overshoots the tick, the tenant is burning faster than the
 * pro-rated budget — the bar tints toward destructive and a "trending
 * over budget" pill appears. That one visual answers "am I on track?"
 * without doing math.
 *
 * Lives under `super-admin/` so the LocalAdmin shell can reuse the same
 * component (the API endpoint already serves both roles).
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Sparkles, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Section } from "@/components/admin/Section";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

const ALL_TENANTS = "all";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const DEFAULT_DAYS = 30;

function fmtUSD(v) {
  if (v == null) return "—";
  if (Math.abs(v) >= 100) return `$${v.toFixed(2)}`;
  if (Math.abs(v) >= 1)   return `$${v.toFixed(2)}`;
  return `$${v.toFixed(4)}`;
}

function fmtTokens(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/**
 * Props:
 *   token           — auth JWT
 *   companies?      — when present, renders a tenant picker (super-admin mode)
 *                     and threads `?company_id=<id>` on the request. Omit for
 *                     local-admin / viewer — the backend reads the JWT's tenant.
 */
export default function LlmUsageTab({ token, companies }) {
  const isSuperAdmin = Array.isArray(companies);
  // Default to "All tenants" for super-admin so the first thing they see
  // is the platform-wide aggregate — that's what a super-admin actually
  // wants to know at a glance ("are we burning hot on OpenAI?").
  const [tenantId, setTenantId] = useState(isSuperAdmin ? ALL_TENANTS : "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(DEFAULT_DAYS);

  const fetchUsage = useCallback(async () => {
    if (isSuperAdmin && !tenantId) return;
    setLoading(true);
    try {
      const qs = new URLSearchParams({ days: String(days) });
      if (isSuperAdmin) qs.set("company_id", tenantId);
      const res = await fetch(`${API}/local-admin/llm-usage?${qs.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "Failed to load");
      setData(body);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, days, tenantId, isSuperAdmin]);

  useEffect(() => { fetchUsage(); }, [fetchUsage]);

  const tenantPicker = isSuperAdmin ? (
    <div className="w-72">
      <Label className="text-xs text-muted-foreground">Tenant</Label>
      <Select value={tenantId} onValueChange={setTenantId}>
        <SelectTrigger className="mt-1"><SelectValue placeholder="Select a tenant" /></SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_TENANTS}>
            <span className="font-medium">All tenants</span>
            <span className="text-muted-foreground ml-1">— platform-wide</span>
          </SelectItem>
          {companies.map((c) => (
            <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  ) : null;

  if (!data && loading) {
    return (
      <div className="space-y-4">
        {tenantPicker}
        <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="space-y-4">
        {tenantPicker}
        <div className="text-center py-12">
          <p className="text-sm text-muted-foreground mb-3">
            {isSuperAdmin && !tenantId ? "Pick a tenant above to view cost data." : "No usage data available yet."}
          </p>
          {tenantId && (
            <Button variant="outline" size="sm" onClick={fetchUsage}>
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Retry
            </Button>
          )}
        </div>
      </div>
    );
  }

  const { mtd, budget, daily, models, tenants = [], aggregate, projected, calendar_pct } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        {tenantPicker || <div />}
        <Button variant="outline" size="sm" onClick={fetchUsage} disabled={loading}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {/* Per-tenant view: full budget gauge. Aggregate view: a stripped-down
          "platform-wide totals" headline since there's no tenant budget to
          pace against. */}
      {budget
        ? <BudgetGauge mtd={mtd} budget={budget} />
        : <PlatformTotals mtd={mtd} projected={projected} calendarPct={calendar_pct} />}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard
          label="Calls this month"
          value={(mtd.calls || 0).toLocaleString()}
        />
        <MetricCard
          label="Prompt tokens"
          value={fmtTokens(mtd.prompt_tokens)}
        />
        <MetricCard
          label="Completion tokens"
          value={fmtTokens(mtd.completion_tokens)}
        />
      </div>

      <DailyBars daily={daily} days={days} onDaysChange={setDays} />

      {aggregate && <TenantRanking tenants={tenants} totalCost={mtd.cost_usd} />}

      <ModelBreakdown models={models} totalCost={mtd.cost_usd} />
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-lg border border-border bg-card px-5 py-4 shadow-sm">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className="text-2xl font-semibold tracking-tight text-foreground mt-0.5 tabular-nums">{value}</p>
    </div>
  );
}

/* ─── Budget gauge ──────────────────────────────────────────────────────── */

function BudgetGauge({ mtd, budget }) {
  const usedPct = Math.min(100, budget.used_pct ?? 0);
  const calPct  = Math.min(100, budget.calendar_pct ?? 0);
  const overPace = !!budget.over_pace;
  const projected = budget.projected ?? 0;
  const overProjection = projected > (budget.monthly_usd || 0);

  // The fill tints red when spend overshoots the calendar tick. Two-stage
  // gradient: green up to the tick, warning past it. Implemented as two
  // overlapping divs so the tick remains crisp.
  const fillBg = overPace
    ? "bg-gradient-to-r from-warning/80 to-destructive/80"
    : "bg-gradient-to-r from-success/70 to-success/90";

  return (
    <Section
      title="Monthly LLM cost"
      description={`Month-to-date spend against the ${fmtUSD(budget.monthly_usd)} budget. The tick marks where you'd be on pure calendar pacing (today is ${calPct.toFixed(0)}% of the way through the month).`}
    >
      <div className="space-y-4">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <p className="text-3xl font-semibold tracking-tight tabular-nums">
              {fmtUSD(mtd.cost_usd || 0)}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              of {fmtUSD(budget.monthly_usd)} budget · {usedPct.toFixed(1)}% used
            </p>
          </div>
          <div className="text-right">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                overPace
                  ? "bg-destructive/10 text-destructive border-destructive/20"
                  : "bg-success/10 text-success border-success/20"
              }`}
            >
              {overPace ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {overPace ? "Trending over budget" : "Trending under budget"}
            </span>
          </div>
        </div>

        {/* The bar itself. Relative-positioned so the tick can be absolutely
            placed at `calPct` regardless of the fill width. */}
        <div className="relative h-6 rounded-full bg-muted overflow-hidden border border-border">
          <div
            className={`h-full ${fillBg} transition-all duration-500`}
            style={{ width: `${usedPct}%` }}
          />
          {/* Calendar tick — a 2px vertical bar with a soft halo so it's
              visible against either the filled or unfilled section. */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-foreground/70 pointer-events-none"
            style={{ left: `${calPct}%` }}
            title={`Calendar pace: ${calPct.toFixed(1)}%`}
          >
            <div className="absolute -top-1.5 -left-1 h-2 w-2 rounded-full bg-foreground/70" aria-hidden />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
          <ForecastCell
            label="Projected month-end"
            value={fmtUSD(projected)}
            tone={overProjection ? "warning" : "success"}
            hint={overProjection
              ? `Over budget by ${fmtUSD(projected - budget.monthly_usd)}`
              : `Under by ${fmtUSD(Math.max(0, budget.monthly_usd - projected))}`}
          />
          <ForecastCell
            label="Days of runway"
            value={budget.days_of_runway != null ? `${budget.days_of_runway} d` : "—"}
            hint={budget.days_of_runway != null ? "at current daily pace" : "no spend recorded yet"}
          />
          <ForecastCell
            label="Pace"
            // Phrase the gap as plain English: "Ahead by 2.1 pp" / "Behind by 84.8 pp".
            // A "pp" suffix is the convention for percentage-point arithmetic — the
            // operator's brain doesn't have to parse a signed number.
            value={(() => {
              const delta = usedPct - calPct;
              if (Math.abs(delta) < 0.05) return "On track";
              return delta > 0 ? `+${delta.toFixed(1)} pp` : `${delta.toFixed(1)} pp`;
            })()}
            tone={overPace ? "warning" : "success"}
            hint={
              overPace
                ? `Spent ${usedPct.toFixed(1)}% but only ${calPct.toFixed(0)}% of the month is gone — burning hot.`
                : `Spent ${usedPct.toFixed(1)}% with ${calPct.toFixed(0)}% of the month gone — under-pacing.`
            }
          />
        </div>
      </div>
    </Section>
  );
}

function ForecastCell({ label, value, hint, tone }) {
  const toneClass = {
    warning: "text-warning",
    success: "text-success",
  }[tone] || "text-foreground";
  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`text-base font-semibold mt-0.5 tabular-nums ${toneClass}`}>{value}</p>
      {hint && <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{hint}</p>}
    </div>
  );
}

/* ─── Daily bars ────────────────────────────────────────────────────────── */

function DailyBars({ daily, days, onDaysChange }) {
  const max = useMemo(() => Math.max(...daily.map((d) => d.cost_usd), 0.0001), [daily]);
  const total = useMemo(() => daily.reduce((s, d) => s + d.cost_usd, 0), [daily]);

  return (
    <Section
      title="Daily spend"
      description={`Last ${days} days. Hover a bar for the day's exact cost.`}
      actions={
        <div className="flex gap-1">
          {[7, 14, 30, 60].map((opt) => (
            <Button
              key={opt}
              size="sm"
              variant={days === opt ? "default" : "outline"}
              className="h-7 px-2.5 text-xs"
              onClick={() => onDaysChange(opt)}
            >
              {opt}d
            </Button>
          ))}
        </div>
      }
    >
      <div className="flex items-end gap-1 h-32">
        {daily.map((row, idx) => {
          const heightPct = row.cost_usd / max * 100;
          // Today's bar gets a primary tint; spendy days (>2x median) get
          // a subtle warning ring so anomalies are visible at a glance.
          const isToday = idx === daily.length - 1;
          return (
            <div
              key={row.day}
              className="flex-1 group relative h-full flex flex-col justify-end"
              title={`${row.day} · ${fmtUSD(row.cost_usd)} · ${row.calls} calls`}
            >
              <div
                className={`w-full rounded-t transition-colors ${
                  isToday
                    ? "bg-primary"
                    : row.cost_usd > 0
                    ? "bg-primary/40 group-hover:bg-primary/60"
                    : "bg-muted"
                }`}
                style={{ height: `${Math.max(heightPct, 2)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex justify-between mt-2 text-[11px] text-muted-foreground">
        <span>{daily[0]?.day}</span>
        <span>Total: <span className="text-foreground font-medium">{fmtUSD(total)}</span></span>
        <span>{daily[daily.length - 1]?.day}</span>
      </div>
    </Section>
  );
}

/* ─── Per-model breakdown ───────────────────────────────────────────────── */

function ModelBreakdown({ models, totalCost }) {
  if (!models.length) {
    return (
      <Section title="By model" description="Month-to-date split by model.">
        <p className="text-sm text-muted-foreground text-center py-6">
          No usage yet this month.
        </p>
      </Section>
    );
  }
  return (
    <Section
      title="By model"
      description="Month-to-date cost split. Calls and tokens are summed across the same window as the budget gauge."
    >
      <ul className="space-y-2">
        {models.map((m) => {
          const sharePct = totalCost > 0 ? (m.cost_usd / totalCost) * 100 : 0;
          return (
            <li key={m.model} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span className="font-mono text-xs text-foreground truncate">{m.model}</span>
                  <span className="text-[11px] text-muted-foreground">
                    {m.calls} calls · {fmtTokens(m.prompt_tokens + m.completion_tokens)} tokens
                  </span>
                </div>
                <span className="font-semibold text-foreground tabular-nums">
                  {fmtUSD(m.cost_usd)}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div className="h-full bg-primary/70" style={{ width: `${sharePct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/* ─── Platform totals (super-admin All tenants view) ────────────────────── */

// Replaces the per-tenant BudgetGauge when the super-admin picks "All
// tenants" — there's no platform-wide budget concept, so we show the
// totals + forecast and let the tenant-ranking section below answer
// "who is driving the spend?".
function PlatformTotals({ mtd, projected, calendarPct }) {
  return (
    <Section
      title="Platform-wide LLM cost"
      description="Total OpenAI spend across every tenant for the current month. No platform budget is set — see the per-tenant ranking below for who's driving the cost."
    >
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <p className="text-3xl font-semibold tracking-tight tabular-nums">
            {fmtUSD(mtd.cost_usd || 0)}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            month-to-date · {calendarPct ? calendarPct.toFixed(0) : 0}% of the month elapsed
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
            Projected month-end
          </p>
          <p className="text-xl font-semibold tracking-tight tabular-nums mt-0.5">
            {fmtUSD(projected || 0)}
          </p>
        </div>
      </div>
    </Section>
  );
}

/* ─── Tenant ranking (super-admin All tenants view) ─────────────────────── */

function TenantRanking({ tenants, totalCost }) {
  if (!tenants.length) {
    return (
      <Section title="By tenant" description="Month-to-date cost per tenant.">
        <p className="text-sm text-muted-foreground text-center py-6">
          No tenant usage yet this month.
        </p>
      </Section>
    );
  }
  return (
    <Section
      title="By tenant"
      description="Month-to-date cost per tenant, descending. Useful for spotting which deployment is driving the platform spend."
    >
      <ul className="space-y-2">
        {tenants.map((t) => {
          const sharePct = totalCost > 0 ? (t.cost_usd / totalCost) * 100 : 0;
          return (
            <li key={t.company_id} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <Building2 className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span className="font-medium text-foreground truncate">{t.name}</span>
                  <span className="text-[11px] text-muted-foreground">
                    {t.calls} calls · {fmtTokens(t.prompt_tokens + t.completion_tokens)} tokens
                  </span>
                </div>
                <span className="font-semibold text-foreground tabular-nums">
                  {fmtUSD(t.cost_usd)}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div className="h-full bg-primary/70" style={{ width: `${sharePct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
