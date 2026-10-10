import type { Tone } from "../components/ui/badge";

/** Colour only ever marks a verdict; anything unknown stays neutral. */

export function verificationTone(verdict: string, verified: boolean): Tone {
  const value = verdict.toLowerCase();
  if (verified || value === "verified" || value === "trusted") return "success";
  if (value === "fraud" || value === "untrusted" || value === "failed") return "danger";
  if (value === "caution" || value === "degraded" || value === "suspicious") return "warning";
  return "neutral";
}

export function verificationLabel(verdict: string, verified: boolean): string {
  const value = verdict.toLowerCase();
  if (verified || value === "verified") return "Verified";
  if (!value || value === "unknown" || value === "unchecked") return "Unchecked";
  return value[0].toUpperCase() + value.slice(1);
}

export function sourceHealthTone(status: string): Tone {
  switch (status.toLowerCase()) {
    case "healthy":
      return "success";
    case "degraded":
      return "warning";
    case "down":
      return "danger";
    default:
      return "neutral";
  }
}

export function runTone(status: string): Tone {
  switch (status.toLowerCase()) {
    case "success":
    case "succeeded":
    case "completed":
      return "success";
    case "running":
    case "queued":
      return "warning";
    case "failed":
    case "error":
      return "danger";
    default:
      return "neutral";
  }
}

export function trustTone(verdict: string): Tone {
  switch (verdict.toLowerCase()) {
    case "trusted":
      return "success";
    case "caution":
      return "warning";
    case "untrusted":
      return "danger";
    default:
      return "neutral";
  }
}

export function capitalize(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1).replace(/_/g, " ") : value;
}
