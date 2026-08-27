"use client";
import { useEffect, useState, useCallback } from "react";
import { Shell } from "@/components/shell";
import { Atmosphere } from "@/components/atmosphere";
import { Icon, IconName } from "@/components/icons";
import { Loading, ErrorState, Empty } from "@/components/states";
import { useRequireAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";

const PRI_NEXT: Record<string, string> = { low: "med", med: "high", high: "low" };
const PRI_CLASS: Record<string, string> = { low: "", med: "blue", high: "red" };

function inDays(n: number, hour = 9) {
  const d = new Date(); d.setDate(d.getDate() + n); d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

export default function TasksPage() {
  const { user, ready } = useRequireAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    try { setTasks(await api.tasks()); setState("ready"); }
    catch (e: any) { setError(e.message); setState("error"); }
  }, []);
  useEffect(() => { if (ready && user) load(); }, [ready, user, load]);

  async function complete(id: string) { await api.completeTask(id); load(); }
  async function reschedule(id: string, n: number) { await api.reschedule(id, inDays(n)); load(); }
  async function cyclePriority(t: Task) { await api.updateTask(t.id, { priority: PRI_NEXT[t.priority] }); load(); }

  if (!ready || !user) return null;
  const open = tasks.filter((t) => t.status === "open");
  const done = tasks.filter((t) => t.status === "done");

  return (
    <>
      <Atmosphere />
      <Shell>
        <h1 className="page-h">Tasks</h1>
        <p className="page-sub">Everything EXPRESS is tracking for you — assignments, reminders and personal work in one queue.</p>

        {state === "loading" && <Loading />}
        {state === "error" && <ErrorState message={error} onRetry={load} />}
        {state === "ready" && (
          <div style={{ marginTop: 22, display: "grid", gap: 20, gridTemplateColumns: "1fr" }}>
            <div className="card">
              <div className="card-h"><span className="card-t">Open · {open.length}</span></div>
              {open.length ? open.map((t) => {
                const I = Icon[(t.icon as IconName)] || Icon.tasks;
                return (
                  <div className="row" key={t.id}>
                    <button className="ico-box" onClick={() => complete(t.id)} title="Complete"><I s={18} /></button>
                    <div className="grow">
                      <div className="t">{t.title}</div>
                      <div className="s">{t.meta || t.category}{t.postpone_count ? ` · moved ${t.postpone_count}×` : ""}</div>
                    </div>
                    <button className={"pill " + PRI_CLASS[t.priority]} onClick={() => cyclePriority(t)}>{t.priority}</button>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn sm" onClick={() => reschedule(t.id, 0)}>Today</button>
                      <button className="btn sm" onClick={() => reschedule(t.id, 1)}>Tmrw</button>
                      <button className="btn sm" onClick={() => reschedule(t.id, 3)}>+3d</button>
                    </div>
                    <button className="btn sm primary" onClick={() => complete(t.id)}><Icon.check s={14} /></button>
                  </div>
                );
              }) : <Empty>Inbox zero. Nothing open.</Empty>}
            </div>

            {done.length > 0 && (
              <div className="card">
                <div className="card-h"><span className="card-t">Completed · {done.length}</span></div>
                {done.map((t) => (
                  <div className="row" key={t.id} style={{ opacity: 0.5 }}>
                    <div className="ico-box"><Icon.check s={16} /></div>
                    <div className="grow"><div className="t" style={{ textDecoration: "line-through" }}>{t.title}</div></div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Shell>
    </>
  );
}
