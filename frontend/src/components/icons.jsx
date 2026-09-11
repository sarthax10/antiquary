// Stroke icons on a 24px grid, 1.5px stroke — drawn for this app, no icon font/library.
// Every icon is decorative by default (aria-hidden); give the *control* an accessible
// name instead of the glyph.
const Svg = ({ children, className, fill = "none", ...rest }) => (
  <svg
    viewBox="0 0 24 24"
    fill={fill}
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
    className={className}
    {...rest}
  >
    {children}
  </svg>
);

export const IconMark = (p) => (
  <Svg {...p}>
    <path d="M12 2.5c.5 4.9 2.6 7 7.5 7.5v.01c-4.9.5-7 2.6-7.5 7.5h-.01c-.5-4.9-2.6-7-7.5-7.5V10c4.9-.5 7-2.6 7.5-7.5Z" fill="currentColor" stroke="none" transform="translate(0 2)" />
  </Svg>
);
export const IconCreate = (p) => (
  <Svg {...p}>
    <path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3" />
    <path d="M12 8.2c.3 2.1 1.6 3.4 3.8 3.8-2.2.4-3.5 1.7-3.8 3.8-.4-2.1-1.7-3.4-3.8-3.8 2.1-.4 3.4-1.7 3.8-3.8Z" />
  </Svg>
);
export const IconReview = (p) => (
  <Svg {...p}>
    <rect x="6.5" y="3" width="11" height="18" rx="2" />
    <path d="M10.5 9.5v5l4-2.5-4-2.5Z" />
  </Svg>
);
export const IconLibrary = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="4" width="5" height="16" rx="1" />
    <rect x="9.5" y="4" width="5" height="16" rx="1" />
    <path d="m16.2 4.8 3.9-1 3.5 15.1-3.9 1Z" transform="translate(-1.2 0.3)" />
  </Svg>
);
export const IconArchive = (p) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="4.5" rx="1" />
    <path d="M4.5 8.5V19a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1V8.5M9.5 12.5h5" />
  </Svg>
);
export const IconMembers = (p) => (
  <Svg {...p}>
    <circle cx="9" cy="8.5" r="3.5" />
    <path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5" />
    <path d="M15.5 5.2a3.5 3.5 0 0 1 0 6.6M18 14.8c2 .6 3.2 2.3 3.5 5.2" />
  </Svg>
);
export const IconSearch = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4.5 4.5" />
  </Svg>
);
export const IconCommand = (p) => (
  <Svg {...p}>
    <path d="M9 6.5a2.5 2.5 0 1 0-2.5 2.5H9V6.5ZM9 9v6M15 9v6M9 15H6.5A2.5 2.5 0 1 0 9 17.5V15ZM15 15h2.5a2.5 2.5 0 1 1-2.5 2.5V15ZM15 9h2.5A2.5 2.5 0 1 0 15 6.5V9ZM9 9h6M9 15h6" />
  </Svg>
);
export const IconCheck = (p) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Svg>
);
export const IconX = (p) => (
  <Svg {...p}>
    <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
  </Svg>
);
export const IconUndo = (p) => (
  <Svg {...p}>
    <path d="M9 14 4.5 9.5 9 5" />
    <path d="M4.5 9.5h9.5a5.5 5.5 0 0 1 0 11H11" />
  </Svg>
);
export const IconRestore = IconUndo;
export const IconChevronL = (p) => (
  <Svg {...p}>
    <path d="m14.5 6-6 6 6 6" />
  </Svg>
);
export const IconChevronR = (p) => (
  <Svg {...p}>
    <path d="m9.5 6 6 6-6 6" />
  </Svg>
);
export const IconChevronDown = (p) => (
  <Svg {...p}>
    <path d="m6 9.5 6 6 6-6" />
  </Svg>
);
export const IconArrowLeft = (p) => (
  <Svg {...p}>
    <path d="M19.5 12h-15M10 6 4 12l6 6" />
  </Svg>
);
export const IconArrowRight = (p) => (
  <Svg {...p}>
    <path d="M4.5 12h15M14 6l6 6-6 6" />
  </Svg>
);
export const IconStop = (p) => (
  <Svg {...p}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="1.5" />
  </Svg>
);
export const IconPlay = (p) => (
  <Svg {...p}>
    <path d="M7.5 5.5v13l11-6.5-11-6.5Z" />
  </Svg>
);
export const IconAlert = (p) => (
  <Svg {...p}>
    <path d="M12 4 2.8 19.5h18.4L12 4Z" />
    <path d="M12 10v4.5M12 17.2v.01" />
  </Svg>
);
export const IconInfo = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5M12 8v.01" />
  </Svg>
);
export const IconUncertain = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.1-2.4 3.7M12 16.8v.01" />
  </Svg>
);
export const IconFlag = (p) => (
  <Svg {...p}>
    <path d="M5.5 21V4M5.5 4.5h11l-2 4 2 4h-11" />
  </Svg>
);
export const IconLogout = (p) => (
  <Svg {...p}>
    <path d="M14 4.5h4a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5h-4" />
    <path d="M10 8 6 12l4 4M6 12h9.5" />
  </Svg>
);
export const IconKeyboard = (p) => (
  <Svg {...p}>
    <rect x="2.5" y="6" width="19" height="12" rx="2" />
    <path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9" />
  </Svg>
);
export const IconClock = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Svg>
);
export const IconFilm = (p) => (
  <Svg {...p}>
    <rect x="4" y="3" width="16" height="18" rx="1.5" />
    <path d="M8 3v18M16 3v18M4 7.5h4M4 12h4M4 16.5h4M16 7.5h4M16 12h4M16 16.5h4" />
  </Svg>
);
export const IconEye = (p) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="2.75" />
  </Svg>
);
export const IconEyeOff = (p) => (
  <Svg {...p}>
    <path d="M10 5.7A9.8 9.8 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.6 3.4M6.3 7.3C3.9 8.9 2.5 12 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.7-1.3" />
    <path d="M10 10a2.8 2.8 0 0 0 4 4M3.5 3.5l17 17" />
  </Svg>
);
export const IconSparkle = (p) => (
  <Svg {...p}>
    <path d="M12 4c.4 3.8 2.2 5.6 6 6-3.8.4-5.6 2.2-6 6-.4-3.8-2.2-5.6-6-6 3.8-.4 5.6-2.2 6-6Z" />
    <path d="M19 15.5c.2 1.4.9 2.1 2.3 2.3-1.4.2-2.1.9-2.3 2.3-.2-1.4-.9-2.1-2.3-2.3 1.4-.2 2.1-.9 2.3-2.3Z" />
  </Svg>
);
export const IconShuffle = (p) => (
  <Svg {...p}>
    <path d="M3.5 7h3.3c2 0 3.2 1 4.2 2.8l2 3.6c1 1.8 2.2 2.6 4.2 2.6h3.3M17.5 13.5 20.5 16l-3 2.5M3.5 17h3.3c1.3 0 2.2-.4 3-1.2M13.8 8.2c.8-.8 1.7-1.2 3-1.2h3.7M17.5 4.5l3 2.5-3 2.5" />
  </Svg>
);
export const IconDots = (p) => (
  <Svg {...p}>
    <path d="M6 12h.01M12 12h.01M18 12h.01" strokeWidth="2.5" />
  </Svg>
);
export const IconShield = (p) => (
  <Svg {...p}>
    <path d="M12 3.5 5 6v5.5c0 4.3 2.9 7.8 7 9 4.1-1.2 7-4.7 7-9V6l-7-2.5Z" />
    <path d="m9 12 2.2 2.2L15.5 10" />
  </Svg>
);
export const IconRefresh = (p) => (
  <Svg {...p}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4" />
  </Svg>
);
export const IconSort = (p) => (
  <Svg {...p}>
    <path d="M7 5v14M4 16l3 3 3-3M17 19V5M14 8l3-3 3 3" />
  </Svg>
);
export const IconUser = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="8.5" r="3.75" />
    <path d="M4.5 20.5c.8-3.9 3.7-6 7.5-6s6.7 2.1 7.5 6" />
  </Svg>
);
