"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Atmosphere } from "@/components/atmosphere";
import { Icon } from "@/components/icons";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("demo@express.os");
  const [password, setPassword] = useState("expressdemo");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr(""); setBusy(true);
    try { await login(email, password); router.replace("/"); }
    catch (e: any) { setErr(e.message || "Login failed"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <Atmosphere />
      <div className="login-wrap">
        <div className="login-card">
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
            <Icon.spider s={30} />
            <div><h1>EXPRESS</h1><div className="eyebrow">COMMAND CENTER</div></div>
          </div>
          <div className="field">
            <label>Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
          </div>
          {err && <div className="err">{err}</div>}
          <button className="btn primary" style={{ width: "100%", marginTop: 20, justifyContent: "center" }} onClick={submit} disabled={busy}>
            {busy ? "Authenticating…" : "Initiate Session"}
          </button>
          <div style={{ color: "var(--text-3)", fontSize: 12, marginTop: 16, textAlign: "center" }}>
            Seeded demo: demo@express.os / expressdemo
          </div>
        </div>
      </div>
    </>
  );
}
