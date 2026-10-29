# AIVOA.AI — Root Cause Investigation module

This build follows the interaction pattern in the supplied AIVOA Copilot demo: a focused investigation form on the left and a persistent AI copilot on the right. The user pastes an incident narrative/email into the copilot or attaches a source document; the assistant extracts the intake and populates editable fields; the investigator reviews the source, requests an RCA draft, evaluates evidence gaps and CAPA suggestions, then saves to the local QMS ledger.

The reference video is a Customer Complaint flow. This implementation adapts its interaction pattern to pharmaceutical API deviation/RCA work; it does **not** implement the complaint module.

## Run in VS Code

### Frontend

```bash
npm install
npm run dev
```

### Backend (for document parsing, database persistence and LangGraph)

Open another terminal in the project root:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Vite proxies `/api` to `http://127.0.0.1:8000`. When the frontend and backend are both running, use **Try a sample OOS incident** in the Copilot, then **Generate five whys & CAPA** and **Commit investigation to QMS ledger**. The front end also has a deterministic safe fallback for pasted text if the API is unavailable; file upload and persistence require the backend.

API documentation: `http://localhost:8000/docs`.

## Optional Groq model

Create a local `.env` (do not commit it) or export variables in your terminal:

```bash
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=sqlite:///./backend/aivoa_rca.db
```

Install `python-dotenv` if you prefer Uvicorn to load `.env`; otherwise export the variables in the shell before starting the backend. Without a key, LangGraph still runs the local evidence-safe workflow. Supported Groq model names depend on current Groq availability.

For PostgreSQL, set a SQLAlchemy URL such as `postgresql+psycopg://user:password@localhost:5432/aivoa_rca` and install `psycopg[binary]`. SQLite is the zero-setup default. The database file is ignored by Git.

## Video-pattern flow

1. Start from **Log Root Cause Investigation**. The Copilot explains that an email, deviation report, or attachment can be supplied.
2. Paste an incident narrative in the Copilot and press Enter / Send, or choose **Try a sample OOS incident**. Upload a PDF, DOCX, TXT, or EML with the backend running.
3. The assistant acknowledges extraction and fills product, batch, department, event summary, containment, impact, evidence and missing-evidence fields. Check and edit fields against the displayed source status.
4. Select **Generate five whys & CAPA**. Review the clear hypothesis-only warning, undetermined cause, evidence checklist, five whys and action recommendations.
5. Edit the form and action owners/dates. Save the draft or **Commit investigation to QMS ledger**. **Saved investigations** reads records from the API database.

PDF/DOCX extraction uses pypdf/python-docx. Scanned PDFs require OCR before upload. EML and plain text are decoded as UTF-8.

## Architecture

- **Frontend:** React + Redux Toolkit, Vite; two-pane form / copilot interaction patterned on the reference demo.
- **API:** Python + FastAPI. Endpoints: `POST /api/extract`, `/api/extract-file`, `/api/rca`, `/api/investigations`; `GET /api/health`, `/api/investigations`.
- **AI orchestration:** LangGraph nodes `extract → analyze`; Groq via `langchain-groq` when `GROQ_API_KEY` exists. Local conservative fallback otherwise.
- **Persistence:** SQLAlchemy; SQLite default and PostgreSQL-compatible configuration.
- **Document extraction:** pypdf, python-docx, UTF-8 TXT/EML.

## Quality / regulatory design notes

The workflow separates source-backed observations from hypotheses, surfaces absent records, keeps root cause unconfirmed until supported, provides a five-whys scaffold, and offers editable correction/corrective/preventive/effectiveness actions. It avoids automatic batch disposition, unsupported invalidation of OOS results, and “testing into compliance.”

References used to inform the workflow (verify applicability against current site procedures and jurisdiction):

- FDA, *Investigating Out-of-Specification (OOS) Test Results for Pharmaceutical Production*, Guidance for Industry, Revision 1 (May 2022): https://www.fda.gov/media/158416/download
- 21 CFR § 211.192, Production record review: https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/subpart-J/section-211.192
- ICH Q7, *Good Manufacturing Practice Guide for Active Pharmaceutical Ingredients*: https://database.ich.org/sites/default/files/Q7_Guideline.pdf
- ICH Q10, *Pharmaceutical Quality System*: https://database.ich.org/sites/default/files/Q10_Guideline.pdf

**Prototype limitation:** This is not validated for GxP use, not a Part 11/Annex 11 system, not an electronic-signature service, and not a substitute for approved SOPs, quality-unit review, or regulatory advice. Before production use, implement and validate identity/authorization, immutable audit trails, electronic records/signatures as applicable, retention, document security, privacy and data-integrity controls, model governance, monitoring, backup/recovery, and complete system validation. Do not use real regulated or personal data in the demo.

## Recording scripts

See `docs/product-demo-script.md` and `docs/code-walkthrough-script.md`. Record the requested videos locally for submission. Do not upload assignment materials or recordings to a public repository.
