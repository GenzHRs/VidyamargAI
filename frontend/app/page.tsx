import { redirect } from "next/navigation";

/**
 * Root Application Entrypoint
 * Completely directs all visitors to the Candidate Dashboard.
 * Public landing page has been removed from navigation.
 */
export default function Home() {
  redirect("/candidate/dashboard");
}
