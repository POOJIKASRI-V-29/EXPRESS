"use client";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Bar, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fromLocalInput, toLocalInput, money, fmtShort } from "@/lib/format";
import type { FinancePayload } from "@/lib/types";

type Dialog = null | "entry" | "budget";

export default function FinancePage() {
  const { user, ready, data, state, error, reload, act } = useModule<FinancePayload>(() => api.finance());
  const [dialog, setDialog] = useState<Dialog>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const open = (d: Dialog, init: any = {}) => { setF(init); setDialog(d); };
  async function submit(fn: () => Promise<any>) { setBusy(true); await act(fn); setBusy(false); setDialog(null); }

  if (!ready || !user) return null;
  const fin = data;
  const maxCat = Math.max(1, ...(fin?.by_category || []).map((c) => c.amount));

  return (
    <ModulePage
      eyebrow="THIS MONTH"
      title="Finance"
      sub="Spending against the caps you set. Spider Sense reads these same numbers, so a warning and the bar can't disagree."
      state={state} error={error} onRetry={reload}
      actions={<>
        <AddButton label="Entry" onClick={() => open("entry", { amount: "", category: "Food", kind: "expense", note: "", date: toLocalInput() })} />
        <AddButton label="Budget" onClick={() => open("budget", { category: "", monthly_limit: "" })} />
      </>}
    >
      {fin && (
        <div className="stack">
          <div className="stats">
            <Stat k="Spent" v={money(fin.month_spent)} n={`${fin.entry_count} entries`} />
            <Stat k="Income" v={money(fin.month_income)} tone="green" />
            <Stat k="Net" v={money(fin.net)} tone={fin.net < 0 ? "red" : "green"} />
            <Stat k="Budgets over" v={fin.budgets.filter((b) => b.state === "over").length}
              n={`${fin.budgets.length} tracked`}
              tone={fin.budgets.some((b) => b.state === "over") ? "red" : undefined} />
          </div>

          <div className="g-2">
            <div className="g-col">
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Budgets</span>
                  <span className="mini">monthly caps per category</span>
                </div>
                {fin.budgets.length ? fin.budgets.map((b) => (
                  <div className="row" key={b.id}>
                    <div className="ico-box" style={b.state === "over" ? { color: "var(--red)", borderColor: "var(--red-line)" } : undefined}>
                      <Icon.finance s={18} />
                    </div>
                    <div className="grow">
                      <div className="t">{b.category}</div>
                      <div className="s num">{money(b.spent)} of {money(b.limit)}</div>
                      <div style={{ marginTop: 8, maxWidth: 320 }}>
                        <Bar pct={b.pct} tone={b.state === "ok" ? "blue" : "red"} />
                      </div>
                    </div>
                    <div className={"pill " + (b.state === "over" ? "red" : b.state === "near" ? "red" : "")}>{b.pct}%</div>
                    <div className="row-acts">
                      <button className="btn sm" onClick={() => open("budget", { id: b.id, category: b.category, monthly_limit: String(b.limit) })}>Edit</button>
                      <IconAction icon={Icon.trash} danger title={`Delete ${b.category} budget`}
                        onClick={() => confirm(`Remove the ${b.category} budget?`, () => act(() => api.deleteBudget(b.id)))} />
                    </div>
                  </div>
                )) : <Empty>No budgets set. Add one and Spider Sense starts watching it.</Empty>}
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Recent entries</span><span className="pill">{fin.recent.length}</span></div>
                {fin.recent.length ? fin.recent.map((e) => (
                  <div className="row" key={e.id}>
                    <div className="ico-box" style={e.kind === "income" ? { color: "var(--green)" } : undefined}>
                      {e.kind === "income" ? <Icon.plus s={16} /> : <Icon.finance s={16} />}
                    </div>
                    <div className="grow">
                      <div className="t" style={{ fontSize: 13 }}>{e.note || e.category}</div>
                      <div className="s">{e.category} · {fmtShort(e.date)}</div>
                    </div>
                    <div className="num" style={{ fontWeight: 700, color: e.kind === "income" ? "var(--green)" : "var(--text)" }}>
                      {e.kind === "income" ? "+" : "−"}{money(e.amount)}
                    </div>
                    <IconAction icon={Icon.trash} danger title="Delete entry"
                      onClick={() => confirm("Delete this entry?", () => act(() => api.deleteEntry(e.id)))} />
                  </div>
                )) : <Empty>Nothing logged this month.</Empty>}
              </div>
            </div>

            <div className="g-col">
              <div className="card">
                <div className="card-h"><span className="card-t">Where it went</span></div>
                {fin.by_category.length ? fin.by_category.map((c) => (
                  <div key={c.category} style={{ padding: "11px 0", borderBottom: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
                      <span>{c.category}</span>
                      <span className="num" style={{ fontWeight: 700 }}>{money(c.amount)}</span>
                    </div>
                    <Bar pct={(c.amount / maxCat) * 100} />
                  </div>
                )) : <Empty>No spending recorded this month.</Empty>}
              </div>
            </div>
          </div>
        </div>
      )}

      {dialog === "entry" && (
        <Modal title="Log money" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createEntry({
            amount: f.amount, category: f.category, kind: f.kind, note: f.note,
            date: fromLocalInput(f.date),
          }))}>
          <div className="field-row">
            <Field label="Amount"><input type="number" step="0.01" min="0" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} required autoFocus /></Field>
            <Field label="Kind">
              <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
                <option value="expense">Expense</option><option value="income">Income</option>
              </select>
            </Field>
          </div>
          <Field label="Category" hint="Matching a budget's category counts it against that cap">
            <input list="fin-cats" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} required />
            <datalist id="fin-cats">
              {(fin?.budgets || []).map((b) => <option key={b.id} value={b.category} />)}
              {["Food", "Books", "Transport", "Subscriptions", "Income", "General"].map((c) => <option key={c} value={c} />)}
            </datalist>
          </Field>
          <Field label="Note"><input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          <Field label="Date"><input type="datetime-local" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        </Modal>
      )}

      {dialog === "budget" && (
        <Modal title={f.id ? `Edit ${f.category} budget` : "Set a budget"} onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => f.id
            ? api.updateBudget(f.id, { monthly_limit: f.monthly_limit })
            : api.createBudget({ category: f.category, monthly_limit: f.monthly_limit }))}>
          {!f.id && (
            <Field label="Category"><input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} required autoFocus placeholder="Food" /></Field>
          )}
          <Field label="Monthly limit"><input type="number" step="0.01" min="0" value={f.monthly_limit} onChange={(e) => setF({ ...f, monthly_limit: e.target.value })} required autoFocus={!!f.id} /></Field>
        </Modal>
      )}
    </ModulePage>
  );
}
