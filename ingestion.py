import os
import sys
import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions
import hashlib
import shutil
from docx import Document as DocxDocument
import csv


SUPPORTED_EXTENSIONS = ['.pdf', '.txt', '.docx', '.csv']
SOURCE_DIR = "source_files"
INGESTED_DIR = "ingested_files"


class DocumentProcessor:
    def __init__(self, persist_directory=".chromadb/"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        try:
            self.collection = self.client.get_collection(name="knowledge_base")
            print("📂 Loaded existing 'knowledge_base' collection.")
        except:
            self.collection = self.client.get_or_create_collection(
                name="knowledge_base",
                embedding_function=self.embedding_function
            )
            print("🆕 Created new 'knowledge_base' collection.")

    def extract_text(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".pdf":
                return self.extract_text_from_pdf(file_path)
            elif ext == ".txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            elif ext == ".docx":
                doc = DocxDocument(file_path)
                return "\n".join([para.text for para in doc.paragraphs])
            elif ext == ".csv":
                with open(file_path, newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    return "\n".join(["\t".join(row) for row in reader])
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
        return ""

    def extract_text_from_pdf(self, file_path):
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        return text

    def chunk_text(self, text, chunk_size=1000, overlap=200):
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += (chunk_size - overlap)
        return chunks

    def hash_chunk(self, chunk_text):
        return hashlib.md5(chunk_text.encode('utf-8')).hexdigest()

    def process_document(self, file_path):
        doc_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        text = self.extract_text(file_path)

        if not text.strip():
            print(f"⚠️ No readable text found in {doc_name}. Skipping.")
            return

        chunks = self.chunk_text(text)
        if not chunks:
            print(f"⚠️ No valid chunks extracted from {doc_name}. Skipping.")
            return

        ids = [self.hash_chunk(chunk) for chunk in chunks]

        try:
            existing = set(self.collection.get(ids=ids)["ids"])
        except Exception as e:
            print(f"❌ Error fetching existing IDs: {e}")
            existing = set()

        new_chunks = [(chunk, id_) for chunk, id_ in zip(chunks, ids) if id_ not in existing]

        if not new_chunks:
            print(f"ℹ️ All chunks from {doc_name} already exist. Skipping.")
            return

        documents = [chunk for chunk, _ in new_chunks]
        new_ids = [id_ for _, id_ in new_chunks]
        metadatas = [{"source": doc_name} for _ in new_chunks]

        if not (len(documents) == len(new_ids) == len(metadatas)):
            print(f"❌ Skipped {doc_name} due to mismatch in data sizes.")
            return

        try:
            self.collection.add(
                documents=documents,
                ids=new_ids,
                metadatas=metadatas
            )
            print(f"✅ Added {len(new_chunks)} new chunks from {doc_name}")
            self.move_to_ingested(file_path, file_ext)
        except Exception as e:
            print(f"❌ Failed to add chunks for {doc_name}: {e}")

    def move_to_ingested(self, file_path, file_ext):
        dest_dir = os.path.join(INGESTED_DIR, file_ext)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(file_path, os.path.join(dest_dir, os.path.basename(file_path)))
        print(f"📦 Moved to {dest_dir}")

    def process_directory(self, directory_path=SOURCE_DIR):
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"❌ Directory not found: {directory_path}")

        files = [
            f for f in os.listdir(directory_path)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
        ]

        if not files:
            print("ℹ️ No supported files found in the directory.")
            return

        for filename in files:
            file_path = os.path.join(directory_path, filename)
            print(f"\n📄 Processing: {filename}")
            self.process_document(file_path)


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else SOURCE_DIR
    os.makedirs(SOURCE_DIR, exist_ok=True)
    os.makedirs(INGESTED_DIR, exist_ok=True)
    processor = DocumentProcessor()
    processor.process_directory(directory)
