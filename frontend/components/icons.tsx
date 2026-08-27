import { ReactNode } from "react";
const S = ({ children, s = 18 }: { children: ReactNode; s?: number }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
export const Icon = {
  home: (p: any) => <S {...p}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></S>,
  college: (p: any) => <S {...p}><path d="M3 8l9-4 9 4-9 4-9-4Z" /><path d="M7 10.5V16c0 1 2.2 2.5 5 2.5s5-1.5 5-2.5v-5.5" /></S>,
  tasks: (p: any) => <S {...p}><path d="M4 6h16M4 12h16M4 18h10" /></S>,
  career: (p: any) => <S {...p}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></S>,
  spider: (p: any) => <S {...p}><path d="M12 2v20M2 12h20M4.5 4.5l15 15M19.5 4.5l-15 15" /><circle cx="12" cy="12" r="3.5" /></S>,
  joc: (p: any) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 3v18" /><path d="M12 12h9" fill="none" /></S>,
  bell: (p: any) => <S {...p}><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" /><path d="M10 20a2 2 0 0 0 4 0" /></S>,
  clock: (p: any) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></S>,
  check: (p: any) => <S {...p}><path d="M20 6 9 17l-5-5" /></S>,
  plus: (p: any) => <S {...p}><path d="M12 5v14M5 12h14" /></S>,
  send: (p: any) => <S {...p}><path d="m22 2-7 20-4-9-9-4 20-7Z" /></S>,
  mic: (p: any) => <S {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></S>,
  learning: (p: any) => <S {...p}><path d="M3 5h18v12H3zM3 20h18" /></S>,
  dumb: (p: any) => <S {...p}><path d="M4 9v6M8 7v10M16 7v10M20 9v6M8 12h8" /></S>,
  mail: (p: any) => <S {...p}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></S>,
  cal: (p: any) => <S {...p}><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M8 2v4M16 2v4" /></S>,
  projects: (p: any) => <S {...p}><path d="M3 7.5 12 3l9 4.5-9 4.5-9-4.5Z" /><path d="m3 12 9 4.5L21 12M3 16.5 12 21l9-4.5" /></S>,
  goals: (p: any) => <S {...p}><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="1" /></S>,
  finance: (p: any) => <S {...p}><rect x="2.5" y="6" width="19" height="12.5" rx="2" /><circle cx="12" cy="12.25" r="2.6" /><path d="M6 10v4.5M18 10v4.5" /></S>,
  memory: (p: any) => <S {...p}><path d="M12 4.5a3.5 3.5 0 0 0-6.6 1.6A3 3 0 0 0 4 12a3 3 0 0 0 1.7 5.3A3.4 3.4 0 0 0 12 19.5Z" /><path d="M12 4.5a3.5 3.5 0 0 1 6.6 1.6A3 3 0 0 1 20 12a3 3 0 0 1-1.7 5.3A3.4 3.4 0 0 1 12 19.5Z" /></S>,
  progress: (p: any) => <S {...p}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></S>,
  plug: (p: any) => <S {...p}><path d="M9 3v6M15 3v6" /><path d="M6 9h12v3a6 6 0 0 1-12 0Z" /><path d="M12 18v3" /></S>,
  note: (p: any) => <S {...p}><path d="M5 3h9l5 5v13H5Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></S>,
  search: (p: any) => <S {...p}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></S>,
  trash: (p: any) => <S {...p}><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></S>,
  edit: (p: any) => <S {...p}><path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17Z" /><path d="M14.5 6.5 17.5 9.5" /></S>,
  pin: (p: any) => <S {...p}><path d="M9 3h6l-1 6 4 3v2H6v-2l4-3Z" /><path d="M12 14v7" /></S>,
  link: (p: any) => <S {...p}><path d="M10 13.5a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 1 0-5.7-5.7L11.4 6.4" /><path d="M14 10.5a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 1 0 5.7 5.7l1.4-1.4" /></S>,
  x: (p: any) => <S {...p}><path d="M6 6 18 18M18 6 6 18" /></S>,
  chev: (p: any) => <S {...p}><path d="m9 6 6 6-6 6" /></S>,
  gear: (p: any) => <S {...p}><circle cx="12" cy="12" r="3.2" /><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" /></S>,
  stop: (p: any) => <S {...p}><rect x="6" y="6" width="12" height="12" rx="2" /></S>,
};
export type IconName = keyof typeof Icon;
