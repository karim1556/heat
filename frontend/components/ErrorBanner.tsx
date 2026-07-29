import { AlertTriangle } from "lucide-react";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-center gap-3 rounded-xl border border-red-200/80 bg-red-50/90 text-red-900 px-4 py-3 text-sm shadow-sm backdrop-blur-sm"
    >
      <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
      <span className="font-medium">{message}</span>
    </div>
  );
}
