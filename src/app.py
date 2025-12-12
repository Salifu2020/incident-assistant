import os
import streamlit as st
import requests
import logging
from datetime import datetime
import time

os.environ["PYTORCH_NO_LIBRARY_FALLBACK"] = "1"

API_URL = "http://127.0.0.1:8000"

# Get project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "streamlit.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Incident Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Incident Assistant - Knowledge Base Assistant"
    }
)

# Custom CSS for modern UI
st.markdown(
    """
    <style>
    /* Main container */
    .main {
        padding-top: 2rem;
    }
    
    /* Header */
    .header-container {
        text-align: center;
        padding: 1.5rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: white;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
    }
    
    .header-subtitle {
        font-size: 1rem;
        color: rgba(255, 255, 255, 0.9);
        margin-top: 0.5rem;
    }
    
    /* Chat bubbles */
    .chat-container {
        margin-bottom: 1.5rem;
    }
    
    .message-user {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem 1.25rem;
        border-radius: 18px 18px 4px 18px;
        margin-left: 20%;
        margin-bottom: 0.75rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        word-wrap: break-word;
    }
    
    .message-bot {
        background: #f0f2f6;
        color: #1f2937;
        padding: 1rem 1.25rem;
        border-radius: 18px 18px 18px 4px;
        margin-right: 20%;
        margin-bottom: 0.75rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        border-left: 4px solid #667eea;
        word-wrap: break-word;
    }
    
    .message-time {
        font-size: 0.75rem;
        color: rgba(0, 0, 0, 0.5);
        margin-top: 0.5rem;
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 10px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    /* Input */
    .stTextInput>div>div>input {
        border-radius: 10px;
        padding: 0.75rem;
    }
    
    /* Status badge */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0.25rem;
    }
    
    .status-online {
        background: #10b981;
        color: white;
    }
    
    .status-offline {
        background: #ef4444;
        color: white;
    }
    
    /* Example questions */
    .example-question {
        background: white;
        border: 2px solid #e5e7eb;
        border-radius: 10px;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .example-question:hover {
        border-color: #667eea;
        background: #f9fafb;
        transform: translateX(5px);
    }
    
    /* Floating sidebar toggle button */
    .sidebar-toggle {
        position: fixed;
        top: 20px;
        left: 20px;
        z-index: 999;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        font-size: 1.5rem;
        cursor: pointer;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        transition: all 0.3s;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .sidebar-toggle:hover {
        transform: scale(1.1);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
    }
    
    /* Show toggle only when sidebar might be closed */
    @media (max-width: 768px) {
        .sidebar-toggle {
            display: flex;
        }
    }
    
    /* Keep header visible for sidebar toggle access */
    footer {visibility: hidden;}
    
    /* Make sure the menu button is visible */
    [data-testid="stHeader"] {
        visibility: visible !important;
    }
    
    /* Help banner styling */
    .help-banner {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # Format: (role, message, timestamp, sources)
if "api_status" not in st.session_state:
    st.session_state.api_status = None
if "kb_status" not in st.session_state:
    st.session_state.kb_status = None
if "show_documents" not in st.session_state:
    st.session_state.show_documents = False

MAX_HISTORY = 50

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Settings & Status")
    st.caption("💡 Use ☰ menu in top-left to toggle sidebar")
    st.markdown("---")
    
    # API Status Check
    if st.button("🔄 Check API Status", use_container_width=True):
        try:
            status_resp = requests.get(f"{API_URL}/status", timeout=2)
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                st.session_state.api_status = "online"
                st.session_state.kb_status = status_data
                st.success("✅ API Connected")
            else:
                st.session_state.api_status = "offline"
                st.error("❌ API Error")
        except:
            st.session_state.api_status = "offline"
            st.error("❌ Cannot connect to API")
    
    # Display status
    if st.session_state.api_status:
        status_class = "status-online" if st.session_state.api_status == "online" else "status-offline"
        status_text = "🟢 Online" if st.session_state.api_status == "online" else "🔴 Offline"
        st.markdown(f'<div class="status-badge {status_class}">{status_text}</div>', unsafe_allow_html=True)
    
    if st.session_state.kb_status is not None:
        kb_data = st.session_state.kb_status
        if isinstance(kb_data, dict):
            chunk_count = kb_data.get("knowledge_base_chunks", 0)
            doc_count = kb_data.get("document_count", 0)
            if chunk_count == 0:
                st.warning("⚠️ **Knowledge Base is empty!** Upload documents to get started.")
            else:
                st.info(f"📚 Knowledge Base: **{chunk_count}** chunks from **{doc_count}** document(s)")
                if doc_count > 0:
                    documents = kb_data.get("documents", [])
                    with st.expander(f"📄 View Documents ({doc_count})"):
                        for doc in documents[:10]:  # Show first 10
                            st.text(f"• {doc}")
                        if len(documents) > 10:
                            st.caption(f"... and {len(documents) - 10} more")
        else:
            # Legacy format
            chunk_count = kb_data if isinstance(kb_data, int) else 0
            if chunk_count == 0:
                st.warning("⚠️ **Knowledge Base is empty!** Upload documents to get started.")
            else:
                st.info(f"📚 Knowledge Base: **{chunk_count}** chunks")
    
    st.markdown("---")
    
    # Search History Section
    st.markdown("### 📜 Search History")
    if st.button("🕐 View History", use_container_width=True):
        st.session_state.show_history = True
        st.rerun()
    
    # Saved Queries Section
    st.markdown("### ⭐ Saved Queries")
    if st.button("💾 View Saved", use_container_width=True):
        st.session_state.show_saved_queries = True
        st.rerun()
    
    st.markdown("---")
    
    # Document Management Section
    st.markdown("### 📚 Document Management")
    if st.button("📋 View All Documents", use_container_width=True):
        st.session_state.show_documents = True
        st.rerun()
    
    st.markdown("---")
    
    # Quick actions
    st.markdown("### 🚀 Quick Actions")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    
    if st.button("📥 Export Chat", use_container_width=True):
        if st.session_state.chat_history:
            export_text = "\n\n".join([
                f"**You:** {msg[0]}\n**Assistant:** {msg[1]}"
                for msg in st.session_state.chat_history
            ])
            st.download_button(
                "⬇️ Download Chat History",
                export_text,
                file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
    
    st.markdown("---")
    
    # File Upload in Sidebar
    st.markdown("### 📁 Upload Documents")
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "docx", "txt", "csv", "html"],
        help="Upload documents to enhance the knowledge base",
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        with st.spinner("Uploading..."):
            try:
                file_ext = uploaded_file.name.split('.')[-1].lower()
                mime_types = {
                    "pdf": "application/pdf",
                    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "txt": "text/plain",
                    "csv": "text/csv",
                    "html": "text/html"
                }
                mime_type = mime_types.get(file_ext, "application/octet-stream")
                
                files = {"file": (uploaded_file.name, uploaded_file, mime_type)}
                upload_resp = requests.post(f"{API_URL}/upload", files=files, timeout=30)
                
                if upload_resp.status_code == 200:
                    st.success(f"✅ {uploaded_file.name}")
                    st.info("⏳ Processing in background...")
                    logger.info(f"Uploaded: {uploaded_file.name}")
                    # Refresh KB status after a delay (processing happens in background)
                    st.info("💡 **Tip:** Processing happens in the background. Wait 5-10 seconds, then click '🔄 Check API Status' to see updated chunk count.")
                    time.sleep(2)
                    try:
                        status_resp = requests.get(f"{API_URL}/status", timeout=2)
                        if status_resp.status_code == 200:
                            st.session_state.kb_status = status_resp.json()
                    except:
                        pass
                else:
                    st.error(f"❌ Upload failed: {upload_resp.status_code}")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

# Sidebar toggle helper banner
st.markdown(
    """
    <div class="help-banner">
        <strong>💡 Sidebar Closed?</strong> Look for the <strong style="font-size: 1.3em;">☰</strong> hamburger menu icon 
        in the <strong>top-left corner</strong> of this page and click it to reopen the sidebar. 
        The sidebar contains file upload, settings, and quick actions.
    </div>
    """,
    unsafe_allow_html=True
)

# Main content
st.markdown(
    """
    <div class="header-container">
        <h1 class="header-title">📚 Incident Assistant</h1>
        <p class="header-subtitle">Your intelligent knowledge base assistant</p>
    </div>
    """,
    unsafe_allow_html=True
)

# Document Management Dashboard
if st.session_state.get("show_documents", False):
    st.markdown("---")
    st.markdown("### 📚 Document Management Dashboard")
    
    # Show loading spinner
    try:
        with st.spinner("Loading documents..."):
            docs_resp = requests.get(f"{API_URL}/documents", timeout=30)
        
        if docs_resp.status_code == 200:
            data = docs_resp.json()
            documents = data.get("documents", [])
            total_docs = data.get("total_documents", 0)
            total_chunks = data.get("total_chunks", 0)
            
            # Summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Documents", total_docs)
            with col2:
                st.metric("Total Chunks", total_chunks)
            with col3:
                avg_chunks = round(total_chunks / total_docs, 1) if total_docs > 0 else 0
                st.metric("Avg Chunks/Doc", avg_chunks)
            
            if total_docs == 0:
                st.info("📭 No documents in the knowledge base. Upload documents to get started!")
            else:
                st.markdown("---")
                
                # Document table
                for idx, doc in enumerate(documents):
                    with st.container():
                        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                        
                        with col1:
                            file_icon = {
                                "pdf": "📄",
                                "docx": "📝",
                                "txt": "📃",
                                "csv": "📊",
                                "html": "🌐"
                            }.get(doc.get("file_type", "").lower(), "📄")
                            
                            st.markdown(f"**{file_icon} {doc.get('filename', 'Unknown')}**")
                            if doc.get('upload_date'):
                                st.caption(f"Uploaded: {doc.get('upload_date')}")
                        
                        with col2:
                            st.metric("Chunks", doc.get("chunk_count", 0))
                        
                        with col3:
                            file_size = doc.get("file_size", 0)
                            if file_size:
                                size_mb = file_size / (1024 * 1024)
                                st.metric("Size", f"{size_mb:.2f} MB")
                            else:
                                st.metric("Size", "N/A")
                        
                        with col4:
                            # Delete button with confirmation
                            delete_key = f"delete_{idx}_{doc.get('filename', '')}"
                            confirm_key = f"confirm_{delete_key}"
                            
                            if st.session_state.get(confirm_key, False):
                                col_confirm, col_cancel = st.columns(2)
                                with col_confirm:
                                    if st.button("✅ Confirm", key=f"yes_{delete_key}", use_container_width=True):
                                        try:
                                            delete_resp = requests.delete(
                                                f"{API_URL}/documents/{doc.get('filename')}",
                                                timeout=10
                                            )
                                            if delete_resp.status_code == 200:
                                                st.success(f"✅ Deleted {doc.get('filename')}")
                                                st.session_state[confirm_key] = False
                                                time.sleep(1)
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Delete failed: {delete_resp.text}")
                                                st.session_state[confirm_key] = False
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                                            st.session_state[confirm_key] = False
                                with col_cancel:
                                    if st.button("❌ Cancel", key=f"no_{delete_key}", use_container_width=True):
                                        st.session_state[confirm_key] = False
                                        st.rerun()
                            else:
                                if st.button("🗑️ Delete", key=delete_key, use_container_width=True):
                                    st.session_state[confirm_key] = True
                                    st.rerun()
                        
                        st.markdown("---")
                
                # Close button
                if st.button("❌ Close Dashboard", use_container_width=True):
                    st.session_state.show_documents = False
                    st.rerun()
        else:
            st.error(f"❌ Failed to load documents: {docs_resp.status_code}")
    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. The knowledge base might be very large. Please try again.")
        st.info("💡 **Tip:** If you have many documents, the query may take longer. The timeout has been increased to 30 seconds.")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure the API server is running.")
        st.info("💡 **Tip:** Start the API server with: `python run_api.py`")
    except Exception as e:
        st.error(f"❌ Error loading documents: {str(e)}")
        st.info("💡 **Tip:** Check the API logs in `logs/api.log` for more details.")
    
    st.markdown("---")

# Search History Dashboard
if st.session_state.get("show_history", False):
    st.markdown("---")
    st.markdown("### 📜 Search History")
    
    try:
        with st.spinner("Loading history..."):
            history_resp = requests.get(f"{API_URL}/history?limit=100", timeout=10)
        
        if history_resp.status_code == 200:
            data = history_resp.json()
            history = data.get("history", [])
            total = data.get("total", 0)
            
            if total == 0:
                st.info("📭 No search history yet. Start asking questions to build your history!")
            else:
                st.metric("Total Queries", total)
                st.markdown("---")
                
                # Display history items
                for idx, entry in enumerate(history):
                    with st.container():
                        col1, col2, col3 = st.columns([4, 1, 1])
                        
                        with col1:
                            st.markdown(f"**{entry.get('query', 'Unknown query')}**")
                            timestamp = entry.get('timestamp', '')
                            if timestamp:
                                try:
                                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                    st.caption(f"📅 {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                except:
                                    st.caption(f"📅 {timestamp}")
                        
                        with col2:
                            if st.button("🔍 Use", key=f"use_history_{idx}", use_container_width=True):
                                st.session_state.example_query = entry.get('query', '')
                                st.session_state.show_history = False
                                st.rerun()
                        
                        with col3:
                            if st.button("🗑️", key=f"delete_history_{idx}", use_container_width=True):
                                try:
                                    delete_resp = requests.delete(
                                        f"{API_URL}/history/{entry.get('timestamp', '')}",
                                        timeout=5
                                    )
                                    if delete_resp.status_code == 200:
                                        st.success("✅ Deleted")
                                        time.sleep(0.5)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                        
                        st.markdown("---")
                
                # Clear all button
                if st.button("🗑️ Clear All History", use_container_width=True, type="secondary"):
                    try:
                        clear_resp = requests.delete(f"{API_URL}/history", timeout=5)
                        if clear_resp.status_code == 200:
                            st.success("✅ History cleared")
                            time.sleep(0.5)
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        else:
            st.error(f"❌ Failed to load history: {history_resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure the API server is running.")
    except Exception as e:
        st.error(f"❌ Error loading history: {str(e)}")
    
    # Close button
    if st.button("❌ Close History", use_container_width=True):
        st.session_state.show_history = False
        st.rerun()
    
    st.markdown("---")

# Saved Queries Dashboard
if st.session_state.get("show_saved_queries", False):
    st.markdown("---")
    st.markdown("### ⭐ Saved Queries")
    
    try:
        with st.spinner("Loading saved queries..."):
            saved_resp = requests.get(f"{API_URL}/saved-queries", timeout=10)
        
        if saved_resp.status_code == 200:
            data = saved_resp.json()
            saved_queries = data.get("saved_queries", [])
            total = data.get("total", 0)
            
            if total == 0:
                st.info("📭 No saved queries yet. Save frequently used queries for quick access!")
            else:
                st.metric("Saved Queries", total)
                st.markdown("---")
                
                # Display saved queries
                for idx, query in enumerate(saved_queries):
                    with st.container():
                        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                        
                        with col1:
                            name = query.get('name', query.get('query', 'Unknown'))
                            st.markdown(f"**{name}**")
                            desc = query.get('description', '')
                            if desc:
                                st.caption(desc)
                            st.caption(f"💬 {query.get('query', '')[:60]}...")
                            usage = query.get('usage_count', 0)
                            if usage > 0:
                                st.caption(f"📊 Used {usage} time(s)")
                        
                        with col2:
                            if st.button("🔍 Use", key=f"use_saved_{idx}", use_container_width=True):
                                # Increment usage
                                try:
                                    import urllib.parse
                                    requests.post(
                                        f"{API_URL}/saved-queries/{urllib.parse.quote(query.get('query', ''))}/use",
                                        timeout=5
                                    )
                                except:
                                    pass
                                st.session_state.example_query = query.get('query', '')
                                st.session_state.show_saved_queries = False
                                st.rerun()
                        
                        with col3:
                            if st.button("✏️ Edit", key=f"edit_saved_{idx}", use_container_width=True):
                                st.session_state[f"editing_query_{idx}"] = True
                                st.rerun()
                        
                        with col4:
                            if st.button("🗑️", key=f"delete_saved_{idx}", use_container_width=True):
                                try:
                                    import urllib.parse
                                    delete_resp = requests.delete(
                                        f"{API_URL}/saved-queries/{urllib.parse.quote(query.get('query', ''))}",
                                        timeout=5
                                    )
                                    if delete_resp.status_code == 200:
                                        st.success("✅ Deleted")
                                        time.sleep(0.5)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                        
                        # Edit form
                        if st.session_state.get(f"editing_query_{idx}", False):
                            with st.form(f"edit_form_{idx}"):
                                new_name = st.text_input("Name", value=query.get('name', ''), key=f"name_{idx}")
                                new_desc = st.text_area("Description", value=query.get('description', ''), key=f"desc_{idx}")
                                col_submit, col_cancel = st.columns(2)
                                with col_submit:
                                    if st.form_submit_button("💾 Save"):
                                        try:
                                            update_resp = requests.put(
                                                f"{API_URL}/saved-queries",
                                                json={
                                                    "query": query.get('query', ''),
                                                    "name": new_name,
                                                    "description": new_desc
                                                },
                                                timeout=5
                                            )
                                            if update_resp.status_code == 200:
                                                st.success("✅ Updated")
                                                st.session_state[f"editing_query_{idx}"] = False
                                                time.sleep(0.5)
                                                st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                                with col_cancel:
                                    if st.form_submit_button("❌ Cancel"):
                                        st.session_state[f"editing_query_{idx}"] = False
                                        st.rerun()
                        
                        st.markdown("---")
        else:
            st.error(f"❌ Failed to load saved queries: {saved_resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure the API server is running.")
    except Exception as e:
        st.error(f"❌ Error loading saved queries: {str(e)}")
    
    # Close button
    if st.button("❌ Close Saved Queries", use_container_width=True):
        st.session_state.show_saved_queries = False
        st.rerun()
    
    st.markdown("---")

# Troubleshooting section
with st.expander("🔧 Troubleshooting: No results found?", expanded=False):
    st.markdown("""
    **If you're getting 'No relevant information found' even after uploading documents:**
    
    1. **⏱️ Wait for processing** - Documents are processed in the background. Wait 5-10 seconds after upload, then click "🔄 Check API Status" in the sidebar.
    
    2. **📊 Check knowledge base** - Use the sidebar status check to verify chunks were added. You should see chunk count > 0.
    
    3. **🔍 Try different queries** - Use keywords that are likely in your documents. Be specific but not too narrow.
    
    4. **📄 Verify document content** - Ensure your documents contain readable text (not just images or scanned PDFs).
    
    5. **💬 Rephrase your question** - Try:
       - Using different keywords from your documents
       - Asking more general questions first
       - Breaking complex questions into simpler ones
    
    6. **📝 Check logs** - Review API logs in `logs/api.log` for processing errors.
    """)

# Add a prominent help section for sidebar access
st.info("""
    **📌 Sidebar Access:** If the sidebar is closed, click the **☰ (hamburger menu)** icon in the **top-left corner** 
    of your browser window to reopen it. The sidebar contains file upload, settings, and quick actions.
""")

# Example questions
st.markdown("### 💡 Example Questions")
example_cols = st.columns(3)
example_questions = [
    "What is the billing process?",
    "How do I handle a student inquiry?",
    "What are the payment deadlines?",
]

for i, (col, question) in enumerate(zip(example_cols, example_questions)):
    with col:
        if st.button(question, key=f"example_{i}", use_container_width=True):
            st.session_state.example_query = question
            st.rerun()

# Handle example query
if "example_query" in st.session_state:
    query = st.session_state.example_query
    del st.session_state.example_query
else:
    query = None

# Chat input
if query is None:
    query = st.chat_input("Ask a question...", key="chat_input")

if query:
    if query.strip():
        logger.info(f"Query: {query}")
        
        # Add user message to history
        timestamp = datetime.now().strftime("%H:%M")
        st.session_state.chat_history.append(("user", query.strip(), timestamp))
        
        # Get response
        with st.spinner("🤔 Thinking..."):
            try:
                start_time = time.time()
                response = requests.post(f"{API_URL}/ask", json={"query": query}, timeout=60)
                elapsed_time = time.time() - start_time
                
                if response.status_code == 200:
                    response_data = response.json()
                    answer = response_data.get("response", "No answer received")
                    sources = response_data.get("sources", [])
                    answer_timestamp = datetime.now().strftime("%H:%M")
                    st.session_state.chat_history.append(("assistant", answer, answer_timestamp, sources))
                    logger.info(f"Response time: {elapsed_time:.2f}s, Sources: {len(sources)}")
                else:
                    error_msg = f"⚠️ Error {response.status_code}: {response.text}"
                    st.session_state.chat_history.append(("assistant", error_msg, timestamp, []))
            except requests.exceptions.ConnectionError:
                error_msg = "❌ Cannot connect to API. Please ensure the server is running."
                st.session_state.chat_history.append(("assistant", error_msg, timestamp, []))
                st.error(error_msg)
            except requests.exceptions.Timeout:
                error_msg = "⏱️ Request timed out. Please try again."
                st.session_state.chat_history.append(("assistant", error_msg, timestamp, []))
                st.error(error_msg)
            except Exception as e:
                error_msg = f"❌ Unexpected error: {str(e)}"
                st.session_state.chat_history.append(("assistant", error_msg, timestamp, []))
                st.error(error_msg)
        
        st.rerun()

# Display chat history
st.markdown("---")
st.markdown("### 💬 Conversation")

if not st.session_state.chat_history:
    st.info("👋 Start a conversation by asking a question or clicking an example above!")
else:
    # Display in reverse order (newest first) or normal order
    for idx, item in enumerate(reversed(st.session_state.chat_history[-MAX_HISTORY:])):
        # Handle both old format (3 items) and new format (4 items with sources)
        if len(item) == 3:
            role, message, msg_time = item
            sources = []
        else:
            role, message, msg_time, sources = item
        
        if role == "user":
            col_msg, col_save = st.columns([5, 1])
            with col_msg:
                st.markdown(
                    f"""
                    <div class="message-user">
                        <strong>You</strong>
                        <div style="margin-top: 0.5rem;">{message}</div>
                        <div class="message-time">{msg_time}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_save:
                # Check if already saved
                is_saved = False
                try:
                    saved_resp = requests.get(f"{API_URL}/saved-queries", timeout=5)
                    if saved_resp.status_code == 200:
                        saved_queries = saved_resp.json().get("saved_queries", [])
                        is_saved = any(sq.get("query") == message for sq in saved_queries)
                except:
                    pass
                
                save_key = f"save_query_{idx}"
                if not is_saved:
                    if st.button("⭐", key=save_key, help="Save this query", use_container_width=True):
                        st.session_state[f"show_save_dialog_{idx}"] = True
                        st.rerun()
                else:
                    st.button("⭐", key=f"saved_{save_key}", disabled=True, use_container_width=True)
            
            # Save dialog
            if st.session_state.get(f"show_save_dialog_{idx}", False):
                with st.form(f"save_form_{idx}"):
                    save_name = st.text_input("Name (optional)", value=message[:50], key=f"save_name_{idx}")
                    save_desc = st.text_area("Description (optional)", key=f"save_desc_{idx}")
                    col_save_btn, col_cancel_btn = st.columns(2)
                    with col_save_btn:
                        if st.form_submit_button("💾 Save"):
                            try:
                                save_resp = requests.post(
                                    f"{API_URL}/saved-queries",
                                    json={
                                        "query": message,
                                        "name": save_name,
                                        "description": save_desc
                                    },
                                    timeout=5
                                )
                                if save_resp.status_code == 200:
                                    st.success("✅ Saved!")
                                    st.session_state[f"show_save_dialog_{idx}"] = False
                                    time.sleep(0.5)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                    with col_cancel_btn:
                        if st.form_submit_button("❌ Cancel"):
                            st.session_state[f"show_save_dialog_{idx}"] = False
                            st.rerun()
        else:
            # Format sources HTML
            sources_html = ""
            if sources and len(sources) > 0:
                sources_list = []
                for source in sources:
                    source_name = source.get("source", "Unknown")
                    relevance = source.get("relevance", 0)
                    
                    # Determine relevance class
                    if relevance >= 0.7:
                        rel_class = "relevance-high"
                        rel_label = "High"
                    elif relevance >= 0.4:
                        rel_class = "relevance-medium"
                        rel_label = "Medium"
                    else:
                        rel_class = "relevance-low"
                        rel_label = "Low"
                    
                    sources_list.append(
                        f"""
                        <div class="source-item">
                            <span class="source-name">📄 {source_name}</span>
                            <span class="source-relevance">
                                <span class="relevance-badge {rel_class}">{rel_label} ({relevance:.0%})</span>
                            </span>
                        </div>
                        """
                    )
                
                sources_html = f"""
                <div class="sources-container">
                    <strong style="color: #667eea; font-size: 0.9rem;">📚 Sources:</strong>
                    {"".join(sources_list)}
                </div>
                """
            
            st.markdown(
                f"""
                <div class="message-bot">
                    <strong>📚 Assistant</strong>
                    <div style="margin-top: 0.5rem;">{message}</div>
                    {sources_html}
                    <div class="message-time">{msg_time}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col2:
    st.markdown(
        "<div style='text-align: center; color: #6b7280; font-size: 0.85rem;'>"
        "Powered by FastAPI & Streamlit | Incident Assistant v1.0"
        "</div>",
        unsafe_allow_html=True
    )
