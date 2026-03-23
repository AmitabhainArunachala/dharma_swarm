import { redirect } from "next/navigation";

export default function QwenTelemetryRedirectPage() {
  redirect("/dashboard/telemetry");
}
