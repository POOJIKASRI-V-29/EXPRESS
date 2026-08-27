"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Icon, IconName } from "@/components/icons";
import { ModulePage, Stat, useModule, useConfirm } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { IntegrationsPayload } from "@/lib/types";

const PILL: Record<string, string> = {
  connected: "blue", pending: "blue", error: "red", disconnected: "", unconfigured: "",
};

/** `useSearchParams` needs a Suspense boundary for Next's static generation. */
export default function IntegrationsPage() {
  return (
    <Suspense fallback={null}>
      <IntegrationsView />
    </Suspense>
  );
}

function IntegrationsView() {
  const { user, ready, data, state, error, reload, act } = useModule<IntegrationsPayload>(() => api.integrations());
  const params = useSearchParams();
  const [busy, setBusy] = useState("");
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const confirm = useConfirm();

  // The OAuth callback redirects back here with the outcome.
  useEffect(() => {
    const connected = params.get("connected");
    const failed = params.get("error");
    if (connected) setFlash({ kind: "ok", text: `${connected} connected.` });
    else if (failed) setFlash({ kind: "err", text: failed });
    if (connected || failed) window.history.replaceState({}, "", "/integrations");
  }, [params]);

  async function connect(provider: string) {
    setBusy(provider);
    try {
      const { authorize_url } = await api.authorizeIntegration(provider);
      // Hand off to the provider's own consent screen.
      window.location.href = authorize_url;
    } catch (e: any) {
      setFlash({ kind: "err", text: e.message });
      setBusy("");
    }
  }

  if (!ready || !user) return null;
  const d = data;

  return (
    <ModulePage
      eyebrow="CONNECTIONS"
      title="Integrations"
      sub="What EXPRESS can reach outside itself. A provider only becomes connectable once the server actually holds its credentials, and tokens never reach this browser."
      state={state} error={error} onRetry={reload}
    >
      {d && (
        <div className="stack">
          {flash && (
            <div className={flash.kind === "ok" ? "gotit" : "ss-banner"}>
              {flash.kind === "ok" ? <div className="dot-on" /> : <div className="lbl"><Icon.spider s={13} /> COULDN&rsquo;T CONNECT</div>}
              <div style={{ flex: 1, fontSize: 13, fontWeight: 600 }}>{flash.text}</div>
              <button className="iconbtn sm" aria-label="Dismiss" onClick={() => setFlash(null)}><Icon.x s={13} /></button>
            </div>
          )}

          <div className="stats">
            <Stat k="Connected" v={d.connected} n={`${d.integrations.length} providers`} />
            <Stat k="Ready to connect" v={d.integrations.filter((i) => i.connectable).length} n="credentials present" />
            <Stat k="Unconfigured" v={d.integrations.filter((i) => !i.connectable).length} n="need server setup" />
          </div>

          <div className="card">
            <div className="card-t" style={{ marginBottom: 6 }}>How this works</div>
            <div className="note-body">{d.note}</div>
          </div>

          <div className="g-auto">
            {d.integrations.map((i) => {
              const I = (Icon[i.icon as IconName] || Icon.plug);
              const live = i.status === "connected";
              return (
                <div className="card" key={i.provider}>
                  <div className="card-h">
                    <span className="card-t">{i.provider}</span>
                    <span className={"pill " + PILL[i.status]}>{i.status}</span>
                  </div>
                  <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                    <div className="ico-box" style={live ? { color: "var(--blue-soft)", borderColor: "rgba(124,156,242,.4)" } : undefined}>
                      <I s={18} />
                    </div>
                    <div className="grow">
                      <div style={{ fontSize: 16, fontWeight: 700 }}>{i.label}</div>
                      <div className="note-body" style={{ marginTop: 6 }}>{i.blurb}</div>
                    </div>
                  </div>

                  <div style={{ marginTop: 14 }}>
                    {i.scopes.split(" ").filter(Boolean).map((s) => (
                      <span className="tag" key={s}>{s.replace("https://www.googleapis.com/auth/", "")}</span>
                    ))}
                  </div>

                  {i.requires && (
                    <div className="mini" style={{ marginTop: 12 }}>Unavailable: {i.requires}.</div>
                  )}
                  {i.last_error && (
                    <div className="mini" style={{ marginTop: 12, color: "var(--red)" }}>{i.last_error}</div>
                  )}
                  {i.account_label && <div className="mini" style={{ marginTop: 12 }}>Account: {i.account_label}</div>}
                  {live && (
                    <div className="mini" style={{ marginTop: 6 }}>
                      {i.last_sync_at ? `Last sync ${fmtDate(i.last_sync_at)}` : "Connected — no sync has run yet"}
                      {i.token_expired ? " · token expired" : ""}
                    </div>
                  )}

                  <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
                    {live ? (
                      <>
                        <button className="btn sm" disabled={busy === i.provider}
                          onClick={() => act(() => api.refreshIntegration(i.provider))}>Refresh token</button>
                        <button className="btn sm ghost-red"
                          onClick={() => confirm(`Disconnect ${i.label}? Stored tokens are destroyed.`,
                            () => act(() => api.disconnectIntegration(i.provider)))}>
                          Disconnect
                        </button>
                      </>
                    ) : (
                      <button className="btn sm primary" disabled={!i.connectable || busy === i.provider}
                        onClick={() => connect(i.provider)}>
                        {!i.connectable ? "Unavailable"
                          : busy === i.provider ? "Redirecting…"
                          : i.status === "error" ? "Try again" : "Connect"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </ModulePage>
  );
}
