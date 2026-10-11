"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

// Core modules and sections
import SmoothScroll from "@/components/landing/SmoothScroll";
import CanvasBackground from "@/components/landing/CanvasBackground";
import { PageTransitionProvider } from "@/components/landing/PageTransitionOverlay";
import Header from "@/components/landing/Header";
import Hero from "@/components/landing/Hero";
import TrustedMarquee from "@/components/landing/TrustedMarquee";
import Ecosystem from "@/components/landing/Ecosystem";
import WhyVidyaMarg from "@/components/landing/WhyVidyaMarg";
import Features from "@/components/landing/Features";
import PlatformScreenshots from "@/components/landing/PlatformScreenshots";
import DashboardPreview from "@/components/landing/DashboardPreview";
import HowItWorks from "@/components/landing/HowItWorks";
import Stats from "@/components/landing/Stats";
import Testimonials from "@/components/landing/Testimonials";
import Pricing from "@/components/landing/Pricing";
import CareerInsights from "@/components/landing/CareerInsights";
import FAQ from "@/components/landing/FAQ";
import FinalCTA from "@/components/landing/FinalCTA";
import Footer from "@/components/landing/Footer";

export default function Home() {
  const router = useRouter();
  const { isAuthenticated, role, initialize, resumeDevMode } = useAuthStore();
  const [checkingAuth, setCheckingAuth] = useState(true);

  const isTestingModeConfigured =
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true" ||
    process.env.NEXT_PUBLIC_DEV_MODE === "true" ||
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "1" ||
    process.env.NEXT_PUBLIC_DEV_MODE === "1";

  // Initialize and check active user session / testing mode
  useEffect(() => {
    let active = true;
    const checkSession = async () => {
      const isExited =
        typeof window !== "undefined" &&
        (sessionStorage.getItem("disable_dev_mode") === "true" ||
         sessionStorage.getItem("disable_testing_mode") === "true");

      if (isTestingModeConfigured && !isExited) {
        const ok = await resumeDevMode();
        if (ok && active) {
          router.replace("/candidate/dashboard");
          return;
        }
      }

      await initialize();
      if (active) setCheckingAuth(false);
    };
    checkSession();
    return () => {
      active = false;
    };
  }, [initialize, resumeDevMode, isTestingModeConfigured, router]);

  // Handle auto-redirection for active sessions
  useEffect(() => {
    if (!checkingAuth && isAuthenticated) {
      router.replace("/candidate/dashboard");
    }
  }, [isAuthenticated, router, checkingAuth]);

  // Prevent flashing landing page if user session is being validated or testing mode is active
  if (checkingAuth || isTestingModeConfigured) {
    return (
      <main className="min-h-screen bg-background flex flex-col items-center justify-center font-heading text-foreground">
        <div className="flex flex-col items-center gap-5">
          <div className="w-10 h-10 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
          <span className="text-purple-500 font-medium tracking-wide">
            {isTestingModeConfigured ? "Opening VidyaMarg AI Dashboard..." : "Connecting to VidyaMarg AI..."}
          </span>
        </div>
      </main>
    );
  }

  return (
    <PageTransitionProvider>
      <SmoothScroll>
        <main className="relative min-h-screen bg-transparent text-foreground overflow-x-hidden font-sans antialiased selection:bg-purple-500/30 selection:text-white">
          {/* Animated 6-layer background canvas */}
          <CanvasBackground />

          {/* Transparent sticky header */}
          <Header />

          {/* Section flow */}
          <div className="relative w-full">
            <Hero />
            
            <Ecosystem />
            
            <WhyVidyaMarg />
            
            <Features />
            
            <PlatformScreenshots />
            
            <DashboardPreview />
            
            <HowItWorks />
            
            <Stats />
            
            <Testimonials />
            
            <Pricing />
            
            <CareerInsights />
            
            <FAQ />
            
            <TrustedMarquee />
            
            <FinalCTA />
          </div>

          {/* Footnotes grid */}
          <Footer />
        </main>
      </SmoothScroll>
    </PageTransitionProvider>
  );
}
