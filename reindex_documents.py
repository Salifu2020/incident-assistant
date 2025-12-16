#!/usr/bin/env python3
"""
Script to re-index existing documents with the new embedding model.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ingestion import DocumentProcessor

def main():
    print("🔄 Re-indexing Documents with New Embedding Model")
    print("=" * 60)
    
    # Initialize processor with new embedding model
    print("\n📦 Initializing DocumentProcessor with 'all-mpnet-base-v2'...")
    processor = DocumentProcessor(embedding_model="all-mpnet-base-v2")
    
    # Check existing documents
    print("\n📋 Checking existing documents...")
    documents = processor.list_documents()
    
    if not documents or len(documents) == 0:
        print("\n⚠️  No documents found in the knowledge base.")
        print("   Please upload documents first, then re-index.")
        return
    
    print(f"\n✅ Found {len(documents)} document(s):")
    for doc in documents:
        print(f"   - {doc.get('filename', 'Unknown')} ({doc.get('chunk_count', 0)} chunks)")
    
    # Confirm re-indexing
    print(f"\n⚠️  WARNING: This will delete the existing collection and re-index all {len(documents)} document(s).")
    print("   This is required when changing embedding models.")
    
    response = input("\n   Continue with re-indexing? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("\n❌ Re-indexing cancelled.")
        return
    
    # Perform re-indexing
    print("\n🔄 Starting re-indexing process...")
    print("   This may take several minutes depending on document size...\n")
    
    success, message = processor.reindex_with_new_model("all-mpnet-base-v2")
    
    if success:
        print(f"\n✅ {message}")
        print("\n🎉 Re-indexing completed successfully!")
        print("   Your documents are now using the improved embedding model.")
    else:
        print(f"\n❌ Re-indexing failed: {message}")
        print("\n   Please check the error message above and try again.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Re-indexing interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

