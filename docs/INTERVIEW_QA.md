# Interview Q&A — Incident Assistant Project

Prepared for discussing the project and Cursor usage in a 1:1 with a recruiter.

---

## Project Overview

### What is this project?

**Q: Can you describe the project in simple terms?**  
**A:** Incident Assistant is an app that lets people upload documents (PDFs, Word docs, spreadsheets, text files) and ask questions in plain English. The app searches through the documents and gives answers, showing which document or section each answer came from. You can chat with it, save common questions, and rate how helpful answers are. It supports multiple languages and user accounts with optional two-factor authentication.

---

### Why did you build it?

**Q: What problem does it solve?**  
**A:** When you have many documents—policy guides, manuals, incident reports—finding specific information quickly is hard. This app turns your documents into a searchable knowledge base so you can ask things like "What's our policy for X?" or "How do I handle Y?" and get instant answers with references. It's useful for support teams, internal knowledge bases, and anyone with lots of documentation.

---

### How long did it take?

**Q: How long have you been working on this project?**  
**A:** [Adjust based on your timeline] I've been building and iterating over [X weeks/months]. I focused on core features first (document upload, search, Q&A), then added conversations, authentication, and deployment. I've used Cursor throughout that process.

---

## Technical Questions

### Architecture

**Q: How does the app work technically?**  
**A:** It has three main parts:  
1. **Frontend** — A Streamlit web interface where users upload documents and ask questions.  
2. **API** — A FastAPI backend that handles uploads, stores documents, and runs searches.  
3. **Storage** — Documents are chunked, turned into embeddings, and stored in a vector database (ChromaDB or PostgreSQL with pgvector). When you ask a question, the app uses hybrid search—semantic and keyword—to find the most relevant chunks and sends them to an LLM (Ollama or Groq) to generate an answer. Responses can stream in real time, and answers include source citations.

---

**Q: What technologies did you use?**  
**A:** Python, FastAPI, Streamlit, ChromaDB (or pgvector for PostgreSQL), and sentence-transformers for embeddings. For the LLM, I can use either Ollama (self-hosted) or Groq (cloud API). I deploy with Docker—on Oracle Cloud I use a separate compose file with Ollama; elsewhere I can use nginx as a reverse proxy.

---

### Features

**Q: What are the main features?**  
**A:** Document upload (PDF, DOCX, TXT, CSV), semantic and hybrid search, Q&A with streaming and source citations, conversation history, saved queries, feedback (thumbs up/down, ratings), user authentication and 2FA, multi-language support, document filtering, analytics, and a CLI for headless use.

---

**Q: How does the search work?**  
**A:** Documents are split into chunks; each chunk is converted into an embedding that captures its meaning. Those embeddings are stored in ChromaDB or pgvector. When you ask a question, the question is embedded the same way, and the system runs a hybrid search—semantic similarity plus keyword matching—to find the most relevant chunks. Those chunks are sent to the LLM, which produces an answer and cites sources. The app can stream the response token-by-token for a faster feel.

---

## Cursor / AI Assistant Usage

### General usage

**Q: How did you use Cursor for this project?**  
**A:** I used Cursor as an AI coding assistant throughout development. It helped with writing code, finding bugs, adding features, creating deployment scripts, and documentation. I treated it as a pair programmer—I stayed in control, reviewed every suggestion, tested it, and only accepted what worked. I also used it to learn new APIs and patterns when needed.

---

**Q: Can you give specific examples of what Cursor helped with?**  
**A:** A few examples:  
1. **Deployment** — I moved from platforms with tight storage limits to Oracle Cloud. Cursor helped write a deployment guide, a Docker Compose setup, and a VM setup script. I checked each step against the Oracle UI and fixed anything that didn't match.  
2. **Bug fixing** — At one point the assistant's replies sometimes showed raw HTML instead of text. Cursor searched the codebase, identified the cause, and proposed fixes. I validated them and refined as needed.  
3. **Missing API endpoints** — Conversation features weren't working because the API didn't have the `/conversations` routes. Cursor helped add those endpoints in line with my existing code style.  
4. **Documentation** — Cursor helped draft a short, non-technical summary; I adjusted the wording so it was clear for non-technical readers.

---

**Q: Did you accept everything Cursor suggested?**  
**A:** No. I reviewed every suggestion. Some were wrong or didn't fit my setup. With the Oracle deployment, the exact steps differed from what Cursor first suggested, so I corrected the guide. I made the final decisions—for example, choosing Ollama vs Groq based on cost and the resources I had.

---

**Q: How did Cursor change how you work?**  
**A:** It sped up routine tasks—boilerplate, config, error handling, and documentation. It was especially helpful for exploring the codebase and understanding how pieces fit together. I still did the design, testing, and decisions; Cursor helped execute faster and reduce the tedious parts.

---

### Specific Cursor examples

**Q: Walk us through a specific task where you used Cursor.**  
**A:** For the Oracle Cloud deployment, I told Cursor I wanted to deploy on Oracle's Always Free tier. It proposed a deployment guide, a Docker Compose file without Ollama (to save memory), and a VM setup script. I wanted to use Ollama instead of Groq, so I asked it to switch. Cursor updated the config and the guide. I then tested the steps in Oracle's UI and fixed what didn't match—firewall and Security List configuration, for example. The final setup reflects both Cursor's draft and my edits.

---

**Q: Where did Cursor help the most?**  
**A:** Most on repetitive or exploratory work: deployment configs, API endpoint scaffolding, searching the codebase for bugs, and turning technical descriptions into clearer documentation. It was less useful for high-level architecture or performance decisions—those I figured out myself with Cursor as a helper.

---

**Q: What would you do differently with Cursor next time?**  
**A:** I'd be more explicit about my environment and constraints from the start—RAM, storage, target platform—so suggestions are more accurate. I'd also use Cursor earlier for tests and documentation instead of adding them at the end.

---

## Challenges & Problem-Solving

**Q: What was the hardest part of this project?**  
**A:** [Adjust to your experience] A few stand out:  
1. **Deployment constraints** — Free tiers often had limited storage. I moved to Oracle Cloud's Always Free tier, which gave enough storage and RAM for the app and Ollama.  
2. **Conversation display bug** — Sometimes the assistant's reply showed HTML tags instead of text. It took tracing through display logic and data flow to find and fix it.  
3. **Missing API endpoints** — The UI expected conversation endpoints that didn't exist. I had to add them and align them with the data model and frontend.

---

**Q: How did you debug the conversation display bug?**  
**A:** I searched the codebase for how messages were rendered. The bug was that in some cases HTML from the template was being stored or displayed as plain text. I added validation to block corrupted or HTML-only content from being stored and filtered it when loading conversations. Cursor helped locate the relevant code and propose fixes; I verified and refined them.

---

**Q: How did you decide on Ollama vs Groq?**  
**A:** Groq is simpler—it's a cloud API with a free tier and no local compute. Ollama runs on my own server. I chose Ollama on Oracle because I wanted full control, no API limits, and to avoid ongoing API costs. Oracle's A1.Flex ARM instances provide enough RAM (4GB+) for Ollama and a small model like phi3:mini. Cursor helped explain the trade-offs and update the deployment config when I switched.

---

## Deployment

**Q: Where is the app deployed?**  
**A:** On Oracle Cloud's Always Free tier, using an A1.Flex ARM instance with 4GB RAM. The app runs in Docker: one container for the API, one for Streamlit, and one for Ollama. Data (documents, ChromaDB, conversations) is stored on the instance. For other environments, I use a compose file with nginx as a reverse proxy and SSL.

---

**Q: Why Oracle Cloud?**  
**A:** Other free tiers had tight storage (e.g. 512MB–1GB). Oracle's Always Free tier offers up to 200GB storage and ARM instances with enough RAM for Ollama. I can run the full stack—API, frontend, and local LLM—without running out of space.

---

**Q: What's your deployment process?**  
**A:** I SSH into the Oracle VM, pull the latest code, rebuild the Docker images if needed, and run `docker compose -f docker-compose.oracle.yml up -d`. I have a setup script that installs Docker and configures the environment. I also configure the Oracle Security List (firewall) to allow ports 22, 8000, and 8501.

---

## Behavioral & Soft Skills

**Q: Tell me about a time you learned something new for this project.**  
**A:** I hadn't used vector databases or embeddings before. I learned how ChromaDB works, how to chunk documents for embeddings, and how semantic search differs from keyword search. I also explored hybrid search and streaming responses. Cursor helped with code and examples; I read docs and experimented to understand the concepts.

---

**Q: How do you ensure code quality when using AI?**  
**A:** I treat AI output as a starting point. I always read the suggested code, run it, and test it. I keep the codebase consistent, follow my own conventions, and use linters. I also use version control so I can revert changes if something goes wrong.

---

**Q: What would you add or improve next?**  
**A:** I'd consider: better UX for document management (bulk actions, processing feedback), improved performance for large knowledge bases, and more robust error handling. I've already implemented many UI improvements—sticky chat input, breadcrumb navigation, streaming indicators—so next I'd add monitoring and logging for production use, and perhaps answer verification or reranking for higher-quality responses.

---

## Quick Reference — One-Line Answers

| Question | Short Answer |
|----------|--------------|
| What does the app do? | Upload documents, ask questions in plain English, get AI answers with source citations. |
| What did Cursor help with? | Code, bugs, deployment scripts, docs, and understanding the codebase. |
| Did you accept everything from Cursor? | No—I reviewed, tested, and adjusted based on my setup and preferences. |
| Hardest challenge? | Deployment constraints (storage/RAM) and fixing the conversation display bug. |
| Tech stack? | Python, FastAPI, Streamlit, ChromaDB/pgvector, Ollama/Groq, Docker, Oracle Cloud. |
| Why Oracle? | More free storage (200GB) and enough RAM to run Ollama. |

---

*Good luck with your interview.*
