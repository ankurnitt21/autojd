"""
Compile .tex to PDF and ensure it fits on 1 page.
Adjusts margins, font size, spacing if it overflows to 2 pages.
"""

import os
import re
import shutil
import subprocess
import tempfile


def _resolve_pdflatex_cmd() -> list[str]:
    """Resolve a usable pdflatex executable, preferring env override."""
    # Allow explicit override in .env/system env.
    override = os.environ.get("PDFLATEX_PATH") or os.environ.get("LATEX_CMD")
    if override:
        return [override]

    # First, rely on PATH.
    in_path = shutil.which("pdflatex")
    if in_path:
        return [in_path]

    # Common Windows install paths for MiKTeX and TeX Live.
    candidates = [
        r"C:\\Program Files\\MiKTeX\\miktex\\bin\\x64\\pdflatex.exe",
        r"C:\\Program Files\\MiKTeX\\miktex\\bin\\pdflatex.exe",
        r"C:\\texlive\\2024\\bin\\windows\\pdflatex.exe",
        r"C:\\texlive\\2025\\bin\\windows\\pdflatex.exe",
        r"C:\\texlive\\2026\\bin\\windows\\pdflatex.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            return [exe]

    raise RuntimeError(
        "pdflatex not found. Install MiKTeX or TeX Live and ensure pdflatex is on PATH, "
        "or set PDFLATEX_PATH in .env to the full pdflatex executable path."
    )


def ensure_latex_available() -> None:
    """Fail fast if no LaTeX compiler is available."""
    _resolve_pdflatex_cmd()


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
        pdflatex_cmd = _resolve_pdflatex_cmd()
        timeout_s = int(os.environ.get("PDFLATEX_TIMEOUT", "240"))
        result = None

        # MiKTeX first run may need extra time for package/setup initialization.
        for attempt in range(2):
            try:
                this_timeout = timeout_s if attempt == 0 else timeout_s * 2
                result = subprocess.run(
                    [*pdflatex_cmd, "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=this_timeout,
                )
                break
            except subprocess.TimeoutExpired:
                if attempt == 1:
                    print(f"[!] pdflatex timed out after {this_timeout}s")
                    return None
                print(f"[*] pdflatex timed out after {this_timeout}s, retrying once...")

        pdf_path = os.path.join(work_dir, "resume.pdf")
        if os.path.exists(pdf_path):
            return pdf_path
        stderr_tail = (result.stderr or "")[-2000:] if result else ""
        stdout_tail = (result.stdout or "")[-1000:] if result else ""
        print(f"[!] pdflatex stderr:\n{stderr_tail}")
        if stdout_tail:
            print(f"[!] pdflatex stdout (tail):\n{stdout_tail}")
        return None
    except FileNotFoundError:
        raise RuntimeError(
            "pdflatex not found. Install MiKTeX or TeX Live and ensure pdflatex is on PATH, "
            "or set PDFLATEX_PATH in .env to the full pdflatex executable path."
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


# Ordered list of adjustments to make a sparse 1-page resume look fuller.
EXPAND_ADJUSTMENTS = [
    {
        "desc": "Increase font to 12.2pt",
        "find": r"\\documentclass\[\d+\.?\d*pt",
        "replace": r"\\documentclass[12.2pt",
    },
    {
        "desc": "Increase top margin to 16mm",
        "find": r"top=\d+mm",
        "replace": "top=16mm",
    },
    {
        "desc": "Increase bottom margin to 12mm",
        "find": r"bottom=\d+mm",
        "replace": "bottom=12mm",
    },
    {
        "desc": "Increase left margin to 17mm",
        "find": r"left=\d+mm",
        "replace": "left=17mm",
    },
    {
        "desc": "Increase right margin to 17mm",
        "find": r"right=\d+mm",
        "replace": "right=17mm",
    },
    {
        "desc": "Increase section title spacing",
        "find": r"\\titlespacing\{\\section\}\{0pt\}\{\d+pt\}\{\d+pt\}",
        "replace": r"\\titlespacing{\\section}{0pt}{12pt}{6pt}",
    },
    {
        "desc": "Increase header name spacing",
        "find": r"\\\\\[\d+pt\]",
        "replace": r"\\\\[10pt]",
    },
    {
        "desc": "Increase vspace 8pt to 10pt",
        "find": r"\\vspace\{8pt\}",
        "replace": r"\\vspace{10pt}",
    },
    {
        "desc": "Increase vspace 6pt to 8pt",
        "find": r"\\vspace\{6pt\}",
        "replace": r"\\vspace{8pt}",
    },
    {
        "desc": "Increase itemize topsep to 4pt",
        "find": r"topsep=\d+pt",
        "replace": "topsep=4pt",
    },
]


def _looks_sparse_layout(tex_content: str) -> bool:
    """Heuristic to detect likely excessive bottom whitespace on a one-page resume."""
    words = len(re.findall(r"\b\w+\b", tex_content))
    bullets = len(re.findall(r"\\item\s+", tex_content))
    # Conservative threshold so we do not expand already dense resumes.
    return words < 500 or bullets < 12


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
        if _looks_sparse_layout(current_tex):
            print("[*] Resume looks sparse. Applying expansion adjustments to reduce bottom emptiness...")
            for adj in EXPAND_ADJUSTMENTS:
                candidate_tex = re.sub(adj["find"], adj["replace"], current_tex)
                work_dir_new = tempfile.mkdtemp(prefix="autojd_")
                pdf_path_new = _compile_tex(candidate_tex, work_dir_new)
                if pdf_path_new is None:
                    continue

                candidate_pages = _get_page_count(pdf_path_new)
                print(f"    {adj['desc']} -> {candidate_pages} page(s)")
                if candidate_pages <= 1:
                    current_tex = candidate_tex
                    pdf_path = pdf_path_new
                else:
                    # Keep previous successful 1-page version.
                    continue
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
