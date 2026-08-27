"use client";
import { useState } from "react";
import { Icon, IconName } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Stat, AddButton, useModule } from "@/components/ui";
import { api } from "@/lib/api";
import { fromLocalInput, toLocalInput, minutes, fmtShort } from "@/lib/format";
import type { PlannerPayload, PlannerDay } from "@/lib/types";

export default function PlannerPage() {
  const { user, ready, data, state, error, reload, act } = useModule<PlannerPayload>(() => api.planner(7));
  const [sel, setSel] = useState(0);
  const [scheduling, setScheduling] = useState<{ id: string; title: string } | null>(null);
  const [creating, setCreating] = useState(false);
  const [when, setWhen] = useState("");
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);

  if (!ready || !user) return null;
  const p = data;
  const day: PlannerDay | undefined = p?.days.find((d) => d.offset === sel) || p?.today;

  async function place(taskId: string, iso: string) {
    setBusy(true);
    await act(() => api.schedule(taskId, iso));
    setBusy(false);
    setScheduling(null);
  }

  async function quickMove(taskId: string, offset: number) {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    d.setHours(9, 0, 0, 0);
    await act(() => api.schedule(taskId, d.toISOString()));
  }

  return (
    <ModulePage
      eyebrow={p ? `LOCAL TIME ${p.now}` : "PLANNER"}
      title="Planner"
      sub="Classes, coursework, study blocks, project work and career deadlines on one timeline — every module lands here."
      state={state} error={error} onRetry={reload}
      red={!!p?.conflicts.length}
      actions={<AddButton label="Task" onClick={() => { setF({ title: "", category: "Personal", due_at: toLocalInput(null, 9, 0), est_minutes: 30, priority: "med" }); setCreating(true); }} />}
    >
      {p && (
        <div className="stack">
          {p.conflicts.length > 0 && (
            <div className="ss-banner">
              <div className="lbl"><Icon.spider s={14} /> SPIDER SENSE</div>
              <div className="msg">{p.conflicts[0].title}</div>
              {p.conflicts.length > 1 && <div className="mini">+{p.conflicts.length - 1} more overlap(s) today</div>}
            </div>
          )}

          <div className="tabs" style={{ overflowX: "auto", maxWidth: "100%" }}>
            {p.days.map((d) => (
              <button key={d.offset} className={"tab" + (d.offset === sel ? " on" : "")} onClick={() => setSel(d.offset)}>
                {d.is_today ? "Today" : `${d.day_label} ${fmtShort(d.date)}`}
                {d.open_count > 0 && <span style={{ opacity: 0.6 }}> · {d.open_count}</span>}
              </button>
            ))}
          </div>

          <div className="g-2">
            <div className="g-col">
              <div className="card">
                <div className="card-h">
                  <span className="card-t">{day?.is_today ? "Today" : `${day?.day_label}, ${fmtShort(day?.date || "")}`} · {day?.items.length || 0} items</span>
                  <span className="pill">{minutes(day?.booked_minutes || 0)} booked</span>
                </div>
                {day?.items.length ? (
                  <div className="tl">
                    {day.items.map((it) => {
                      const I = (Icon[it.icon as IconName] || Icon.tasks);
                      const fixed = !it.movable;
                      return (
                        <div className={"slot" + (fixed ? " fixed" : "") + (it.status === "done" ? " done" : "")} key={`${it.kind}-${it.id}`}>
                          <div className="when num">{it.time}</div>
                          <div className="ico-box" style={{ marginTop: 4 }}><I s={18} /></div>
                          <div className="grow" style={{ paddingTop: 4 }}>
                            <div className="t">{it.title}</div>
                            <div className="s">
                              {it.meta}
                              {it.end ? ` · until ${it.end}` : ""}
                              {it.est_minutes ? ` · ${minutes(it.est_minutes)}` : ""}
                              {fixed ? " · fixed" : ""}
                            </div>
                          </div>
                          {it.kind === "task" && it.status === "open" && (
                            <div className="row-acts" style={{ paddingTop: 4 }}>
                              <button className="btn sm" onClick={() => setScheduling({ id: it.id, title: it.title })}>Move</button>
                              <button className="btn sm primary" title="Complete" onClick={() => act(() => api.completeTask(it.id))}>
                                <Icon.check s={14} />
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : <Empty>Nothing scheduled. {day?.is_today ? "Enjoy the calm." : "A clear day."}</Empty>}
              </div>
            </div>

            <div className="g-col">
              <div className="stats">
                <Stat k="Open today" v={p.today.open_count} n={minutes(p.today.booked_minutes)} />
                <Stat k="Unscheduled" v={p.unscheduled.length} n="need a slot" />
              </div>

              <div className="card">
                <div className="card-h">
                  <span className="card-t">Unscheduled</span>
                  <span className="pill">{p.unscheduled.length}</span>
                </div>
                {p.unscheduled.length ? p.unscheduled.map((t) => {
                  const I = (Icon[t.icon as IconName] || Icon.tasks);
                  return (
                    <div className="row" key={t.id}>
                      <div className="ico-box"><I s={18} /></div>
                      <div className="grow">
                        <div className="t" style={{ fontSize: 13 }}>{t.title}</div>
                        <div className="s">{t.meta} · {minutes(t.est_minutes)}</div>
                      </div>
                      <div className="row-acts">
                        <button className="btn sm" onClick={() => quickMove(t.id, 0)}>Today</button>
                        <button className="btn sm" onClick={() => quickMove(t.id, 1)}>Tmrw</button>
                        <button className="btn sm" onClick={() => setScheduling({ id: t.id, title: t.title })}>Pick</button>
                      </div>
                    </div>
                  );
                }) : <Empty>Everything has a slot.</Empty>}
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Week at a glance</span></div>
                {p.days.map((d) => (
                  <div className="kv" key={d.offset}>
                    <span className="k">{d.is_today ? "Today" : `${d.day_label} ${fmtShort(d.date)}`}</span>
                    <span className="v">{d.items.length} · {minutes(d.booked_minutes)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {scheduling && (
        <Modal title="Pick a slot" sub={scheduling.title} busy={busy}
          onClose={() => setScheduling(null)}
          onSubmit={() => place(scheduling.id, fromLocalInput(when || toLocalInput(null, 9, 0)))}>
          <Field label="When" hint="Moving a dated task counts as a postpone — Spider Sense watches for repeats.">
            <input type="datetime-local" autoFocus value={when || toLocalInput(null, 9, 0)}
              onChange={(e) => setWhen(e.target.value)} />
          </Field>
        </Modal>
      )}

      {creating && (
        <Modal title="Add task" busy={busy} onClose={() => setCreating(false)}
          onSubmit={async () => {
            setBusy(true);
            await act(() => api.createTask({
              title: f.title, category: f.category, priority: f.priority,
              est_minutes: Number(f.est_minutes) || 30,
              due_at: f.due_at ? fromLocalInput(f.due_at) : null,
              meta: f.category,
            }));
            setBusy(false); setCreating(false);
          }}>
          <Field label="Title"><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required autoFocus /></Field>
          <div className="field-row">
            <Field label="Category">
              <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {["Personal", "College", "Learning", "Project", "Career", "Routine"].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
            <Field label="Priority">
              <select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
                {["low", "med", "high"].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
          </div>
          <div className="field-row">
            <Field label="When" hint="Clear it to leave the task unscheduled">
              <input type="datetime-local" value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} />
            </Field>
            <Field label="Est. minutes"><input type="number" min={5} value={f.est_minutes} onChange={(e) => setF({ ...f, est_minutes: e.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </ModulePage>
  );
}
