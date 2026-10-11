"use client";

import { useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { apiService } from "@/services/api";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import {
  Settings,
  User,
  Bell,
  Shield,
  Palette,
  Moon,
  Sun,
  Save,
  Loader2,
  CheckCircle,
  ChevronRight,
  Mail,
  Phone,
  MapPin,
  Link as LinkIcon,
} from "lucide-react";

import { useGlobalTheme } from "@/utils/themeUtils";

export default function SettingsPage() {
  const { fullName, email, updateUser } = useAuthStore();
  const { theme, setTheme } = useGlobalTheme();
  const [notifications, setNotifications] = useState({
    jobMatches: true,
    courseRecommendations: true,
    interviewReminders: true,
    profileUpdates: false,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const { data: profile = null } = useQuery({
    queryKey: ["candidate", "profile"],
    queryFn: () => apiService.getProfile(),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });

  const [activeSection, setActiveSection] = useState<"profile" | "appearance" | "notifications" | "privacy">("profile");


  const applyTheme = (t: "dark" | "light") => {
    setTheme(t);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiService.updatePreferences(theme);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {}
    setSaving(false);
  };

  const sections = [
    { id: "profile", label: "Profile", icon: User },
    { id: "appearance", label: "Appearance", icon: Palette },
    { id: "notifications", label: "Notifications", icon: Bell },
    { id: "privacy", label: "Privacy & Security", icon: Shield },
  ] as const;

  return (
    <div className="min-h-screen bg-app-bg text-app-text font-sans">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-app-text">Settings</h1>
          <p className="text-sm text-app-text-muted mt-0.5">Manage your account preferences</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-6">
          {/* Sidebar nav */}
          <div className="sm:w-52 shrink-0">
            <nav className="space-y-1">
              {sections.map((s) => {
                const Icon = s.icon;
                const active = activeSection === s.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => setActiveSection(s.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                      active
                        ? "bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400"
                        : "text-app-text-muted hover:text-app-text hover:bg-app-surface"
                    }`}
                  >
                    <Icon size={16} />
                    {s.label}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 space-y-4">

            {/* Profile section */}
            {activeSection === "profile" && (
              <div className="bg-app-surface border border-app-border rounded-2xl p-6 space-y-4">
                <h2 className="font-bold text-app-text">Account Information</h2>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-3 rounded-xl border border-app-border">
                    <User size={15} className="text-app-text-muted shrink-0" />
                    <div>
                      <p className="text-[11px] text-app-text-muted">Full Name</p>
                      <p className="text-sm font-semibold text-app-text">{fullName || "—"}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-xl border border-app-border">
                    <Mail size={15} className="text-app-text-muted shrink-0" />
                    <div>
                      <p className="text-[11px] text-app-text-muted">Email</p>
                      <p className="text-sm font-semibold text-app-text">{email || "—"}</p>
                    </div>
                  </div>
                  {profile?.phone && (
                    <div className="flex items-center gap-3 p-3 rounded-xl border border-app-border">
                      <Phone size={15} className="text-app-text-muted shrink-0" />
                      <div>
                        <p className="text-[11px] text-app-text-muted">Phone</p>
                        <p className="text-sm font-semibold text-app-text">{profile.phone}</p>
                      </div>
                    </div>
                  )}
                  {profile?.location && (
                    <div className="flex items-center gap-3 p-3 rounded-xl border border-app-border">
                      <MapPin size={15} className="text-app-text-muted shrink-0" />
                      <div>
                        <p className="text-[11px] text-app-text-muted">Location</p>
                        <p className="text-sm font-semibold text-app-text">{profile.location}</p>
                      </div>
                    </div>
                  )}
                </div>
                <a
                  href="/candidate/profile"
                  className="flex items-center gap-2 text-sm font-semibold text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Edit Profile <ChevronRight size={14} />
                </a>
              </div>
            )}

            {/* Appearance section */}
            {activeSection === "appearance" && (
              <div className="bg-app-surface border border-app-border rounded-2xl p-6 space-y-4">
                <h2 className="font-bold text-app-text">Appearance</h2>
                <div>
                  <p className="text-sm font-medium text-app-text mb-3">Theme</p>
                  <div className="flex gap-3">
                    {(["light", "dark"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => applyTheme(t)}
                        className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border-2 text-sm font-semibold transition-all ${
                          theme === t
                            ? "border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400"
                            : "border-app-border hover:border-blue-300 text-app-text-muted"
                        }`}
                      >
                        {t === "light" ? <Sun size={16} className="text-amber-500" /> : <Moon size={16} className="text-slate-400" />}
                        {t === "light" ? "Light Mode" : "Dark Mode"}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Notifications section */}
            {activeSection === "notifications" && (
              <div className="bg-app-surface border border-app-border rounded-2xl p-6 space-y-4">
                <h2 className="font-bold text-app-text">Notifications</h2>
                <div className="space-y-3">
                  {[
                    { key: "jobMatches" as const, label: "New Job Matches", desc: "Get notified when new jobs match your profile" },
                    { key: "courseRecommendations" as const, label: "Course Recommendations", desc: "Personalized course suggestions based on skill gaps" },
                    { key: "interviewReminders" as const, label: "Interview Reminders", desc: "Reminders for scheduled interviews" },
                    { key: "profileUpdates" as const, label: "Profile Insights", desc: "Tips to improve your profile completeness" },
                  ].map((item) => (
                    <div key={item.key} className="flex items-center justify-between p-4 rounded-xl border border-app-border">
                      <div>
                        <p className="text-sm font-semibold text-app-text">{item.label}</p>
                        <p className="text-xs text-app-text-muted mt-0.5">{item.desc}</p>
                      </div>
                      <button
                        onClick={() => setNotifications((n) => ({ ...n, [item.key]: !n[item.key] }))}
                        className={`w-11 h-6 rounded-full transition-all relative ${
                          notifications[item.key] ? "bg-blue-600" : "bg-app-border"
                        }`}
                      >
                        <span
                          className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${
                            notifications[item.key] ? "left-6" : "left-1"
                          }`}
                        />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Privacy section */}
            {activeSection === "privacy" && (
              <div className="bg-app-surface border border-app-border rounded-2xl p-6 space-y-4">
                <h2 className="font-bold text-app-text">Privacy & Security</h2>
                <div className="space-y-3">
                  <div className="p-4 rounded-xl border border-app-border">
                    <p className="text-sm font-semibold text-app-text">Password</p>
                    <p className="text-xs text-app-text-muted mt-0.5">Change your account password</p>
                    <button className="mt-2 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline">
                      Change Password →
                    </button>
                  </div>
                  <div className="p-4 rounded-xl border border-app-border">
                    <p className="text-sm font-semibold text-app-text">Data & Privacy</p>
                    <p className="text-xs text-app-text-muted mt-0.5">
                      Your resume and profile data is kept private and only used to power your personal AI career assistant.
                    </p>
                  </div>
                  <div className="p-4 rounded-xl border border-red-200/60 dark:border-red-800/40 bg-red-50/50 dark:bg-red-950/10">
                    <p className="text-sm font-semibold text-red-600 dark:text-red-400">Delete Account</p>
                    <p className="text-xs text-red-500/80 dark:text-red-500 mt-0.5">
                      Permanently delete your account and all associated data.
                    </p>
                    <button className="mt-2 text-xs font-bold text-red-600 dark:text-red-400 hover:underline">
                      Request Account Deletion →
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Save button */}
            <div className="flex justify-end">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition-colors disabled:opacity-60"
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : saved ? (
                  <CheckCircle size={14} className="text-emerald-300" />
                ) : (
                  <Save size={14} />
                )}
                {saved ? "Saved!" : saving ? "Saving…" : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
