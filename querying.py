from ingestion import DocumentProcessor
import ollama


class KnowledgeAssistant:
    def __init__(self, processor, model_name: str = "mistral", max_context_chars=3000):
        self.processor = processor
        self.llm_model = model_name
        self.max_context_chars = max_context_chars
        self.reset_history()

    def reset_history(self):
        self.chat_history = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant at the University of Miami.\n\n"
                    "You always answer concisely and clearly using only the context provided.\n"
                    "Never say things like 'According to the context', 'Based on the context', or anything similar.\n"
                    "Simply answer the question as if you already know the information — be confident and factual.\n"
                    "Do not make assumptions or add outside knowledge.\n"
                    "Even if the context is limited, provide the best possible answer strictly from it.\n"
                    "Do not say 'not provided in the context you've given'"
                )
            }
        ]
        self.accumulated_context = ""

    def retrieve_context(self, query, k=2):
        try:
            results = self.processor.collection.query(
                query_texts=[query],
                n_results=k
            )
            docs = results.get('documents', [[]])[0]
            new_context = "\n\n".join(doc for doc in docs if doc.strip())

            # Accumulate new context, avoiding overlength
            combined_context = (self.accumulated_context + "\n\n" + new_context).strip()
            if len(combined_context) > self.max_context_chars:
                # Trim from the beginning if we exceed max characters
                combined_context = combined_context[-self.max_context_chars:]

            self.accumulated_context = combined_context
            return self.accumulated_context

        except Exception as e:
            print(f"❌ Error retrieving context: {e}")
            return ""

    def generate_response(self, query, context):
        self.chat_history.append({
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {query}"
        })

        try:
            response = ollama.chat(
                model=self.llm_model,
                messages=self.chat_history,
                stream=False
            )
            answer = response["message"]["content"].strip()

            for phrase in [
                "According to the context",
                "Based on the context",
                "From the context provided",
                "According to the provided context",
                "According to the information provided",
                "Based on the provided information"
            ]:
                if answer.lower().startswith(phrase.lower()):
                    answer = answer[len(phrase):].lstrip(":,. ")

            self.chat_history.append({
                "role": "assistant",
                "content": answer
            })
            return answer

        except Exception as e:
            return f"❌ Ollama Error: {e}"

    def ask_question(self, query):
        context = self.retrieve_context(query)

        if not context:
            return "⚠️ No relevant context found to answer the question."

        print(f"\n--- Accumulated Context for: {query} ---\n{context[:300]}...\n")
        return self.generate_response(query, context)
