from src.ingestion import DocumentProcessor

processor = DocumentProcessor(embedding_model="all-mpnet-base-v2")
docs = processor.list_documents()
total = processor.collection.count()

print("\n✅ Re-indexing Complete!")
print("=" * 60)
print(f"Total chunks: {total}")
print(f"Documents: {len(docs)}")
print("\nDocument details:")
for d in docs:
    print(f"  - {d.get('filename')}: {d.get('chunk_count')} chunks")
print("\n🎉 All documents have been re-indexed with 'all-mpnet-base-v2'!")


