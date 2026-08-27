"use client";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Bar, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fromLocalInput, toLocalInput, fmtDate, fmtDue, daysUntil } from "@/lib/format";
import type { Project } from "@/lib/types";

type Dialog = null | "project" | "phase" | "task";

export default function ProjectsPage() {
  const { user, ready, data, state, error, reload, act } =
    useModule<{ projects: Project[] }>(() => api.projects());
  const [dialog, setDialog] = useState<Dialog>(null);
  const [target, setTarget] = useState<Project | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const open = (d: Dialog, init: any = {}, p: Project | null = null) => { setF(init); setTarget(p); setDialog(d); };
  async function submit(fn: () => Promise<any>) { setBusy(true); await act(fn); setBusy(false); setDialog(null); }

  if (!ready || !user) return null;
  const projects = data?.projects || [];
  const active = projects.filter((p) => p.status === "Active");

  return (
    <ModulePage
      eyebrow="BUILD LOG"
      title="Projects"
      sub="Phases drive completion, and every project task joins the same queue your Planner reads."
      state={state} error={error} onRetry={reload}
      actions={<AddButton label="Project" onClick={() => open("project", { name: "", description: "", stack: "", phase: "Alpha V1", status: "Active", priority: 1, commits: 0, repo_url: "", due_at: "" })} />}
    >
      <div className="stack">
        <div className="stats">
          <Stat k="Projects" v={projects.length} n={`${active.length} active`} />
          <Stat k="Avg. completion" v={`${projects.length ? Math.round(projects.reduce((s, p) => s + p.completion, 0) / projects.length) : 0}%`} />
          <Stat k="Open tasks" v={projects.reduce((s, p) => s + p.open_tasks, 0)} />
          <Stat k="Commits" v={projects.reduce((s, p) => s + p.commits, 0)} n="recorded" />
        </div>

        {projects.length ? (
          <div className="g-auto">
            {projects.map((p) => {
              const dLeft = daysUntil(p.due_at);
              return (
                <div className="card" key={p.id}>
                  <div className="card-h">
                    <span className="card-t">{p.status}</span>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      {p.due_at && <span className={"pill " + (dLeft !== null && dLeft < 7 ? "red" : "")}>{fmtDate(p.due_at)}</span>}
                      <IconAction icon={Icon.trash} danger title={`Delete ${p.name}`}
                        onClick={() => confirm(`Delete ${p.name} and everything in it?`, () => act(() => api.deleteProject(p.id)))} />
                    </div>
                  </div>

                  <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.5px" }}>{p.name}</div>
                  <div className="note-body" style={{ marginTop: 8 }}>{p.description || "No description."}</div>

                  <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                    {p.stack && <span className="tag">{p.stack}</span>}
                    <span className="tag">{p.commits} commits</span>
                    <span className="tag">{p.note_count} notes</span>
                    {p.repo_url && <a className="tag" href={p.repo_url} target="_blank" rel="noreferrer">repo ↗</a>}
                  </div>

                  <div style={{ margin: "16px 0 6px", display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span style={{ color: "var(--text-2)" }}>Next: {p.phase}</span>
                    <span className="num" style={{ fontWeight: 700 }}>{p.completion}%</span>
                  </div>
                  <Bar pct={p.completion} />

                  <div className="card-h" style={{ marginTop: 20, marginBottom: 10 }}>
                    <span className="card-t">Phases</span>
                    <button className="link" onClick={() => open("phase", { name: "" }, p)}>+ Add</button>
                  </div>
                  {p.phases.length ? p.phases.map((ph) => (
                    <div className="row" key={ph.id} style={{ padding: "9px 0" }}>
                      <button className="ico-box" style={{ width: 30, height: 30 }} title={ph.done ? "Mark not done" : "Mark done"}
                        onClick={() => act(() => api.togglePhase(p.id, ph.id))}>
                        {ph.done ? <Icon.check s={15} /> : <Icon.plus s={15} />}
                      </button>
                      <div className="grow">
                        <div className="t" style={{ fontSize: 13, opacity: ph.done ? 0.55 : 1, textDecoration: ph.done ? "line-through" : "none" }}>
                          {ph.name}
                        </div>
                      </div>
                      <IconAction icon={Icon.trash} danger title="Delete phase"
                        onClick={() => confirm(`Delete phase ${ph.name}?`, () => act(() => api.deletePhase(p.id, ph.id)))} />
                    </div>
                  )) : <Empty>No phases — completion stays manual until you add some.</Empty>}

                  <div className="card-h" style={{ marginTop: 20, marginBottom: 10 }}>
                    <span className="card-t">Tasks · {p.open_tasks} open</span>
                    <button className="link" onClick={() => open("task", { title: "", due_at: toLocalInput(null, 20, 2) }, p)}>+ Add</button>
                  </div>
                  {p.tasks.length ? p.tasks.map((t) => (
                    <div className="row" key={t.id} style={{ padding: "9px 0" }}>
                      <button className="ico-box" style={{ width: 30, height: 30 }} title="Toggle"
                        onClick={() => act(() => api.toggleProjectTask(p.id, t.id))}>
                        {t.status === "done" ? <Icon.check s={15} /> : <Icon.projects s={15} />}
                      </button>
                      <div className="grow">
                        <div className="t" style={{ fontSize: 13, opacity: t.status === "done" ? 0.55 : 1, textDecoration: t.status === "done" ? "line-through" : "none" }}>
                          {t.title}
                        </div>
                        {t.due_at && <div className="s">{fmtDue(t.due_at)}</div>}
                      </div>
                    </div>
                  )) : <Empty>No project tasks yet.</Empty>}
                </div>
              );
            })}
          </div>
        ) : <Empty>No projects yet. Add one to start tracking phases and build tasks.</Empty>}
      </div>

      {dialog === "project" && (
        <Modal title="Add project" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createProject({
            name: f.name, description: f.description, stack: f.stack, phase: f.phase,
            status: f.status, priority: Number(f.priority) || 1, commits: Number(f.commits) || 0,
            repo_url: f.repo_url, ...(f.due_at ? { due_at: fromLocalInput(f.due_at) } : {}),
          }))}>
          <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required autoFocus /></Field>
          <Field label="Description"><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <div className="field-row">
            <Field label="Stack"><input value={f.stack} onChange={(e) => setF({ ...f, stack: e.target.value })} placeholder="Next.js / FastAPI" /></Field>
            <Field label="Status">
              <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
                {["Active", "Paused", "Shipped", "Archived"].map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
          </div>
          <div className="field-row">
            <Field label="Target date" hint="Optional — Spider Sense watches it"><input type="datetime-local" value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} /></Field>
            <Field label="Repo URL"><input value={f.repo_url} onChange={(e) => setF({ ...f, repo_url: e.target.value })} placeholder="https://…" /></Field>
          </div>
        </Modal>
      )}

      {dialog === "phase" && target && (
        <Modal title="Add phase" sub={`${target.name} — completion is recomputed from phases.`}
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.addPhase(target.id, { name: f.name }))}>
          <Field label="Phase name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required autoFocus /></Field>
        </Modal>
      )}

      {dialog === "task" && target && (
        <Modal title="Add project task" sub={`${target.name} — it also appears on your Planner.`}
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.addProjectTask(target.id, {
            title: f.title, ...(f.due_at ? { due_at: fromLocalInput(f.due_at) } : {}),
          }))}>
          <Field label="Title"><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required autoFocus /></Field>
          <Field label="Due" hint="Optional"><input type="datetime-local" value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} /></Field>
        </Modal>
      )}
    </ModulePage>
  );
}
