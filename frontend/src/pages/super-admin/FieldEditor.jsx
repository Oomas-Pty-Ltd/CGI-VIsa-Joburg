/**
 * Per-field editor used inside the Tenant Services dialog (Sprint 4E).
 *
 * Three field types — switching the type selector swaps the bottom
 * panel between three different control layouts:
 *
 *   input       — `question` textarea
 *   conditional — condition + on_match / on_no_match builder
 *   api_call    — method, URL, headers, body, store_response_as inputs
 *
 * The component is fully controlled by `value` / `onChange` so the
 * parent owns the full fields[] array and can reorder / delete.
 */
import React from "react";
import { Trash2, ChevronUp, ChevronDown, GripVertical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const FIELD_TYPES = [
  { value: "input",       label: "Input — ask the user" },
  { value: "conditional", label: "Conditional — branch on a prior answer" },
  { value: "api_call",    label: "API call — fetch / verify" },
];

const COND_OPERATORS = [
  { value: "equals",     label: "equals" },
  { value: "not_equals", label: "not equals" },
  { value: "in",         label: "is one of (comma-separated)" },
  { value: "matches",    label: "matches regex" },
];

const ADVANCE_OPTIONS = [
  { value: "continue",     label: "continue to next field" },
  { value: "skip_to_docs", label: "skip remaining → start docs upload" },
];

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

export default function FieldEditor({
  field, index, totalFields, priorFieldKeys,
  onChange, onDelete, onMoveUp, onMoveDown,
}) {
  const type = field.type || "input";

  const update = (patch) => onChange({ ...field, ...patch });

  // Recreate per-type sub-objects when switching, so the row never carries
  // leftover keys from the previous type.
  const switchType = (newType) => {
    const base = { key: field.key, type: newType };
    if (newType === "input")        return onChange({ ...base, question: field.question ?? "" });
    if (newType === "conditional")  return onChange({ ...base, condition: { field: "", equals: "" }, on_match: "skip_to_docs", on_no_match: "continue" });
    if (newType === "api_call")     return onChange({ ...base, api_config: { method: "GET", url: "" } });
  };

  return (
    <div className="rounded-lg border bg-white p-3 space-y-3">
      {/* Header: drag handle, key, type, reorder, delete */}
      <div className="flex items-center gap-2">
        <GripVertical className="h-4 w-4 text-slate-300 shrink-0" />
        <div className="flex-1 grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs">Key (form-data key)</Label>
            <Input
              value={field.key || ""}
              onChange={(e) => update({ key: e.target.value })}
              placeholder="full_name"
              className="font-mono text-xs h-8"
            />
          </div>
          <div>
            <Label className="text-xs">Type</Label>
            <Select value={type} onValueChange={switchType}>
              <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                {FIELD_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={onMoveUp} disabled={index === 0}>
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={onMoveDown} disabled={index === totalFields - 1}>
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </div>
        <Button size="sm" variant="ghost" onClick={onDelete}>
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      </div>

      {/* Type-specific panel */}
      {type === "input"       && <InputPanel       field={field} update={update} />}
      {type === "conditional" && <ConditionalPanel field={field} update={update} priorFieldKeys={priorFieldKeys} />}
      {type === "api_call"    && <ApiCallPanel     field={field} update={update} priorFieldKeys={priorFieldKeys} />}
    </div>
  );
}

/* ─── input ───────────────────────────────────────────────────────────── */

function InputPanel({ field, update }) {
  return (
    <div>
      <Label className="text-xs">Question shown to the user</Label>
      <Textarea
        value={field.question || ""}
        onChange={(e) => update({ question: e.target.value })}
        rows={2}
        placeholder="Please enter your **full name** (as it appears on your passport):"
      />
      <p className="text-xs text-slate-400 mt-1">Markdown **bold** is rendered in chat.</p>
    </div>
  );
}

/* ─── conditional ─────────────────────────────────────────────────────── */

function ConditionalPanel({ field, update, priorFieldKeys }) {
  const cond = field.condition || {};
  // Detect which operator key is set on the condition
  const op = COND_OPERATORS.find((o) => o.value in cond)?.value || "equals";
  const opValue = cond[op] ?? "";

  const setCondField = (v) => update({ condition: { ...cond, field: v } });

  const setOperator = (newOp) => {
    // Drop all op-value keys, set the new one
    const next = { field: cond.field };
    next[newOp] = newOp === "in" ? [] : "";
    update({ condition: next });
  };

  const setOpValue = (v) => {
    const next = { ...cond };
    if (op === "in") {
      // comma-split into trimmed array
      next.in = v.split(",").map((s) => s.trim()).filter(Boolean);
    } else {
      next[op] = v;
    }
    update({ condition: next });
  };

  const displayValue = op === "in" ? (cond.in || []).join(", ") : opValue;

  return (
    <div className="space-y-2 bg-slate-50 rounded p-2">
      <div className="grid grid-cols-[1fr,1fr,2fr] gap-2 items-end">
        <div>
          <Label className="text-xs">IF field</Label>
          <Select value={cond.field || "__none__"} onValueChange={(v) => setCondField(v === "__none__" ? "" : v)}>
            <SelectTrigger className="h-8"><SelectValue placeholder="Pick a prior field" /></SelectTrigger>
            <SelectContent>
              {priorFieldKeys.length === 0 && <SelectItem value="__none__">(no prior fields)</SelectItem>}
              {priorFieldKeys.map((k) => <SelectItem key={k} value={k}>{k}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">operator</Label>
          <Select value={op} onValueChange={setOperator}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {COND_OPERATORS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">value{op === "in" ? "s (comma-separated)" : ""}</Label>
          <Input
            value={displayValue}
            onChange={(e) => setOpValue(e.target.value)}
            placeholder={op === "matches" ? "^[A-Z]\\d{7}$" : op === "in" ? "south african, lesotho" : "south african"}
            className="h-8 font-mono text-xs"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">When matched</Label>
          <Select value={field.on_match || "continue"} onValueChange={(v) => update({ on_match: v })}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ADVANCE_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">When NOT matched</Label>
          <Select value={field.on_no_match || "continue"} onValueChange={(v) => update({ on_no_match: v })}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ADVANCE_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

/* ─── api_call ────────────────────────────────────────────────────────── */

function ApiCallPanel({ field, update, priorFieldKeys }) {
  const cfg = field.api_config || {};
  const updateCfg = (patch) => update({ api_config: { ...cfg, ...patch } });

  return (
    <div className="space-y-2 bg-slate-50 rounded p-2">
      <div className="grid grid-cols-[100px,1fr] gap-2">
        <div>
          <Label className="text-xs">Method</Label>
          <Select value={cfg.method || "GET"} onValueChange={(v) => updateCfg({ method: v })}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {METHODS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">URL <span className="text-slate-400">(supports {`{{field_key}}`} substitution)</span></Label>
          <Input
            value={cfg.url || ""}
            onChange={(e) => updateCfg({ url: e.target.value })}
            placeholder="https://verify.example/passport/{{passport_number}}"
            className="h-8 font-mono text-xs"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Headers (JSON, optional)</Label>
          <Textarea
            value={typeof cfg.headers === "object" ? JSON.stringify(cfg.headers, null, 2) : (cfg.headers || "")}
            onChange={(e) => {
              try { updateCfg({ headers: JSON.parse(e.target.value || "{}") }); }
              catch { updateCfg({ headers: e.target.value }); } // keep as string while typing
            }}
            rows={3}
            placeholder='{"Authorization": "Bearer {{api_token}}"}'
            className="text-xs font-mono"
          />
        </div>
        <div>
          <Label className="text-xs">Body (JSON, optional)</Label>
          <Textarea
            value={typeof cfg.body === "object" ? JSON.stringify(cfg.body, null, 2) : (cfg.body || "")}
            onChange={(e) => {
              try { updateCfg({ body: JSON.parse(e.target.value || "{}") }); }
              catch { updateCfg({ body: e.target.value }); }
            }}
            rows={3}
            placeholder='{"applicant": "{{full_name}}"}'
            className="text-xs font-mono"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Store response as (form field key, optional)</Label>
          <Input
            value={cfg.store_response_as || ""}
            onChange={(e) => updateCfg({ store_response_as: e.target.value || undefined })}
            placeholder="passport_verified"
            className="h-8 font-mono text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">Timeout (seconds, max 30)</Label>
          <Input
            type="number"
            min={1}
            max={30}
            value={cfg.timeout_seconds ?? 10}
            onChange={(e) => updateCfg({ timeout_seconds: Number(e.target.value) })}
            className="h-8"
          />
        </div>
      </div>

      {priorFieldKeys.length > 0 && (
        <p className="text-xs text-slate-400">
          Available substitutions: {priorFieldKeys.map((k) => `{{${k}}}`).join("  ")}
        </p>
      )}
    </div>
  );
}
