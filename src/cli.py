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

            response = assistant.ask_question(query)
            print("Salibot:", response, "\n")

    except KeyboardInterrupt:
        print("\n🛑 Exiting. Goodbye!")


if __name__ == "__main__":
    main()