# VidyaMarg AI — Complete Database Table Dependency Matrix
**Document ID:** `01_DATABASE_TABLE_DEPENDENCY_MATRIX`  
**Database File:** `vidyamarg.db` (SQLite)  
**Initial Tables Audited:** 86  
**Final Post-Cleanup Tables:** 70  

---

## 1. Schema Classification Taxonomy

Every table in the physical database schema and SQLAlchemy metadata was systematically audited across 10 evaluation vectors:
1. Active production route read/write operations
2. Foreign-key relationships (inbound and outbound)
3. SQLAlchemy relationship mappers
4. Raw SQL queries and query builders
5. Background worker and scheduler jobs
6. AI Agent tool executions (Resume Intelligence, Job Hunter, Baelyx Mentor)
7. Migration history and table initialization
8. Historical record retention (candidate submissions, parsed resumes)
9. Candidate data isolation and ownership
10. Authentication and security compliance

### Classification Categories:
- **Category 1: Candidate-Critical (52 Tables)** — Absolutely required by active candidate features (Resume Center, Job Agent, ATS Optimization, Skill Lab, Interviews).
- **Category 2: Restored Candidate Tables (13 Tables)** — Tables previously misattributed with a `legacy_` prefix in earlier audits, but actively queried by production candidate modules. Restored to canonical schema names.
- **Category 3: Shared Infrastructure & Security (5 Tables)** — Shared authentication, refresh tokens, consent logging, and audit records.
- **Category 4: Admin-Only (5 Tables)** — Exclusively used by obsolete administrative dashboard, course generation, and telegram features. Approved for safe removal.
- **Category 5: Legacy/Unused (11 Tables)** — Obsolete schema iterations with zero active production queries and zero data rows. Approved for safe removal.

---

## 2. Table Dependency & Classification Inventory

### Category 1: Candidate-Critical Tables (Preserved — 52 Tables)

| Table Name | Foreign Key Dependencies | Active Production Consumers | Business Function | Status |
| :--- | :--- | :--- | :--- | :--- |
| `users` | Referenced by 18 tables | `auth.py`, `profile.py`, all features | Core authentication entity (UUID/int PK) | **PRESERVED** |
| `candidates` | $\rightarrow$ `users.id` | `profile.py`, `resume_center.py` | Candidate identity, skills, stage | **PRESERVED** |
| `candidate_profiles` | $\rightarrow$ `candidates.id` | `resume_center.py`, `profile.py` | Parsed profile metadata & graph | **PRESERVED** |
| `candidate_resumes` | $\rightarrow$ `candidates.id` | `resume_center.py`, `storage.py` | Uploaded resume files and URLs | **PRESERVED** |
| `candidate_embeddings` | $\rightarrow$ `candidates.id` | `resume_center.py`, RAG agent | 768-dim vector embeddings | **PRESERVED** |
| `resumes` | $\rightarrow$ `candidates.id` | `resume_center.py` | Master resume root entity | **PRESERVED** |
| `resume_templates` | None | `resume_center.py` | Overleaf-compatible LaTeX templates | **PRESERVED** |
| `resume_document_versions` | $\rightarrow$ `resumes.id` | `resume_center.py` | Immutable snapshots of LaTeX & PDF | **PRESERVED** |
| `resume_extractions` | $\rightarrow$ `resumes.id` | `resume_extractor_engine.py` | Universal OCR & parser outputs | **PRESERVED** |
| `resume_profiles` | $\rightarrow$ `resumes.id` | `resume_center.py` | Resume header, contact, summary | **PRESERVED** |
| `resume_skills` | $\rightarrow$ `resumes.id` | `resume_center.py`, ATS engine | Technical & soft skill sets | **PRESERVED** |
| `resume_experiences` | $\rightarrow$ `resumes.id` | `resume_center.py`, ATS engine | Employment positions & bullets | **PRESERVED** |
| `resume_educations` | $\rightarrow$ `resumes.id` | `resume_center.py` | Degrees, institutions, GPA | **PRESERVED** |
| `resume_projects` | $\rightarrow$ `resumes.id` | `resume_center.py`, ATS engine | Projects, tech stack, URLs | **PRESERVED** |
| `resume_certifications` | $\rightarrow$ `resumes.id` | `resume_center.py` | Professional certifications & dates | **PRESERVED** |
| `resume_sections` | $\rightarrow$ `resumes.id` | `resume_center.py` | Custom resume sections | **PRESERVED** |
| `resume_optimizations` | $\rightarrow$ `resumes.id`, `jobs.id` | `resume_center.py`, tailoring engine | Targeted job tailoring iterations | **PRESERVED** |
| `resume_optimization_evidence` | $\rightarrow$ `resume_optimizations.id` | Tailoring pipeline | Bullet matching evidence | **PRESERVED** |
| `job_descriptions` | $\rightarrow$ `users.id` | `resume_center.py` | Ingested target job descriptions | **PRESERVED** |
| `resume_ai_analysis` | $\rightarrow$ `resumes.id` | `resume_center.py` | ATS scores, breakdown, metrics | **PRESERVED** |
| `resume_improvements` | $\rightarrow$ `resumes.id` | `resume_center.py` | Suggested bullet rewrites | **PRESERVED** |
| `resume_versions` | $\rightarrow$ `resumes.id` | `resume_center.py` | Semantic resume checkpoints | **PRESERVED** |
| `resume_embeddings` | $\rightarrow$ `resumes.id` | Resume RAG search | Embedding vectors for bullet points | **PRESERVED** |
| `companies` | None | `jobs.py`, `job_agent.py` | Company intelligence records | **PRESERVED** |
| `job_sources` | None | `job_agent.py`, scrapers | Source metadata (LinkedIn, Indeed) | **PRESERVED** |
| `jobs` | $\rightarrow$ `companies.id`, `job_sources.id`| `jobs.py`, `job_agent.py` | Active job postings database | **PRESERVED** |
| `matches` | $\rightarrow$ `candidates.id`, `jobs.id` | Matching engine | Candidate $\leftrightarrow$ Job compatibility | **PRESERVED** |
| `recommendations` | $\rightarrow$ `candidates.id` | Job intelligence | Suggested roles & career steps | **PRESERVED** |
| `applications` | $\rightarrow$ `candidates.id`, `jobs.id` | `job_agent.py`, Kanban | Candidate application tracker | **PRESERVED** |
| `application_events` | $\rightarrow$ `applications.id` | `job_agent.py` | Application status timeline | **PRESERVED** |
| `interview_preparations` | $\rightarrow$ `candidates.id`, `jobs.id` | Interview Room | Custom interview preparation packs | **PRESERVED** |
| `skill_gap_analysis` | $\rightarrow$ `candidates.id` | Career Intelligence | Identified skill deficiencies | **PRESERVED** |
| `career_insights` | $\rightarrow$ `candidates.id` | Career Intelligence | Salary benchmarks & demand scores | **PRESERVED** |
| `market_intelligence` | None | Career Intelligence | Hiring velocity & market trends | **PRESERVED** |
| `analytics_events` | $\rightarrow$ `users.id` | Telemetry pipeline | Feature interaction logs | **PRESERVED** |
| `candidate_agents` | $\rightarrow$ `candidates.id` | `career_agent.py` | Autonomous job agent configuration | **PRESERVED** |
| `candidate_agent_preferences` | $\rightarrow$ `candidate_agents.id` | `career_agent.py` | Search & application preferences | **PRESERVED** |
| `agent_runs` | $\rightarrow$ `candidate_agents.id` | `career_agent.py` | Execution history of agent loops | **PRESERVED** |
| `agent_actions` | $\rightarrow$ `agent_runs.id` | `career_agent.py` | Discrete actions taken by agents | **PRESERVED** |
| `agent_notifications` | $\rightarrow$ `candidates.id` | `career_agent.py` | In-app alerts from agent runs | **PRESERVED** |
| `candidate_skill_graph` | $\rightarrow$ `candidates.id` | Skill Lab | Skill taxonomy & relationships | **PRESERVED** |
| `candidate_career_graph` | $\rightarrow$ `candidates.id` | Career Navigator | Target job trajectories | **PRESERVED** |
| `candidate_career_dna` | $\rightarrow$ `candidates.id` | Career Navigator | Behavioral & technical profile | **PRESERVED** |
| `career_paths` | None | Career Navigator | Roadmap role milestone definitions | **PRESERVED** |
| `career_opportunities` | None | Career Navigator | Opportunistic recommendations | **PRESERVED** |
| `career_eligibility_matrix` | None | Career Navigator | Role prerequisite criteria | **PRESERVED** |
| `courses` | None | `learning.py` | LMS course curriculum repository | **PRESERVED** |
| `course_modules` | $\rightarrow$ `courses.id` | `learning.py` | Learning modules & topics | **PRESERVED** |
| `course_projects` | $\rightarrow$ `courses.id` | `learning.py` | Capstone projects & rubrics | **PRESERVED** |
| `course_assessments` | $\rightarrow$ `courses.id` | `learning.py` | Course quizzes & final interviews | **PRESERVED** |
| `course_progress` | $\rightarrow$ `users.id`, `courses.id` | `learning.py` | Video and quiz progress tracking | **PRESERVED** |
| `notifications` | $\rightarrow$ `users.id` | `notifications.py` | Candidate system notifications | **PRESERVED** |

---

### Category 2: Restored Candidate Tables (13 Tables)
These tables were formerly renamed with a `legacy_` prefix by a previous automated schema script, which broke production queries when candidates used AI Mentor, Chat, or Portal Automation. They have been restored to canonical status:

| Former Name in DB | Restored Canonical Name | Active Production Consumer | Reason for Restoration |
| :--- | :--- | :--- | :--- |
| `legacy_ai_mentor_sessions` | `ai_mentor_sessions` | `mentor.py:246` | Stores candidate Baelyx mentor chat sessions |
| `legacy_ai_mentor_messages` | `ai_mentor_messages` | `mentor.py:264` | Stores candidate mentor message threads |
| `legacy_ai_mentor_study_plans` | `ai_mentor_study_plans` | `mentor.py:29` | Stores candidate personalized study roadmaps |
| `legacy_ai_mentor_insights` | `ai_mentor_insights` | `mentor.py:204` | Stores achievements, warnings & learning advice |
| `legacy_ai_mentor_artifacts` | `ai_mentor_artifacts` | `mentor.py:246` | Stores candidate revision notes & quizzes |
| `legacy_ai_mentor_usage` | `ai_mentor_usage` | `mentor.py:92` | Stores LLM token usage and rate tracking |
| `legacy_user_career_profiles` | `user_career_profiles` | `mentor.py:217` | Stores candidate target roles and goals |
| `legacy_email_notifications` | `email_notifications` | `notifications.py:45` | Stores candidate outbound email status |
| `legacy_messages` | `messages` | `chat.py:650` | Stores candidate direct messages and team chat |
| `legacy_learning_events` | `learning_events` | `learning.py:1534` | Stores candidate LMS learning interactions |
| `legacy_agent_memory` | `agent_memory` | `career_agent.py:110` | Stores long-term candidate preference memory |
| `legacy_browser_sessions` | `browser_sessions` | `session_models.py:13` | Stores Playwright portal application sessions |
| `legacy_browser_cookies` | `browser_cookies` | `session_models.py:34` | Stores candidate authenticated portal cookies |

---

### Category 3: Shared Infrastructure & Security (5 Tables)

| Table Name | Foreign Key Dependencies | Active Consumers | Purpose | Status |
| :--- | :--- | :--- | :--- | :--- |
| `otps` | None | `auth.py:494` | One-time password verification tokens | **PRESERVED** |
| `user_refresh_tokens` | $\rightarrow$ `users.id` | `auth.py:90` | JWT refresh tokens and rotation hashes | **PRESERVED** |
| `user_preferences` | $\rightarrow$ `users.id` | `profile.py:30` | Candidate theme (light/dark) persistence | **PRESERVED** |
| `user_consents` | $\rightarrow$ `users.id` | GDPR compliance | User privacy and terms consent records | **PRESERVED** |
| `audit_logs` | $\rightarrow$ `users.id` | Compliance logging | Security access and credential changes | **PRESERVED** |

---

### Category 4: Admin-Only Tables (Removed — 5 Tables)

| Table Name | Row Count | Foreign Keys | Evidence Supporting Safe Dropping | Status |
| :--- | :---: | :--- | :--- | :--- |
| `legacy_course_analytics` | 0 | None | Exclusively served `/admin/courses` LMS metrics | **DROPPED** |
| `legacy_telegram_sources` | 0 | None | Exclusively served `/admin/telegram-sources` CRUD | **DROPPED** |
| `legacy_video_analytics` | 0 | None | Exclusively served `/admin/dashboard` metrics | **DROPPED** |
| `dead_letter_jobs` | 0 | None | Admin-only worker queue recovery table | **DROPPED** |
| `tool_permissions` | 0 | None | Admin role permission matrix table | **DROPPED** |

---

### Category 5: Genuine Legacy / Unused Tables (Removed — 11 Tables)

| Table Name | Row Count | Foreign Keys | Reason for Safe Removal | Status |
| :--- | :---: | :--- | :--- | :--- |
| `legacy_agent_activities` | 0 | None | Superseded by `agent_actions` in `job_models.py` | **DROPPED** |
| `legacy_agent_health` | 0 | None | Obsolete background health monitoring experiment | **DROPPED** |
| `legacy_application_history` | 0 | None | Superseded by `applications` & `application_events` | **DROPPED** |
| `legacy_candidate_preferences` | 0 | None | Superseded by `candidate_agent_preferences` | **DROPPED** |
| `legacy_career_health_snapshots` | 0 | None | Superseded by `career_insights` in `job_models.py` | **DROPPED** |
| `legacy_circuit_breaker_states` | 0 | None | Circuit breakers use in-memory state tracking | **DROPPED** |
| `legacy_company_intelligence_cache` | 0 | None | Superseded by `companies` in `job_models.py` | **DROPPED** |
| `legacy_mcp_chat_messages` | 0 | $\rightarrow$ `mcp_chat_sessions` | Superseded by active candidate chat (`messages`) | **DROPPED** |
| `legacy_mcp_chat_sessions` | 0 | None | Superseded by active candidate chat (`messages`) | **DROPPED** |
| `legacy_mcp_audit_logs` | 0 | None | Unused experimental MCP audit logging | **DROPPED** |
| `legacy_vector_memory` | 0 | None | Superseded by `candidate_embeddings` and Qdrant | **DROPPED** |

---

## 3. Reconciliation Summary

$$\text{Initial Tables (86)} - \text{Dropped Tables (16)} = \text{Remaining Tables (70)}$$

Every remaining table actively supports an authenticated candidate workflow or core authentication and security compliance.
