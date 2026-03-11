"""
Use OpenAI to tailor a resume .tex file to a specific job description.
Modifies: Summary, Skills (2 categories only), Work Experience (\\textbf for bold keywords).
"""

import os
import re
from openai import OpenAI


SYSTEM_PROMPT = r"""You are an expert resume writer who tailors LaTeX resumes to match job descriptions.

You will receive:
1. A job description (JD)
2. A LaTeX resume

You must modify ONLY these sections of the resume:
- **Summary** (the paragraph right after the header, before \section*{SKILLS})
- **Skills** (keep EXACTLY 2 skill categories, each on its own line with \\[3pt] between them. Format: \textbf{Category} --- skill1, skill2, ...)
- **Work Experience bullet points** (rewrite bullets to align with JD keywords and requirements i want it to match the JD 100 percent. Use \textbf{...} to bold important keywords/technologies that match the JD)

RULES:
1. Do NOT change the header (name, email, phone, links).
2. Do NOT change project section, education section, or any dates/titles/company names.
3. Do NOT add or remove any jobs or projects. Keep the same number of bullet points per job.
4. Skills section must have EXACTLY 2 categories (lines). Pick the 2 most relevant groupings for the JD. Format exactly like:
   \textbf{Category1} --- item1, item2, item3\\[3pt]
   \textbf{Category2} --- item4, item5, item6
5. Summary should be 2-3 lines, tailored to the JD, highlighting relevant experience.
6. In experience bullets, use \textbf{keyword} to bold technologies/tools/metrics that match the JD.
7. Keep the LaTeX formatting EXACTLY as the original - same structure, same commands, same packages.
8. Return ONLY the complete LaTeX document, nothing else. No markdown code fences, no explanations.
9. The resume MUST fit on exactly 1 page. Keep content concise.
10. Make sure LaTeX compiles without errors. Escape special characters properly (%, &, #, $, _).
"""


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

    user_msg = (
        f"## Job Description:\n{jd_text}\n\n"
        f"## Current Resume LaTeX:\n{resume_tex}\n\n"
        "Modify the resume to match this JD following all the rules. "
        "Return ONLY the complete LaTeX document."
    )

    print("[*] Sending to OpenAI for resume tailoring...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    result = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if result.startswith("```"):
        result = re.sub(r"^```(?:latex|tex)?\s*\n?", "", result)
        result = re.sub(r"\n?```\s*$", "", result)

    # Validate it looks like a LaTeX document
    if r"\documentclass" not in result or r"\begin{document}" not in result:
        raise RuntimeError("OpenAI returned invalid LaTeX. Please retry.")

    print("[+] Received tailored resume from OpenAI")
    return result
