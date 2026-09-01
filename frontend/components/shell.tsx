"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Icon } from "./icons";
import { useAuth } from "@/lib/auth";

/**
 * Seven primary destinations, one question each:
 *   Home      what matters right now
 *   Planner   what am I doing today   (tasks live here, not as their own page)
 *   College   what courses do I have
 *   Learning  what am I learning
 *   Projects  what am I building
 *   Goals     what am I trying to become
 *   JOCasta   help me manage all of it
 */
export const NAV = [
  { href: "/", label: "HOME", icon: Icon.home },
  { href: "/planner", label: "PLANNER", icon: Icon.cal },
  { href: "/college", label: "COLLEGE", icon: Icon.college },
  { href: "/learning", label: "LEARNING", icon: Icon.learning },
  { href: "/projects", label: "PROJECTS", icon: Icon.projects },
  { href: "/goals", label: "GOALS", icon: Icon.goals },
  { href: "/jocasta", label: "JOCASTA", icon: Icon.joc },
];

/**
 * Still reachable, still working — just not competing for attention with the
 * seven above. Routes are unchanged, so existing links keep resolving.
 */
export const SECONDARY = [
  { href: "/memory", label: "Memory", icon: Icon.memory },
  { href: "/progress", label: "Progress", icon: Icon.progress },
  { href: "/personal", label: "Notes & habits", icon: Icon.note },
  { href: "/finance", label: "Finance", icon: Icon.finance },
  { href: "/career", label: "Career", icon: Icon.career },
  { href: "/integrations", label: "Integrations", icon: Icon.plug },
];

export function Shell({ children, red = false }: { children: React.ReactNode; red?: boolean }) {
  const path = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const initials = (user?.name || "P").slice(0, 1).toUpperCase();

  const go = (href: string) => { setDrawer(false); setMenu(false); router.push(href); };
  const active = (href: string) => href === "/" ? path === "/" : path.startsWith(href);

  // Close the profile menu on an outside click or Escape.
  useEffect(() => {
    if (!menu) return;
    const away = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    document.addEventListener("mousedown", away);
    window.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); window.removeEventListener("keydown", esc); };
  }, [menu]);

  const navList = (
    <nav className="navlist">
      {NAV.map((n) => (
        <button key={n.href} className={"navitem" + (active(n.href) ? " on" : "")}
          onClick={() => go(n.href)} aria-current={active(n.href) ? "page" : undefined}>
          <n.icon s={17} />{n.label}
        </button>
      ))}
      <div style={{ flex: 1, minHeight: 12 }} />
      <button className="jocchip" onClick={() => go("/jocasta")}>
        <Icon.joc s={20} />
        <div style={{ textAlign: "left" }}>
          <div className="nm">JOCASTA CORE</div>
          <div className="st">ONLINE &amp; SYNCING</div>
        </div>
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
              <button className="iconbtn" aria-label="Close menu" onClick={() => setDrawer(false)}>
                <Icon.x s={16} />
              </button>
            </div>
            {navList}
            <div className="drawer-more">
              <div className="section-t" style={{ marginBottom: 8 }}>More</div>
              {SECONDARY.map((s) => (
                <button key={s.href} className="navitem" onClick={() => go(s.href)}>
                  <s.icon s={16} />{s.label}
                </button>
              ))}
            </div>
          </aside>
        </>
      )}

      <div className="main">
        <header className="topbar">
          <button className="iconbtn hamb" aria-label="Menu" onClick={() => setDrawer(true)}>
            <Icon.tasks s={17} />
          </button>
          <div style={{ flex: 1 }} />
          <div className="top-actions" ref={menuRef}>
            <button className="iconbtn" aria-label="Ask JOCasta" onClick={() => go("/jocasta")}>
              <Icon.joc s={17} />
            </button>
            <div style={{ position: "relative" }}>
              <button className="avatar" onClick={() => setMenu((m) => !m)}
                aria-haspopup="menu" aria-expanded={menu} aria-label="Profile and settings">
                {initials}
              </button>
              {menu && (
                <div className="menu" role="menu">
                  <div className="menu-head">
                    <div className="menu-name">{user?.name}</div>
                    <div className="menu-mail">{user?.email}</div>
                  </div>
                  {SECONDARY.map((s) => (
                    <button key={s.href} className="menu-item" role="menuitem"
                      onClick={() => go(s.href)}>
                      <s.icon s={15} />{s.label}
                    </button>
                  ))}
                  <div className="menu-sep" />
                  <button className="menu-item danger" role="menuitem" onClick={logout}>
                    <Icon.x s={15} />Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>

      {/* Five thumb-reachable destinations; everything else is behind More. */}
      <nav className="botnav">
        <button className={active("/") ? "on" : ""} onClick={() => router.push("/")} aria-label="Home">
          <Icon.home s={20} />
        </button>
        <button className={active("/planner") ? "on" : ""} onClick={() => router.push("/planner")} aria-label="Planner">
          <Icon.cal s={20} />
        </button>
        <button className="cap" onClick={() => router.push("/jocasta")} aria-label="Ask JOCasta">
          <Icon.joc s={20} />
        </button>
        <button className={active("/college") ? "on" : ""} onClick={() => router.push("/college")} aria-label="College">
          <Icon.college s={20} />
        </button>
        <button onClick={() => setDrawer(true)} aria-label="More">
          <Icon.chev s={20} />
        </button>
      </nav>
    </div>
  );
}
