// Shared UI primitives. Deliberately thin wrappers over semantic HTML + the classes in
// styles/components.css — no styling logic lives in JS.
import { forwardRef, useEffect, useId, useRef, useState } from "react";
import { IconAlert, IconCheck, IconEye, IconEyeOff } from "./icons";

export const Button = forwardRef(function Button(
  { variant = "secondary", size, block, icon: Icon, iconRight: IconRight, loading, kbd, className = "", children, type = "button", ...rest },
  ref
) {
  const cls = ["btn", `btn-${variant}`, size && `btn-${size}`, block && "btn-block", !children && Icon && "btn-icon", className]
    .filter(Boolean)
    .join(" ");
  return (
    <button ref={ref} type={type} className={cls} data-loading={loading ? "true" : undefined} aria-busy={loading || undefined} {...rest}>
      {Icon && <Icon />}
      {children}
      {IconRight && <IconRight />}
      {kbd && <kbd className="kbd" aria-hidden="true">{kbd}</kbd>}
      {loading && <span className="spinner" aria-hidden="true" />}
    </button>
  );
});

export function Spinner({ label = "Loading" }) {
  return (
    <span role="status" style={{ display: "inline-flex" }}>
      <span className="spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

const STATUS_LABEL = {
  pending: "Awaiting review",
  approved: "Approved",
  rejected: "Rejected",
  suspended: "Suspended",
};

export function Stamp({ status, children, className = "" }) {
  return (
    <span className={`stamp ${className}`} data-status={status}>
      {children || STATUS_LABEL[status] || status}
    </span>
  );
}

export function Kbd({ children }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function PageHeader({ index, eyebrow, title, description, actions, titleId = "page-title" }) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        {(index || eyebrow) && (
          <div className="page-eyebrow">
            {index && <span className="label" style={{ color: "var(--tungsten)" }}>{index}</span>}
            {index && eyebrow && <span className="rule" aria-hidden="true" />}
            {eyebrow && <span className="label">{eyebrow}</span>}
          </div>
        )}
        <h1 id={titleId} className="h1 page-title" tabIndex={-1}>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function EmptyState({ icon: Icon, title, children, actions }) {
  return (
    <div className="empty page-enter">
      {Icon && (
        <div className="empty-mark" aria-hidden="true">
          <Icon />
        </div>
      )}
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {actions && <div className="empty-actions">{actions}</div>}
    </div>
  );
}

export function Callout({ tone = "info", icon: Icon = IconAlert, title, children, actions, role }) {
  return (
    <div className={`callout callout-${tone} page-enter`} role={role}>
      <Icon />
      <div style={{ minWidth: 0 }}>
        {title && <div className="callout-title">{title}</div>}
        {children}
      </div>
      {actions ? <div className="callout-actions">{actions}</div> : <span />}
    </div>
  );
}

export function ErrorState({ title = "Something didn’t load", error, onRetry }) {
  return (
    <Callout tone="error" title={title} role="alert" actions={onRetry && <Button size="sm" onClick={onRetry}>Try again</Button>}>
      <span>{error?.message || "The studio couldn’t be reached. Check your connection and try again."}</span>
    </Callout>
  );
}

/** Text input with label, hint, and error wired up with aria-describedby. */
export const TextField = forwardRef(function TextField({ label, hint, hintOk, error, id, className = "", adornment, ...rest }, ref) {
  const autoId = useId();
  const inputId = id || autoId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  return (
    <div className={`field ${className}`}>
      <label className="field-label" htmlFor={inputId}>{label}</label>
      <div className={`input-wrap ${adornment ? "has-adorn" : ""}`}>
        <input
          ref={ref}
          id={inputId}
          className="input"
          aria-invalid={error ? "true" : undefined}
          aria-describedby={[errorId, hintId].filter(Boolean).join(" ") || undefined}
          {...rest}
        />
        {adornment && <span className="input-adorn">{adornment}</span>}
      </div>
      {error ? (
        <p className="field-error" id={errorId}><IconAlert />{error}</p>
      ) : hint ? (
        <p className="field-hint" id={hintId} data-ok={hintOk ? "true" : undefined}>{hintOk && <IconCheck />}{hint}</p>
      ) : null}
    </div>
  );
});

export const PasswordField = forwardRef(function PasswordField(props, ref) {
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      ref={ref}
      type={visible ? "text" : "password"}
      adornment={
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-icon"
          style={{ "--btn-h": "36px" }}
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
        >
          {visible ? <IconEyeOff /> : <IconEye />}
        </button>
      }
      {...props}
    />
  );
});

/**
 * Native <dialog> wrapper: showModal() gives focus trapping, Esc-to-close, inert page and
 * top-layer stacking for free — more robust than a hand-rolled div modal.
 */
export function Dialog({ open, onClose, className = "dialog", labelledBy, children, initialFocusRef }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
      if (initialFocusRef?.current) initialFocusRef.current.focus();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open, initialFocusRef]);

  return (
    <dialog
      ref={ref}
      className={className}
      aria-labelledby={labelledBy}
      onCancel={(e) => {
        e.preventDefault();
        onClose?.();
      }}
      onClick={(e) => {
        // Click on the backdrop (the dialog element itself, outside its content box).
        if (e.target === ref.current) onClose?.();
      }}
    >
      {open && children}
    </dialog>
  );
}

export function ConfirmDialog({ open, title, children, confirmLabel = "Confirm", tone = "primary", busy, onConfirm, onCancel }) {
  const titleId = useId();
  const cancelRef = useRef(null);
  return (
    <Dialog open={open} onClose={onCancel} labelledBy={titleId} initialFocusRef={cancelRef}>
      <div className="dialog-body">
        <h2 id={titleId}>{title}</h2>
        {children && <p>{children}</p>}
      </div>
      <div className="dialog-foot">
        <Button ref={cancelRef} variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button variant={tone === "danger" ? "danger-solid" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Dialog>
  );
}

export function Skeleton({ width, height, radius, className = "", style }) {
  return <span className={`skeleton ${className}`} aria-hidden="true" style={{ display: "block", width, height, borderRadius: radius, ...style }} />;
}
