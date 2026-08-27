"use client";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Icon } from "./icons";
import { useAuth } from "@/lib/auth";

export const NAV = [
  { href: "/", label: "COMMAND CENTER", icon: Icon.home },
  { href: "/planner", label: "PLANNER", icon: Icon.cal },
  { href: "/tasks", label: "TASKS", icon: Icon.tasks },
  { href: "/college", label: "COLLEGE", icon: Icon.college },
  { href: "/learning", label: "LEARNING", icon: Icon.learning },
  { href: "/projects", label: "PROJECTS", icon: Icon.projects },
  { href: "/career", label: "CAREER", icon: Icon.career },
  { href: "/goals", label: "GOALS", icon: Icon.goals },
  { href: "/personal", label: "PERSONAL", icon: Icon.note },
  { href: "/finance", label: "FINANCE", icon: Icon.finance },
  { href: "/memory", label: "MEMORY", icon: Icon.memory },
  { href: "/progress", label: "PROGRESS", icon: Icon.progress },
  { href: "/integrations", label: "INTEGRATIONS", icon: Icon.plug },
  { href: "/jocasta", label: "JOCASTA", icon: Icon.joc },
];

export function Shell({ children, red = false }: { children: React.ReactNode; red?: boolean }) {
  const path = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const initials = (user?.name || "P").slice(0, 1).toUpperCase();

  const go = (href: string) => { setDrawer(false); router.push(href); };

  const navList = (
    <nav className="navlist">
      {NAV.map((n) => {
        const on = path === n.href;
        return (
          <button key={n.href} className={"navitem" + (on ? " on" : "")} onClick={() => go(n.href)}>
            <n.icon s={17} />{n.label}
          </button>
        );
      })}
      <div style={{ flex: 1, minHeight: 12 }} />
      <button className="jocchip" onClick={() => go("/jocasta")}>
        <Icon.joc s={20} />
        <div style={{ textAlign: "left" }}><div className="nm">JOCASTA CORE</div><div className="st">ONLINE & SYNCING</div></div>
        <div style={{ flex: 1 }} /><div className="dot-on" />
      </button>
    </nav>
  );

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <Icon.spider s={26} />
          <div><b>EXPRESS</b><small>COMMAND CENTER</small></div>
        </div>
        {navList}
      </aside>

      {drawer && (
        <>
          <div className="scrim" onClick={() => setDrawer(false)} aria-hidden />
          <aside className="side drawer">
            <div className="brand">
              <Icon.spider s={26} />
              <div><b>EXPRESS</b><small>COMMAND CENTER</small></div>
              <div style={{ flex: 1 }} />
              <button className="iconbtn" aria-label="Close menu" onClick={() => setDrawer(false)}><Icon.x s={16} /></button>
            </div>
            {navList}
          </aside>
        </>
      )}

      <div className="main">
        <header className="topbar">
          <button className="iconbtn hamb" aria-label="Menu" onClick={() => setDrawer(true)}><Icon.tasks s={17} /></button>
          <div style={{ flex: 1 }} />
          <div className="top-actions">
            <button className="iconbtn" aria-label="Notifications" onClick={() => router.push("/")}><Icon.bell s={17} /></button>
            <button className="avatar" onClick={logout} title="Log out">{initials}</button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>

      <nav className="botnav">
        <button className={path === "/" ? "on" : ""} onClick={() => router.push("/")} aria-label="Command Center"><Icon.home s={20} /></button>
        <button className={path === "/planner" ? "on" : ""} onClick={() => router.push("/planner")} aria-label="Planner"><Icon.cal s={20} /></button>
        <button className="cap" onClick={() => router.push("/jocasta")} aria-label="JOCasta"><Icon.plus s={20} /></button>
        <button className={path === "/tasks" ? "on" : ""} onClick={() => router.push("/tasks")} aria-label="Tasks"><Icon.tasks s={20} /></button>
        <button onClick={() => setDrawer(true)} aria-label="All modules"><Icon.chev s={20} /></button>
      </nav>
    </div>
  );
}
