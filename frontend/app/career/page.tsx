"use client";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Modal, Field, Stat, AddButton, IconAction, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fromLocalInput, toLocalInput, fmtDue, isOverdue } from "@/lib/format";
import type { CareerPayload, Internship } from "@/lib/types";

const STAGE_LABEL: Record<string, string> = {
  applied: "Applied", oa: "Online Assessment", interview: "Interview", result: "Result",
};
type Dialog = null | "internship" | "application";

export default function CareerPage() {
  const { user, ready, data, state, error, reload, act } = useModule<CareerPayload>(() => api.career());
  const [dialog, setDialog] = useState<Dialog>(null);
  const [target, setTarget] = useState<Internship | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const open = (d: Dialog, init: any = {}, i: Internship | null = null) => { setF(init); setTarget(i); setDialog(d); };
  async function submit(fn: () => Promise<any>) { setBusy(true); await act(fn); setBusy(false); setDialog(null); }

  if (!ready || !user) return null;
  const c = data;

  return (
    <ModulePage
      eyebrow="CAREER PIPELINE"
      title="Career"
      sub="Applications with a deadline become dated tasks, so prep competes for real time alongside coursework."
      state={state} error={error} onRetry={reload}
      actions={<AddButton label="Opportunity" onClick={() => open("internship", { company: "", role: "", status: "Applied", location: "", link: "" })} />}
    >
      {c && (
        <div className="stack">
          <div className="stats">
            {c.stages.map((s) => (
              <Stat key={s} k={STAGE_LABEL[s] || s} v={c.pipeline[s] ?? 0}
                tone={s === "interview" && (c.pipeline[s] ?? 0) > 0 ? "green" : undefined} />
            ))}
          </div>

          {c.internships.length ? (
            <div className="g-auto">
              {c.internships.map((i) => (
                <div className="card" key={i.id}>
                  <div className="card-h">
                    <span className="card-t">{i.status}</span>
                    <IconAction icon={Icon.trash} danger title={`Delete ${i.company}`}
                      onClick={() => confirm(`Delete ${i.company} and its applications?`, () => act(() => api.deleteInternship(i.id)))} />
                  </div>

                  <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.4px" }}>{i.company}</div>
                  <div className="s" style={{ marginTop: 4 }}>{i.role}{i.location ? ` · ${i.location}` : ""}</div>
                  {i.link && <a className="tag" style={{ marginTop: 10, display: "inline-block" }} href={i.link} target="_blank" rel="noreferrer">posting ↗</a>}

                  <div className="card-h" style={{ marginTop: 18, marginBottom: 10 }}>
                    <span className="card-t">Stages</span>
                    <button className="link" onClick={() => open("application", { internship_id: i.id, stage: "applied", deadline: "", notes: "" }, i)}>+ Add</button>
                  </div>

                  {i.applications.length ? i.applications.map((a) => (
                    <div className="row" key={a.id}>
                      <div className="ico-box" style={a.stage === "interview" ? { color: "var(--green)" } : undefined}>
                        <Icon.career s={16} />
                      </div>
                      <div className="grow">
                        <select className="t" style={{ background: "transparent", border: "none", color: "var(--text)", fontSize: 14, fontWeight: 600, padding: 0 }}
                          value={a.stage} onChange={(e) => act(() => api.updateApplication(a.id, { stage: e.target.value }))}>
                          {c.stages.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
                        </select>
                        <div className="s">{a.notes || "No notes"}</div>
                      </div>
                      {a.deadline && (
                        <div className={"pill " + (isOverdue(a.deadline) ? "red" : "")}>{fmtDue(a.deadline)}</div>
                      )}
                      <IconAction icon={Icon.trash} danger title="Delete stage"
                        onClick={() => confirm("Delete this stage?", () => act(() => api.deleteApplication(a.id)))} />
                    </div>
                  )) : <Empty>No stages logged for this one yet.</Empty>}
                </div>
              ))}
            </div>
          ) : <Empty>No opportunities tracked yet. Add one to start a pipeline.</Empty>}
        </div>
      )}

      {dialog === "internship" && (
        <Modal title="Add opportunity" onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createInternship(f))}>
          <div className="field-row">
            <Field label="Company"><input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} required autoFocus /></Field>
            <Field label="Role"><input value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} required /></Field>
          </div>
          <div className="field-row">
            <Field label="Location"><input value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></Field>
            <Field label="Status">
              <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
                {["Applied", "In Progress", "Interviewing", "Result"].map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Posting link"><input value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} placeholder="https://…" /></Field>
        </Modal>
      )}

      {dialog === "application" && target && (
        <Modal title="Add stage" sub={`${target.company} — a stage with a deadline becomes a dated task.`}
          onClose={() => setDialog(null)} busy={busy}
          onSubmit={() => submit(() => api.createApplication({
            internship_id: target.id, stage: f.stage, notes: f.notes,
            ...(f.deadline ? { deadline: fromLocalInput(f.deadline) } : {}),
          }))}>
          <Field label="Stage">
            <select value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })} autoFocus>
              {(data?.stages || []).map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
            </select>
          </Field>
          <Field label="Deadline" hint="Optional — leave blank if there's nothing to schedule">
            <input type="datetime-local" value={f.deadline} onChange={(e) => setF({ ...f, deadline: e.target.value })} />
          </Field>
          <Field label="Notes"><textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="What to prepare…" /></Field>
        </Modal>
      )}
    </ModulePage>
  );
}
