# SSR Strategy Codex

A local-first dashboard for Semantic Similarity Rating (SSR) experiments that mirror the paper “LLMs Reproduce Human Purchase Intent via Semantic Similarity Elicitation of Likert Ratings.” Researchers and marketers can register personas and criteria, apply prompt templates, enqueue SSR tasks with operational context, and export JSON, PDF, and Codex session artifacts for reproducible analysis.

## Features
- **Shoelace-powered UI** with glassy panels, pill tags, and modern form controls.
- **Personas & criteria**: manage demographic personas and Likert-scale anchors, then attach them to tasks.
- **Prompt templates**: store evaluation prompts that can be injected per task.
- **Task queue**: enqueue SSR tasks with text/image stimuli, operational context, similarity strategy, and random seed.
- **Reports**: download PDF summaries, view persona-level aggregates, and export raw `~/.codex/session/...` files.
- **Benchmarks**: record human distributions, compute KS similarity, and show correlation attainment versus paper targets.
- **Live overview**: command bar to jump between flows plus live persona/template/task counters.

## Requirements
- Python 3.11+
- Local Codex CLI authentication (expects `~/.codex/auth.json` to exist). For testing, decode the `Codex_Auth_Json` secret and place it at `~/.codex/auth.json`.

## Setup
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Open `http://localhost:8000` in a browser. Use **Quick setup** to load sample personas, criteria, and templates.

## Usage tips
- Upload an image or provide a short description to enrich the stimulus text; both are sent to the SSR worker.
- Choose **Similarity strategy** (`tfidf` or `uniform`) and optionally fix a **Seed** for reproducibility.
- Download PDF reports or the raw session files for offline inspection and paper-aligned evaluation.

## Project structure
- `app/`: FastAPI application, models, jobs, evaluation, and PDF report generation.
- `static/`: JavaScript and CSS for the dashboard experience.
- `templates/`: Jinja2 templates for the HTML shell.
- `docs/`: Reference papers and supporting materials about SSR.
