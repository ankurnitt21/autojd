"""
Compile .tex to PDF and ensure it fits on 1 page.
Adjusts margins, font size, spacing if it overflows to 2 pages.
"""

import os
import re
import shutil
import subprocess
import tempfile


def _get_page_count(pdf_path: str) -> int:
    """Get page count from a PDF file by reading its binary content."""
    with open(pdf_path, "rb") as f:
        content = f.read()
    # Simple regex to count /Type /Page (not /Pages)
    count = len(re.findall(rb"/Type\s*/Page(?!s)", content))
    return max(count, 1)


def _compile_tex(tex_content: str, work_dir: str) -> str | None:
    """Compile LaTeX and return path to PDF, or None on failure."""
    tex_path = os.path.join(work_dir, "resume.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex_content)

    try:
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        pdf_path = os.path.join(work_dir, "resume.pdf")
        if os.path.exists(pdf_path):
            return pdf_path
        print(f"[!] pdflatex stderr:\n{result.stdout[-2000:]}")
        return None
    except FileNotFoundError:
        raise RuntimeError(
            "pdflatex not found. Please install a LaTeX distribution "
            "(e.g., MiKTeX on Windows or TeX Live on Linux)."
        )
    except subprocess.TimeoutExpired:
        print("[!] pdflatex timed out")
        return None


# Ordered list of adjustments to try to fit on 1 page.
# Each is a (description, find_pattern, replace_with) or a callable.
ADJUSTMENTS = [
    # 1. Reduce top margin
    {
        "desc": "Reduce top margin to 10mm",
        "find": r"top=\d+mm",
        "replace": "top=10mm",
    },
    # 2. Reduce bottom margin
    {
        "desc": "Reduce bottom margin to 6mm",
        "find": r"bottom=\d+mm",
        "replace": "bottom=6mm",
    },
    # 3. Reduce left/right margins
    {
        "desc": "Reduce left margin to 12mm",
        "find": r"left=\d+mm",
        "replace": "left=12mm",
    },
    {
        "desc": "Reduce right margin to 12mm",
        "find": r"right=\d+mm",
        "replace": "right=12mm",
    },
    # 4. Reduce font size
    {
        "desc": "Reduce font to 11pt",
        "find": r"\\documentclass\[\d+\.?\d*pt",
        "replace": r"\\documentclass[11pt",
    },
    # 5. Reduce section spacing
    {
        "desc": "Reduce section title spacing",
        "find": r"\\titlespacing\{\\section\}\{0pt\}\{\d+pt\}\{\d+pt\}",
        "replace": r"\\titlespacing{\\section}{0pt}{6pt}{3pt}",
    },
    # 6. Reduce vspace throughout
    {
        "desc": "Reduce \\vspace{8pt} to 4pt",
        "find": r"\\vspace\{8pt\}",
        "replace": r"\\vspace{4pt}",
    },
    {
        "desc": "Reduce \\vspace{6pt} to 3pt",
        "find": r"\\vspace\{6pt\}",
        "replace": r"\\vspace{3pt}",
    },
    {
        "desc": "Reduce \\vspace{5pt} to 2pt",
        "find": r"\\vspace\{5pt\}",
        "replace": r"\\vspace{2pt}",
    },
    # 7. Reduce header spacing
    {
        "desc": "Reduce header name spacing",
        "find": r"\\\\\[7pt\]",
        "replace": r"\\\\[4pt]",
    },
    # 8. Further reduce font
    {
        "desc": "Reduce font to 10.5pt",
        "find": r"\\documentclass\[\d+\.?\d*pt",
        "replace": r"\\documentclass[10.5pt",
    },
    # 9. Tighten itemize
    {
        "desc": "Tighten itemize spacing",
        "find": r"topsep=\d+pt",
        "replace": "topsep=0pt",
    },
    # 10. Reduce all remaining vspaces
    {
        "desc": "Reduce \\vspace{4pt} to 2pt",
        "find": r"\\vspace\{4pt\}",
        "replace": r"\\vspace{2pt}",
    },
    {
        "desc": "Reduce \\vspace{3pt} to 1pt",
        "find": r"\\vspace\{3pt\}",
        "replace": r"\\vspace{1pt}",
    },
    # 11. Even smaller top margin
    {
        "desc": "Reduce top margin to 8mm",
        "find": r"top=\d+mm",
        "replace": "top=8mm",
    },
    # 12. Even smaller font
    {
        "desc": "Reduce font to 10pt",
        "find": r"\\documentclass\[\d+\.?\d*pt",
        "replace": r"\\documentclass[10pt",
    },
    # 13. Further reduce left/right margins
    {
        "desc": "Reduce left margin to 10mm",
        "find": r"left=\d+mm",
        "replace": "left=10mm",
    },
    {
        "desc": "Reduce right margin to 10mm",
        "find": r"right=\d+mm",
        "replace": "right=10mm",
    },
    # 14. Kill all remaining vspaces
    {
        "desc": "Remove \\vspace{2pt}",
        "find": r"\\vspace\{2pt\}",
        "replace": r"\\vspace{0pt}",
    },
    {
        "desc": "Remove \\vspace{1pt}",
        "find": r"\\vspace\{1pt\}",
        "replace": r"\\vspace{0pt}",
    },
    # 15. Reduce hrule vspace
    {
        "desc": "Reduce section rule vspace",
        "find": r"\\vspace\{1pt\}\\hrule\\vspace\{6pt\}",
        "replace": r"\\vspace{0pt}\\hrule\\vspace{2pt}",
    },
    # 16. Further reduce font to 9.5pt
    {
        "desc": "Reduce font to 9.5pt",
        "find": r"\\documentclass\[\d+\.?\d*pt",
        "replace": r"\\documentclass[9.5pt",
    },
    # 17. Minimal margins
    {
        "desc": "Reduce top margin to 6mm",
        "find": r"top=\d+mm",
        "replace": "top=6mm",
    },
    {
        "desc": "Reduce bottom margin to 4mm",
        "find": r"bottom=\d+mm",
        "replace": "bottom=4mm",
    },
]


def compile_and_fit(tex_content: str) -> tuple[str, str]:
    """
    Compile tex to PDF. If it's >1 page, iteratively adjust spacing/fonts/margins.
    Returns (final_tex_content, pdf_path).
    """
    work_dir = tempfile.mkdtemp(prefix="autojd_")
    current_tex = tex_content

    # First attempt
    pdf_path = _compile_tex(current_tex, work_dir)
    if pdf_path is None:
        raise RuntimeError("LaTeX compilation failed. Check the .tex for errors.")

    pages = _get_page_count(pdf_path)
    print(f"[*] Initial PDF: {pages} page(s)")

    if pages <= 1:
        return current_tex, pdf_path

    print("[*] Resume is >1 page. Applying adjustments to fit...")

    for adj in ADJUSTMENTS:
        current_tex = re.sub(adj["find"], adj["replace"], current_tex)
        # Recompile
        work_dir_new = tempfile.mkdtemp(prefix="autojd_")
        pdf_path_new = _compile_tex(current_tex, work_dir_new)
        if pdf_path_new is None:
            # This adjustment broke something, skip
            continue

        pages = _get_page_count(pdf_path_new)
        print(f"    {adj['desc']} -> {pages} page(s)")
        pdf_path = pdf_path_new
        work_dir = work_dir_new

        if pages <= 1:
            print("[+] Resume fits on 1 page!")
            return current_tex, pdf_path

    print("[!] Warning: Could not reduce to 1 page after all adjustments.")
    return current_tex, pdf_path
