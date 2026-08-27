"use client";
import { Icon } from "@/components/icons";
import { Empty } from "@/components/states";
import { ModulePage, Bar, Stat, useModule } from "@/components/ui";
import { api } from "@/lib/api";
import { money, minutes, fmtShort, titleCase } from "@/lib/format";
import type { ProgressReport } from "@/lib/types";

/** Bar series in the design's own palette — no new colours introduced. */
function Series({ values, labels, unit }: { values: number[]; labels: string[]; unit: string }) {
  const max = Math.max(1, ...values);
  const total = values.reduce((a, b) => a + b, 0);
  return (
    <>
      <div className="spark" role="img" aria-label={`${unit} per day for the last ${values.length} days`}>
        {values.map((v, i) => (
          <i key={i} className={v > 0 ? "on" : ""}
            style={{ height: `${Math.max(v > 0 ? 8 : 3, (v / max) * 100)}%` }}
            title={`${labels[i]}: ${v} ${unit}`} />
        ))}
      </div>
      <div className="mini" style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
        <span>{fmtShort(labels[0])}</span>
        <span>{total} {unit} over {values.length} days</span>
        <span>{fmtShort(labels[labels.length - 1])}</span>
      </div>
    </>
  );
}

export default function ProgressPage() {
  const { user, ready, data, state, error, reload } = useModule<ProgressReport>(() => api.progressReport());
  if (!ready || !user) return null;
  const r = data;

  return (
    <ModulePage
      eyebrow={r ? `GENERATED ${new Date(r.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "PROGRESS"}
      title="Progress"
      sub="Every module reporting its own real state. Where a module has no data, it says zero rather than guessing."
      state={state} error={error} onRetry={reload}
    >
      {r && (
        <div className="stack">
          <div className="stats">
            <Stat k="Tasks done" v={`${r.tasks.done}/${r.tasks.total}`} n={`${r.tasks.completion_pct}% complete`} />
            <Stat k="Overdue" v={r.tasks.overdue} tone={r.tasks.overdue ? "red" : undefined} n={`${r.tasks.open} still open`} />
            <Stat k="Attendance" v={`${r.college.attendance}%`} n={`${r.college.courses} courses`}
              tone={r.college.at_risk.length ? "red" : undefined} />
            <Stat k="Active signals" v={r.signals.active} tone={r.signals.active ? "red" : "green"} />
          </div>

          <div className="g-2">
            <div className="g-col">
              <div className="card">
                <div className="card-h">
                  <span className="card-t">Tasks completed · last 14 days</span>
                  <span className="pill">{r.tasks.completion_pct}%</span>
                </div>
                <Series values={r.tasks.series.map((s) => s.count)} labels={r.tasks.series.map((s) => s.date)} unit="done" />
              </div>

              <div className="card">
                <div className="card-h">
                  <span className="card-t">Study time · last 14 days</span>
                  <span className="pill">{minutes(r.learning.total_minutes)}</span>
                </div>
                <Series values={r.learning.series.map((s) => s.minutes)} labels={r.learning.series.map((s) => s.date)} unit="min" />
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">College</span></div>
                <div className="kv"><span className="k">Coursework done</span>
                  <span className="v">{r.college.assignments_done}/{r.college.assignments_total}</span></div>
                <div className="kv"><span className="k">Average attendance</span><span className="v">{r.college.attendance}%</span></div>
                {r.college.at_risk.length ? r.college.at_risk.map((c) => (
                  <div className="kv" key={c.name}>
                    <span className="k" style={{ color: "var(--red)" }}>{c.name} at risk</span>
                    <span className="v" style={{ color: "var(--red)" }}>{c.attendance}%</span>
                  </div>
                )) : <div className="kv"><span className="k">Courses at risk</span><span className="v">None</span></div>}
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Career pipeline</span><span className="pill">{r.career.applications}</span></div>
                {r.career.applications ? Object.entries(r.career.by_stage).map(([stage, n]) => (
                  <div key={stage} style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
                      <span>{titleCase(stage)}</span><span className="v num">{n}</span>
                    </div>
                    <Bar pct={(n / Math.max(1, r.career.applications)) * 100} />
                  </div>
                )) : <Empty>No applications tracked yet.</Empty>}
              </div>
            </div>

            <div className="g-col">
              <div className="card">
                <div className="card-h"><span className="card-t">Learning</span></div>
                <div className="kv"><span className="k">Topics</span><span className="v">{r.learning.topics}</span></div>
                <div className="kv"><span className="k">Strong</span><span className="v">{r.learning.strong}</span></div>
                <div className="kv"><span className="k">Needs revision</span>
                  <span className="v" style={r.learning.needs_revision ? { color: "var(--red)" } : undefined}>{r.learning.needs_revision}</span></div>
                <div className="kv"><span className="k">Sessions logged</span><span className="v">{r.learning.session_count}</span></div>
                <div style={{ marginTop: 14 }}>
                  <div className="mini" style={{ marginBottom: 6 }}>Average topic progress · {r.learning.avg_progress}%</div>
                  <Bar pct={r.learning.avg_progress} />
                </div>
                <div style={{ marginTop: 12 }}>
                  <div className="mini" style={{ marginBottom: 6 }}>Average skill · {r.learning.avg_skill}% across {r.learning.skills}</div>
                  <Bar pct={r.learning.avg_skill} />
                </div>
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Projects & Goals</span></div>
                <div className="kv"><span className="k">Active projects</span><span className="v">{r.projects.active}/{r.projects.total}</span></div>
                <div style={{ margin: "10px 0 16px" }}>
                  <div className="mini" style={{ marginBottom: 6 }}>Average completion · {r.projects.avg_completion}%</div>
                  <Bar pct={r.projects.avg_completion} />
                </div>
                <div className="kv"><span className="k">Active goals</span><span className="v">{r.goals.active}/{r.goals.total}</span></div>
                <div className="kv"><span className="k">Achieved</span><span className="v">{r.goals.achieved}</span></div>
                <div style={{ marginTop: 10 }}>
                  <div className="mini" style={{ marginBottom: 6 }}>Average goal progress · {r.goals.avg_progress}%</div>
                  <Bar pct={r.goals.avg_progress} />
                </div>
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Habits & Personal</span></div>
                <div className="kv"><span className="k">Habits done today</span>
                  <span className="v">{r.habits.done_today}/{r.habits.total}</span></div>
                <div className="kv"><span className="k">Best streak</span><span className="v">{r.habits.best_streak} days</span></div>
                <div className="kv"><span className="k">Notes</span><span className="v">{r.personal.notes}</span></div>
                <div className="kv"><span className="k">Memories</span><span className="v">{r.personal.memories}</span></div>
              </div>

              <div className="card">
                <div className="card-h"><span className="card-t">Finance · this month</span></div>
                <div className="kv"><span className="k">Spent</span><span className="v">{money(r.finance.month_spent)}</span></div>
                <div className="kv"><span className="k">Income</span><span className="v">{money(r.finance.month_income)}</span></div>
                <div className="kv"><span className="k">Net</span>
                  <span className="v" style={{ color: r.finance.net < 0 ? "var(--red)" : "var(--green)" }}>{money(r.finance.net)}</span></div>
                {r.finance.budgets.length ? r.finance.budgets.slice(0, 4).map((b) => (
                  <div key={b.id} style={{ marginTop: 12 }}>
                    <div className="mini" style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                      <span>{b.category}</span><span>{b.pct}%</span>
                    </div>
                    <Bar pct={b.pct} tone={b.state === "ok" ? "blue" : "red"} />
                  </div>
                )) : <div className="mini" style={{ marginTop: 10 }}>No budgets set.</div>}
              </div>
            </div>
          </div>
        </div>
      )}
    </ModulePage>
  );
}
