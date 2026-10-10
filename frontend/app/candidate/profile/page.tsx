"use client";

import { useEffect, useState } from "react";
import { apiService } from "@/services/api";
import { useAuthStore } from "@/store/authStore";
import { useQueryClient } from "@tanstack/react-query";
import { 
  User, Globe, CheckCircle, Phone, MapPin, Link2, Code2, 
  Briefcase, GraduationCap, Award, Edit3, Target, Sparkles, Languages
} from "lucide-react";

export default function CandidateProfile() {
  const queryClient = useQueryClient();
  const { fullName, email, updateUser } = useAuthStore();
  
  // Canonical Raw Profile Payload from Backend
  const [profileData, setProfileData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Form edit states
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [education, setEducation] = useState("");
  const [experience, setExperience] = useState("");
  const [skills, setSkills] = useState("");
  const [certifications, setCertifications] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [github, setGithub] = useState("");
  const [portfolio, setPortfolio] = useState("");
  const [summary, setSummary] = useState("");
  const [projects, setProjects] = useState("");
  
  // UI States
  const [isEditMode, setIsEditMode] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError] = useState("");

  const loadProfile = async () => {
    setIsLoading(true);
    try {
      const data = await apiService.getProfile();
      setProfileData(data);
      
      const newName = data.personal_info?.full_name || data.parsed_name || data.user?.full_name;
      const newEmail = data.personal_info?.email || data.parsed_email || data.user?.email;
      if (newName && (newName !== fullName || newEmail !== email)) {
        updateUser(newName, newEmail);
      }

      setPhone(data.personal_info?.phone || data.phone || "");
      setAddress(data.personal_info?.location || data.personal_info?.address || data.address || "");
      setSkills(typeof data.skills === "string" ? data.skills : (data.skills_list ? data.skills_list.map((s: any) => s.name || s).join(", ") : ""));
      setCertifications(typeof data.certifications === "string" ? data.certifications : (data.certifications_list ? data.certifications_list.map((c: any) => c.name || c).join(", ") : ""));
      setLinkedin(data.links?.linkedin || data.linkedin || "");
      setGithub(data.links?.github || data.github || "");
      setPortfolio(data.links?.portfolio || data.portfolio || "");
      setSummary(data.professional?.summary || data.summary || "");

      // Format arrays for JSON edit mode if toggled
      const expArr = data.experience || data.experience_list || [];
      setExperience(Array.isArray(expArr) ? JSON.stringify(expArr, null, 2) : String(expArr));

      const eduArr = data.education || data.education_list || [];
      setEducation(Array.isArray(eduArr) ? JSON.stringify(eduArr, null, 2) : String(eduArr));

      const projArr = data.projects || data.projects_list || [];
      setProjects(Array.isArray(projArr) ? JSON.stringify(projArr, null, 2) : String(projArr));

    } catch (err) {
      console.error("Failed to load profile:", err);
      setError("Failed to load active resume profile.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccess(false);
    setError("");
    try {
      const data = await apiService.updateProfile({
        phone,
        address,
        education,
        experience,
        skills,
        certifications,
        linkedin,
        github,
        portfolio,
        summary,
        projects
      });
      setSaveSuccess(true);
      setIsEditMode(false);

      const newName = data.personal_info?.full_name || data.parsed_name || data.user?.full_name;
      const newEmail = data.personal_info?.email || data.parsed_email || data.user?.email;
      if (newName) {
        updateUser(newName, newEmail);
      }

      // Invalidate React Query caches
      queryClient.invalidateQueries();
      await loadProfile();
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to update profile details.");
    }
  };

  // Safe parsing helper for list attributes
  const parseList = (val: any) => {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    if (typeof val === "string") {
      try {
        const parsed = JSON.parse(val);
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    }
    return [];
  };

  // Derived structured elements from profileData
  const activeResumeId = profileData?.active_resume_id;
  const personalInfo = profileData?.personal_info || {};
  const linksObj = profileData?.links || {};
  const professionalObj = profileData?.professional || {};

  const nameToDisplay = personalInfo.full_name || profileData?.parsed_name || fullName || "Not available";
  const emailToDisplay = personalInfo.email || profileData?.parsed_email || email || "Not available";
  const phoneToDisplay = personalInfo.phone || profileData?.phone || "Not available";
  const locationToDisplay = personalInfo.location || personalInfo.address || profileData?.address || "Not available";
  const summaryToDisplay = professionalObj.summary || profileData?.summary || "";
  const primaryDesignation = professionalObj.primary_designation || profileData?.primary_designation || "";
  
  const targetRoles: any[] = parseList(professionalObj.target_roles || profileData?.target_roles);
  const roleEvidence: any[] = parseList(professionalObj.role_evidence || profileData?.role_evidence);

  const expList = parseList(profileData?.experience || profileData?.experience_list);
  const projList = parseList(profileData?.projects || profileData?.projects_list);
  const eduList = parseList(profileData?.education || profileData?.education_list);
  const certList = parseList(profileData?.certifications || profileData?.certifications_list);
  const rawSkills = profileData?.skills || profileData?.skills_list || [];

  const skillsList: any[] = Array.isArray(rawSkills) 
    ? rawSkills 
    : (typeof rawSkills === "string" ? rawSkills.split(",").map(s => ({ name: s.trim(), category: "Other Skills" })).filter(s => s.name) : []);

  // Categorize skills by group
  const groupSkillsByCategory = (list: any[]) => {
    const groups: Record<string, string[]> = {
      "Programming Languages": [],
      "AI & Machine Learning": [],
      "Frameworks & Libraries": [],
      "Databases & Storage": [],
      "Cloud & DevOps": [],
      "Tools & Software": [],
      "Other Competencies": []
    };

    list.forEach((item: any) => {
      let sName = "";
      let cat = "Other Competencies";

      if (typeof item === "string") {
        sName = item.trim();
      } else if (item && typeof item === "object") {
        sName = item.name || item.skill_name || "";
        cat = item.category || "Other Competencies";
      }

      if (!sName) return;

      const lowerCat = cat.toLowerCase();
      if (lowerCat.includes("language") || lowerCat.includes("programming")) {
        groups["Programming Languages"].push(sName);
      } else if (lowerCat.includes("ai") || lowerCat.includes("ml") || lowerCat.includes("learning") || lowerCat.includes("nlp") || lowerCat.includes("data")) {
        groups["AI & Machine Learning"].push(sName);
      } else if (lowerCat.includes("framework") || lowerCat.includes("library")) {
        groups["Frameworks & Libraries"].push(sName);
      } else if (lowerCat.includes("database") || lowerCat.includes("sql") || lowerCat.includes("storage")) {
        groups["Databases & Storage"].push(sName);
      } else if (lowerCat.includes("cloud") || lowerCat.includes("aws") || lowerCat.includes("devops") || lowerCat.includes("docker")) {
        groups["Cloud & DevOps"].push(sName);
      } else if (lowerCat.includes("tool") || lowerCat.includes("software") || lowerCat.includes("platform")) {
        groups["Tools & Software"].push(sName);
      } else {
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(sName);
      }
    });

    return Object.entries(groups).filter(([_, items]) => items.length > 0);
  };

  const groupedSkills = groupSkillsByCategory(skillsList);

  return (
    <div className="w-full min-h-screen bg-background dark:bg-background p-6 font-sans text-gray-800 dark:text-gray-100 transition-colors duration-300">
      
      {/* Header Profile Title and Mode switch */}
      <div className="border-b border-gray-200 dark:border-gray-850 pb-5 mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">Profile Workspace</h1>
            {activeResumeId && (
              <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                Active Resume Synced
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-normal">
            Canonical candidate profile driven strictly by PostgreSQL structured data extracted from your active resume.
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsEditMode(!isEditMode)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer border ${
              isEditMode 
                ? "bg-gray-150 border-gray-300 dark:bg-gray-800 dark:border-gray-700 text-gray-700 dark:text-gray-200"
                : "bg-indigo-500/10 border-indigo-500/20 hover:bg-indigo-500/20 text-indigo-500"
            }`}
          >
            <Edit3 size={13} />
            <span>{isEditMode ? "View Profile" : "Edit Profile"}</span>
          </button>
        </div>
      </div>

      {saveSuccess && (
        <div className="p-3 mb-6 rounded-xl bg-emerald-950/20 border border-emerald-800/40 text-emerald-400 text-xs font-semibold flex items-center gap-2">
          <CheckCircle size={16} />
          <span>Profile changes updated successfully!</span>
        </div>
      )}

      {error && (
        <div className="p-3 mb-6 rounded-xl bg-red-950/20 border border-red-800/40 text-red-400 text-xs font-semibold">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center p-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : !isEditMode ? (
        // --- VIEW PROFILE MODE ---
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Left Side: Avatar, Contacts, Skills (5/12 width) */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            
            {/* User Main Card */}
            <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col items-center text-center gap-4">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 border-2 border-purple-200 dark:border-purple-800 flex items-center justify-center font-extrabold text-3xl text-white shadow-md">
                {nameToDisplay ? nameToDisplay[0].toUpperCase() : "?"}
              </div>
              <div>
                <h2 className="text-lg font-bold text-gray-950 dark:text-white">{nameToDisplay}</h2>
                {primaryDesignation && (
                  <span className="inline-block mt-1 text-xs font-bold px-3 py-1 rounded-full bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/40">
                    {primaryDesignation}
                  </span>
                )}
                <span className="text-xs text-gray-400 block mt-1.5">{emailToDisplay}</span>
              </div>
              
              {/* Social links */}
              <div className="flex gap-3 mt-1">
                {linksObj.linkedin || profileData?.linkedin ? (
                  <a href={linksObj.linkedin || profileData?.linkedin} target="_blank" rel="noopener noreferrer" className="p-2 border border-gray-200 dark:border-gray-800 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-900 text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors" title="LinkedIn Profile">
                    <Link2 size={15} />
                  </a>
                ) : null}
                {linksObj.github || profileData?.github ? (
                  <a href={linksObj.github || profileData?.github} target="_blank" rel="noopener noreferrer" className="p-2 border border-gray-200 dark:border-gray-800 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-900 text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors" title="GitHub Profile">
                    <Code2 size={15} />
                  </a>
                ) : null}
                {linksObj.portfolio || profileData?.portfolio ? (
                  <a href={linksObj.portfolio || profileData?.portfolio} target="_blank" rel="noopener noreferrer" className="p-2 border border-gray-200 dark:border-gray-800 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-900 text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors" title="Portfolio Website">
                    <Globe size={15} />
                  </a>
                ) : null}
              </div>
            </div>

            {/* Target Roles Card */}
            {targetRoles.length > 0 && (
              <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-3">
                <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2 flex items-center gap-1.5">
                  <Target size={14} className="text-indigo-500" />
                  <span>Target Job Roles</span>
                </h3>
                <div className="flex flex-wrap gap-2 pt-1">
                  {targetRoles.map((role, rIdx) => {
                    const roleStr = typeof role === "object" ? (role?.role || JSON.stringify(role)) : String(role);
                    return (
                      <span key={rIdx} className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/30 text-blue-600 dark:text-blue-400 border border-blue-200/50 dark:border-blue-800/40">
                        {roleStr}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Contact Details Card */}
            <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-4">
              <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2">
                Contact & Details
              </h3>
              
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-xs">
                  <Phone size={14} className="text-gray-400 shrink-0" />
                  <div>
                    <span className="text-gray-400 block text-[9px] uppercase font-bold tracking-wider">Phone</span>
                    <span className="text-gray-700 dark:text-gray-250 font-semibold">{phoneToDisplay}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs">
                  <MapPin size={14} className="text-gray-400 shrink-0" />
                  <div>
                    <span className="text-gray-400 block text-[9px] uppercase font-bold tracking-wider">Location / Address</span>
                    <span className="text-gray-700 dark:text-gray-250 font-semibold">{locationToDisplay}</span>
                  </div>
                </div>

                {certList.length > 0 && (
                  <div className="flex items-start gap-3 text-xs">
                    <Award size={14} className="text-gray-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="text-gray-400 block text-[9px] uppercase font-bold tracking-wider">Certifications</span>
                      <div className="space-y-1 mt-1">
                        {certList.map((cert: any, cIdx: number) => (
                          <div key={cIdx} className="text-xs font-semibold text-gray-700 dark:text-gray-250">
                            • {cert.name || cert.certification_name || cert} {cert.issuer ? `(${cert.issuer})` : ""}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Categorized Skills */}
            <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-4">
              <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2 flex items-center gap-1.5">
                <Sparkles size={14} className="text-indigo-500" />
                <span>Extracted Skills</span>
              </h3>

              {groupedSkills.length === 0 ? (
                <p className="text-xs text-gray-500 italic">No skills listed in active resume.</p>
              ) : (
                <div className="space-y-4">
                  {groupedSkills.map(([category, items]) => (
                    <div key={category} className="space-y-1.5">
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{category}</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((skName, skIdx) => (
                          <span 
                            key={skIdx}
                            className="text-xs font-bold px-2.5 py-1 rounded-xl bg-purple-50 dark:bg-purple-950/20 text-indigo-600 dark:text-purple-300 border border-purple-100/60 dark:border-purple-900/20 shadow-2xs"
                          >
                            {skName}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>

          {/* Right Side: Professional Summary, Experience, Education, Projects (7/12 width) */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            
            {/* Professional Summary */}
            {summaryToDisplay && (
              <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-3">
                <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2">
                  Professional Summary
                </h3>
                <p className="text-xs text-gray-700 dark:text-gray-250 leading-relaxed whitespace-pre-wrap">
                  {summaryToDisplay}
                </p>
              </div>
            )}

            {/* Role Evidence if present */}
            {roleEvidence.length > 0 && (
              <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-3">
                <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2">
                  Role Qualification Evidence
                </h3>
                <ul className="space-y-3">
                  {roleEvidence.map((ev: any, evIdx: number) => {
                    const roleName = typeof ev === "object" ? ev?.role : null;
                    const rawEv = typeof ev === "object" ? ev?.evidence : ev;
                    const evidenceList = Array.isArray(rawEv) ? rawEv : [rawEv];

                    return (
                      <li key={evIdx} className="text-xs text-gray-600 dark:text-gray-300 flex flex-col gap-1.5 pb-1">
                        {roleName && (
                          <span className="font-bold text-gray-900 dark:text-gray-100 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
                            {roleName}
                          </span>
                        )}
                        <div className="space-y-1 pl-3">
                          {evidenceList.map((item: any, iIdx: number) => (
                            <div key={iIdx} className="flex items-start gap-2">
                              <span className="text-indigo-400 font-bold">•</span>
                              <span>{typeof item === "string" ? item : (typeof item === "object" ? JSON.stringify(item) : String(item))}</span>
                            </div>
                          ))}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Employment History (STRICT Company ↔ Designation distinction) */}
            <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-5">
              <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2 flex items-center gap-1.5">
                <Briefcase size={14} className="text-indigo-500" />
                <span>Employment History</span>
              </h3>

              {expList.length === 0 ? (
                <p className="text-xs text-gray-500 italic">No work experience entries found in active resume.</p>
              ) : (
                <div className="relative border-l border-gray-200 dark:border-gray-800 ml-3.5 pl-6 space-y-6 py-1">
                  {expList.map((exp: any, idx: number) => {
                    const compName = exp.company || exp.employer || "Not specified";
                    const desigTitle = exp.designation || exp.role || exp.title || "Not specified";
                    const datesStr = `${exp.start_date || ""} ${exp.start_date && exp.end_date ? "-" : ""} ${exp.end_date || (exp.is_current ? "Present" : "")}`.trim();
                    const respBullets = parseList(exp.responsibilities || exp.bullets);
                    const techList = parseList(exp.technologies);

                    return (
                      <div key={idx} className="relative">
                        {/* Timeline dot */}
                        <span className="absolute -left-[31px] top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-white dark:bg-background border-2 border-indigo-500" />
                        
                        <div className="space-y-1">
                          <h4 className="text-sm font-bold text-gray-950 dark:text-white">
                            {desigTitle}
                          </h4>
                          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                            <span>{compName}</span>
                            {exp.employment_type && (
                              <span className="text-[10px] px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                                {exp.employment_type}
                              </span>
                            )}
                            {datesStr && (
                              <span className="text-[10px] text-gray-400 font-normal">
                                • {datesStr}
                              </span>
                            )}
                          </div>

                          {exp.location && (
                            <p className="text-[11px] text-gray-400">{exp.location}</p>
                          )}

                          {respBullets.length > 0 && (
                            <ul className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                              {respBullets.map((bullet: string, bIdx: number) => (
                                <li key={bIdx} className="flex items-start gap-1.5">
                                  <span className="text-gray-400">•</span>
                                  <span>{bullet}</span>
                                </li>
                              ))}
                            </ul>
                          )}

                          {techList.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2.5">
                              {techList.map((t: string, tIdx: number) => (
                                <span key={tIdx} className="text-[10px] font-semibold px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                                  {t}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Extracted Projects */}
            {projList.length > 0 && (
              <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-5">
                <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2 flex items-center gap-1.5">
                  <Code2 size={14} className="text-indigo-500" />
                  <span>Projects</span>
                </h3>
                <div className="grid grid-cols-1 gap-6 w-full">
                  {projList.map((proj: any, idx: number) => {
                    const pName = proj.name || proj.project_name || "Project Name";
                    const pUrl = proj.url || proj.project_url || proj.link;
                    
                    // Technology string tokenization
                    let pTechs: string[] = [];
                    const rawTech = proj.technologies || proj.tech_stack;
                    if (Array.isArray(rawTech)) {
                      pTechs = rawTech.flatMap((t: string) => typeof t === "string" ? t.split(/[,;|•·/\n]\s*/) : []);
                    } else if (typeof rawTech === "string" && rawTech.trim()) {
                      pTechs = rawTech.split(/[,;|•·/\n]\s*/);
                    }
                    pTechs = Array.from(new Set(pTechs.map((t: string) => t.trim()).filter(Boolean)));

                    const rawBullets: string[] = parseList(proj.responsibilities || proj.bullets || proj.features);
                    const pBullets = Array.from(new Set(rawBullets.map((b: string) => b.replace(/^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*/, "").trim()).filter(Boolean)));

                    // Description vs bullets deduplication check
                    const pDesc = proj.description ? proj.description.replace(/^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*/, "").trim() : "";
                    const joinedBullets = pBullets.join(" ").toLowerCase().replace(/\s+/g, " ");
                    const normDesc = pDesc.toLowerCase().replace(/\s+/g, " ");
                    const isDescDuplicated = pBullets.length > 0 && normDesc && (joinedBullets.includes(normDesc) || normDesc.includes(joinedBullets) || pBullets.some(b => b.toLowerCase().includes(normDesc)));

                    const pDates = proj.start_date || proj.end_date 
                      ? `${proj.start_date || ""} ${proj.start_date && proj.end_date ? "-" : ""} ${proj.end_date || ""}`.trim()
                      : (proj.date || proj.duration || "");

                    return (
                      <div key={idx} className="w-full p-5 rounded-2xl border border-gray-150 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/20 space-y-3 flex flex-col justify-between">
                        <div className="space-y-2">
                          <div className="flex flex-wrap justify-between items-center gap-3">
                            <div className="flex items-center gap-2">
                              <h5 className="text-sm font-bold text-gray-900 dark:text-white leading-snug">{pName}</h5>
                              {pDates && (
                                <span className="text-[11px] text-gray-400 font-normal">
                                  • {pDates}
                                </span>
                              )}
                            </div>
                            {pUrl && (
                              <a href={pUrl} target="_blank" rel="noopener noreferrer" className="text-xs font-bold text-indigo-500 hover:underline flex items-center gap-1 cursor-pointer shrink-0">
                                <span>Link</span>
                                <Globe size={12} />
                              </a>
                            )}
                          </div>
                          {pDesc && !isDescDuplicated && (
                            <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed">
                              {pDesc}
                            </p>
                          )}
                          {pBullets.length > 0 && (
                            <ul className="space-y-1.5 text-xs text-gray-600 dark:text-gray-300">
                              {pBullets.map((b: string, bIdx: number) => (
                                <li key={bIdx} className="flex items-start gap-1.5">
                                  <span className="text-gray-400">•</span>
                                  <span>{b}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                        {pTechs.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {pTechs.map((tech: string, tIdx: number) => (
                              <span key={tIdx} className="text-[10px] font-bold px-2 py-0.5 rounded bg-white dark:bg-background border border-gray-200 dark:border-gray-800 text-gray-600 dark:text-gray-400">
                                {tech}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Education Timeline */}
            <div className="bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col gap-5">
              <h3 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider border-b border-gray-100 dark:border-gray-850 pb-2 flex items-center gap-1.5">
                <GraduationCap size={14} className="text-indigo-500" />
                <span>Education Background</span>
              </h3>

              {eduList.length === 0 ? (
                <p className="text-xs text-gray-500 italic">No education entries found in active resume.</p>
              ) : (
                <div className="relative border-l border-gray-200 dark:border-gray-800 ml-3.5 pl-6 space-y-6 py-1">
                  {eduList.map((edu: any, idx: number) => (
                    <div key={idx} className="relative">
                      {/* Timeline dot */}
                      <span className="absolute -left-[31px] top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-white dark:bg-background border-2 border-purple-500" />
                      
                      <div>
                        <h4 className="text-xs font-bold text-gray-950 dark:text-white">
                          {edu.degree || "Degree Not Listed"} {edu.field_of_study ? `in ${edu.field_of_study}` : ""}
                        </h4>
                        <span className="text-[11px] font-semibold text-gray-500 block mt-0.5">
                          {edu.institution || edu.school || "Institution Not Listed"} {edu.start_date || edu.end_date ? `• ${edu.start_date || ""} ${edu.end_date ? `- ${edu.end_date}` : ""}` : ""}
                        </span>
                        {edu.gpa && (
                          <p className="text-[10px] text-purple-600 dark:text-purple-400 font-bold mt-1">
                            CGPA / GPA: {edu.gpa}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>

        </div>
      ) : (
        // --- EDIT PROFILE MODE (FORM INPUTS) ---
        <div className="max-w-4xl mx-auto bg-white dark:bg-card border border-gray-200 dark:border-gray-800 rounded-3xl p-6 shadow-sm">
          <form onSubmit={handleSaveProfile} className="flex flex-col gap-6">
            
            <div className="flex items-center gap-2 border-b border-gray-100 dark:border-gray-850 pb-3">
              <User size={16} className="text-indigo-500" />
              <h2 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-wider">General Information</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-500">Phone Number</label>
                <input
                  type="text"
                  placeholder="+1 (555) 019-9238"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-500">Physical Address / Location</label>
                <input
                  type="text"
                  placeholder="San Francisco, CA"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-500">Professional Summary</label>
              <textarea
                placeholder="A brief overview of your background, experience, and key skills..."
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={3}
                className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500 resize-none"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-500">Skills Core Competencies (comma separated)</label>
              <textarea
                placeholder="Python, React, TypeScript, FastAPI, WebSockets, PostgreSQL, Docker"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                rows={2}
                className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500 resize-none"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-500">LinkedIn URL</label>
                <input
                  type="text"
                  placeholder="https://linkedin.com/in/..."
                  value={linkedin}
                  onChange={(e) => setLinkedin(e.target.value)}
                  className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-500">GitHub URL</label>
                <input
                  type="text"
                  placeholder="https://github.com/..."
                  value={github}
                  onChange={(e) => setGithub(e.target.value)}
                  className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-500">Portfolio URL</label>
                <input
                  type="text"
                  placeholder="https://myportfolio.com"
                  value={portfolio}
                  onChange={(e) => setPortfolio(e.target.value)}
                  className="bg-white dark:bg-card border border-gray-250 dark:border-gray-800 rounded-xl px-4 py-2.5 text-xs text-gray-800 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-gray-100 dark:border-gray-850">
              <button
                type="button"
                onClick={() => setIsEditMode(false)}
                className="px-5 py-2.5 rounded-xl text-xs font-bold text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-6 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-md transition-all cursor-pointer"
              >
                Save Profile Changes
              </button>
            </div>

          </form>
        </div>
      )}

    </div>
  );
}
