import { forwardRef, useRef, type ReactNode } from "react";
import { Badge, Button as SharedButton, Dialog, EmptyState as SharedEmptyState, ErrorState as SharedErrorState, Select as SharedSelect, type ButtonProps, type SelectProps } from "@xsec/ui-react";
import { collectionBucket, statusLabel } from "./utils";

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({ className = "", children, variant, size, ...props }, ref) {
  const classes = new Set(className.split(/\s+/));
  const resolvedVariant = variant ?? (classes.has("danger") ? "danger" : classes.has("primary") ? "primary" : classes.has("text") ? "ghost" : "outline");
  const resolvedSize = size ?? (classes.has("compact") ? "sm" : "md");
  return <SharedButton {...props} ref={ref} variant={resolvedVariant} size={resolvedSize} className={className.split(/\s+/).filter(name => !["danger", "primary", "text", "compact"].includes(name)).join(" ")}>{children}</SharedButton>;
});

export function Select({ onChange, ...props }: Omit<SelectProps, "onValueChange"> & { onChange: (value: string) => void }) {
  return <SharedSelect {...props} onValueChange={next => {
    const selected = props.options.find(option => option.value === next);
    if (!selected) throw new Error("Invalid plugin selection");
    onChange(selected.value);
  }} />;
}

export function StatusBadge({ status }: { status: string }) {
  const bucket = collectionBucket(status);
  return <Badge tone={bucket === "completed" ? "success" : bucket === "failed" ? "danger" : bucket === "running" ? "warning" : "neutral"}>{statusLabel(status)}</Badge>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return typeof children === "string" ? <SharedEmptyState title={children} /> : <SharedEmptyState title="收集任务" action={children} />;
}

export function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  return <SharedErrorState title="读取失败" description={error} action={<Button size="sm" onClick={onRetry}>重新读取</Button>} />;
}

export function Notice({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return <div className="ad-notice"><span>{children}</span>{action}</div>;
}

export function Modal({
  title,
  children,
  onClose,
  footer,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer: ReactNode;
  busy?: boolean;
}) {
  const content = useRef<HTMLDivElement>(null);
  return <Dialog open title={title} className="ad-shared-dialog" initialFocus={interaction => interaction === "touch" ? true : content.current?.querySelector<HTMLElement>("input:not([disabled]),textarea:not([disabled]),.xui-select-trigger:not([disabled])") ?? true} preventOutsideDismissal={busy} onOpenChange={open => { if (!open && !busy) onClose(); }} footer={footer}><div ref={content}>{children}</div></Dialog>;
}

export function ConfirmModal({
  title,
  detail,
  confirmLabel,
  danger = false,
  busy = false,
  onClose,
  onConfirm,
}: {
  title: string;
  detail: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const close = () => { if (!busy) onClose(); };
  return <Modal title={title} busy={busy} onClose={close} footer={<><Button disabled={busy} onClick={close}>取消</Button><Button variant={danger ? "danger" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button></>}><p className="ad-confirm-detail">{detail}</p></Modal>;
}

export function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="ad-section">
      <div className="ad-section-title"><strong>{title}</strong><span>{actions}</span></div>
      <div className="ad-section-body">{children}</div>
    </section>
  );
}
