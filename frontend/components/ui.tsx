import type { ReactNode } from "react";

type SurfaceTone = "default" | "strong" | "warning" | "data";

export function Surface({ children, className = "", tone = "default" }: { children: ReactNode; className?: string; tone?: SurfaceTone }) { return <section className={`obs-surface obs-surface-${tone} ${className}`}>{children}</section>; }
export function SectionHeading({ action, description, title }: { action?: ReactNode; description?: string; title: string }) { return <header className="obs-section-heading"><div><h1>{title}</h1>{description ? <p>{description}</p> : null}</div>{action}</header>; }
export function Metric({ detail, label, tone = "default", value }: { detail?: string; label: string; tone?: SurfaceTone; value: ReactNode }) { return <div className={`obs-metric obs-metric-${tone}`}><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>; }
export function InlineNotice({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "warning" | "danger" }) { return <div className={`obs-notice obs-notice-${tone}`} role={tone === "danger" ? "alert" : "status"}>{children}</div>; }
export function LoadingState({ label = "Loading live climate data" }: { label?: string }) { return <div className="obs-loading" role="status"><span aria-hidden="true" /><span>{label}</span></div>; }
