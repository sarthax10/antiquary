import { useId } from "react";
import { Button, Dialog, Kbd } from "./ui";
import { modKey } from "../lib/hooks";

const GROUPS = [
  {
    title: "Anywhere",
    rows: [
      ["Open command menu", [modKey, "K"]],
      ["Go to Create", ["G", "C"]],
      ["Go to Review", ["G", "R"]],
      ["Go to Library", ["G", "L"]],
      ["Go to Archive", ["G", "A"]],
      ["Show this list", ["?"]],
    ],
  },
  {
    title: "Review desk",
    rows: [
      ["Approve and advance", ["A"]],
      ["Reject and advance", ["R"]],
      ["Next / previous story", ["J", "K"]],
      ["Play / pause", ["Space"]],
      ["Show verified claims", ["F"]],
    ],
  },
  {
    title: "Create",
    rows: [["Generate story", [modKey, "Enter"]]],
  },
  {
    title: "Library & Archive",
    rows: [["Focus search", ["/"]]],
  },
];

export default function ShortcutsDialog({ open, onClose }) {
  const titleId = useId();
  return (
    <Dialog open={open} onClose={onClose} labelledBy={titleId}>
      <div className="dialog-body">
        <h2 id={titleId}>Keyboard shortcuts</h2>
        <div>
          {GROUPS.map((g) => (
            <div className="shortcut-group" key={g.title}>
              <div className="label" style={{ marginBottom: 6 }}>{g.title}</div>
              <div className="shortcut-list">
                {g.rows.map(([label, keys]) => (
                  <div className="shortcut-row" key={label}>
                    <span>{label}</span>
                    <span className="shortcut-keys">{keys.map((k, i) => <Kbd key={i}>{k}</Kbd>)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="dialog-foot">
        <Button variant="primary" onClick={onClose}>Done</Button>
      </div>
    </Dialog>
  );
}
