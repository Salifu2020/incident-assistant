import os
import sys
import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions
import hashlib
import shutil
from docx import Document as DocxDocument
import csv
import datetime


# Get project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUPPORTED_EXTENSIONS = ['.pdf', '.txt', '.docx', '.csv', '.html']
SOURCE_DIR = os.path.join(PROJECT_ROOT, "source_files")
INGESTED_DIR = os.path.join(PROJECT_ROOT, "ingested_files")


class DocumentProcessor:
    def __init__(self, persist_directory=None):
        if persist_directory is None:
            persist_directory = os.path.join(PROJECT_ROOT, ".chromadb")
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
        """Extract text from a file with comprehensive error handling."""
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return ""
        
        if not os.path.isfile(file_path):
            print(f"❌ Path is not a file: {file_path}")
            return ""
        
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".pdf":
                return self.extract_text_from_pdf(file_path)
            elif ext == ".txt":
                return self._extract_text_from_txt(file_path)
            elif ext == ".docx":
                return self._extract_text_from_docx(file_path)
            elif ext == ".csv":
                return self._extract_text_from_csv(file_path)
            elif ext == ".html":
                return self._extract_text_from_html(file_path)
            else:
                print(f"⚠️ Unsupported file extension: {ext}")
                return ""
        except Exception as e:
            print(f"❌ Error reading {file_path}: {type(e).__name__}: {e}")
            return ""
    
    def _extract_text_from_txt(self, file_path):
        """Extract text from a TXT file with encoding fallback."""
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except PermissionError:
                print(f"❌ Permission denied reading {file_path}")
                return ""
            except IOError as e:
                print(f"❌ IO error reading {file_path}: {e}")
                return ""
        print(f"⚠️ Could not decode {file_path} with any supported encoding")
        return ""
    
    def _extract_text_from_docx(self, file_path):
        """Extract text from a DOCX file."""
        try:
            doc = DocxDocument(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        except PermissionError:
            print(f"❌ Permission denied reading {file_path}")
            return ""
        except Exception as e:
            print(f"❌ Error reading DOCX file {file_path}: {type(e).__name__}: {e}")
            return ""
    
    def _extract_text_from_csv(self, file_path):
        """Extract text from a CSV file."""
        try:
            with open(file_path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                return "\n".join(["\t".join(row) for row in reader])
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, newline='', encoding='latin-1') as f:
                    reader = csv.reader(f)
                    return "\n".join(["\t".join(row) for row in reader])
            except Exception as e:
                print(f"❌ Error reading CSV file {file_path}: {type(e).__name__}: {e}")
                return ""
        except PermissionError:
            print(f"❌ Permission denied reading {file_path}")
            return ""
        except Exception as e:
            print(f"❌ Error reading CSV file {file_path}: {type(e).__name__}: {e}")
            return ""
    
    def _extract_text_from_html(self, file_path):
        """Extract text from an HTML file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    return f.read()
            except Exception as e:
                print(f"❌ Error reading HTML file {file_path}: {type(e).__name__}: {e}")
                return ""
        except PermissionError:
            print(f"❌ Permission denied reading {file_path}")
            return ""
        except Exception as e:
            print(f"❌ Error reading HTML file {file_path}: {type(e).__name__}: {e}")
            return ""

    def extract_text_from_pdf(self, file_path):
        """Extract text from a PDF file with error handling."""
        doc = None
        try:
            doc = fitz.open(file_path)
            text = ""
            for page_num, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                    text += page_text
                except Exception as e:
                    print(f"⚠️ Error extracting text from page {page_num} of {file_path}: {e}")
                    continue
            return text
        except fitz.FileDataError:
            print(f"❌ Corrupted or invalid PDF file: {file_path}")
            return ""
        except PermissionError:
            print(f"❌ Permission denied reading PDF: {file_path}")
            return ""
        except Exception as e:
            print(f"❌ Error reading PDF {file_path}: {type(e).__name__}: {e}")
            return ""
        finally:
            if doc:
                try:
                    doc.close()
                except:
                    pass

    def chunk_text(self, text, chunk_size=800, overlap=150):
        """
        Optimized chunking with better semantic boundaries.
        Smaller chunks (800) with less overlap (150) for faster retrieval.
        """
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + chunk_size, text_length)
            
            # Try to break at sentence boundaries for better semantic chunks
            if end < text_length:
                # Look for sentence endings near the chunk boundary
                for punct in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
                    last_punct = text.rfind(punct, start, end)
                    if last_punct > start + chunk_size * 0.7:  # Only if not too early
                        end = last_punct + len(punct)
                        break
            
            chunk = text[start:end].strip()
            if chunk and len(chunk) > 50:  # Skip very small chunks
                chunks.append(chunk)
            
            start += (chunk_size - overlap)
        
        return chunks

    def hash_chunk(self, chunk_text):
        return hashlib.md5(chunk_text.encode('utf-8')).hexdigest()

    def process_document(self, file_path):
        """Process a document with comprehensive error handling."""
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return
        
        if not os.path.isfile(file_path):
            print(f"❌ Path is not a file: {file_path}")
            return
        
        doc_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        
        try:
            text = self.extract_text(file_path)
        except Exception as e:
            print(f"❌ Unexpected error extracting text from {doc_name}: {type(e).__name__}: {e}")
            return

        if not text.strip():
            print(f"⚠️ No readable text found in {doc_name}. Skipping.")
            return

        try:
            chunks = self.chunk_text(text)
        except Exception as e:
            print(f"❌ Error chunking text from {doc_name}: {type(e).__name__}: {e}")
            return
        
        if not chunks:
            print(f"⚠️ No valid chunks extracted from {doc_name}. Skipping.")
            return

        try:
            ids = [self.hash_chunk(chunk) for chunk in chunks]
        except Exception as e:
            print(f"❌ Error generating chunk IDs for {doc_name}: {type(e).__name__}: {e}")
            return

        try:
            existing = set(self.collection.get(ids=ids)["ids"])
        except Exception as e:
            # ChromaDB errors are typically generic exceptions
            error_type = type(e).__name__
            if "Chroma" in error_type or "chroma" in str(type(e)).lower():
                print(f"❌ ChromaDB error fetching existing IDs: {e}")
            else:
                print(f"❌ Error fetching existing IDs: {error_type}: {e}")
            existing = set()

        new_chunks = [(chunk, id_) for chunk, id_ in zip(chunks, ids) if id_ not in existing]

        if not new_chunks:
            print(f"ℹ️ All chunks from {doc_name} already exist. Skipping.")
            return

        documents = [chunk for chunk, _ in new_chunks]
        new_ids = [id_ for _, id_ in new_chunks]
        
        # Enhanced metadata with file type and processing date
        file_type = os.path.splitext(doc_name)[1].lower().lstrip('.')
        processing_date = datetime.datetime.now().isoformat()[:10]  # YYYY-MM-DD format
        
        metadatas = [{
            "source": doc_name,
            "file_type": file_type,
            "processing_date": processing_date
        } for _ in new_chunks]

        if not (len(documents) == len(new_ids) == len(metadatas)):
            print(f"❌ Skipped {doc_name} due to mismatch in data sizes (docs:{len(documents)}, ids:{len(new_ids)}, metas:{len(metadatas)}).")
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
            error_type = type(e).__name__
            if "Chroma" in error_type or "chroma" in str(type(e)).lower():
                print(f"❌ ChromaDB error adding chunks for {doc_name}: {e}")
            else:
                print(f"❌ Failed to add chunks for {doc_name}: {error_type}: {e}")

    def move_to_ingested(self, file_path, file_ext):
        """Move processed file to ingested directory with error handling."""
        if not os.path.exists(file_path):
            print(f"⚠️ Cannot move {file_path}: file does not exist")
            return
        
        dest_dir = os.path.join(INGESTED_DIR, file_ext)
        
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as e:
            print(f"❌ Failed to create ingested directory {dest_dir}: {e}")
            return
        
        dest_path = os.path.join(dest_dir, os.path.basename(file_path))
        
        # Check if destination already exists
        if os.path.exists(dest_path):
            try:
                os.remove(file_path)
                print(f"ℹ️ File already exists in {dest_dir}, removed source file")
            except Exception as e:
                print(f"⚠️ Could not remove source file {file_path}: {e}")
            return
        
        try:
            shutil.move(file_path, dest_path)
            print(f"📦 Moved to {dest_dir}")
        except PermissionError:
            print(f"❌ Permission denied moving {file_path} to {dest_path}")
        except OSError as e:
            if "No space left" in str(e) or "disk" in str(e).lower():
                print(f"❌ Disk full: Cannot move {file_path}")
            else:
                print(f"❌ OS error moving {file_path}: {e}")
        except Exception as e:
            print(f"❌ Error moving {file_path}: {type(e).__name__}: {e}")

    def get_document_info(self, filename: str):
        """Get information about a specific document."""
        try:
            # Get all chunks for this document
            results = self.collection.get(
                where={"source": filename},
                include=['metadatas']
            )
            chunk_count = len(results['ids']) if results and 'ids' in results else 0
            
            # Find the file in ingested_files
            file_path = None
            file_size = None
            for ext in SUPPORTED_EXTENSIONS:
                ext_dir = os.path.join(INGESTED_DIR, ext[1:])
                potential_path = os.path.join(ext_dir, filename)
                if os.path.exists(potential_path):
                    file_path = potential_path
                    file_size = os.path.getsize(potential_path)
                    break
            
            file_type = os.path.splitext(filename)[1].lower().lstrip('.')
            
            # Get file modification time as upload date
            upload_date = None
            if file_path and os.path.exists(file_path):
                mtime = os.path.getmtime(file_path)
                upload_date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            return {
                "filename": filename,
                "file_type": file_type,
                "chunk_count": chunk_count,
                "upload_date": upload_date,
                "file_size": file_size,
                "file_path": file_path
            }
        except Exception as e:
            print(f"❌ Error getting document info for {filename}: {e}")
            return None
    
    def list_documents(self):
        """List all documents in the knowledge base."""
        try:
            # Get total count first
            total_count = self.collection.count()
            
            if total_count == 0:
                print("ℹ️ Knowledge base is empty")
                return []
            
            print(f"📊 Knowledge base has {total_count} chunks, extracting document list...")
            
            # Get all chunks to extract unique document names
            # For most use cases, this is acceptable even with thousands of chunks
            try:
                all_results = self.collection.get(include=['metadatas'])
            except Exception as e:
                print(f"❌ Error getting chunks from ChromaDB: {e}")
                return []
            
            if not all_results or 'metadatas' not in all_results:
                print("⚠️ No metadata found in knowledge base")
                return []
            
            # Extract unique document names
            unique_docs = set()
            for metadata in all_results['metadatas']:
                if metadata and 'source' in metadata:
                    unique_docs.add(metadata['source'])
            
            if not unique_docs:
                print("⚠️ No documents found in knowledge base metadata")
                return []
            
            print(f"📋 Found {len(unique_docs)} unique document(s): {list(unique_docs)}")
            
            # Get accurate chunk counts for each document
            doc_chunks = {}
            for doc_name in unique_docs:
                try:
                    # Note: ids are always returned by ChromaDB, no need to include them
                    doc_results = self.collection.get(
                        where={"source": doc_name}
                    )
                    if doc_results and 'ids' in doc_results:
                        doc_chunks[doc_name] = len(doc_results['ids'])
                        print(f"  📄 {doc_name}: {doc_chunks[doc_name]} chunks")
                    else:
                        doc_chunks[doc_name] = 0
                except Exception as e:
                    print(f"⚠️ Error counting chunks for {doc_name}: {e}")
                    doc_chunks[doc_name] = 0
            
            # Get file information for each document
            documents = []
            for filename in unique_docs:
                try:
                    doc_info = self.get_document_info(filename)
                    if doc_info:
                        # Use the accurate chunk count from our query
                        doc_info['chunk_count'] = doc_chunks.get(filename, 0)
                        documents.append(doc_info)
                        print(f"✅ Got info for {filename}")
                    else:
                        # Even if get_document_info returns None, create a basic entry
                        print(f"⚠️ Could not get full info for {filename}, creating basic entry")
                        file_type = os.path.splitext(filename)[1].lower().lstrip('.')
                        documents.append({
                            "filename": filename,
                            "file_type": file_type,
                            "chunk_count": doc_chunks.get(filename, 0),
                            "upload_date": None,
                            "file_size": None,
                            "file_path": None
                        })
                except Exception as e:
                    print(f"⚠️ Error processing document info for {filename}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Create a basic entry anyway
                    file_type = os.path.splitext(filename)[1].lower().lstrip('.')
                    documents.append({
                        "filename": filename,
                        "file_type": file_type,
                        "chunk_count": doc_chunks.get(filename, 0),
                        "upload_date": None,
                        "file_size": None,
                        "file_path": None
                    })
            
            # Sort by filename
            documents.sort(key=lambda x: x['filename'])
            print(f"✅ Returning {len(documents)} document(s) with info")
            return documents
        except Exception as e:
            print(f"❌ Error listing documents: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def delete_document(self, filename: str):
        """Delete a document and all its chunks from the knowledge base."""
        try:
            # Get all chunk IDs for this document
            # Note: ids are always returned by ChromaDB, no need to include them
            results = self.collection.get(
                where={"source": filename}
            )
            
            if not results or 'ids' not in results or len(results['ids']) == 0:
                return 0, f"Document '{filename}' not found in knowledge base"
            
            chunk_ids = results['ids']
            
            # Delete chunks from ChromaDB
            self.collection.delete(ids=chunk_ids)
            
            # Try to delete the physical file
            file_deleted = False
            for ext in SUPPORTED_EXTENSIONS:
                ext_dir = os.path.join(INGESTED_DIR, ext[1:])
                file_path = os.path.join(ext_dir, filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        file_deleted = True
                        break
                    except Exception as e:
                        print(f"⚠️ Could not delete file {file_path}: {e}")
            
            return len(chunk_ids), None
        except Exception as e:
            error_msg = f"Error deleting document: {type(e).__name__}: {e}"
            print(f"❌ {error_msg}")
            return 0, error_msg

    def process_directory(self, directory_path=SOURCE_DIR):
        """Process all supported files in a directory with error handling."""
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"❌ Directory not found: {directory_path}")
        
        if not os.path.isdir(directory_path):
            raise NotADirectoryError(f"❌ Path is not a directory: {directory_path}")

        try:
            files = [
                f for f in os.listdir(directory_path)
                if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
            ]
        except PermissionError:
            raise PermissionError(f"❌ Permission denied accessing directory: {directory_path}")
        except Exception as e:
            raise Exception(f"❌ Error listing directory {directory_path}: {type(e).__name__}: {e}")

        if not files:
            print("ℹ️ No supported files found in the directory.")
            return

        for filename in files:
            file_path = os.path.join(directory_path, filename)
            print(f"\n📄 Processing: {filename}")
            try:
                self.process_document(file_path)
            except Exception as e:
                print(f"❌ Error processing {filename}: {type(e).__name__}: {e}")
                continue  # Continue with next file


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else SOURCE_DIR
    os.makedirs(SOURCE_DIR, exist_ok=True)
    os.makedirs(INGESTED_DIR, exist_ok=True)
    processor = DocumentProcessor()
    processor.process_directory(directory)
