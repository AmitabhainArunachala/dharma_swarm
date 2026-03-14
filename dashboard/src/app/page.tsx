import { redirect } from "next/navigation";

/**
 * Root page -- immediately redirects to the dashboard.
 */
export default function Home() {
  redirect("/dashboard");
}
