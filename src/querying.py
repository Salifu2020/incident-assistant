from .ingestion import DocumentProcessor
import ollama


class KnowledgeAssistant:
    def __init__(self, processor, model_name: str = "mistral", max_context_chars=2500, enable_streaming=True):
        self.processor = processor
        self.llm_model = model_name
        self.max_context_chars = max_context_chars
        self.enable_streaming = enable_streaming
        self.reset_history()

    def reset_history(self):
        self.chat_history = [
            {
                "role": "system",
                "content": (
                    "You are a helpful, knowledgeable assistant. Answer questions concisely and accurately "
                    "using only the information provided in the context.\n\n"
                    "Guidelines:\n"
                    "- Answer directly and confidently, as if you know the information\n"
                    "- Be specific and cite relevant details from the context\n"
                    "- If the context doesn't contain the answer, say so briefly\n"
                    "- Never make up information or use knowledge outside the context\n"
                    "- Keep answers concise but complete"
                )
            }
        ]

    def retrieve_context(self, query, k=4):
        """Retrieve context from the knowledge base with source information."""
        try:
            # Quick check if collection exists and has data
            try:
                collection_count = self.processor.collection.count()
                if collection_count == 0:
                    return "", []
            except Exception:
                return "", []
            
            # Adaptive k: use fewer results for faster retrieval, but ensure we have enough
            n_results = min(k, max(3, collection_count // 10)) if collection_count else k
            
            # Query with optimized parameters
            results = self.processor.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['documents', 'distances', 'metadatas']
            )
            
            docs = results.get('documents', [[]])[0]
            distances = results.get('distances', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            
            if not docs:
                return "", []
            
            # Smart filtering: use adaptive threshold based on result quality
            # If top result is very good (distance < 0.3), be more selective
            # If top result is mediocre, include more results
            # Lower threshold to be more inclusive
            top_distance = distances[0] if distances else 1.0
            threshold = 0.5 if top_distance < 0.3 else 0.85  # More lenient threshold
            
            filtered_docs = []
            filtered_sources = []  # Track sources for each chunk
            total_length = 0
            
            for i, (doc, distance) in enumerate(zip(docs, distances)):
                if distance < threshold and total_length < self.max_context_chars:
                    doc_text = doc.strip() if doc else ""
                    if doc_text:
                        doc_length = len(doc_text)
                        # Stop if adding this doc would exceed limit
                        if total_length + doc_length > self.max_context_chars:
                            # Try to add partial if we have space
                            remaining = self.max_context_chars - total_length
                            if remaining > 200:  # Only if meaningful space remains
                                filtered_docs.append(doc_text[:remaining])
                                # Get source info
                                source_info = metadatas[i] if metadatas and i < len(metadatas) else {}
                                filtered_sources.append({
                                    "source": source_info.get("source", "Unknown"),
                                    "relevance": round(1 - distance, 3),  # Convert distance to relevance score
                                    "distance": round(distance, 3)
                                })
                            break
                        filtered_docs.append(doc_text)
                        total_length += doc_length
                        # Get source info
                        source_info = metadatas[i] if metadatas and i < len(metadatas) else {}
                        filtered_sources.append({
                            "source": source_info.get("source", "Unknown"),
                            "relevance": round(1 - distance, 3),  # Convert distance to relevance score
                            "distance": round(distance, 3)
                        })
            
            # If no docs passed threshold, use top result anyway (fallback)
            if not filtered_docs and docs:
                # Use at least the top result even if below threshold
                top_doc = docs[0].strip() if docs[0] else ""
                if top_doc:
                    filtered_docs = [top_doc[:self.max_context_chars]]
                    if metadatas and len(metadatas) > 0:
                        source_info = metadatas[0]
                        filtered_sources = [{
                            "source": source_info.get("source", "Unknown"),
                            "relevance": round(1 - distances[0], 3) if distances else 0.5,
                            "distance": round(distances[0], 3) if distances else 0.5
                        }]
            
            if not filtered_docs:
                return "", []
            
            # Join with minimal separator for efficiency
            context = "\n\n".join(filtered_docs)
            
            # Deduplicate sources and sort by relevance
            unique_sources = {}
            for source in filtered_sources:
                source_name = source["source"]
                if source_name not in unique_sources or source["relevance"] > unique_sources[source_name]["relevance"]:
                    unique_sources[source_name] = source
            
            # Sort by relevance (highest first)
            sorted_sources = sorted(unique_sources.values(), key=lambda x: x["relevance"], reverse=True)
            
            return context[:self.max_context_chars], sorted_sources  # Final safety trim

        except Exception as e:
            print(f"❌ Error retrieving context: {type(e).__name__}: {e}")
            return "", []

    def generate_response(self, query, context):
        """Generate response with optimized prompt and optional streaming."""
        # Optimized prompt format for faster processing
        user_message = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
        
        # Use minimal history for faster processing (only last 2 exchanges)
        recent_history = self.chat_history[-2:] if len(self.chat_history) > 2 else self.chat_history
        messages = recent_history + [{"role": "user", "content": user_message}]

        try:
            if self.enable_streaming:
                # Try streaming for faster perceived response time
                try:
                    response_text = ""
                    stream = ollama.chat(
                        model=self.llm_model,
                        messages=messages,
                        stream=True,
                        options={
                            "temperature": 0.3,  # Lower temperature for more focused answers
                            "num_predict": 500,  # Limit response length for speed
                        }
                    )
                    for chunk in stream:
                        if 'message' in chunk and 'content' in chunk['message']:
                            response_text += chunk['message']['content']
                    answer = response_text.strip()
                except Exception:
                    # Fallback to non-streaming if streaming fails
                    response = ollama.chat(
                        model=self.llm_model,
                        messages=messages,
                        stream=False,
                        options={
                            "temperature": 0.3,
                            "num_predict": 500,
                        }
                    )
                    answer = response["message"]["content"].strip()
            else:
                response = ollama.chat(
                    model=self.llm_model,
                    messages=messages,
                    stream=False,
                    options={
                        "temperature": 0.3,
                        "num_predict": 500,
                    }
                )
                answer = response["message"]["content"].strip()

            # Clean up common prefixes
            prefixes = [
                "according to the context",
                "based on the context",
                "from the context",
                "according to the provided",
                "based on the provided",
            ]
            answer_lower = answer.lower()
            for prefix in prefixes:
                if answer_lower.startswith(prefix):
                    answer = answer[len(prefix):].lstrip(":,. ")
                    break

            # Update history (keep it minimal)
            if len(self.chat_history) > 6:  # Keep only last 3 exchanges
                self.chat_history = self.chat_history[0:1] + self.chat_history[-5:]
            
            self.chat_history.append({"role": "user", "content": query})
            self.chat_history.append({"role": "assistant", "content": answer})
            
            return answer

        except Exception as e:
            return f"❌ Error: {str(e)}"

    def ask_question(self, query):
        """Ask a question and return answer with source citations."""
        # Quick validation
        if not query or not query.strip():
            return "Please provide a valid question.", []
        
        # Check if knowledge base has any documents
        try:
            kb_count = self.processor.collection.count()
            if kb_count == 0:
                return "⚠️ Knowledge base is empty. Please upload documents first. Documents are processed in the background - wait a few seconds after uploading and try again.", []
        except Exception as e:
            return f"⚠️ Error accessing knowledge base: {str(e)}", []
        
        # Retrieve context with sources
        context, sources = self.retrieve_context(query)

        if not context:
            # Provide more helpful error message
            try:
                kb_count = self.processor.collection.count()
                if kb_count > 0:
                    return f"⚠️ No relevant information found for your query. The knowledge base has {kb_count} chunks, but they don't match your question. Try:\n- Rephrasing your question\n- Using different keywords\n- Asking a more general question", []
                else:
                    return "⚠️ Knowledge base is empty. Please upload documents and wait for processing to complete.", []
            except:
                return "⚠️ No relevant information found. Please ensure documents have been uploaded and processed, then try rephrasing your question.", []
        
        # Generate response
        try:
            response = self.generate_response(query, context)
            return response, sources
        except Exception as e:
            return f"❌ Error: {str(e)}", []
