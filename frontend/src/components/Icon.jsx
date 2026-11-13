// Ícones em SVG (traço), sem dependência externa. Uso: <Icon name="chat" />
const PATHS = {
  chat: "M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z",
  pulse: "M3 12h4l3-8 4 16 3-8h4",
  contacts: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M21 19v-1a4 4 0 0 0-3-3.9M16 3.1a3.5 3.5 0 0 1 0 6.8",
  phone: "M7 2h10a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1ZM11 18h2",
  building: "M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16M15 9h4a1 1 0 0 1 1 1v11M3 21h18M8 8h3M8 12h3M8 16h3",
  user: "M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
  plug: "M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0V8ZM12 17v5",
  tag: "M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9-9-9ZM8 8h.01",
  list: "M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01",
  zap: "M13 2 4 14h7l-1 8 9-12h-7l1-8Z",
  logout: "M15 17l5-5-5-5M20 12H9M12 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h7",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z",
  transfer: "M7 7h13l-4-4M17 17H4l4 4",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM21 21l-4.3-4.3",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6",
  eyeOff: "M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2",
  plus: "M12 5v14M5 12h14",
  arrowLeft: "M19 12H5M12 19l-7-7 7-7",
  inbox: "M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6l3.5-7Z",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 6v6l4 2",
  wifiOff: "M2 2l20 20M8.5 16.4a5 5 0 0 1 7 0M5 12.9a10 10 0 0 1 4.3-2.6M19 12.9a10 10 0 0 0-2.1-1.6M1.4 9a15 15 0 0 1 4.4-2.7M22.6 9A15 15 0 0 0 10.7 5M12 20h.01",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z",
  archive: "M3 4h18v4H3ZM5 8v12h14V8M10 12h4",
  trash: "M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15",
  whatsapp: "M3 21l1.6-4.8A9 9 0 1 1 8 19.6L3 21ZM9 9.5c0 3 2.5 5.5 5.5 5.5l1.3-1.3-2-1-1 1a4 4 0 0 1-2.5-2.5l1-1-1-2L9 9.5Z",
};

export default function Icon({ name, size = 18, className = "", title }) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      <path d={d} />
    </svg>
  );
}
