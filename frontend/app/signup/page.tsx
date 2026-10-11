import { redirect } from "next/navigation";

/**
 * Candidate Signup Route
 * Public signup form has been removed. All visitors are directed to Candidate Dashboard.
 */
export default function SignupPage() {
  redirect("/candidate/dashboard");
}
