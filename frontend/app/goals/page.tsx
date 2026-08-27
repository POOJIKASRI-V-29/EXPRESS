"use client";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Bar, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fromLocalInput, toLocalInput, fmtDate, daysUntil, titleCase } from "@/lib/format";
import type { GoalsPayload, Goal } from "@/lib/types";

const LINK_ICON: Record<string, any> = {
  task: Icon.tasks, project: Icon.projects, topic: Icon.learning,
  skill: Icon.dumb, habit: Icon.check,
};
type Dialog = null | "goal" | "link";

export default function GoalsPage() {
  const { user, ready, data, state, error, reload, act } = useModule<GoalsPayload>(() => api.goals());
  const [filter, setFilter] = useState("active");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [target, setTarget] = useState<Goal | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const open = (d: Dialog, init: any = {}, g: Goal | null = null) => { setF(init); setTarget(g); setDialog(d); };
  async function submit(fn: () => Promise<any>) { setBusy(true); await act(fn); setBusy(false); setDialog(null); }

  if (!ready || !user) return null;
  const all = data?.goals || [];
  const goals = all.filter((g) => filter === "all" || g.status === filter);
  const linkable = data?.linkable || {};
  const kinds = Object.keys(linkable);

  return (
    <ModulePage
      eyebrow="INTENT"
      title="Goals"
      sub="A goal's progress is read from the work linked to it — tasks, projects, topics, skills, habits — not typed in by hand."
      state={state} error={error} onRetry={reload}
      actions={<AddButton label="Goal" onClick={() => open("goal", { title: "", detail: "", horizon: "short", category: "personal", target_date: "", progress: 0 })} />}
    >
      {data && (
        <div className="stack">
          <div className="stats">
            <Stat k="Active" v={all.filter((g) => g.status === "active").length} />
            <Stat k="Achieved" v={all.filter((g) => g.status === "achieved").length} tone="green" />
            <Stat k="Avg. progress" v={`${all.length ? Math.round(all.reduce((s, g) => s + g.progress, 0) / all.length) : 0}%`} />
            <Stat k="Linked items" v={all.reduce((s, g) => s + g.links.length, 0)} n="driving progress" />
          </div>

          <div className="chips">
            {["active", "achieved", "dropped", "all"].map((s) => (
              <button key={s} className={"chip" + (s === filter ? " on" : "")} onClick={() => setFilter(s)}>{s}</button>
            ))}
          </div>

          {goals.length ? (
            <div className="g-auto">
              {goals.map((g) => {
                const left = daysUntil(g.target_date);
                const late = left !== null && left < 14 && g.progress < 70 && g.status === "active";
                return (
                  <div className="card" key={g.id}>
                    <div className="card-h">
                      <span className="card-t">{g.horizon} term · {g.category}</span>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        {g.target_date && <span className={"pill " + (late ? "red" : "")}>{fmtDate(g.target_date)}</span>}
                        <IconAction icon={Icon.trash} danger title={`Delete ${g.title}`}
                          onClick={() => confirm(`Delete "${g.title}"?`, () => act(() => api.deleteGoal(g.id)))} />
                      </div>
                    </div>

                    <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>{g.title}</div>
                    {g.detail && <div className="note-body" style={{ marginTop: 8 }}>{g.detail}</div>}

                    <div style={{ margin: "16px 0 6px", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                      <span className="mini">from {g.progress_source}</span>
                      <span className="num" style={{ fontWeight: 800, fontSize: 18 }}>{g.progress}%</span>
                    </div>
                    <Bar pct={g.progress} tone={late ? "red" : "blue"} />

                    <div className="card-h" style={{ marginTop: 20, marginBottom: 10 }}>
                      <span className="card-t">Linked work · {g.links.length}</span>
                      <button className="link" onClick={() => open("link", { ref_type: kinds[0] || "task", ref_id: "" }, g)}>+ Link</button>
                    </div>
                    {g.links.length ? g.links.map((l) => {
                      const I = LINK_ICON[l.ref_type] || Icon.link;
                      return (
                        <div className="row" key={l.id} style={{ padding: "9px 0" }}>
                          <div className="ico-box" style={{ width: 30, height: 30 }}><I s={15} /></div>
                          <div className="grow">
                            <div className="t" style={{ fontSize: 13 }}>{l.label}</div>
                            <div className="s">{l.ref_type} · {l.progress}%</div>
                          </div>
                          <IconAction icon={Icon.x} title="Unlink"
                            onClick={() => act(() => api.unlinkGoal(g.id, l.id))} />
                        </div>
                      );
                    }) : <Empty>Nothing linked — progress falls back to the manual value.</Empty>}

                    <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
                      {g.status !== "achieved" && (
                        <button className="btn sm" onClick={() => act(() => api.updateGoal(g.id, { status: "achieved" }))}>Mark achieved</button>
                      )}
                      {g.status !== "active" && (
                        <button className="btn sm" onClick={() => act(() => api.updateGoal(g.id, { status: "active" }))}>Reactivate</button>
                      )}
                      {g.status === "active" && (
                        <button className="btn sm ghost-red" onClick={() => act(() => api.updateGoal(g.id, { status: "dropped" }))}>Drop</button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : <Empty>{filter === "all" ? "No goals yet." : `No ${filter} goals.`}</Empty>}
        </div>
      )}

      {dialog === "goal" && (
        <Modal title="Add goal" sub="Link it to real work afterwards and progress tracks itself."
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createGoal({
            title: f.title, detail: f.detail, horizon: f.horizon, category: f.category,
            progress: Number(f.progress) || 0,
            ...(f.target_date ? { target_date: fromLocalInput(f.target_date) } : {}),
          }))}>
          <Field label="Title"><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required autoFocus /></Field>
          <Field label="Detail"><textarea value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} /></Field>
          <div className="field-row">
            <Field label="Horizon">
              <select value={f.horizon} onChange={(e) => setF({ ...f, horizon: e.target.value })}>
                <option value="short">Short term</option><option value="long">Long term</option>
              </select>
            </Field>
            <Field label="Category">
              <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {["personal", "college", "learning", "projects", "career", "finance", "health"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Target date" hint="Optional — Spider Sense warns if progress lags the date">
            <input type="datetime-local" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} />
          </Field>
        </Modal>
      )}

      {dialog === "link" && target && (
        <Modal title="Link work to this goal" sub={target.title} onClose={() => setDialog(null)} busy={busy}
          submitLabel="Link"
          onSubmit={() => submit(() => api.linkGoal(target.id, { ref_type: f.ref_type, ref_id: f.ref_id }))}>
          <Field label="Kind">
            <select value={f.ref_type} onChange={(e) => setF({ ref_type: e.target.value, ref_id: "" })} autoFocus>
              {kinds.map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}
            </select>
          </Field>
          <Field label="Item" hint={(linkable[f.ref_type] || []).length ? undefined : `Nothing to link under ${f.ref_type} yet.`}>
            <select value={f.ref_id} onChange={(e) => setF({ ...f, ref_id: e.target.value })} required>
              <option value="">Choose…</option>
              {(linkable[f.ref_type] || []).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </Field>
        </Modal>
      )}
    </ModulePage>
  );
}
