// Stroke-based icons, 24x24, ported 1:1 from the original design — no icon font/library.
const base = (children, extra = "") => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...(extra ? { className: extra } : {})}>
    {children}
  </svg>
);

export const IconCreate = () => base(<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9L12 3Z" fill="currentColor" stroke="none" />);
export const IconReview = () => base(<><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" /><circle cx="12" cy="12" r="2.6" /></>);
export const IconLibrary = () => base(<><rect x="3" y="3" width="7.5" height="7.5" rx="1.3" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.3" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.3" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.3" /></>);
export const IconArchive = () => base(<><rect x="2.5" y="3.5" width="19" height="4" rx="1" /><path d="M4 7.5v11a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-11M9.7 12h4.6" /></>);
export const IconCheck = () => base(<path d="M5 12.5l4.5 4.5L19 7" />);
export const IconX = () => base(<path d="M6 6l12 12M18 6L6 18" />);
export const IconRestore = () => base(<path d="M4.5 9.5a7.5 7.5 0 1 1 1.3 7.7M4.5 9.5V4M4.5 9.5H10" />);
export const IconChevronL = () => base(<path d="M14.5 5l-6.5 7 6.5 7" />);
export const IconChevronR = () => base(<path d="M9.5 5l6.5 7-6.5 7" />);
export const IconStop = () => base(<rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" stroke="none" />);
export const IconUncertain = () => base(<><circle cx="12" cy="12" r="9" /><path d="M12 16v.01M12 8v5" /></>);
