"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// "My Learning" redirects to the Skill Lab's My Learning tab
export default function MyLearningPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/candidate/skill-lab");
  }, [router]);
  return null;
}
