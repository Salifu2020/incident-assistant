from fastapi import FastAPI, File, UploadFile, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import os
import logging
from logging.handlers import RotatingFileHandler

from dependencies import processor, assistant
from models import QuestionRequest, QuestionResponse, UploadResponse

# Logging Configuration
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "api.log")

file_handler = RotatingFileHandler(log_file_path, maxBytes=1_000_000, backupCount=3)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), file_handler],
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Assistant API")

# Allow CORS (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    logger.info("🚀 FastAPI app is starting...")

@app.get("/")
def root():
    return {"message": "📚 Knowledge Assistant API is running"}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid input. Please check your request format."},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )

@app.post("/ask", response_model=QuestionResponse)
def ask_question(payload: QuestionRequest):
    try:
        logger.info(f"Received query: {payload.query}")
        answer = assistant.ask_question(payload.query)
        logger.info(f"Answer generated: {answer}")
        return {"response": answer}
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    allowed_extensions = {".pdf", ".docx", ".txt", ".html", ".csv"}
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in allowed_extensions:
        logger.warning(f"Rejected file upload: {file.filename}")
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    os.makedirs("source_files", exist_ok=True)
    source_path = os.path.join("source_files", file.filename)

    try:
        # Save uploaded file to source_files
        content = await file.read()
        with open(source_path, "wb") as f:
            f.write(content)
        logger.info(f"📥 File saved to source_files: {source_path}")

        # Schedule background task
        background_tasks.add_task(process_and_move_file, source_path, ext)
        return {"message": f"📤 {file.filename} is being processed in the background."}

    except Exception as e:
        logger.error(f" Error saving {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


def process_and_move_file(source_path: str, ext: str):
    filename = os.path.basename(source_path)
    try:
        # Run the ingestion processor
        processor.process_document(source_path)

        # Move to ingested_files/<ext_without_dot>/
        ingested_dir = os.path.join("ingested_files", ext[1:])
        os.makedirs(ingested_dir, exist_ok=True)
        ingested_path = os.path.join(ingested_dir, filename)

        os.rename(source_path, ingested_path)
        logger.info(f"✅ {filename} processed and moved to {ingested_path}")

    except Exception as e:
        logger.error(f" Background task failed for {filename}: {e}")
