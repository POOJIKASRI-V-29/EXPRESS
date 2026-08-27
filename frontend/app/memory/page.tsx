"use client";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { Empty, Loading, ErrorState } from "@/components/states";
import { Shell } from "@/components/shell";
import { Atmosphere } from "@/components/atmosphere";
import { Modal, Field, Stat, AddButton, IconAction, useConfirm } from "@/components/ui";
import { useRequireAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { MemoryPayload, MemoryItem } from "@/lib/types";

type Convo = { id: string; role: string; content: string; tool_name: string | null; created_at: string };

export default function MemoryPage() {
  const { user, ready } = useRequireAuth();
  const [data, setData] = useState<MemoryPayload | null>(null);
  const [convo, setConvo] = useState<Convo[]>([]);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("All");
  const [tab, setTab] = useState<"memories" | "transcript">("memories");
  const [dialog, setDialog] = useState<null | "add" | "edit">(null);
  const [editing, setEditing] = useState<MemoryItem | null>(null);
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  // Search runs on the server, so it matches every memory — not just the page.
  const load = useCallback(async (query: string, category: string, quiet = false) => {
    if (!quiet) setState("loading");
    try {
      const [m, c] = await Promise.all([api.memory(query, category), api.conversations()]);
      setData(m); setConvo(c); setState("ready");
    } catch (e: any) { setError(e.message); setState("error"); }
  }, []);

  useEffect(() => { if (ready && user) load(q, cat); /* eslint-disable-next-line */ }, [ready, user]);

  useEffect(() => {
    if (!ready || !user) return;
    const t = setTimeout(() => load(q, cat, true), 220);   // debounce the server search
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, cat]);

  async function act(fn: () => Promise<any>) {
    setBusy(true);
    try { await fn(); await load(q, cat, true); }
    catch (e: any) { setError(e.message); setState("error"); }
    setBusy(false); setDialog(null); setEditing(null);
  }

  if (!ready || !user) return null;
  const d = data;

  return (
    <>
      <Atmosphere />
      <Shell>
        <div className="head-row">
          <div>
            <div className="eyebrow">JOCASTA · LONG-TERM STORE</div>
            <h1 className="page-h" style={{ marginTop: 8 }}>Memory</h1>
            <p className="page-sub">
              Everything JOCasta has been told to remember — and everything you've written here yourself.
              Search it, correct it, or delete it. What JOCasta saved is labelled as such.
            </p>
          </div>
          <AddButton label="Memory" onClick={() => { setF({ text: "", category: "Note" }); setDialog("add"); }} />
        </div>

        {state === "loading" && <Loading label="Reading the memory store…" />}
        {state === "error" && <ErrorState message={error} onRetry={() => load(q, cat)} />}

        {state === "ready" && d && (
          <div style={{ marginTop: 22 }} className="stack">
            <div className="stats">
              <Stat k="Stored" v={d.total} n="memories in total" />
              <Stat k="From JOCasta" v={d.from_jocasta} n="saved by the assistant" />
              <Stat k="Written by you" v={d.total - d.from_jocasta} />
              <Stat k="Pinned" v={d.pinned} />
            </div>

            <div className="tabs">
              <button className={"tab" + (tab === "memories" ? " on" : "")} onClick={() => setTab("memories")}>Memories</button>
              <button className={"tab" + (tab === "transcript" ? " on" : "")} onClick={() => setTab("transcript")}>
                Transcript · {convo.length}
              </button>
            </div>

            {tab === "memories" && (
              <div className="card">
                <div className="capture" style={{ marginBottom: 14 }}>
                  <Icon.search s={16} />
                  <input placeholder="Trace a thread…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
                  {q && <button className="iconbtn sm" aria-label="Clear search" onClick={() => setQ("")}><Icon.x s={13} /></button>}
                </div>

                <div className="chips" style={{ marginBottom: 16 }}>
                  <button className={"chip" + (cat === "All" ? " on" : "")} onClick={() => setCat("All")}>
                    All · {d.total}
                  </button>
                  {Object.entries(d.counts).map(([c, n]) => (
                    <button key={c} className={"chip" + (cat === c ? " on" : "")} onClick={() => setCat(c)}>
                      {c} · {n}
                    </button>
                  ))}
                </div>

                <div className="card-h">
                  <span className="card-t">
                    {q || cat !== "All" ? `${d.memories.length} match${d.memories.length === 1 ? "" : "es"}` : `All ${d.total}`}
                  </span>
                  {(q || cat !== "All") && (
                    <button className="link" onClick={() => { setQ(""); setCat("All"); }}>Clear filters</button>
                  )}
                </div>

                {d.memories.length ? d.memories.map((m) => (
                  <div className="row" key={m.id} style={{ alignItems: "flex-start" }}>
                    <button className="ico-box" title={m.pinned ? "Unpin" : "Pin"}
                      style={m.pinned ? { color: "var(--blue-soft)", borderColor: "rgba(124,156,242,.4)" } : undefined}
                      onClick={() => act(() => api.updateMemory(m.id, { pinned: !m.pinned }))}>
                      <Icon.pin s={16} />
                    </button>
                    <div className="grow">
                      <div className="t" style={{ lineHeight: 1.5 }}>{m.text}</div>
                      <div style={{ marginTop: 8 }}>
                        <span className="tag">{m.category}</span>
                        <span className="tag">{m.source === "jocasta" ? "saved by JOCasta" : "written by you"}</span>
                        <span className="tag">{fmtDate(m.created_at)}</span>
                      </div>
                    </div>
                    <div className="row-acts">
                      <IconAction icon={Icon.edit} title="Edit memory"
                        onClick={() => { setEditing(m); setF({ text: m.text, category: m.category }); setDialog("edit"); }} />
                      <IconAction icon={Icon.trash} danger title="Delete memory"
                        onClick={() => confirm("Delete this memory? JOCasta will stop recalling it.", () => act(() => api.deleteMemory(m.id)))} />
                    </div>
                  </div>
                )) : (
                  <Empty>
                    {q || cat !== "All"
                      ? `Nothing matches${q ? ` “${q}”` : ""}${cat !== "All" ? ` in ${cat}` : ""}.`
                      : "The web is quiet here. Tell JOCasta “remember that…” and it lands in this store."}
                  </Empty>
                )}
              </div>
            )}

            {tab === "transcript" && (
              <div className="card">
                <div className="card-h">
                  <span className="card-t">JOCasta transcript</span>
                  <span className="mini">what was said, and which tools ran</span>
                </div>
                {convo.length ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {convo.map((c) => c.role === "user" ? (
                      <div className="bubble me" key={c.id}>{c.content}</div>
                    ) : c.role === "assistant" ? (
                      <div className="bubble joc" key={c.id}>{c.content}</div>
                    ) : (
                      <div className="mini" key={c.id} style={{ paddingLeft: 4 }}>
                        <Icon.joc s={11} /> {c.tool_name} → {c.content.slice(0, 140)}{c.content.length > 140 ? "…" : ""}
                      </div>
                    ))}
                  </div>
                ) : <Empty>No conversations yet.</Empty>}
              </div>
            )}
          </div>
        )}

        {dialog === "add" && (
          <Modal title="Add memory" sub="JOCasta will recall this when it's relevant."
            onClose={() => setDialog(null)} busy={busy}
            onSubmit={() => act(() => api.createMemory(f))}>
            <Field label="Memory"><textarea value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} required autoFocus placeholder="I prefer studying DSA at night." /></Field>
            <Field label="Category">
              <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {(d?.categories || ["Note"]).map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
          </Modal>
        )}

        {dialog === "edit" && editing && (
          <Modal title="Edit memory" sub={editing.source === "jocasta" ? "Originally saved by JOCasta." : undefined}
            onClose={() => { setDialog(null); setEditing(null); }} busy={busy}
            onSubmit={() => act(() => api.updateMemory(editing.id, f))}>
            <Field label="Memory"><textarea value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} required autoFocus /></Field>
            <Field label="Category">
              <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {(d?.categories || ["Note"]).map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
          </Modal>
        )}
      </Shell>
    </>
  );
}
