export function Atmosphere({ red = false }: { red?: boolean }) {
  return (
    <div className={"atmos" + (red ? " red" : "")} aria-hidden>
      <div className="sky" />
      <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, opacity: 0.14 }}>
        <defs>
          <radialGradient id="web" cx="78%" cy="18%" r="70%">
            <stop offset="0%" stopColor={red ? "#E5675C" : "#7C9CF2"} stopOpacity="0.5" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
        {[...Array(9)].map((_, i) => (
          <line key={i} x1="78%" y1="18%" x2={`${(i / 8) * 100}%`} y2="100%" stroke="url(#web)" strokeWidth="0.6" />
        ))}
        {[26, 52, 82, 120, 170].map((r, i) => (
          <circle key={i} cx="78%" cy="18%" r={r} fill="none" stroke="url(#web)" strokeWidth="0.5" />
        ))}
      </svg>
    </div>
  );
}
