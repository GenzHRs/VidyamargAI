import { redirect } from "next/navigation";

/**
 * Candidate Login Route
 * Public login form has been removed. All visitors are directed to Candidate Dashboard.
 */
export default function LoginPage() {
  redirect("/candidate/dashboard");
}
