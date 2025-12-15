try:
    from .ingestion import DocumentProcessor
    from .querying import KnowledgeAssistant
except ImportError:
    # Fallback for direct script execution
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.ingestion import DocumentProcessor
    from src.querying import KnowledgeAssistant


def main():
    processor = DocumentProcessor()
    assistant = KnowledgeAssistant(processor, model_name="mistral")

    print("📚 Knowledge Transfer Assistant (Chat Mode)")
    print("Type 'reset' to clear conversation or 'exit' to quit.\n")

    try:
        while True:
            query = input("\nYou: ").strip()

            if query.lower() in {"exit", "quit"}:
                print("🛑 Exiting. Goodbye!")
                break
            elif query.lower() == "reset":
                assistant.reset_history()
                print("🔄 Chat history reset.")
                continue
            elif not query:
                # Ignore empty inputs
                continue

            result = assistant.ask_question(query)
            # Handle new return format (answer, sources, intent, confidence)
            if isinstance(result, tuple) and len(result) >= 2:
                answer = result[0]
                sources = result[1] if len(result) > 1 else []
                confidence_info = result[3] if len(result) > 3 else None
                
                print("Salibot:", answer)
                if confidence_info and confidence_info.get("confidence"):
                    conf = confidence_info.get("confidence", 0.0)
                    level = confidence_info.get("level", "unknown")
                    print(f"   [Confidence: {conf:.0%} ({level})]")
                if sources:
                    print(f"   [Sources: {', '.join([s.get('source', 'Unknown') for s in sources[:3]])}]")
                print()
            else:
                # Fallback for old format
                print("Salibot:", result, "\n")

    except KeyboardInterrupt:
        print("\n🛑 Exiting. Goodbye!")


if __name__ == "__main__":
    main()