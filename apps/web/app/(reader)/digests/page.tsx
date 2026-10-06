import { redirect } from "next/navigation";

// The digest is part of the briefing since plan 13 C2: its archive is the briefing archive.
export default function DigestsPage() {
  redirect("/briefings");
}
