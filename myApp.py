import os
import streamlit as st
import requests
import logging

os.environ["PYTORCH_NO_LIBRARY_FALLBACK"] = "1"

API_URL = "http://127.0.0.1:8000"

# Configure logging to write to logs/streamlit.log
log_dir = "logs"
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

st.set_page_config(page_title="Incident Assistant", page_icon="♾️", layout="wide")

# Header section
st.markdown(
    """
    <style>
    .title-container {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0.75rem;
    }
    .title-text {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .bubble-user {
        background-color: #E0F7FA;
        padding: 0.8rem;
        border-radius: 1rem;
        margin-bottom: 0.5rem;
        color: #333;
    }
    .bubble-bot {
        background-color: #E8EAF6;
        padding: 0.8rem;
        border-radius: 1rem;
        margin-bottom: 1rem;
        color: #111;
    }
    .stButton>button {
        border-radius: 10px;
        padding: 0.5rem 1rem;
    }
    </style>
    <div class="title-container">
        <div class="title-text">Your Incident Assistant</div>
    </div>
    """,
    unsafe_allow_html=True
)

# Chat history state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

MAX_HISTORY = 20

# Chat interface
with st.form(key="query_form", clear_on_submit=True):
    query = st.text_input("How can I help you?", placeholder="e.g., When is billing notice sent to students?")
    submitted = st.form_submit_button("Ask")

if submitted:
    if query.strip():
        logger.info(f"User query submitted: {query}")
        with st.spinner("Retrieving. Hang tight..."):
            try:
                response = requests.post(f"{API_URL}/ask", json={"query": query})
                if response.status_code == 200:
                    answer = response.json().get("response", "No answer received")
                    logger.info(f"Assistant response: {answer}")
                elif response.status_code == 422:
                    answer = "⚠️ Invalid question format. Please check and try again."
                    logger.warning(f"Validation error for query: {query}")
                elif response.status_code == 400:
                    answer = "⚠️ Bad request. Please try again."
                    logger.warning(f"Bad request for query: {query}")
                else:
                    answer = f"❌ API Error {response.status_code}: {response.text}"
                    logger.error(f"API error {response.status_code}: {response.text}")
            except requests.exceptions.ConnectionError:
                answer = "❌ Cannot connect to the server. Is the API running?"
                logger.error("Connection error: Failed to reach backend.")
            except Exception as e:
                answer = f"❌ Unexpected error: {e}"
                logger.error(f"Frontend exception: {e}")

        st.session_state.chat_history.append((query.strip(), answer.strip()))
        st.session_state.chat_history = st.session_state.chat_history[-MAX_HISTORY:]
    else:
        st.warning("Please enter a question before submitting.")


# File uploader
with st.expander("📁 Upload a PDF to enhance the assistant's knowledge"):
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
    if uploaded_file:
        with st.spinner("Uploading and processing..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
                upload_resp = requests.post(f"{API_URL}/upload", files=files)
                if upload_resp.status_code == 200:
                    st.success("✅ File uploaded successfully!")
                    logger.info(f"Uploaded PDF: {uploaded_file.name}")
                elif upload_resp.status_code == 400:
                    st.error("⚠️ Only PDF files are supported.")
                    logger.warning(f"Upload rejected for: {uploaded_file.name}")
                else:
                    st.error(f"Upload failed: {upload_resp.status_code}")
                    logger.error(f"Upload failed with status {upload_resp.status_code}")
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to the API.")
                logger.error("Streamlit failed to connect to backend during upload.")
            except Exception as e:
                st.error(f" Unexpected error: {e}")
                logger.error(f"Unexpected upload error: {e}")

# Display conversation
st.markdown("---")
for idx, (user_msg, bot_msg) in enumerate(st.session_state.chat_history, 1):
    st.markdown(f'<div class="bubble-user"><strong>You {idx}:</strong><br>{user_msg}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="bubble-bot"><strong>Salibot {idx}:</strong><br>{bot_msg}</div>', unsafe_allow_html=True)

# Reset
if st.button("♻️ Reset Conversation"):
    logger.info("Conversation reset triggered by user.")
    st.session_state.chat_history = []
    st.rerun()
