import { redirect } from "next/navigation";

// Legacy navigation route. Preserve bookmarks without maintaining a duplicate page.
export default function LegacySessionPage() {
  redirect("/workspace");
}
