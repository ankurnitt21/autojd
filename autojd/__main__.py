"""
AutoJD - Automatically tailor your resume to any job description.

Usage:
    python -m autojd <JD_URL> <COMPANY_NAME> [--api-key KEY]

Environment:
    OPENAI_API_KEY - OpenAI API key (or pass via --api-key)
"""

import argparse
import os
import sys

from autojd.fetcher import fetch_jd
from autojd.modifier import modify_resume
from autojd.pdf_builder import compile_and_fit
from autojd.storage import company_exists, save_resume, update_tracker


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resume_template(base_dir: str, use_second: bool) -> str:
    """Read the appropriate resume template."""
    filename = "resume2.tex" if use_second else "resume.tex"
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Resume template not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def run(url: str, company: str, api_key: str | None = None):
    """Main pipeline: fetch JD -> modify resume -> build PDF -> save & track."""
    base_dir = BASE_DIR

    # Check if company already exists (use resume2.tex in that case)
    is_second = company_exists(company, base_dir)
    if is_second:
        print(f"[*] Company '{company}' already exists. Using resume2.tex for second version.")
    else:
        print(f"[*] New company '{company}'. Using resume.tex.")

    # Step 1: Fetch JD
    jd_text = fetch_jd(url)
    print(f"\n{'='*60}")
    print("JD Preview (first 500 chars):")
    print(jd_text)
    print(f"{'='*60}\n")

    # Step 2: Read resume template
    resume_tex = get_resume_template(base_dir, is_second)

    # Step 3: Modify resume with OpenAI
    tailored_tex = modify_resume(jd_text, resume_tex, api_key=api_key)

    # Step 4: Compile to PDF and ensure 1 page
    final_tex, pdf_path = compile_and_fit(tailored_tex)

    # Step 5: Save to resume/{company}/
    result = save_resume(company, final_tex, pdf_path, base_dir, is_second=is_second)

    # Step 6: Update tracker.xlsx
    update_tracker(company, url, result["pdf_path"], base_dir, is_second=is_second)

    print(f"\n{'='*60}")
    print(f"[✓] Done! Resume saved to: {result['company_dir']}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="AutoJD - Tailor your resume to any job description",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python -m autojd "https://jobs.example.com/12345" "Google"\n'
            '  python -m autojd "https://boards.greenhouse.io/..." "Meta" --api-key sk-...\n'
        ),
    )
    parser.add_argument("url", help="URL of the job posting")
    parser.add_argument("company", help="Company name (used for folder naming)")
    parser.add_argument("--api-key", help="OpenAI API key (or set OPENAI_API_KEY env var)")

    args = parser.parse_args()
    run(args.url, args.company, api_key=args.api_key)


if __name__ == "__main__":
    main()
