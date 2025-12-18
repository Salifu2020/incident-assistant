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
import re
import numpy as np


# Get project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUPPORTED_EXTENSIONS = ['.pdf', '.txt', '.docx', '.csv', '.html']
SOURCE_DIR = os.path.join(PROJECT_ROOT, "source_files")
INGESTED_DIR = os.path.join(PROJECT_ROOT, "ingested_files")


class DocumentProcessor:
    def __init__(self, persist_directory=None, embedding_model="all-mpnet-base-v2", 
                 chunking_strategy="adaptive", chunk_size=800, overlap=150, min_chunk_size=100):
        """
        Initialize DocumentProcessor with configurable embedding model and chunking strategy.
        
        Args:
            persist_directory: Directory for ChromaDB persistence
            embedding_model: Embedding model to use. Options:
                - "all-MiniLM-L6-v2" (fast, smaller, default old)
                - "all-mpnet-base-v2" (better accuracy, recommended)
                - "BAAI/bge-large-en-v1.5" (state-of-the-art, slower)
            chunking_strategy: Chunking strategy to use. Options:
                - "adaptive" (default, tries multiple strategies)
                - "semantic" (uses embeddings to find topic boundaries)
                - "recursive" (recursive chunking with overlap)
                - "sliding_window" (sliding window with overlap)
                - "hierarchical" (multi-level hierarchical chunking)
                - "paragraph" (paragraph-based only)
                - "sentence" (sentence-based only)
            chunk_size: Target chunk size in characters
            overlap: Overlap size in characters
            min_chunk_size: Minimum chunk size to keep
        """
        if persist_directory is None:
            persist_directory = os.path.join(PROJECT_ROOT, ".chromadb")
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embedding_model = embedding_model
        self.chunking_strategy = chunking_strategy
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size
        
        # Lazy loading: Don't load embedding model until first use
        self._embedding_function = None
        self._embedding_model_name = embedding_model
        
        # For semantic chunking, lazy load the model
        self._semantic_model = None
        self._semantic_model_loaded = False
        
        # Batch processing cache
        self._batch_embedding_cache = {}
        self._batch_cache_size = 100

        # Lazy collection loading - will be initialized on first use
        self._collection = None
        self._collection_initialized = False
    
    @property
    def embedding_function(self):
        """Lazy load embedding function on first access."""
        if self._embedding_function is None:
            print(f"🔤 Loading embedding model: {self._embedding_model_name}...")
            self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model_name
            )
            print(f"✅ Embedding model loaded: {self._embedding_model_name}")
        return self._embedding_function
    
    @property
    def collection(self):
        """Lazy load collection on first access."""
        if not self._collection_initialized:
            try:
                # Try to get existing collection
                existing_collection = self.client.get_collection(name="knowledge_base")
                self._collection = existing_collection
                print(f"📂 Loaded existing 'knowledge_base' collection.")
                print(f"🔤 Using embedding model: {self._embedding_model_name}")
                print("⚠️  Note: If you changed the embedding model, you may need to re-index documents.")
            except:
                # Create new collection with the embedding function (lazy loaded)
                self._collection = self.client.get_or_create_collection(
                    name="knowledge_base",
                    embedding_function=self.embedding_function
                )
                print("🆕 Created new 'knowledge_base' collection.")
                print(f"🔤 Using embedding model: {self._embedding_model_name}")
            self._collection_initialized = True
        return self._collection
    
    @collection.setter
    def collection(self, value):
        """Allow setting collection directly (for reindexing)."""
        self._collection = value
        self._collection_initialized = True
    
    def _get_semantic_model(self):
        """Lazy load semantic model for chunking."""
        if not self._semantic_model_loaded:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"🔤 Loading semantic model for chunking: {self._embedding_model_name}...")
                self._semantic_model = SentenceTransformer(self._embedding_model_name)
                self._semantic_model_loaded = True
                print(f"✅ Semantic model loaded")
            except ImportError:
                self._semantic_model = None
                self._semantic_model_loaded = True
                print("⚠️ sentence-transformers not available for semantic chunking, falling back to adaptive")
        return self._semantic_model

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

    def chunk_text(self, text, chunk_size=None, overlap=None, min_chunk_size=None):
        """
        Advanced chunking with multiple strategies.
        
        Args:
            text: The text to chunk
            chunk_size: Target chunk size in characters (uses instance default if None)
            overlap: Overlap size in characters (uses instance default if None)
            min_chunk_size: Minimum chunk size to keep (uses instance default if None)
        """
        # Use instance defaults if not provided
        chunk_size = chunk_size or self.chunk_size
        overlap = overlap or self.overlap
        min_chunk_size = min_chunk_size or self.min_chunk_size
        
        if not text or len(text.strip()) < min_chunk_size:
            return [text.strip()] if text.strip() else []
        
        # Route to appropriate strategy
        strategy = self.chunking_strategy.lower()
        
        if strategy == "semantic":
            return self._chunk_semantic(text, chunk_size, overlap, min_chunk_size)
        elif strategy == "recursive":
            return self._chunk_recursive(text, chunk_size, overlap, min_chunk_size)
        elif strategy == "sliding_window":
            return self._chunk_sliding_window(text, chunk_size, overlap, min_chunk_size)
        elif strategy == "hierarchical":
            return self._chunk_hierarchical(text, chunk_size, overlap, min_chunk_size)
        elif strategy == "paragraph":
            paragraphs = self._split_into_paragraphs(text)
            if len(paragraphs) > 1:
                chunks = self._chunk_by_paragraphs(paragraphs, chunk_size, overlap, min_chunk_size)
                return chunks if chunks else [text.strip()]
            return [text.strip()]
        elif strategy == "sentence":
            sentences = self._split_into_sentences(text)
            if len(sentences) > 1:
                chunks = self._chunk_by_sentences(sentences, chunk_size, overlap, min_chunk_size)
                return chunks if chunks else [text.strip()]
            return [text.strip()]
        else:  # "adaptive" or default
            return self._chunk_adaptive(text, chunk_size, overlap, min_chunk_size)
    
    def _chunk_adaptive(self, text, chunk_size, overlap, min_chunk_size):
        """Adaptive chunking: tries multiple strategies in order."""
        # Strategy 1: Try paragraph-based chunking first (best for structured documents)
        paragraphs = self._split_into_paragraphs(text)
        if len(paragraphs) > 1:
            chunks = self._chunk_by_paragraphs(paragraphs, chunk_size, overlap, min_chunk_size)
            if chunks:
                return chunks
        
        # Strategy 2: Sentence-aware chunking (good for narrative text)
        sentences = self._split_into_sentences(text)
        if len(sentences) > 1:
            chunks = self._chunk_by_sentences(sentences, chunk_size, overlap, min_chunk_size)
            if chunks:
                return chunks
        
        # Strategy 3: Fallback to smart character-based chunking
        return self._chunk_by_characters(text, chunk_size, overlap, min_chunk_size)
    
    def _chunk_semantic(self, text, chunk_size, overlap, min_chunk_size):
        """
        Semantic chunking: uses embeddings to find topic boundaries.
        Splits text where semantic similarity drops significantly.
        """
        semantic_model = self._get_semantic_model()
        if semantic_model is None:
            # Fallback to adaptive if semantic model not available
            return self._chunk_adaptive(text, chunk_size, overlap, min_chunk_size)
        
        try:
            # Split into sentences first
            sentences = self._split_into_sentences(text)
            if len(sentences) < 3:
                # Too few sentences, use adaptive
                return self._chunk_adaptive(text, chunk_size, overlap, min_chunk_size)
            
            # Compute embeddings for sentences (batch processing)
            embeddings = semantic_model.encode(sentences, show_progress_bar=False, batch_size=32)
            
            # Find semantic boundaries (where similarity drops)
            chunks = []
            current_chunk = []
            current_length = 0
            similarity_threshold = 0.7  # Threshold for topic change
            
            for i in range(len(sentences)):
                sent = sentences[i]
                sent_length = len(sent)
                
                # Check if we should start a new chunk
                should_split = False
                if i > 0 and current_length + sent_length > chunk_size * 0.8:
                    # Check semantic similarity with previous sentence
                    if i < len(embeddings):
                        similarity = self._cosine_similarity(embeddings[i-1], embeddings[i])
                        if similarity < similarity_threshold:
                            should_split = True
                
                # Also split if chunk is getting too large
                if current_length + sent_length > chunk_size and current_chunk:
                    should_split = True
                
                if should_split and current_chunk:
                    # Save current chunk
                    chunk_text = ' '.join(current_chunk)
                    if len(chunk_text) >= min_chunk_size:
                        chunks.append(chunk_text)
                    
                    # Start new chunk with overlap
                    if overlap > 0 and len(current_chunk) > 0:
                        # Keep last sentence(s) for overlap
                        overlap_text = ' '.join(current_chunk[-1:])
                        if len(overlap_text) <= overlap:
                            current_chunk = [overlap_text, sent]
                            current_length = len(overlap_text) + sent_length
                        else:
                            current_chunk = [sent]
                            current_length = sent_length
                    else:
                        current_chunk = [sent]
                        current_length = sent_length
                else:
                    current_chunk.append(sent)
                    current_length += sent_length
            
            # Add final chunk
            if current_chunk:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) >= min_chunk_size:
                    chunks.append(chunk_text)
            
            return chunks if chunks else [text.strip()]
        except Exception as e:
            print(f"⚠️ Semantic chunking failed: {e}, falling back to adaptive")
            return self._chunk_adaptive(text, chunk_size, overlap, min_chunk_size)
    
    def _cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)
    
    def _chunk_recursive(self, text, chunk_size, overlap, min_chunk_size, max_depth=3):
        """
        Recursive chunking: recursively splits large chunks until they fit.
        Better preserves context with intelligent overlap.
        """
        if len(text) <= chunk_size:
            return [text.strip()] if len(text.strip()) >= min_chunk_size else []
        
        # Try to split at natural boundaries
        paragraphs = self._split_into_paragraphs(text)
        if len(paragraphs) > 1:
            # Recursively chunk each paragraph
            all_chunks = []
            for para in paragraphs:
                if len(para) > chunk_size and max_depth > 0:
                    # Recursively chunk this paragraph
                    sub_chunks = self._chunk_recursive(para, chunk_size, overlap, min_chunk_size, max_depth - 1)
                    all_chunks.extend(sub_chunks)
                elif len(para.strip()) >= min_chunk_size:
                    all_chunks.append(para.strip())
            
            # Merge small chunks and add overlap
            return self._merge_chunks_with_overlap(all_chunks, chunk_size, overlap, min_chunk_size)
        
        # If no paragraphs, try sentences
        sentences = self._split_into_sentences(text)
        if len(sentences) > 1:
            all_chunks = []
            for sent in sentences:
                if len(sent) > chunk_size and max_depth > 0:
                    sub_chunks = self._chunk_recursive(sent, chunk_size, overlap, min_chunk_size, max_depth - 1)
                    all_chunks.extend(sub_chunks)
                elif len(sent.strip()) >= min_chunk_size:
                    all_chunks.append(sent.strip())
            
            return self._merge_chunks_with_overlap(all_chunks, chunk_size, overlap, min_chunk_size)
        
        # Fallback: split at character level
        return self._chunk_by_characters(text, chunk_size, overlap, min_chunk_size)
    
    def _merge_chunks_with_overlap(self, chunks, chunk_size, overlap, min_chunk_size):
        """Merge chunks with intelligent overlap."""
        if not chunks:
            return []
        
        merged = []
        current = []
        current_length = 0
        
        for chunk in chunks:
            chunk_length = len(chunk)
            
            if current_length + chunk_length > chunk_size and current:
                # Save current chunk
                merged_text = ' '.join(current)
                if len(merged_text) >= min_chunk_size:
                    merged.append(merged_text)
                
                # Start new chunk with overlap
                if overlap > 0 and len(current) > 0:
                    # Use last part of current chunk for overlap
                    overlap_text = current[-1]
                    if len(overlap_text) <= overlap:
                        current = [overlap_text, chunk]
                        current_length = len(overlap_text) + chunk_length
                    else:
                        # Use last N characters for overlap
                        overlap_part = overlap_text[-overlap:]
                        current = [overlap_part, chunk]
                        current_length = len(overlap_part) + chunk_length
                else:
                    current = [chunk]
                    current_length = chunk_length
            else:
                current.append(chunk)
                current_length += chunk_length
        
        # Add final chunk
        if current:
            merged_text = ' '.join(current)
            if len(merged_text) >= min_chunk_size:
                merged.append(merged_text)
        
        return merged
    
    def _chunk_sliding_window(self, text, chunk_size, overlap, min_chunk_size):
        """
        Sliding window chunking: creates overlapping chunks with a fixed window.
        Good for ensuring context is preserved across boundaries.
        """
        chunks = []
        text_length = len(text)
        step_size = chunk_size - overlap  # How much to move forward
        
        start = 0
        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk = text[start:end].strip()
            
            if len(chunk) >= min_chunk_size:
                # Try to end at a sentence boundary
                if end < text_length:
                    # Look for sentence ending near the end
                    search_start = max(start, end - 100)
                    search_end = min(text_length, end + 50)
                    window = text[search_start:search_end]
                    
                    # Find last sentence ending
                    sentence_endings = re.finditer(r'[.!?]\s+', window)
                    last_match = None
                    for match in sentence_endings:
                        last_match = match
                    
                    if last_match:
                        # Adjust end to sentence boundary
                        adjusted_end = search_start + last_match.end()
                        if adjusted_end > start + min_chunk_size:
                            chunk = text[start:adjusted_end].strip()
                            end = adjusted_end
                
                chunks.append(chunk)
            
            # Move window forward
            start += step_size
            if start >= text_length:
                break
        
        return chunks if chunks else [text.strip()]
    
    def _chunk_hierarchical(self, text, chunk_size, overlap, min_chunk_size):
        """
        Hierarchical chunking: creates chunks at multiple levels.
        Level 1: Large chunks (2x chunk_size)
        Level 2: Medium chunks (chunk_size)
        Level 3: Small chunks (chunk_size / 2)
        """
        # First, create large chunks
        large_chunks = self._chunk_by_paragraphs(
            self._split_into_paragraphs(text),
            chunk_size * 2,
            overlap * 2,
            min_chunk_size
        )
        
        if not large_chunks:
            large_chunks = [text]
        
        # Then, chunk each large chunk into medium chunks
        all_chunks = []
        for large_chunk in large_chunks:
            if len(large_chunk) <= chunk_size:
                all_chunks.append(large_chunk)
            else:
                # Chunk this large chunk
                medium_chunks = self._chunk_adaptive(large_chunk, chunk_size, overlap, min_chunk_size)
                all_chunks.extend(medium_chunks)
        
        return all_chunks if all_chunks else [text.strip()]
    
    def _split_into_paragraphs(self, text):
        """Split text into paragraphs, preserving structure."""
        # Split by double newlines (paragraph breaks)
        paragraphs = re.split(r'\n\s*\n+', text)
        # Also split by single newlines if they look like paragraph breaks
        refined = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # If paragraph is very long, try to split by single newlines
            if len(para) > 1000:
                lines = para.split('\n')
                current = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        if current:
                            refined.append('\n'.join(current))
                            current = []
                    else:
                        current.append(line)
                if current:
                    refined.append('\n'.join(current))
            else:
                refined.append(para)
        return [p for p in refined if p.strip()]
    
    def _split_into_sentences(self, text):
        """Split text into sentences using improved regex."""
        # Enhanced sentence splitting regex
        # Handles abbreviations, decimals, URLs, etc.
        sentence_endings = r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\n+(?=[A-Z])'
        sentences = re.split(sentence_endings, text)
        
        # Clean up sentences
        cleaned = []
        for sent in sentences:
            sent = sent.strip()
            if sent and len(sent) > 10:  # Skip very short fragments
                cleaned.append(sent)
        
        return cleaned
    
    def _chunk_by_paragraphs(self, paragraphs, chunk_size, overlap, min_chunk_size):
        """Chunk text by combining paragraphs intelligently."""
        chunks = []
        current_chunk = []
        current_length = 0
        
        for i, para in enumerate(paragraphs):
            para_length = len(para)
            
            # If single paragraph exceeds chunk size, split it
            if para_length > chunk_size * 1.5:
                # Split this paragraph using sentences
                sentences = self._split_into_sentences(para)
                if len(sentences) > 1:
                    # Recursively chunk this paragraph
                    sub_chunks = self._chunk_by_sentences(sentences, chunk_size, overlap, min_chunk_size)
                    # Add completed chunks
                    for sub_chunk in sub_chunks[:-1]:  # All but last
                        chunks.append(sub_chunk)
                    # Continue with last sub-chunk
                    if sub_chunks:
                        current_chunk = [sub_chunks[-1]]
                        current_length = len(sub_chunks[-1])
                    continue
            
            # Check if adding this paragraph would exceed chunk size
            if current_length + para_length > chunk_size and current_chunk:
                # Save current chunk
                chunk_text = '\n\n'.join(current_chunk)
                if len(chunk_text) >= min_chunk_size:
                    chunks.append(chunk_text)
                
                # Start new chunk with overlap
                if overlap > 0 and len(current_chunk) > 0:
                    # Keep last paragraph(s) for overlap
                    overlap_text = current_chunk[-1]
                    if len(overlap_text) <= overlap:
                        current_chunk = [overlap_text, para]
                        current_length = len(overlap_text) + para_length
                    else:
                        # Use part of last paragraph for overlap
                        overlap_part = overlap_text[-overlap:]
                        current_chunk = [overlap_part, para]
                        current_length = len(overlap_part) + para_length
                else:
                    current_chunk = [para]
                    current_length = para_length
            else:
                # Add paragraph to current chunk
                current_chunk.append(para)
                current_length += para_length
        
        # Add final chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
        
        return chunks if chunks else None
    
    def _chunk_by_sentences(self, sentences, chunk_size, overlap, min_chunk_size):
        """Chunk text by combining sentences intelligently."""
        chunks = []
        current_chunk = []
        current_length = 0
        
        for i, sent in enumerate(sentences):
            sent_length = len(sent)
            
            # Check if adding this sentence would exceed chunk size
            if current_length + sent_length > chunk_size and current_chunk:
                # Save current chunk
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) >= min_chunk_size:
                    chunks.append(chunk_text)
                
                # Start new chunk with overlap
                if overlap > 0 and len(current_chunk) > 0:
                    # Keep last sentence(s) for overlap
                    overlap_sentences = []
                    overlap_length = 0
                    for j in range(len(current_chunk) - 1, -1, -1):
                        if overlap_length + len(current_chunk[j]) <= overlap:
                            overlap_sentences.insert(0, current_chunk[j])
                            overlap_length += len(current_chunk[j])
                        else:
                            break
                    
                    if overlap_sentences:
                        current_chunk = overlap_sentences + [sent]
                        current_length = overlap_length + sent_length
                    else:
                        current_chunk = [sent]
                        current_length = sent_length
                else:
                    current_chunk = [sent]
                    current_length = sent_length
            else:
                # Add sentence to current chunk
                current_chunk.append(sent)
                current_length += sent_length
        
        # Add final chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
        
        return chunks if chunks else None
    
    def _chunk_by_characters(self, text, chunk_size, overlap, min_chunk_size):
        """Fallback: Smart character-based chunking with sentence boundary awareness."""
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + chunk_size, text_length)
            
            # Try to break at sentence boundaries for better semantic chunks
            if end < text_length:
                # Look for sentence endings near the chunk boundary
                # Search in a window around the target end position
                search_start = max(start, end - chunk_size * 0.3)
                search_end = min(text_length, end + chunk_size * 0.2)
                
                # Enhanced sentence ending patterns
                sentence_patterns = [
                    r'\.\s+',      # Period followed by space
                    r'\.\n+',      # Period followed by newline
                    r'!\s+',       # Exclamation
                    r'!\n+',
                    r'\?\s+',      # Question mark
                    r'\?\n+',
                    r'\.\"\s+',    # Period with quote
                    r'\.\"\n+',
                ]
                
                best_break = -1
                for pattern in sentence_patterns:
                    matches = list(re.finditer(pattern, text[search_start:search_end]))
                    if matches:
                        # Use the match closest to target end
                        for match in reversed(matches):
                            pos = search_start + match.end()
                            if start < pos <= end:
                                best_break = pos
                                break
                        if best_break > 0:
                            break
                
                if best_break > start + min_chunk_size:
                    end = best_break
            
            chunk = text[start:end].strip()
            if chunk and len(chunk) >= min_chunk_size:
                chunks.append(chunk)
            
            # Move start position with overlap
            if end >= text_length:
                break
            start = max(start + 1, end - overlap)
        
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
            # Batch check existing IDs in chunks for better performance
            existing = set()
            batch_size = 1000
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i+batch_size]
                try:
                    batch_result = self.collection.get(ids=batch_ids)
                    if batch_result and "ids" in batch_result:
                        existing.update(batch_result["ids"])
                except Exception as e:
                    # Continue with next batch if one fails
                    print(f"⚠️ Error checking batch {i//batch_size + 1}: {e}")
                    continue
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
            # Batch add chunks in smaller batches for better performance
            batch_size = 100
            num_batches = (len(documents) + batch_size - 1) // batch_size
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i+batch_size]
                batch_ids = new_ids[i:i+batch_size]
                batch_metas = metadatas[i:i+batch_size]
                
                self.collection.add(
                    documents=batch_docs,
                    ids=batch_ids,
                    metadatas=batch_metas
                )
            print(f"✅ Added {len(new_chunks)} new chunks from {doc_name} (in {num_batches} batches)")
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

    def reindex_with_new_model(self, new_embedding_model: str):
        """Re-index all documents with a new embedding model.
        
        This is required when changing the embedding model because embeddings
        are model-specific and cannot be reused across different models.
        
        Args:
            new_embedding_model: Name of the new embedding model to use
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            print(f"🔄 Starting re-indexing with new embedding model: {new_embedding_model}")
            
            # Get all existing documents and their metadata
            all_results = self.collection.get()
            if not all_results or not all_results.get('ids') or len(all_results['ids']) == 0:
                return True, "No documents to re-index"
            
            # Get list of unique source files
            metadatas = all_results.get('metadatas', [])
            sources = set()
            for meta in metadatas:
                if meta and 'source' in meta:
                    sources.add(meta['source'])
            
            if not sources:
                return True, "No source files found to re-index"
            
            print(f"📚 Found {len(sources)} documents to re-index")
            
            # Delete existing collection
            try:
                self.client.delete_collection(name="knowledge_base")
                print("🗑️  Deleted old collection")
            except Exception as e:
                print(f"⚠️  Error deleting old collection: {e}")
            
            # Update embedding model
            self.embedding_model = new_embedding_model
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=new_embedding_model
            )
            
            # Create new collection with new embedding function
            self.collection = self.client.get_or_create_collection(
                name="knowledge_base",
                embedding_function=self.embedding_function
            )
            print(f"🆕 Created new collection with model: {new_embedding_model}")
            
            # Re-process all source files
            reindexed_count = 0
            for source_file in sources:
                # Find the file in ingested_files directory
                file_found = False
                for ext in SUPPORTED_EXTENSIONS:
                    ext_dir = os.path.join(INGESTED_DIR, ext[1:])
                    file_path = os.path.join(ext_dir, source_file)
                    if os.path.exists(file_path):
                        try:
                            # Re-process the file
                            self.process_document(file_path)
                            reindexed_count += 1
                            print(f"✅ Re-indexed: {source_file}")
                            file_found = True
                            break
                        except Exception as e:
                            print(f"⚠️  Error re-indexing {source_file}: {e}")
                            import traceback
                            traceback.print_exc()
                
                if not file_found:
                    print(f"⚠️  Source file not found for: {source_file}")
            
            message = f"Re-indexing complete: {reindexed_count}/{len(sources)} documents processed"
            print(f"✅ {message}")
            return True, message
            
        except Exception as e:
            error_msg = f"Error during re-indexing: {type(e).__name__}: {e}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg

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
