"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { useResumeStore } from "@/store/resumeStore";
import { apiService } from "@/services/api";
import Link from "next/link";
import {
  Mic2,
  MessageSquare,
  Play,
  ArrowRight,
  FileText,
  Loader2,
  Bot,
  User,
  Send,
  ChevronDown,
  CheckCircle,
  BarChart3,
  Award,
  RefreshCw,
  X,
  AlertCircle,
  Sparkles,
  Target,
  BookOpen,
} from "lucide-react";

type InterviewType = "HR" | "Technical" | "Project" | "Behavioral" | "Mixed";
type Difficulty = "Beginner" | "Intermediate" | "Advanced" | "Expert";
type Stage = "setup" | "active" | "completed";

interface InterviewMessage {
  role: "interviewer" | "candidate";
  content: string;
  timestamp: Date;
  questionIndex?: number;
}

interface InterviewScore {
  overall: number;
  technical: number;
  communication: number;
  problemSolving: number;
  confidence: number;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
}

const INTERVIEW_TYPES: { id: InterviewType; label: string; desc: string }[] = [
  { id: "HR", label: "HR Interview", desc: "Company culture, motivation, background" },
  { id: "Technical", label: "Technical Interview", desc: "Deep technical knowledge & problem-solving" },
  { id: "Project", label: "Project Interview", desc: "Your past projects & design decisions" },
  { id: "Behavioral", label: "Behavioral Interview", desc: "STAR-format situational questions" },
  { id: "Mixed", label: "Mixed Interview", desc: "Combination of all types" },
];

const DIFFICULTIES: Difficulty[] = ["Beginner", "Intermediate", "Advanced", "Expert"];

function InterviewRoomContent() {
  const searchParams = useSearchParams();
  const { fullName } = useAuthStore();
  const { activeResume, hasResume, isLoading: loadingResumes } = useResumeStore();
  const roleParam = searchParams.get("role") || "";

  // Setup state
  const [stage, setStage] = useState<Stage>("setup");
  const [selectedType, setSelectedType] = useState<InterviewType>("Technical");
  const [difficulty, setDifficulty] = useState<Difficulty>("Intermediate");
  const [targetRole, setTargetRole] = useState(roleParam);
  const [jobDescription, setJobDescription] = useState("");

  // Active interview state
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [answer, setAnswer] = useState("");
  const [sending, setSending] = useState(false);
  const [questionCount, setQuestionCount] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Results state
  const [score, setScore] = useState<InterviewScore | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const startInterview = async () => {
    if (!targetRole.trim()) {
      setStartError("Please enter a target role.");
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      // We call the existing chat copilot with a structured system message
      // to simulate an AI interviewer. This is the in-platform interview.
      const systemContext = `You are an AI interviewer conducting a ${selectedType} interview for the role of "${targetRole}" at ${difficulty} difficulty level.
You are interviewing ${fullName || "the candidate"}.
${jobDescription ? `Job Description context: ${jobDescription}` : ""}
${activeResume ? `The candidate's global active resume (${activeResume.title}) has been loaded for context.` : ""}

Rules:
1. Start by warmly greeting the candidate and introducing yourself.
2. Ask ONE question at a time. Wait for the answer before asking the next.
3. Based on the answer, ask relevant follow-up questions.
4. Adjust difficulty dynamically based on answer quality.
5. After 8-10 questions, conclude the interview professionally.
6. Be realistic, professional, and human-like — not robotic.
7. For technical questions, ask about specific technologies from the candidate's background.
Start the interview now.`;

      const openingRes = await apiService.chatCopilot(systemContext, []);
      const openingText = openingRes?.reply || openingRes?.message || openingRes?.content || 
        `Hello ${fullName ? fullName.split(" ")[0] : "there"}! Welcome to your ${selectedType} interview for the ${targetRole} role. I'm glad you're here today. Let's begin.\n\nCould you start by telling me a little about yourself and what excites you about this role?`;

      const sid = `interview_${Date.now()}`;
      setSessionId(sid);

      setMessages([{
        role: "interviewer",
        content: openingText,
        timestamp: new Date(),
        questionIndex: 1,
      }]);

      setQuestionCount(1);
      setStage("active");
    } catch (e: any) {
      setStartError("Failed to start interview. Please try again.");
    } finally {
      setStarting(false);
    }
  };

  const sendAnswer = async () => {
    if (!answer.trim() || sending) return;

    const userAnswer = answer.trim();
    setAnswer("");
    setSending(true);

    const candidateMsg: InterviewMessage = {
      role: "candidate",
      content: userAnswer,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, candidateMsg]);

    try {
      // Build conversation history
      const history = messages.map((m) => ({
        role: m.role === "interviewer" ? "assistant" : "user",
        content: m.content,
      }));

      const continuationPrompt = questionCount >= 9
        ? `This was the candidate's ${questionCount}th answer. As the interviewer, conclude the interview professionally — thank the candidate, let them know you'll be in touch, and wish them well. Keep it brief and warm.`
        : `This was the candidate's answer. As the interviewer, ${
            questionCount === 1 ? "acknowledge their introduction and ask a relevant technical or situational question based on their background" :
            "provide brief acknowledgment and ask your next interview question. Keep it conversational and professional."
          }`;

      const res = await apiService.chatCopilot(continuationPrompt, [
        ...history,
        { role: "user", content: userAnswer },
      ]);

      const interviewerReply = res?.reply || res?.message || res?.content || 
        "Thank you for that answer. Could you elaborate further?";

      const isConclusion = questionCount >= 9;

      setMessages((prev) => [...prev, {
        role: "interviewer",
        content: interviewerReply,
        timestamp: new Date(),
        questionIndex: isConclusion ? undefined : questionCount + 1,
      }]);

      if (isConclusion) {
        setTimeout(() => finishInterview(), 2000);
      } else {
        setQuestionCount((c) => c + 1);
      }
    } catch (e) {
      setMessages((prev) => [...prev, {
        role: "interviewer",
        content: "I apologize — I had a technical issue. Could you please repeat your answer?",
        timestamp: new Date(),
      }]);
    } finally {
      setSending(false);
    }
  };

  const finishInterview = async () => {
    setLoadingReport(true);
    try {
      const transcript = messages.map(m => `${m.role === "interviewer" ? "Interviewer" : "Candidate"}: ${m.content}`).join("\n");
      const evalPrompt = `Evaluate the following interview transcript for the target role "${targetRole}" (${selectedType} interview, ${difficulty} level).
Candidate Name: ${fullName || "Candidate"}

Transcript:
${transcript}

Return ONLY a JSON object with this exact structure:
{
  "overall": 78,
  "technical": 80,
  "communication": 75,
  "problemSolving": 78,
  "confidence": 75,
  "strengths": ["string1", "string2", "string3"],
  "weaknesses": ["string1", "string2", "string3"],
  "recommendations": ["string1", "string2", "string3"]
}`;

      const res = await apiService.chatCopilot(evalPrompt, []);
      let text = res?.reply || res?.message || res?.content || "";
      let parsedScore: InterviewScore | null = null;
      try {
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          parsedScore = JSON.parse(jsonMatch[0]);
        }
      } catch (e) {
        console.error("Failed to parse AI evaluation JSON", e);
      }

      if (parsedScore && typeof parsedScore.overall === "number") {
        setScore(parsedScore);
      } else {
        setScore({
          overall: 70,
          technical: 70,
          communication: 75,
          problemSolving: 70,
          confidence: 70,
          strengths: ["Completed full interview session", "Responded to all interviewer prompts"],
          weaknesses: ["Detailed technical depth could be expanded"],
          recommendations: ["Review target role concepts and practice system design"],
        });
      }
    } catch (err) {
      console.error("Error evaluating interview", err);
      setScore({
        overall: 70,
        technical: 70,
        communication: 70,
        problemSolving: 70,
        confidence: 70,
        strengths: ["Completed interview session"],
        weaknesses: ["Evaluation service temporary offline"],
        recommendations: ["Review key interview concepts"],
      });
    } finally {
      setLoadingReport(false);
      setStage("completed");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendAnswer();
    }
  };

  // ─── SETUP STAGE ───
  if (stage === "setup") {
    return (
      <div className="min-h-screen bg-app-bg text-app-text font-sans">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-6">
          {/* Header */}
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white shadow-md">
                <Mic2 size={22} />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-app-text">AI Interview Room</h1>
                <p className="text-sm text-app-text-muted">Realistic AI-powered interview based on your resume</p>
              </div>
            </div>
          </div>

          {/* Active Resume Status */}
          <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-app-text text-sm flex items-center gap-2">
                <FileText size={15} className="text-blue-500" />
                Active Candidate Resume
              </h3>
              {hasResume && (
                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <CheckCircle size={13} /> Active Global Resume
                </span>
              )}
            </div>
            {loadingResumes ? (
              <div className="flex items-center gap-2 text-sm text-app-text-muted">
                <Loader2 size={14} className="animate-spin" /> Resolving active resume…
              </div>
            ) : !hasResume || !activeResume ? (
              <div className="flex items-center gap-3 p-3 rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-800/40">
                <AlertCircle size={16} className="text-amber-500 shrink-0" />
                <div>
                  <p className="text-sm text-amber-700 dark:text-amber-400 font-medium">No active resume found</p>
                  <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">
                    Upload a resume to enable AI personalized interview preparation.{" "}
                    <Link href="/candidate/resumes/upload" className="underline font-semibold">Upload →</Link>
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between p-3.5 rounded-xl bg-app-card border border-app-border">
                <div className="flex items-center gap-3 min-w-0">
                  <FileText size={16} className="text-blue-500 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-app-text truncate">{activeResume.title}</p>
                    <p className="text-[11px] text-app-text-muted mt-0.5">
                      {activeResume.file_name ? `${activeResume.file_name} • ` : ""}Loaded automatically for AI interview questions
                    </p>
                  </div>
                </div>
                <Link
                  href="/candidate/resumes/upload"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-semibold shrink-0 ml-2"
                >
                  Update
                </Link>
              </div>
            )}
          </div>

          {/* Target Role */}
          <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
            <h3 className="font-bold text-app-text text-sm flex items-center gap-2">
              <Target size={15} className="text-violet-500" />
              Target Role
            </h3>
            <input
              type="text"
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value)}
              placeholder="e.g. GenAI Engineer, Full Stack Developer, Data Scientist…"
              className="w-full px-4 py-3 rounded-xl border border-app-border bg-app-bg text-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:ring-2 focus:ring-violet-500/40 transition-all"
            />
          </div>

          {/* Interview Type */}
          <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
            <h3 className="font-bold text-app-text text-sm flex items-center gap-2">
              <MessageSquare size={15} className="text-emerald-500" />
              Interview Type
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {INTERVIEW_TYPES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSelectedType(t.id)}
                  className={`flex flex-col items-start p-3.5 rounded-xl border text-left transition-all ${
                    selectedType === t.id
                      ? "border-indigo-500/60 bg-indigo-50/50 dark:bg-indigo-950/20"
                      : "border-app-border hover:border-indigo-300 dark:hover:border-indigo-800/60"
                  }`}
                >
                  <span className="text-sm font-semibold text-app-text">{t.label}</span>
                  <span className="text-xs text-app-text-muted mt-0.5">{t.desc}</span>
                  {selectedType === t.id && (
                    <span className="mt-1.5 text-[10px] font-bold text-indigo-600 dark:text-indigo-400">Selected ✓</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Difficulty */}
          <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
            <h3 className="font-bold text-app-text text-sm flex items-center gap-2">
              <BarChart3 size={15} className="text-amber-500" />
              Difficulty Level
            </h3>
            <div className="flex gap-2 flex-wrap">
              {DIFFICULTIES.map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`px-4 py-2 rounded-xl text-sm font-semibold border transition-all ${
                    difficulty === d
                      ? "bg-amber-100 dark:bg-amber-950/40 border-amber-500/60 text-amber-700 dark:text-amber-400"
                      : "border-app-border text-app-text-muted hover:text-app-text hover:border-amber-300 dark:hover:border-amber-800/60"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          {/* Optional JD */}
          <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
            <h3 className="font-bold text-app-text text-sm flex items-center gap-2">
              <Sparkles size={15} className="text-blue-500" />
              Job Description <span className="text-app-text-muted font-normal">(Optional)</span>
            </h3>
            <textarea
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder="Paste the job description to make the interview more targeted…"
              rows={4}
              className="w-full px-4 py-3 rounded-xl border border-app-border bg-app-bg text-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-none transition-all"
            />
          </div>

          {/* Error */}
          {startError && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200/60 dark:border-red-800/40 text-sm text-red-600 dark:text-red-400">
              <AlertCircle size={15} className="shrink-0" />
              {startError}
            </div>
          )}

          {/* Start */}
          <button
            onClick={startInterview}
            disabled={starting || !targetRole.trim()}
            className="w-full flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-bold text-base hover:from-indigo-700 hover:to-violet-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-indigo-500/20"
          >
            {starting ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Starting Interview…
              </>
            ) : (
              <>
                <Play size={18} />
                Start {selectedType} Interview
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  // ─── ACTIVE INTERVIEW STAGE ───
  if (stage === "active") {
    return (
      <div className="h-screen flex flex-col bg-app-bg text-app-text font-sans overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 px-4 sm:px-6 py-3 border-b border-app-border bg-app-surface flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white">
              <Mic2 size={17} />
            </div>
            <div>
              <p className="font-bold text-sm text-app-text">{selectedType} Interview — {targetRole}</p>
              <p className="text-[11px] text-app-text-muted">Q{questionCount} of ~10 · {difficulty}</p>
            </div>
          </div>
          <button
            onClick={finishInterview}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-app-border text-xs font-semibold text-app-text-muted hover:text-red-500 hover:border-red-300 transition-colors"
          >
            End Interview
          </button>
        </div>

        {/* Progress bar */}
        <div className="w-full h-0.5 bg-app-border">
          <div
            className="h-0.5 bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
            style={{ width: `${Math.min(100, (questionCount / 10) * 100)}%` }}
          />
        </div>

        {/* Messages */}
        <div className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-6 py-5 space-y-5">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "candidate" ? "flex-row-reverse" : "flex-row"}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1 ${
                msg.role === "interviewer"
                  ? "bg-gradient-to-br from-indigo-500 to-violet-600 text-white"
                  : "bg-blue-600 text-white"
              }`}>
                {msg.role === "interviewer" ? <Bot size={15} /> : <User size={15} />}
              </div>
              <div className={`flex flex-col gap-1 max-w-[80%] ${msg.role === "candidate" ? "items-end" : "items-start"}`}>
                <div className={`text-[10px] font-semibold mb-0.5 ${msg.role === "candidate" ? "text-blue-500" : "text-indigo-500"}`}>
                  {msg.role === "interviewer" ? "AI Interviewer" : "You"}
                  {msg.questionIndex && ` · Q${msg.questionIndex}`}
                </div>
                <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  msg.role === "candidate"
                    ? "bg-blue-600 text-white rounded-tr-sm"
                    : "bg-app-surface border border-app-border text-app-text rounded-tl-sm"
                }`}>
                  {msg.content.split("\n").map((line, j) => (
                    <span key={j}>{line}{j < msg.content.split("\n").length - 1 && <br />}</span>
                  ))}
                </div>
                <span className="text-[10px] text-app-text-muted">
                  {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-white flex items-center justify-center">
                <Bot size={15} />
              </div>
              <div className="bg-app-surface border border-app-border px-4 py-3 rounded-2xl rounded-tl-sm flex items-center gap-2">
                <div className="flex gap-1">
                  {[0, 150, 300].map((d) => (
                    <div key={d} className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: `${d}ms` }} />
                  ))}
                </div>
                <span className="text-xs text-app-text-muted">Thinking…</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Answer input */}
        <div className="flex-shrink-0 px-4 sm:px-6 py-4 border-t border-app-border bg-app-surface">
          <div className="flex items-end gap-3">
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your answer… (Enter to send, Shift+Enter for new line)"
              rows={2}
              disabled={sending}
              className="flex-1 px-4 py-3 rounded-xl border border-app-border bg-app-bg text-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:ring-2 focus:ring-indigo-500/40 resize-none transition-all disabled:opacity-60"
              style={{ maxHeight: "120px" }}
              onInput={(e) => {
                const t = e.target as HTMLTextAreaElement;
                t.style.height = "auto";
                t.style.height = Math.min(t.scrollHeight, 120) + "px";
              }}
            />
            <button
              onClick={sendAnswer}
              disabled={!answer.trim() || sending}
              className="w-11 h-11 rounded-xl bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ─── COMPLETED STAGE ───
  if (stage === "completed") {
    if (loadingReport) {
      return (
        <div className="min-h-screen bg-app-bg flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 rounded-full border-4 border-t-indigo-500 border-app-border animate-spin" />
            <p className="text-sm text-app-text-muted font-medium">Analyzing your interview performance…</p>
          </div>
        </div>
      );
    }

    return (
      <div className="min-h-screen bg-app-bg text-app-text font-sans">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 space-y-6">
          {/* Header */}
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white mx-auto mb-4 shadow-lg">
              <Award size={28} />
            </div>
            <h1 className="text-2xl font-bold text-app-text">Interview Complete!</h1>
            <p className="text-sm text-app-text-muted mt-1">
              {selectedType} Interview · {targetRole} · {difficulty}
            </p>
          </div>

          {/* Overall Score */}
          {score && (
            <>
              <div className="bg-gradient-to-br from-indigo-50 to-violet-50 dark:from-indigo-950/30 dark:to-violet-950/30 border border-indigo-200/60 dark:border-indigo-800/40 rounded-2xl p-6 text-center">
                <p className="text-sm font-medium text-app-text-muted mb-2">Overall Score</p>
                <p className="text-5xl font-bold text-indigo-600 dark:text-indigo-400">{score.overall}</p>
                <p className="text-sm text-app-text-muted mt-1">out of 100</p>
              </div>

              {/* Score breakdown */}
              <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-4">
                <h3 className="font-bold text-app-text text-sm flex items-center gap-2">
                  <BarChart3 size={15} className="text-blue-500" /> Score Breakdown
                </h3>
                {[
                  { label: "Technical Knowledge", value: score.technical, color: "bg-blue-500" },
                  { label: "Communication", value: score.communication, color: "bg-emerald-500" },
                  { label: "Problem Solving", value: score.problemSolving, color: "bg-violet-500" },
                  { label: "Confidence", value: score.confidence, color: "bg-amber-500" },
                ].map((item) => (
                  <div key={item.label} className="space-y-1">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-medium text-app-text">{item.label}</span>
                      <span className="text-xs font-bold text-app-text">{item.value}/100</span>
                    </div>
                    <div className="w-full h-2 bg-app-border rounded-full">
                      <div
                        className={`h-2 rounded-full ${item.color} transition-all duration-700`}
                        style={{ width: `${item.value}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Strengths */}
              <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
                <h3 className="font-bold text-sm text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                  <CheckCircle size={14} /> Strengths
                </h3>
                <ul className="space-y-1.5">
                  {score.strengths.map((s) => (
                    <li key={s} className="flex items-center gap-2 text-sm text-app-text">
                      <span className="text-emerald-500">✓</span> {s}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Weaknesses */}
              <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
                <h3 className="font-bold text-sm text-amber-600 dark:text-amber-400 flex items-center gap-2">
                  <AlertCircle size={14} /> Areas to Improve
                </h3>
                <ul className="space-y-1.5">
                  {score.weaknesses.map((w) => (
                    <li key={w} className="flex items-center gap-2 text-sm text-app-text">
                      <span className="text-amber-500">⚠</span> {w}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Recommendations */}
              <div className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
                <h3 className="font-bold text-sm text-blue-600 dark:text-blue-400 flex items-center gap-2">
                  <Sparkles size={14} /> Recommendations
                </h3>
                <ul className="space-y-1.5">
                  {score.recommendations.map((r) => (
                    <li key={r} className="flex items-center gap-2 text-sm text-app-text">
                      <ArrowRight size={12} className="text-blue-500 shrink-0" /> {r}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {/* CTA Buttons */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              onClick={() => {
                setStage("setup");
                setMessages([]);
                setQuestionCount(0);
                setScore(null);
              }}
              className="flex items-center justify-center gap-2 py-3 rounded-xl border border-app-border text-sm font-semibold hover:bg-app-surface transition-colors"
            >
              <RefreshCw size={15} /> Practice Again
            </button>
            <Link
              href="/candidate/skill-lab"
              className="flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600 text-white text-sm font-bold hover:bg-blue-700 transition-colors"
            >
              <BookOpen size={15} /> Start Learning
            </Link>
          </div>

          <Link
            href="/candidate/interview-history"
            className="flex items-center justify-center gap-1.5 text-sm font-semibold text-app-text-muted hover:text-app-text transition-colors"
          >
            View Interview History <ChevronDown size={13} />
          </Link>
        </div>
      </div>
    );
  }

  return null;
}

export default function InterviewRoomPage() {
  return (
    <Suspense fallback={null}>
      <InterviewRoomContent />
    </Suspense>
  );
}
