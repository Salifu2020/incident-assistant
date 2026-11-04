# Incident Assistant

A Knowledge Assistant API and Streamlit frontend that lets users upload **multiple document types** (`.pdf`, `.txt`, `.docx`, `.csv`), 
ingest their content, and ask questions with instant AI-powered answers.

---

## **Features**

- 📂 Upload `.pdf`, `.txt`, `.docx`, `.csv` files to expand the knowledge base  
- 📑 Ingest documents with chunking and vector storage (via ChromaDB)  
- 💬 Query the knowledge base with natural language questions  
- 🎨 Streamlit frontend styled for a clean, interactive experience  
- ⚡ FastAPI backend exposing `/ask` and `/upload` endpoints  
- 📝 Logging to `api.log` and `streamlit.log` for both questions and answers  
- 📁 Organized storage:
  - **`source_files/`** – raw uploaded files of all types  
  - **`ingested_files/<filetype>/`** – processed files stored in subfolders by type  

---

## **Getting Started**

### **Prerequisites**
- Python 3.8+
- Poetry or pip for dependencies
- (Optional) A virtual environment tool like `venv` or `conda`

---

### **Installation**
```bash
git clone https://github.com/Salifu2020/incident-assistant
cd incident-assistant
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
# Full local stack (API + embeddings + Streamlit)
pip install -r requirements-api.txt
```

Streamlit Community Cloud uses root `requirements.txt` (UI-only). See [docs/STREAMLIT_CLOUD_DEPLOYMENT.md](docs/STREAMLIT_CLOUD_DEPLOYMENT.md).

---

## **Running the API Server**
```bash
# Option 1: Using the unified entry point
python run.py api

# Option 2: Using uvicorn directly
uvicorn src.api:app --reload
```
The API will be available at:  
➡️ **http://127.0.0.1:8000**

---

## **Running the Streamlit Frontend**
```bash
# Option 1: Using the unified entry point
python run.py app

# Option 2: Using streamlit directly
streamlit run src/app.py
```
Open the displayed URL (usually **http://localhost:8501**) in your browser.

---

## **Running the CLI Interface**
```bash
# Option 1: Using the unified entry point
python run.py cli

# Option 2: Using Python module
python -m src.cli
```
Interactive command-line interface for querying the knowledge base.

---

## **API Endpoints**
| Endpoint  | Method | Description |
|-----------|--------|-------------|
| `/`       | GET    | API status check |
| `/ask`    | POST   | Query the knowledge base with `{ "query": "your question" }` |
| `/upload` | POST   | Upload a `.pdf`, `.txt`, `.docx`, or `.csv` file to ingest new documents |

---

## **Project Structure**
```
incident-assistant/
├── src/               # Main application source code
│   ├── __init__.py
│   ├── api.py         # FastAPI backend
│   ├── app.py         # Streamlit frontend
│   ├── cli.py         # CLI interface
│   ├── ingestion.py   # Document ingestion logic
│   ├── querying.py    # Logic for querying knowledge base
│   ├── dependencies.py # Dependency injection for assistant and processor
│   └── models.py      # Pydantic models for API request/response
├── scripts/           # Utility and deployment scripts
│   ├── deploy.sh      # Docker deployment script
│   ├── setup_oracle_vm.sh  # Oracle Cloud VM setup
│   ├── generate_secret_key.py  # Generate JWT secret key
│   └── reindex_documents.py   # Re-index with new embedding model
├── docs/              # Documentation
│   ├── INTERVIEW_QA.md
│   └── UI_IMPROVEMENT_RECOMMENDATIONS.md
├── config/            # Configuration templates
│   └── nginx.conf.example
├── run.py             # Unified entry point (api | app | cli)
├── requirements.txt   # Python dependencies
├── source_files/      # Stores uploaded files (all supported types)
├── ingested_files/    # Stores processed files by type
│   ├── pdf/
│   ├── txt/
│   ├── docx/
│   └── csv/
├── logs/              # Application logs
│   ├── api.log        # Backend logs
│   └── streamlit.log  # Frontend logs
└── .chromadb/         # Persistent vector DB data
```

---

## **Usage**
1. Upload documents via the frontend or `/upload` endpoint.  
2. Files are saved in `source_files/` and processed into `ingested_files/<filetype>/`.  
3. The system automatically chunks and stores them in ChromaDB.  
4. Ask questions via the frontend or `/ask` endpoint.  
5. Logs are recorded in both **`api.log`** and **`streamlit.log`**.

---

## **Streamlit Cloud**
Deploy **only** `src/app.py` on Community Cloud, with a **separate** public FastAPI host. Set secrets:

```toml
API_URL = "https://your-api-host.example.com"
```

If the Cloud app spins forever, it was usually installing `torch`/ChromaDB from the old monolithic `requirements.txt`. That file is now UI-only; reboot after pulling this change. Full steps: [docs/STREAMLIT_CLOUD_DEPLOYMENT.md](docs/STREAMLIT_CLOUD_DEPLOYMENT.md).

---

## **Troubleshooting**
- **Port 8000 already in use (WinError 10048):** Run the API on another port:
  ```powershell
  $env:PORT=8001; python run.py api
  ```
  If running Streamlit, point it to the API: `$env:API_URL="http://127.0.0.1:8001"; python run.py app`
- **Database password authentication failed / "Falling back to JSON file storage":** For local dev this is fine—the app uses JSON file storage. To use PostgreSQL, set `DATABASE_URL` (or `POSTGRES_URL`) with valid credentials.
- **404 errors:** Ensure you are calling `/ask` or `/upload**.  
- **Changes not taking effect:** Restart the API server after modifying code or adding dependencies.  
- **Logs not updating:** Check file permissions and ensure logging is enabled in both backend and frontend.  

---

## **License**
MIT License © Fuseini Salifu
