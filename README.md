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
pip install -r requirements.txt
```

---

## **Running the API Server**
```bash
# Option 1: Using the entry point script
python run_api.py

# Option 2: Using uvicorn directly
uvicorn src.api:app --reload
```
The API will be available at:  
➡️ **http://127.0.0.1:8000**

---

## **Running the Streamlit Frontend**
```bash
# Option 1: Using the entry point script
python run_app.py

# Option 2: Using streamlit directly
streamlit run src/app.py
```
Open the displayed URL (usually **http://localhost:8501**) in your browser.

---

## **Running the CLI Interface**
```bash
# Option 1: Using the entry point script
python run_cli.py

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
├── run_api.py         # Entry point for API server
├── run_app.py         # Entry point for Streamlit frontend
├── run_cli.py         # Entry point for CLI interface
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

## **Troubleshooting**
- **404 errors:** Ensure you are calling `/ask` or `/upload`.  
- **Changes not taking effect:** Restart the API server after modifying code or adding dependencies.  
- **Logs not updating:** Check file permissions and ensure logging is enabled in both backend and frontend.  

---

## **License**
MIT License © Fuseini Salifu
