import { type ReactNode } from "react";
import { Search, PlugZap, Inbox, type LucideIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
export function Heading({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}
export function Empty({
  title = "Nothing here yet",
  description = "Your data will appear when your support service is connected.",
  icon: Icon = Inbox,
  action,
}: {
  title?: string;
  description?: string;
  icon?: LucideIcon;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function IntegrationNote({ children }: { children?: ReactNode }) {
  if (!children) return null;
  return (
    <div className="integration-note">
      <PlugZap />
      <span>{children}</span>
    </div>
  );
}
export function Metric({
  label,
  icon: Icon,
  tone = "",
  value = "—",
  foot = "",
}: {
  label: string;
  icon: LucideIcon;
  tone?: string;
  value?: string | number;
  foot?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-head">
        <span>{label}</span>
        <span className={`metric-icon ${tone}`}>
          <Icon />
        </span>
      </div>
      <div className="metric-value">{value}</div>
      {foot ? (
        <div className="metric-foot">
          <span className="size-1 rounded-full bg-muted-foreground/50" />
          {foot}
        </div>
      ) : null}
    </div>
  );
}
export function SearchField({
  value,
  onChange,
  placeholder = "Search…",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search-field">
      <Search />
      <Input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
export function Segments({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label="Filter results">
      {options.map((o) => (
        <Button
          key={o}
          variant="ghost"
          size="sm"
          className={value === o ? "selected" : "text-muted-foreground"}
          aria-pressed={value === o}
          onClick={() => onChange(o)}
        >
          {o}
        </Button>
      ))}
    </div>
  );
}

export function StatusBadge({
  status,
  size = "md",
}: {
  status: string;
  size?: "sm" | "md";
}) {
  const s = (status || "").toLowerCase().trim();
  let style = "bg-muted text-muted-foreground border-border";

  if (s === "resolved" || s === "closed") {
    style = "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20";
  } else if (s === "confirmed" || s === "critical" || s === "high_risk" || s === "very_high") {
    style = "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/25";
  } else if (s === "investigating" || s === "mitigated" || s === "in progress" || s === "moderate") {
    style = "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/25";
  } else if (s === "open" || s === "candidate" || s === "waiting_for_user" || s === "low") {
    style = "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20";
  } else if (s === "ai_processing" || s === "auto_resolved") {
    style = "bg-primary/10 text-primary border-primary/20";
  }

  const padding = size === "sm" ? "px-1.5 py-0.2 text-[10px]" : "px-2.5 py-0.5 text-[11px]";

  return (
    <span
      className={`inline-flex items-center gap-1 font-medium capitalize rounded-full border ${padding} ${style}`}
    >
      <span
        className={`size-1.5 rounded-full ${
          s === "resolved"
            ? "bg-emerald-500"
            : s === "confirmed" || s === "critical"
            ? "bg-rose-500"
            : s === "investigating" || s === "in progress"
            ? "bg-amber-500 animate-pulse"
            : "bg-blue-500"
        }`}
      />
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function MetricSkeleton() {
  return (
    <div className="metric animate-pulse">
      <div className="metric-head">
        <div className="h-3 w-24 bg-muted rounded" />
        <div className="size-7 rounded-full bg-muted" />
      </div>
      <div className="h-8 w-16 bg-muted rounded my-2" />
      <div className="h-2.5 w-28 bg-muted rounded" />
    </div>
  );
}

export function TableSkeleton({ rows = 4, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="table-scroll p-4 space-y-3 animate-pulse">
      <div className="h-5 w-full bg-muted/60 rounded" />
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 items-center">
          {Array.from({ length: cols }).map((_, c) => (
            <div
              key={c}
              className="h-4 bg-muted/50 rounded"
              style={{ width: `${Math.max(20, 100 / cols - 5)}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function InlineAlert({
  type = "info",
  title,
  message,
  onDismiss,
}: {
  type?: "info" | "success" | "warning" | "error";
  title?: string;
  message: string;
  onDismiss?: () => void;
}) {
  const styles = {
    info: "bg-primary/5 border-primary/20 text-primary",
    success: "bg-emerald-500/10 border-emerald-500/20 text-emerald-800 dark:text-emerald-300",
    warning: "bg-amber-500/10 border-amber-500/25 text-amber-900 dark:text-amber-200",
    error: "bg-rose-500/10 border-rose-500/25 text-rose-900 dark:text-rose-200",
  }[type];

  return (
    <div className={`p-3.5 rounded-xl border text-xs flex items-start justify-between gap-3 ${styles}`} role="alert">
      <div>
        {title && <h4 className="font-semibold mb-0.5">{title}</h4>}
        <p className="leading-relaxed">{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-muted-foreground hover:text-foreground text-sm font-semibold p-1"
          aria-label="Dismiss alert"
        >
          ×
        </button>
      )}
    </div>
  );
}

