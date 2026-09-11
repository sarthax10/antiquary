import { IconArchive, IconCreate, IconLibrary, IconMembers, IconReview } from "./icons";

// Single source of truth for primary navigation — sidebar, tab bar, command menu and
// the "g then key" shortcuts all read from this list.
export const NAV_ITEMS = [
  { to: "/create", label: "Create", index: "01", icon: IconCreate, hotkey: "c" },
  { to: "/review", label: "Review", index: "02", icon: IconReview, countKey: "pending", attention: true, hotkey: "r" },
  { to: "/library", label: "Library", index: "03", icon: IconLibrary, countKey: "approved", hotkey: "l" },
  { to: "/archive", label: "Archive", index: "04", icon: IconArchive, countKey: "rejected", hotkey: "a" },
];

export const ADMIN_ITEMS = [
  { to: "/admin/users", label: "Members", icon: IconMembers, countKey: "members", attention: true, hotkey: "m" },
];
