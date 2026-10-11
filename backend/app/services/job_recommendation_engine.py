"""
VidyaMarg AI — Strict Target-Role & Skill-Based Job Recommendation Engine
========================================================================

Architecture:
1. Candidate Profile Context Retrieval (Active Resume only)
2. Controlled Skill Normalization & Canonical Equivalence
3. Hard Rejection Rules (Profession Mismatch, Unrelated Stack, Single Generic Skill Trap, Seniority Gap)
4. Five-Dimension Weighted Scoring (Target Role: 35%, Required Skills: 30%, Tech Stack: 15%, Experience: 10%, Responsibilities: 10%)
5. Strict Recommendation Threshold (MATCH SCORE >= 65)
6. Detailed Match Explanation & Reason Generation
7. Candidate Isolation & Database Persistence
"""
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.models import Candidate, User
from app.models.job_models import Job, Match, CandidateAgent
from app.services.active_resume_rag_service import ActiveResumeRAGService

logger = logging.getLogger("app.services.job_recommendation_engine")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONTROLLED SKILL EQUIVALENCES
# ─────────────────────────────────────────────────────────────────────────────

CONTROLLED_EQUIVALENCES: Dict[str, str] = {
    # Large Language Models
    "llm": "large language models",
    "large language model": "large language models",
    "large language models": "large language models",
    "llms": "large language models",
    # Generative AI
    "generative ai": "generative ai",
    "genai": "generative ai",
    "gen ai": "generative ai",
    # REST API
    "rest api": "rest api",
    "rest apis": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    # Machine Learning
    "machine learning": "machine learning",
    "ml": "machine learning",
    # Deep Learning
    "deep learning": "deep learning",
    "dl": "deep learning",
    # Natural Language Processing
    "natural language processing": "natural language processing",
    "nlp": "natural language processing",
    # Semantic Search
    "semantic search": "semantic search",
    "semantic retrieval": "semantic search",
    # Vector Database
    "vector database": "vector database",
    "vector db": "vector database",
    "vectordb": "vector database",
    "vector databases": "vector database",
    # PostgreSQL
    "postgresql": "postgresql",
    "postgres": "postgresql",
    # Kubernetes
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
}

# Strict Unsafe Equivalences: Forbidden from matching each other
# Python != Java, Python != C++, FastAPI != Flask, FastAPI != Django,
# TensorFlow != PyTorch, AWS != Azure, React != Angular, PostgreSQL != MySQL


class SkillNormalizer:
    """Normalizes skills using controlled, truthful equivalence mappings."""

    @classmethod
    def clean(cls, skill: str) -> str:
        if not skill:
            return ""
        s = skill.strip().lower()
        # Remove trailing punctuation
        s = re.sub(r"[^\w\s\+\#\.\-]", "", s)
        return s.strip()

    @classmethod
    def normalize(cls, skill: str) -> str:
        cleaned = cls.clean(skill)
        if not cleaned:
            return ""
        return CONTROLLED_EQUIVALENCES.get(cleaned, cleaned)

    @classmethod
    def normalize_set(cls, skills: List[str]) -> Set[str]:
        res: Set[str] = set()
        for s in skills:
            norm = cls.normalize(s)
            if norm:
                res.add(norm)
        return res


# ─────────────────────────────────────────────────────────────────────────────
# 2. HARD REJECTION RULES
# ─────────────────────────────────────────────────────────────────────────────

UNRELATED_PROFESSION_PATTERNS = [
    # Sales, Marketing, Business
    r"\bsales\b",
    r"\baccount executive\b",
    r"\bmarketing\b",
    r"\bbusiness development\b",
    r"\bproduct sales\b",
    # Content & Clerical
    r"\bcontent writer\b",
    r"\bcopywriter\b",
    r"\bdata entry\b",
    r"\btypist\b",
    r"\bsecretary\b",
    # Non-software engineering
    r"\bmechanical engineer\b",
    r"\bcivil engineer\b",
    r"\belectrical engineer\b",
    r"\bchemical engineer\b",
    # Non-technical corporate domains
    r"\baccountant\b",
    r"\bfinancial controller\b",
    r"\btax auditor\b",
    r"\bequity research\b",
    r"\bhuman resources\b",
    r"\btalent acquisition\b",
    r"\bclinical research\b",
]

UNRELATED_TECH_STACK_PATTERNS = [
    # Java / Spring stack (when candidate is AI/Python)
    r"\bjava\b.*\bspring\b",
    r"\bspring boot\b",
    # Frontend JS frameworks
    r"\breact\b.*\bnode\b",
    r"\bangular\b",
    # Enterprise ERP
    r"\bsap\b.*\babap\b",
    r"\babap\b",
]


class HardRejectionFilter:
    """
    Evaluates strict disqualification rules to reject irrelevant jobs immediately.
    """

    @classmethod
    def evaluate(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_rejected: bool, rejection_reason: Optional[str]).
        """
        title_lower = (job.title or "").strip().lower()
        role_cat_lower = (job.role_category or "").strip().lower()
        cand_primary = (candidate_context.get("primary_designation") or "").strip().lower()
        cand_target_roles = [r.strip().lower() for r in (candidate_context.get("target_roles") or []) if r]
        cand_skills_norm = candidate_context.get("skills_norm", set())
        cand_years_exp = candidate_context.get("years_experience", 2.0)

        # ── RULE 1: Unrelated Profession / Non-Target Roles ───────────────────
        # Check if title indicates a different profession (e.g. Sales Manager, Data Entry)
        is_candidate_tech_ai = any("ai" in r or "ml" in r or "machine learning" in r or "data" in r for r in [cand_primary] + cand_target_roles)

        if is_candidate_tech_ai:
            for pat in UNRELATED_PROFESSION_PATTERNS:
                if re.search(pat, title_lower) or re.search(pat, role_cat_lower):
                    # Check if candidate explicitly targets this role
                    if not any(re.search(pat, tr) for tr in cand_target_roles):
                        return True, f"Role profession mismatch: '{job.title}' is outside target career tracks"

            # Check if frontend / mobile / SAP when candidate has NO such skills
            if ("frontend" in title_lower or "react developer" in title_lower or "angular" in title_lower or "ui/ux" in title_lower):
                has_frontend_skill = any(s in cand_skills_norm for s in ["react", "vue", "angular", "next.js", "frontend", "figma", "ui/ux"])
                if not has_frontend_skill:
                    return True, "Role is frontend/design engineering, candidate profile has no verified frontend stack"

            if ("java developer" in title_lower or "spring boot" in title_lower):
                has_java = any(s in cand_skills_norm for s in ["java", "spring", "spring boot"])
                if not has_java:
                    return True, "Role requires Java / Spring ecosystem, candidate has no verified Java stack"

            if ("sap" in title_lower or "abap" in title_lower):
                has_sap = any(s in cand_skills_norm for s in ["sap", "abap"])
                if not has_sap:
                    return True, "Role is enterprise SAP/ABAP, candidate has no verified SAP stack"

        # ── RULE 2: Single Generic Skill Trap ─────────────────────────────────
        # "Do not consider a job relevant merely because it contains one generic skill such as Python."
        job_req_skills = job.required_skills or []
        if isinstance(job_req_skills, list) and len(job_req_skills) >= 3:
            norm_job_req = {SkillNormalizer.normalize(s) for s in job_req_skills if s}
            matched_skills = norm_job_req.intersection(cand_skills_norm)
            overlap_ratio = len(matched_skills) / len(norm_job_req)

            # If only 1 generic skill matched (e.g. Python) and job requires 4+ distinct tech stacks
            generic_anchor_skills = {"python", "sql", "git"}
            is_only_generic_anchor = (len(matched_skills) == 1 and next(iter(matched_skills)) in generic_anchor_skills)
            
            # Check if role title has ANY overlap with candidate target roles
            role_words = [w for r in ([cand_primary] + cand_target_roles) for w in r.split() if len(w) > 2 and w not in ["and", "the", "for"]]
            has_role_word_match = any(w in title_lower or w in role_cat_lower for w in role_words)

            if is_only_generic_anchor and not has_role_word_match:
                return True, f"Insufficient technical overlap: only 1 generic skill ({list(matched_skills)[0]}) matches, remaining {len(norm_job_req)-1} core skills missing"

            if overlap_ratio < 0.20 and not has_role_word_match:
                return True, f"Very low skill overlap ({len(matched_skills)}/{len(norm_job_req)}) with no target role alignment"

        # ── RULE 3: Seniority & Experience Gap ────────────────────────────────
        # E.g. Candidate ~2 yrs vs Principal / Lead (8+ yrs)
        is_principal_lead = any(w in title_lower for w in ["principal", "director", "head of", "vp", "chief", "partner"])
        job_min_exp = getattr(job, "experience_min_years", None) or 0.0

        if is_principal_lead or job_min_exp >= 8.0:
            if cand_years_exp <= 3.5:
                return True, f"Seniority gap: Job requires {job_min_exp or '8+'} years / leadership, candidate profile reflects ~{cand_years_exp} years"

        return False, None


# ─────────────────────────────────────────────────────────────────────────────
# 3. FIVE-DIMENSION WEIGHTED MATCH SCORER
# ─────────────────────────────────────────────────────────────────────────────

class JobMatchScorer:
    """
    Computes weighted job recommendation score (0 - 100):
    - Target Role Match: 35%
    - Required Skill Match: 30%
    - Technical Stack Match: 15%
    - Experience Match: 10%
    - Responsibility Match: 10%
    """

    @classmethod
    def calculate_role_match(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> Tuple[float, str]:
        title_lower = (job.title or "").strip().lower()
        cat_lower = (job.role_category or "").strip().lower()
        cand_primary = (candidate_context.get("primary_designation") or "").strip().lower()
        cand_target_roles = [r.strip().lower() for r in (candidate_context.get("target_roles") or []) if r]

        # 1. Exact primary designation match
        if cand_primary and (cand_primary in title_lower or title_lower in cand_primary):
            return 100.0, f"Exact primary designation match: {cand_primary.title()}"

        # 2. Exact match with any target role
        for tr in cand_target_roles:
            if tr in title_lower or title_lower in tr:
                return 95.0, f"Exact target role match: {tr.title()}"

        # 3. Closely aligned target role keywords
        # e.g., "Generative AI", "Machine Learning", "NLP", "RAG", "Deep Learning", "Data Scientist"
        matched_roles = []
        for tr in [cand_primary] + cand_target_roles:
            if not tr:
                continue
            words = [w for w in tr.split() if len(w) > 2 and w not in ["and", "the", "for", "with"]]
            if any(w in title_lower or w in cat_lower for w in words):
                matched_roles.append(tr.title())

        if matched_roles:
            score = 88.0 if len(matched_roles) >= 2 else 80.0
            return score, f"Target role alignment: {matched_roles[0]}"

        # 4. Domain / Sub-category alignment
        domain = candidate_context.get("domain", "")
        if domain and domain.lower() in cat_lower:
            return 60.0, f"Domain alignment: {cat_lower.title()}"

        return 20.0, "Weak role alignment"

    @classmethod
    def calculate_required_skill_match(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> Tuple[float, List[str], List[str]]:
        cand_skills_norm = candidate_context.get("skills_norm", set())
        job_req_raw = job.required_skills or []
        if not isinstance(job_req_raw, list):
            job_req_raw = []

        if not job_req_raw:
            # If job didn't specify required_skills, infer from description
            return 70.0, [], []

        matched_names: List[str] = []
        missing_names: List[str] = []

        for skill in job_req_raw:
            norm = SkillNormalizer.normalize(skill)
            if norm in cand_skills_norm:
                matched_names.append(skill)
            else:
                missing_names.append(skill)

        ratio = len(matched_names) / max(len(job_req_raw), 1)
        score = round(min(100.0, ratio * 100.0), 1)
        return score, matched_names, missing_names

    @classmethod
    def calculate_tech_stack_match(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> Tuple[float, List[str]]:
        cand_skills_norm = candidate_context.get("skills_norm", set())
        job_pref_raw = job.preferred_skills or []
        if not isinstance(job_pref_raw, list):
            job_pref_raw = []

        matched_pref: List[str] = []
        for s in job_pref_raw:
            norm = SkillNormalizer.normalize(s)
            if norm in cand_skills_norm:
                matched_pref.append(s)

        if job_pref_raw:
            ratio = len(matched_pref) / len(job_pref_raw)
            score = round(min(100.0, 50.0 + ratio * 50.0), 1)
        else:
            # Complementary stack bonus if candidate has modern tools (Docker, Cloud, DB)
            stack_tools = {"docker", "git", "postgresql", "fastapi", "azure", "aws", "qdrant"}
            tool_overlap = len(stack_tools.intersection(cand_skills_norm))
            score = round(min(95.0, 65.0 + tool_overlap * 6.0), 1)

        return score, matched_pref

    @classmethod
    def calculate_experience_match(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> float:
        cand_exp = candidate_context.get("years_experience", 2.0)
        job_min = getattr(job, "experience_min_years", None)
        job_max = getattr(job, "experience_max_years", None)

        if job_min is None and job_max is None:
            return 85.0

        job_min = job_min or 0.0
        job_max = job_max or (job_min + 3.0)

        if job_min <= cand_exp <= job_max:
            return 100.0
        elif cand_exp >= job_min - 1.0 and cand_exp <= job_max + 1.5:
            return 85.0
        elif cand_exp >= job_min - 2.0:
            return 65.0
        else:
            diff = abs(cand_exp - job_min)
            return max(15.0, 60.0 - diff * 12.0)

    @classmethod
    def calculate_responsibility_match(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> float:
        # Check alignment between candidate's past responsibilities and job description
        cand_resps = candidate_context.get("responsibilities", [])
        job_desc = (job.description or "").lower()

        if not job_desc or not cand_resps:
            return 75.0

        key_action_stems = [
            "develop", "build", "design", "deploy", "implement", "train", "evaluat",
            "fine-tun", "rag", "pipeline", "api", "optim", "model", "architect"
        ]

        cand_stems = set()
        for r in cand_resps:
            r_low = r.lower()
            for stem in key_action_stems:
                if stem in r_low:
                    cand_stems.add(stem)

        job_stems = set()
        for stem in key_action_stems:
            if stem in job_desc:
                job_stems.add(stem)

        if not job_stems:
            return 75.0

        overlap = len(cand_stems.intersection(job_stems))
        ratio = overlap / len(job_stems)
        return round(min(98.0, max(50.0, 50.0 + ratio * 48.0)), 1)

    @classmethod
    def score_job(
        cls,
        candidate_context: Dict[str, Any],
        job: Job,
    ) -> Dict[str, Any]:
        """
        Calculates all 5 weighted components and determines recommendation status.
        """
        # Hard rejection check
        is_rejected, reject_reason = HardRejectionFilter.evaluate(candidate_context, job)
        if is_rejected:
            return {
                "is_recommended": False,
                "overall_score": 20.0,
                "role_match": 15.0,
                "skill_match": 10.0,
                "experience_match": 20.0,
                "responsibility_match": 20.0,
                "matched_skills": [],
                "missing_skills": job.required_skills or [],
                "recommendation_reason": reject_reason or "Does not meet candidate criteria",
                "is_hard_rejected": True,
                "rejection_reason": reject_reason,
            }

        # 1. Target Role Match (35%)
        role_score, role_reason = cls.calculate_role_match(candidate_context, job)

        # 2. Required Skill Match (30%)
        req_skill_score, matched_skills, missing_skills = cls.calculate_required_skill_match(candidate_context, job)

        # 3. Technical Stack Match (15%)
        tech_score, matched_pref = cls.calculate_tech_stack_match(candidate_context, job)

        # 4. Experience Match (10%)
        exp_score = cls.calculate_experience_match(candidate_context, job)

        # 5. Responsibility Match (10%)
        resp_score = cls.calculate_responsibility_match(candidate_context, job)

        # Composite Score (Total = 100)
        overall_score = round(
            0.35 * role_score +
            0.30 * req_skill_score +
            0.15 * tech_score +
            0.10 * exp_score +
            0.10 * resp_score,
            1
        )

        is_recommended = (overall_score >= 65.0)

        # Construct informative, truthful reason
        cand_primary = candidate_context.get("primary_designation", "profile")
        if is_recommended:
            if matched_skills:
                rec_reason = f"Strong match for your {cand_primary} background and skills ({', '.join(matched_skills[:3])})."
            else:
                rec_reason = f"High alignment with your target role as {cand_primary}."
        else:
            rec_reason = f"Match score {overall_score}% is below the 65% recommendation threshold."

        return {
            "is_recommended": is_recommended,
            "overall_score": overall_score,
            "role_match": role_score,
            "skill_match": req_skill_score,
            "technical_stack_match": tech_score,
            "experience_match": exp_score,
            "responsibility_match": resp_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills[:4],
            "recommendation_reason": rec_reason,
            "is_hard_rejected": False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. RECOMMENDATION ENGINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class JobRecommendationEngine:
    """
    Two-stage production recommendation pipeline with candidate isolation.
    """

    @classmethod
    def extract_candidate_context(cls, db: Session, candidate_id: int) -> Dict[str, Any]:
        """
        Extracts verified candidate profile context exclusively from the candidate's
        single active master resume.
        """
        profile_data = ActiveResumeRAGService.get_exact_profile(db, candidate_id)
        if not profile_data or profile_data.get("error"):
            # Fallback to candidate row if no resume
            cand = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            if not cand:
                return {}
            all_skills = [s.strip() for s in (cand.skills or "").split(",") if s.strip()]
            return {
                "candidate_id": candidate_id,
                "primary_designation": cand.primary_designation or "Candidate",
                "target_roles": [cand.primary_designation] if cand.primary_designation else [],
                "all_skills": all_skills,
                "skills_norm": SkillNormalizer.normalize_set(all_skills),
                "years_experience": 2.0,
                "responsibilities": [],
            }

        # Calculate total years of experience
        exps = profile_data.get("experience", [])
        total_months = 0
        all_resps = []
        for e in exps:
            all_resps.extend(e.get("responsibilities", []))
            # Default ~12 months per entry if dates not parsed
            total_months += 12
        years_exp = max(1.0, round(total_months / 12.0, 1))

        all_skills = profile_data.get("all_skills", [])
        skills_norm = SkillNormalizer.normalize_set(all_skills)

        return {
            "candidate_id": candidate_id,
            "active_resume_id": profile_data.get("active_resume_id"),
            "primary_designation": profile_data.get("primary_designation") or "Candidate",
            "target_roles": profile_data.get("target_roles", []) or [],
            "all_skills": all_skills,
            "skills_norm": skills_norm,
            "years_experience": years_exp,
            "responsibilities": all_resps,
        }

    @classmethod
    def get_recommended_jobs(
        cls,
        db: Session,
        candidate_id: int,
        limit: int = 50,
        persist_matches: bool = True,
    ) -> Dict[str, Any]:
        """
        Two-stage recommendation pipeline:
        Stage 1: Check candidate-scoped Redis cache for instant sub-5ms response.
        Stage 2: Strictly filter, score against candidate context, enforce threshold >= 65.
        Returns validated recommended jobs with match breakdown.
        """
        from app.services.resume_cache import (
            get_cached_job_recommendations,
            set_cached_job_recommendations,
            get_candidate_context_revision,
        )

        cached = get_cached_job_recommendations(candidate_id, limit=limit)
        if cached:
            return cached

        context = cls.extract_candidate_context(db, candidate_id)
        if not context:
            return {
                "jobs": [],
                "total": 0,
                "candidate_context": {
                    "primary_designation": "",
                    "target_roles": [],
                },
            }

        active_jobs = db.query(Job).filter(Job.is_active == True).all()

        recommended_list = []
        all_scored_matches = []

        for job in active_jobs:
            score_data = JobMatchScorer.score_job(context, job)

            match_entry = {
                "job": job,
                "score_data": score_data,
            }
            all_scored_matches.append(match_entry)

            if score_data["is_recommended"]:
                recommended_list.append(match_entry)

        # Sort recommended jobs by overall_score descending
        recommended_list.sort(key=lambda x: x["score_data"]["overall_score"], reverse=True)
        recommended_list = recommended_list[:limit]

        # Persist / Synchronize to Match table if requested
        if persist_matches:
            cls._sync_matches_to_db(db, candidate_id, all_scored_matches)

        formatted_jobs = []
        for item in recommended_list:
            job = item["job"]
            s = item["score_data"]
            formatted_jobs.append({
                "id": job.id,
                "title": job.title,
                "company": job.company_name,
                "location": job.location or ("Remote" if job.is_remote else "On-site"),
                "employment_type": job.employment_type or "Full-time",
                "salary": job.salary_raw or (f"${job.salary_min}k - ${job.salary_max}k" if job.salary_min else None),
                "description": job.description_summary or job.description,
                "required_skills": job.required_skills or [],
                "match_score": s["overall_score"],
                "role_match": s["role_match"],
                "skill_match": s["skill_match"],
                "experience_match": s["experience_match"],
                "responsibility_match": s["responsibility_match"],
                "matched_skills": s["matched_skills"],
                "missing_skills": s["missing_skills"],
                "recommendation_reason": s["recommendation_reason"],
                "application_url": job.apply_url or job.job_url,
                "posted_date": job.posted_at.isoformat() if job.posted_at else None,
                "role_category": job.role_category,
                "industry": job.industry,
            })

        result = {
            "jobs": formatted_jobs,
            "total": len(formatted_jobs),
            "candidate_context": {
                "candidate_id": candidate_id,
                "primary_designation": context["primary_designation"],
                "target_roles": context["target_roles"],
                "verified_skills_count": len(context["all_skills"]),
            },
        }

        # Cache with candidate context revision
        current_rev = get_candidate_context_revision(candidate_id)
        set_cached_job_recommendations(candidate_id, limit, current_rev, result)

        return result

    @classmethod
    def _sync_matches_to_db(
        cls,
        db: Session,
        candidate_id: int,
        scored_matches: List[Dict[str, Any]],
    ):
        """
        Updates the Match table records so overall_score, match_reasons, and missing_skills
        stay 100% in sync with the recommendation engine.
        """
        try:
            existing_matches = {
                m.job_id: m for m in db.query(Match).filter(Match.candidate_id == candidate_id).all()
            }

            for item in scored_matches:
                job = item["job"]
                s = item["score_data"]
                score = s["overall_score"]
                reasons = [s["recommendation_reason"]]
                if s["matched_skills"]:
                    reasons.append(f"Matches skills: {', '.join(s['matched_skills'][:3])}")

                m = existing_matches.get(job.id)
                if m:
                    m.overall_score = score
                    m.skill_score = s["skill_match"]
                    m.experience_score = s["experience_match"]
                    m.match_reasons = reasons
                    m.missing_skills = s["missing_skills"]
                    m.match_explanation = s["recommendation_reason"]
                else:
                    new_m = Match(
                        candidate_id=candidate_id,
                        job_id=job.id,
                        overall_score=score,
                        skill_score=s["skill_match"],
                        experience_score=s["experience_match"],
                        location_score=85.0 if job.is_remote else 70.0,
                        match_reasons=reasons,
                        missing_skills=s["missing_skills"],
                        match_explanation=s["recommendation_reason"],
                        status="new",
                    )
                    db.add(new_m)

            db.commit()
        except Exception as e:
            logger.warning(f"Error syncing matches to DB for candidate {candidate_id}: {e}")
            db.rollback()

    @classmethod
    def invalidate_and_recalculate(cls, candidate_id: int, db: Session):
        """
        Wipes candidate's old recommendation matches and recalculates freshly
        against active jobs using their new active resume context.
        """
        try:
            logger.info(f"Invalidating and recalculating recommendations for candidate {candidate_id}")
            db.query(Match).filter(Match.candidate_id == candidate_id).delete(synchronize_session=False)
            db.commit()
            return cls.get_recommended_jobs(db, candidate_id, persist_matches=True)
        except Exception as e:
            logger.error(f"Failed to invalidate/recalculate for candidate {candidate_id}: {e}")
            db.rollback()
            return None
