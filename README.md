# AutoJD - Automatic Resume Tailor

Automatically tailor your resume to any job description URL.

## What it does

1. **Fetches JD** from any URL (static HTML, JS-rendered pages, JSON APIs)
2. **Tailors your resume** using OpenAI - modifies Summary, Skills (2 categories), Work Experience
3. **Compiles to PDF** using pdflatex - automatically adjusts to fit 1 page
4. **Organizes files** in `resume/{company}/` folders
5. **Tracks everything** in `tracker.xlsx`
6. **Handles duplicates** - if same company exists, uses `resume2.tex` and adds a second column

## Prerequisites

- **Python 3.10+**
- **pdflatex** (install [MiKTeX](https://miktex.org/) on Windows or TeX Live on Linux)
- **OpenAI API key**

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

Set your OpenAI API key:

```bash
# Create a .env file in project root
OPENAI_API_KEY=sk-...

# Optional: if pdflatex is not on PATH, set full executable path
# Windows example:
PDFLATEX_PATH=C:\\Program Files\\MiKTeX\\miktex\\bin\\x64\\pdflatex.exe
```

## Usage

```bash
python -m autojd "<JD_URL>" "<COMPANY_NAME>"
```

### Examples

```bash
# First application to Google
python -m autojd "https://careers.google.com/jobs/123" "Google"

# Second application to Google (auto-uses resume2.tex)
python -m autojd "https://careers.google.com/jobs/456" "Google"

# With explicit API key
python -m autojd "https://jobs.lever.co/..." "Meta" --api-key sk-...
```

## Output Structure

```
resume/
  Google/
    resume.pdf        # First tailored resume
    resume.tex
    resume_v2.pdf     # Second tailored resume (if applied again)
    resume_v2.tex
tracker.xlsx          # Master tracking spreadsheet
```

## Tracker Excel Columns

| Company | JD URL      | Resume Path              | Date       | Resume2 Path                |
| ------- | ----------- | ------------------------ | ---------- | --------------------------- |
| Google  | https://... | resume/Google/resume.pdf | 2026-03-11 | resume/Google/resume_v2.pdf |



Preview first:
py -m autojd --batch-file sample_jobs.txt --dry-run
Then run:
py -m autojd --batch-file sample_jobs.txt