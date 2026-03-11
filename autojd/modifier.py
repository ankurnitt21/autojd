"""
Use OpenAI to tailor a resume .tex file to a specific job description.
Modifies: Summary, Skills (2 categories only), Work Experience (\\textbf for bold keywords).
"""

import json
import os
import re
from datetime import datetime
from typing import Any
from openai import OpenAI


PLAN_PROMPT = r"""You are an expert resume writer.

You will receive:
1. A job description (JD)
2. A STRICT list of technologies extracted from JD
3. Existing work-experience structure (2 roles, exact bullet counts)

Your task:
- Create tailored content for ONLY these sections:
    1) Summary (2-3 lines, MUST explicitly mention 4.9 years of experience)
  2) Skills (EXACTLY 2 categories)
  3) Work Experience (2 roles)

CRITICAL SKILL-EXPERIENCE ALIGNMENT RULE:
Every single skill you list in the Skills section MUST be incorporated into at least one experience bullet.
Do NOT list a skill unless you plan to demonstrate it in a work experience bullet.

STRICT RULES:
1. Use ONLY technologies from the provided JD technology list in Skills and Experience.
2. Do NOT invent technologies not present in that list.
3. Skills must have EXACTLY 2 lines, format:
   - Category name (e.g., "Languages & Frameworks", "Tools & Platforms")
   - comma-separated items (typically 5-8 items per category)
4. For each of the 2 experience roles:
   - Provide a project_name (new title allowed)
   - Provide EXACT number of bullets requested for that role
    - Each bullet should naturally mention 2-4 technologies from the JD list
    - Each bullet MUST contain at least 13 words
   - Distribute ALL skills from your Skills section across the bullets
5. Keep bullets concise, action-oriented, and ATS-friendly.
6. Return JSON only (no markdown fences).

BEFORE FINALIZING YOUR RESPONSE:
- List all skills from category1 and category2
- For each skill, mentally verify it appears in at least one bullet
- If any skill is unused, either add it to a bullet or remove it from Skills
- Verify every bullet has at least 13 words
- Verify summary explicitly contains "4.9 years"
"""


KEYWORD_EXTRACT_PROMPT = r"""You extract technology/skill keywords from a job description.

Rules:
1. Return JSON only, with shape: {"technologies": ["..."]}
2. Include only technologies/skills explicitly present in the JD text.
3. Keep items concise (1-4 words), no duplicates.
4. Prefer concrete tech terms, tools, integration methods, protocols, and domain platforms.
5. Do not invent or infer missing technologies.
"""


LATEX_PROMPT = r"""You are an expert LaTeX resume editor.

You will receive:
1. The current resume LaTeX
2. A structured content plan JSON containing Summary, Skills, and Experience updates

Apply the plan to the LaTeX with STRICT rules:
1. Modify ONLY Summary, Skills, and Work Experience sections.
2. Keep header, projects, education, packages, and document structure unchanged.
3. Skills section must contain exactly 2 category lines with this format:
   \textbf{Category} --- item1, item2, item3\\[3pt]
   \textbf{Category2} --- item4, item5, item6
4. In Experience:
   - Keep same two jobs, same job titles/company names/dates unless project_name replacement is requested.
   - Replace the first bold label in each experience heading with provided project_name.
   - Keep exact bullet counts per role as provided in plan.
   - Use bullets exactly from plan.
5. Output valid LaTeX that compiles.
6. Return ONLY the complete LaTeX document (no markdown fences).
"""


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|latex|tex)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_jd_technologies(client: OpenAI, jd_text: str) -> list[str]:
    """Dynamically extract JD technologies, then strictly verify they exist in JD text."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": KEYWORD_EXTRACT_PROMPT},
            {"role": "user", "content": f"Extract technologies from this JD:\n\n{jd_text}"},
        ],
        temperature=0.0,
        max_tokens=1200,
    )

    raw = _strip_code_fences(response.choices[0].message.content.strip())
    data = json.loads(raw)
    techs = data.get("technologies", [])
    if not isinstance(techs, list):
        return []

    # Strict verification: keep only phrases that actually appear in JD text.
    jd_lower = jd_text.lower()
    cleaned: list[str] = []
    for item in techs:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if len(token) < 2:
            continue
        pattern = r"\b" + re.escape(token.lower()).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, jd_lower):
            cleaned.append(token)

    # Deduplicate preserving order.
    return list(dict.fromkeys(cleaned))


def _store_extracted_keywords(keywords: list[str]) -> str:
    """Persist latest extracted JD keywords to project root for traceability."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root_dir, "jd_keywords_latest.json")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(keywords),
        "keywords": keywords,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out_path


def _extract_experience_structure(resume_tex: str) -> list[dict[str, Any]]:
    """Extract two experience roles and their exact bullet counts."""
    m = re.search(
        r"\\section\*\{EXPERIENCE\}(.*?)(?:\\section\*\{PROJECTS\}|\\end\{document\})",
        resume_tex,
        re.S,
    )
    if not m:
        raise RuntimeError("Could not locate EXPERIENCE section in resume template.")

    exp_block = m.group(1)
    role_pattern = re.compile(
        r"\\noindent\s*\n"
        r"\\textbf\{(?P<project>[^}]+)\},\s*(?P<title>[^\\\n]+)\s*\\hfill\s*(?P<meta>[^\n]+)\n"
        r"\\begin\{itemize\}(?P<items>.*?)\\end\{itemize\}",
        re.S,
    )

    roles: list[dict[str, Any]] = []
    for match in role_pattern.finditer(exp_block):
        items_block = match.group("items")
        bullets = re.findall(r"\\item\s+", items_block)
        roles.append(
            {
                "project": match.group("project").strip(),
                "title": match.group("title").strip(),
                "meta": match.group("meta").strip(),
                "bullet_count": len(bullets),
            }
        )

    if len(roles) < 2:
        raise RuntimeError("Expected 2 experience roles in template, but found fewer.")
    return roles[:2]


def _normalize_tech(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _extract_skills_from_latex(tex: str) -> list[str]:
    m = re.search(r"\\section\*\{SKILLS\}(.*?)(?:\\section\*\{|\\end\{document\})", tex, re.S)
    if not m:
        return []

    lines = re.findall(r"\\textbf\{[^}]+\}\s*---\s*(.*)", m.group(1))
    skills: list[str] = []
    for line in lines[:2]:
        clean = line.replace(r"\\[3pt]", "")
        for item in clean.split(","):
            token = item.strip().strip(".")
            if token:
                skills.append(token)
    return list(dict.fromkeys(skills))


def _extract_experience_section(tex: str) -> str:
    m = re.search(
        r"\\section\*\{EXPERIENCE\}(.*?)(?:\\section\*\{PROJECTS\}|\\end\{document\})",
        tex,
        re.S,
    )
    return m.group(1) if m else ""


def _replace_outside_bold(
    text: str, pattern: re.Pattern[str], max_count: int
) -> tuple[str, int]:
    """Replace keyword matches only in non-bold segments."""
    parts = re.split(r"(\\textbf\{[^{}]*\})", text)
    remaining = max_count
    replaced_total = 0
    for i, part in enumerate(parts):
        if remaining <= 0:
            break
        # Odd indices are captured bold blocks; skip them.
        if i % 2 == 1:
            continue

        replaced_here = 0

        def _wrap(match: re.Match[str]) -> str:
            nonlocal replaced_here
            if replaced_here >= remaining:
                return match.group(0)
            replaced_here += 1
            return r"\textbf{" + match.group(0) + "}"

        parts[i] = pattern.sub(_wrap, part)
        remaining -= replaced_here
        replaced_total += replaced_here

    return "".join(parts), replaced_total


def _bold_jd_keywords_in_experience(
    tex: str, keywords: list[str], max_per_keyword: int = 2
) -> tuple[str, dict[str, int]]:
    """Bold JD keywords in EXPERIENCE section, capped per keyword."""
    section_re = re.compile(
        r"(\\section\*\{EXPERIENCE\})(.*?)(\\section\*\{PROJECTS\}|\\end\{document\})",
        re.S,
    )
    m = section_re.search(tex)
    if not m:
        return tex, {}

    prefix, body, suffix = m.group(1), m.group(2), m.group(3)

    # Split into bullet and non-bullet blocks to enforce "different bullet points".
    blocks = re.split(r"(\\item\s+.*?(?=(?:\\item\s+|\\end\{itemize\})))", body, flags=re.S)
    bullet_block_indices = [
        i for i, b in enumerate(blocks) if b.lstrip().startswith(r"\item")
    ]

    counts: dict[str, int] = {}
    # Longer phrases first (e.g., "Workday Studio" before "Workday").
    sorted_keywords = sorted(
        [k.strip() for k in keywords if k and k.strip()], key=len, reverse=True
    )

    for kw in sorted_keywords:
        pattern = re.compile(
            r"\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b",
            re.I,
        )
        replaced = 0
        # Ensure each keyword gets bolded in different bullet points.
        for block_idx in bullet_block_indices:
            if replaced >= max_per_keyword:
                break
            updated_block, hit = _replace_outside_bold(blocks[block_idx], pattern, 1)
            if hit > 0:
                blocks[block_idx] = updated_block
                replaced += hit
        counts[kw] = replaced

    body = "".join(blocks)

    updated = tex[: m.start()] + prefix + body + suffix + tex[m.end() :]
    return updated, counts


def _skills_are_jd_only(plan: dict[str, Any], jd_tech: list[str]) -> bool:
    allowed = {_normalize_tech(x) for x in jd_tech}
    skills = plan.get("skills", {})
    for key in ("category1", "category2"):
        cat = skills.get(key, {})
        items = cat.get("items", [])
        for item in items:
            if _normalize_tech(item) not in allowed:
                return False
    return True


def _verify_skills_in_plan_bullets(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check if all skills from Skills section appear in Experience bullets."""
    skills = plan.get("skills", {})
    all_skills: list[str] = []
    for key in ("category1", "category2"):
        cat = skills.get(key, {})
        all_skills.extend(cat.get("items", []))
    
    exp = plan.get("experience", [])
    all_bullets = []
    for role in exp:
        all_bullets.extend(role.get("bullets", []))
    
    bullets_text = " ".join(all_bullets).lower()
    missing: list[str] = []
    for skill in all_skills:
        if skill.lower() not in bullets_text:
            missing.append(skill)
    
    return len(missing) == 0, missing


def _validate_summary_and_bullet_length(plan: dict[str, Any]) -> tuple[bool, str]:
    """Require summary to mention 4.9 years and every bullet to be >=13 words."""
    summary = str(plan.get("summary", ""))
    if "4.9" not in summary:
        return False, "Summary must explicitly mention 4.9 years of experience."

    exp = plan.get("experience", [])
    for role_idx, role in enumerate(exp, start=1):
        for bullet_idx, bullet in enumerate(role.get("bullets", []), start=1):
            word_count = len(re.findall(r"\b\w+\b", bullet))
            if word_count < 13:
                return (
                    False,
                    f"Role {role_idx}, bullet {bullet_idx} has {word_count} words; must be >=13 words.",
                )
    return True, ""


def _parse_plan_json(raw: str, expected_roles: list[dict[str, Any]]) -> dict[str, Any]:
    data = json.loads(_strip_code_fences(raw))
    if "summary" not in data or "skills" not in data or "experience" not in data:
        raise RuntimeError("Plan JSON missing required keys.")

    exp = data["experience"]
    if not isinstance(exp, list) or len(exp) != 2:
        raise RuntimeError("Plan JSON must contain exactly 2 experience entries.")

    for i, role in enumerate(exp):
        bullets = role.get("bullets", [])
        expected = expected_roles[i]["bullet_count"]
        if len(bullets) != expected:
            raise RuntimeError(
                f"Plan role {i + 1} bullet count mismatch. Expected {expected}, got {len(bullets)}."
            )
    return data

def modify_resume(jd_text: str, resume_tex: str, api_key: str | None = None) -> str:
    """
    Send JD + resume to OpenAI and get back a tailored .tex file.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key param."
        )

    client = OpenAI(api_key=key)

    jd_tech = _extract_jd_technologies(client, jd_text)
    if len(jd_tech) < 5:
        raise RuntimeError(
            "Could not extract enough JD technologies. Please use a JD with clear technical skills/requirements."
        )

    keywords_path = _store_extracted_keywords(jd_tech)
    print(f"[*] Stored extracted JD keywords: {keywords_path}")

    roles = _extract_experience_structure(resume_tex)

    print("[*] Step 1/3: Extracted strict JD technologies")
    print(f"[*] JD technologies: {', '.join(jd_tech)}")

    print("[*] Step 2/3: Generating structured skills + experience plan...")
    plan_user_msg = (
        f"JD:\n{jd_text}\n\n"
        f"STRICT JD TECHNOLOGIES (use only these):\n{json.dumps(jd_tech, ensure_ascii=True)}\n\n"
        f"EXPERIENCE STRUCTURE (exact bullets required):\n{json.dumps(roles, ensure_ascii=True)}\n\n"
        "Return JSON in this shape exactly:\n"
        "{\n"
        '  "summary": "...",\n'
        '  "skills": {\n'
        '    "category1": {"name": "...", "items": ["...", "..."]},\n'
        '    "category2": {"name": "...", "items": ["...", "..."]}\n'
        "  },\n"
        '  "experience": [\n'
        '    {"project_name": "...", "bullets": ["...", "..."]},\n'
        '    {"project_name": "...", "bullets": ["...", "..."]}\n'
        "  ]\n"
        "}\n\n"
        "REMINDER: Every skill you put in 'skills' MUST appear in at least one bullet in 'experience'. "
        "Every bullet must be >=13 words. Summary must include '4.9 years'."
    )

    plan_data: dict[str, Any] | None = None
    for attempt in range(5):  # Increased attempts
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PLAN_PROMPT},
                {"role": "user", "content": plan_user_msg},
            ],
            temperature=0.2 + attempt * 0.1,
            max_tokens=4096,
        )
        raw = response.choices[0].message.content.strip()
        try:
            candidate = _parse_plan_json(raw, roles)
            if not _skills_are_jd_only(candidate, jd_tech):
                raise RuntimeError("Skills include non-JD technologies.")
            
            # NEW: Verify skills appear in bullets in the PLAN itself
            skills_in_bullets, missing_from_bullets = _verify_skills_in_plan_bullets(candidate)
            if not skills_in_bullets:
                print(f"[!] Attempt {attempt + 1}: Skills missing from bullets: {', '.join(missing_from_bullets)}")
                if attempt < 4:
                    plan_user_msg = (
                        f"{plan_user_msg}\n\n"
                        f"CORRECTION: These skills are in your Skills section but NOT in any experience bullet: "
                        f"{', '.join(missing_from_bullets)}. Either add them to bullets or remove them from Skills."
                    )
                    continue
                else:
                    raise RuntimeError(f"Plan has skills not used in bullets: {', '.join(missing_from_bullets)}")

            format_ok, format_err = _validate_summary_and_bullet_length(candidate)
            if not format_ok:
                print(f"[!] Attempt {attempt + 1}: {format_err}")
                if attempt < 4:
                    plan_user_msg = (
                        f"{plan_user_msg}\n\n"
                        f"CORRECTION: {format_err} Regenerate full JSON and satisfy all constraints."
                    )
                    continue
                raise RuntimeError(format_err)
            
            plan_data = candidate
            print("[+] Plan validated: all skills present in experience bullets")
            break
        except Exception as exc:
            print(f"[!] Attempt {attempt + 1} failed: {exc}")
            if attempt == 4:
                raise RuntimeError(f"Failed to build strict plan from JD: {exc}")

    if plan_data is None:
        raise RuntimeError("Failed to generate structured plan.")

    print("[*] Step 3/3: Rendering final LaTeX from structured plan...")
    render_user_msg = (
        f"CURRENT RESUME LATEX:\n{resume_tex}\n\n"
        f"STRUCTURED PLAN JSON:\n{json.dumps(plan_data, ensure_ascii=True)}\n\n"
        "Return ONLY full updated LaTeX."
    )

    result = ""
    for attempt in range(5):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": LATEX_PROMPT},
                {"role": "user", "content": render_user_msg},
            ],
            temperature=0.2 + attempt * 0.1,
            max_tokens=4096,
        )
        result = _strip_code_fences(response.choices[0].message.content.strip())
        is_latex = r"\documentclass" in result and r"\begin{document}" in result
        if is_latex:
            break
        if attempt == 4:
            raise RuntimeError("OpenAI returned invalid LaTeX after retries.")

    # Deterministic post-processing: bold extracted JD keywords in EXPERIENCE (max 2 each).
    max_bold_per_keyword = int(os.environ.get("BOLD_MAX_PER_KEYWORD", "2"))
    result, bold_map = _bold_jd_keywords_in_experience(
        result, jd_tech, max_per_keyword=max_bold_per_keyword
    )
    print(
        f"[*] Applied deterministic bolding (max {max_bold_per_keyword} per keyword) in EXPERIENCE"
    )
    used = {k: v for k, v in bold_map.items() if v > 0}
    if used:
        print("[*] Bold usage map: " + ", ".join(f"{k}:{v}" for k, v in used.items()))

    # Validate it looks like a LaTeX document
    if r"\documentclass" not in result or r"\begin{document}" not in result:
        raise RuntimeError("OpenAI returned invalid LaTeX. Please retry.")

    print("[+] Resume tailoring complete!")
    return result