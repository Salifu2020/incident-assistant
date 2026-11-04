import os
import re
import streamlit as st
import streamlit.components.v1 as components
import requests
import logging
from datetime import datetime
import time
import json
import textwrap
import html
import hashlib
from urllib3.exceptions import ProtocolError
from requests.exceptions import ChunkedEncodingError

os.environ["PYTORCH_NO_LIBRARY_FALLBACK"] = "1"

# API URL - can be configured via environment variable
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")

def get_api_connection_error_message() -> str:
    """Get a helpful error message when API connection fails."""
    api_url = os.environ.get("API_URL", "http://127.0.0.1:8000")
    # Only show Streamlit Cloud guidance when actually running on Streamlit Cloud.
    is_streamlit_cloud = bool(os.environ.get("STREAMLIT_SHARING_MODE"))

    if (api_url.startswith("http://127.0.0.1") or api_url.startswith("http://localhost")) and is_streamlit_cloud:
        return (
            "❌ Cannot connect to API.\n\n"
            "**The API URL is set to localhost, which won't work on Streamlit Cloud.**\n\n"
            "**To fix this:**\n"
            "1. Deploy your FastAPI backend to Railway, Render, Fly.io, or another platform\n"
            "2. In Streamlit Cloud, go to: Settings → Secrets\n"
            "3. Add: `API_URL = \"https://your-backend-url.com\"`\n"
            "4. Redeploy your app\n\n"
            "See `STREAMLIT_CLOUD_DEPLOYMENT.md` for detailed instructions."
        )
    elif api_url.startswith("http://127.0.0.1") or api_url.startswith("http://localhost"):
        return (
            f"❌ Cannot connect to local API at `{api_url}`.\n\n"
            "**This is a local run issue (not Streamlit Cloud).**\n"
            "**Please check:**\n"
            "1. Is FastAPI running on that exact port?\n"
            "2. Are Streamlit and API using the same `API_URL` / `PORT` values?\n"
            "3. Restart Streamlit after changing environment variables.\n\n"
            "Tip: run `python run_api.py` and `python run_app.py` from fresh terminals."
        )
    else:
        return (
            f"❌ Cannot connect to API at `{api_url}`.\n\n"
            "**Please check:**\n"
            "1. Is the backend server running?\n"
            "2. Is the API URL correct in Streamlit Cloud secrets?\n"
            "3. Can you access the backend directly? Try: `curl {api_url}/health`\n\n"
            "See `STREAMLIT_CLOUD_DEPLOYMENT.md` for troubleshooting."
        )

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

# Helper function to log errors to both Streamlit UI and browser console
def log_error_to_console(error_message, error_type="Error", exception=None):
    """
    Log error to Streamlit UI and browser console.
    
    Args:
        error_message: The error message to display
        error_type: Type of error (Error, Warning, Info)
        exception: Optional exception object for detailed logging
    """
    # Log to Python logger
    if exception:
        logger.error(f"{error_type}: {error_message}", exc_info=exception)
    else:
        logger.error(f"{error_type}: {error_message}")
    
    # Display in Streamlit UI
    if error_type == "Warning":
        st.warning(f"⚠️ {error_message}")
    elif error_type == "Info":
        st.info(f"ℹ️ {error_message}")
    else:
        st.error(f"❌ {error_message}")
    
    # Send to browser console via JavaScript
    escaped_message = error_message.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$').replace('\n', '\\n').replace('\r', '\\r')
    exception_str = json.dumps(str(exception)) if exception else 'null'
    console_script = f"""
    <script>
        console.error('[Streamlit {error_type}]', `{escaped_message}`);
        if ({exception_str} !== null) {{
            console.error('[Exception Details]', {exception_str});
        }}
    </script>
    """
    st.markdown(console_script, unsafe_allow_html=True)

# Page configuration - respect ?sidebar=open for reopening when Streamlit's control is hidden
_sidebar_open = "sidebar" in st.query_params and st.query_params.get("sidebar") == "open"
_want_sidebar_reload = st.session_state.pop("_want_sidebar_reload", False)
st.set_page_config(
    page_title="Incident Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded" if _sidebar_open else "auto",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Incident Assistant - Knowledge Base Assistant"
    }
)

# Copilot-style UI Design
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700&family=DM+Sans:opsz,wght@9..40,400;9..40,500&display=swap');
    /* Global Styles - Fluid, Modern, Simplified */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    
    /* Main - Soft gradient background */
    .main {
        padding: 0;
        background: linear-gradient(180deg, #0c1222 0%, #0f172a 50%, #0a0f1a 100%);
        color: #e2e8f0;
    }
    
    /* Tab Navigation Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(15, 23, 42, 0.5);
        padding: 8px 12px;
        border-radius: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: 500;
        font-size: 14px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
    }
    
    /* Slim command bar - logo above, nav bar below */
    .zone-top-nav {
        background: rgba(15, 23, 42, 0.95);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid rgba(51, 65, 85, 0.35);
        margin: -1rem -1rem 0 -1rem;
        padding: 0.5rem 1.25rem 0.35rem 1.25rem;
    }
    .nav-brand-row {
        margin-bottom: 0.35rem;
    }
    /* Nav bar row (Chat | Documents | ... | avatar) - same visual bar as logo area */
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"]:first-of-type {
        margin-top: 0;
        padding: 0.35rem 0 0.35rem 0;
        background: transparent;
    }
    /* Nav bar columns - align nav items */
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:first-child {
        display: flex !important;
        align-items: center !important;
    }
    .nav-brand {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 1rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0;
        line-height: 1.2;
    }
    .nav-brand-icon {
        font-size: 1.75rem;
        opacity: 0.95;
        flex-shrink: 0;
    }
    .nav-brand-text {
        letter-spacing: -0.02em;
        white-space: nowrap;
    }
    .zone-nav-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0;
    }
    .zone-nav-tabs {
        display: flex;
        gap: 0.2rem;
        flex-wrap: wrap;
    }
    .zone-nav-tabs .stButton > button,
    .cmd-bar-nav .stButton > button {
        padding: 0.3rem 0.75rem !important;
        font-size: 0.8rem !important;
        border-radius: 6px !important;
        background: transparent !important;
        border: 1px solid transparent !important;
        min-height: 32px !important;
    }
    .zone-nav-tabs .stButton > button:hover,
    .cmd-bar-nav .stButton > button:hover {
        background: rgba(51, 65, 85, 0.5) !important;
    }
    .zone-nav-active .stButton > button,
    .cmd-bar-nav-active .stButton > button {
        background: rgba(59, 130, 246, 0.25) !important;
        border-color: rgba(59, 130, 246, 0.4) !important;
        color: #93c5fd !important;
    }
    /* Nav bar buttons - dark grey style */
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button {
        background: rgba(30, 41, 59, 0.9) !important;
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        color: #e2e8f0 !important;
    }
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button:hover {
        background: rgba(51, 65, 85, 0.9) !important;
    }
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button[kind="primary"] {
        background: rgba(59, 130, 246, 0.2) !important;
        border-color: rgba(59, 130, 246, 0.4) !important;
        color: #93c5fd !important;
    }
    /* Sidebar toggle in top nav */
    div[class*="st-key-nav_toggle_sidebar"] .stButton > button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0.4rem 0.75rem !important;
        border-radius: 10px !important;
        background: rgba(30, 41, 59, 0.9) !important;
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        color: #e2e8f0 !important;
        font-size: 1.1rem !important;
        min-width: 2.6rem !important;
        width: auto !important;
        box-shadow: none !important;
        transform: none !important;
    }
    div[class*="st-key-nav_toggle_sidebar"] .stButton > button:hover {
        background: rgba(51, 65, 85, 0.9) !important;
        border-color: rgba(148, 163, 184, 0.35) !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .cmd-bar-avatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid rgba(71, 85, 105, 0.5);
    }
    /* Profile avatar button - normal pill shape */
    div:has(.nav-avatar-col) .stButton > button {
        border-radius: 10px !important;
        padding: 0.5rem 1rem !important;
        background: rgba(30, 41, 59, 0.8) !important;
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        color: #e2e8f0 !important;
        width: 100% !important;
        min-width: unset !important;
        max-width: none !important;
        height: auto !important;
    }
    /* Nav bar - modern pill shape, full text, NOT circular */
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button {
        border-radius: 10px !important;
        width: 100% !important;
        min-width: 0 !important;
        max-width: none !important;
        height: auto !important;
        padding: 0.4rem 0.9rem !important;
    }
    /* Profile page avatar image - round */
    .profile-avatar-section ~ div [data-testid="stImage"] img {
        border-radius: 50% !important;
        object-fit: cover !important;
    }
    
    /* Right context panel - zone C layout */
    .zone-context-panel {
        background: rgba(30, 41, 59, 0.4);
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid rgba(71, 85, 105, 0.4);
        min-height: 200px;
    }
    .zone-context-panel h4 {
        font-size: 0.9rem;
        color: #94a3b8;
        margin: 0 0 0.75rem 0;
    }
    
    /* Header - legacy, kept for non-chat views */
    .header-container {
        text-align: center;
        padding: 0.75rem 2rem;
        background: rgba(15, 23, 42, 0.7);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid rgba(51, 65, 85, 0.4);
        margin-bottom: 0;
        transition: all 0.3s ease;
    }
    .header-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #94a3b8;
        margin: 0;
        letter-spacing: -0.02em;
        line-height: 1.3;
    }
    .header-subtitle {
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 0.2rem;
        font-weight: 400;
        opacity: 0.9;
    }
    
    /* Copilot-style empty state: centered greeting */
    .copilot-greeting {
        text-align: center;
        padding: 3rem 2rem 2rem;
        margin-bottom: 1rem;
    }
    .copilot-greeting h2 {
        font-size: 1.75rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0 0 0.5rem 0;
        letter-spacing: -0.02em;
    }
    .copilot-greeting p {
        font-size: 1.1rem;
        color: #94a3b8;
        margin: 0;
    }
    /* Suggestion pills - row of buttons below chat bar */
    .copilot-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        justify-content: center;
        margin-top: 1.5rem;
        padding: 0 1rem;
    }
    /* Constrain pill parent so overflow is clipped */
    [data-testid="stMarkdown"]:has(.copilot-pills-marker) ~ [data-testid="stHorizontalBlock"] .stButton,
    div:has(.copilot-pills-marker) ~ [data-testid="stHorizontalBlock"] .stButton {
        overflow: hidden !important;
        max-width: 100% !important;
        min-width: 0 !important;
    }
    .copilot-pills .stButton>button,
    div:has(.copilot-pills-marker) .stButton > button,
    div:has(.copilot-pills-marker) ~ div .stButton > button,
    div:has(.copilot-pills-marker) ~ [data-testid="stHorizontalBlock"] .stButton > button,
    [data-testid="stMarkdown"]:has(.copilot-pills-marker) ~ [data-testid="stHorizontalBlock"] .stButton > button,
    div.copilot-pills-marker ~ div .stButton > button {
        border-radius: 12px !important;
        padding: 0.5rem 1rem !important;
        font-size: 0.875rem !important;
        background: rgba(55, 65, 81, 0.9) !important;
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        color: #e5e7eb !important;
        min-width: 0 !important;
        max-width: 100% !important;
        width: 100% !important;
        height: auto !important;
        overflow: hidden !important;
        box-sizing: border-box !important;
        margin: 0 0.25rem 0.5rem 0.25rem !important;
        white-space: normal !important;
        text-overflow: unset !important;
        text-align: center !important;
        direction: ltr !important;
        display: block !important;
    }
    .copilot-pills .stButton>button:hover,
    div:has(.copilot-pills-marker) .stButton > button:hover {
        background: rgba(71, 85, 105, 0.8) !important;
        border-color: rgba(100, 116, 139, 0.6) !important;
    }
    /* Override blue - pills must stay dark grey (revert from primary) */
    div:has(.copilot-pills-marker) .stButton > button[kind="primary"],
    div:has(.copilot-pills-marker) .stButton > button {
        background: rgba(51, 65, 85, 0.6) !important;
        border-color: rgba(71, 85, 105, 0.5) !important;
        color: #e2e8f0 !important;
    }
    /* Nav bar - modern pill shape, full text, uniform height */
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:first-child .stButton > button {
        border-radius: 10px !important;
        width: 100% !important;
        min-width: unset !important;
        max-width: none !important;
        min-height: 38px !important;
        height: 38px !important;
        max-height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0.5rem 1rem !important;
        font-size: 0.9rem !important;
        line-height: 1 !important;
        overflow: hidden !important;
    }
    .zone-top-nav ~ div [data-testid="stHorizontalBlock"] > div:first-child .stButton > button[kind="secondary"] {
        background: rgba(30, 41, 59, 0.8) !important;
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        color: #e2e8f0 !important;
    }
    /* Sidebar buttons: keep rail styling (override generic pill look) */
    [data-testid="stSidebar"] .stButton > button {
        width: 100% !important;
        min-width: unset !important;
        height: auto !important;
        border-radius: 10px !important;
    }
    
    /* Chat - Fluid message bubbles */
    .chat-container {
        margin-bottom: 0;
        padding: 0.5rem 0;
    }
    
    .message-user {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        padding: 1rem 1.25rem;
        border-radius: 20px 20px 6px 20px;
        margin-left: 15%;
        margin-bottom: 0.75rem;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25);
        word-wrap: break-word;
        font-size: 0.95rem;
        line-height: 1.55;
        max-width: 80%;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    .message-bot {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(8px);
        color: #e2e8f0;
        padding: 1rem 1.25rem;
        border-radius: 20px 20px 20px 6px;
        margin-right: 15%;
        margin-bottom: 0.75rem;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
        border: 1px solid rgba(51, 65, 85, 0.4);
        word-wrap: break-word;
        font-size: 0.95rem;
        line-height: 1.6;
        max-width: 80%;
        transition: border-color 0.2s ease;
    }
    
    .message-time {
        font-size: 0.7rem;
        color: #64748b;
        margin-top: 0.5rem;
        font-weight: 400;
        opacity: 0.9;
    }
    
    /* Buttons - Softer, fluid interactions */
    .stButton>button {
        border-radius: 12px;
        padding: 0.55rem 1.1rem;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid rgba(71, 85, 105, 0.5);
        background: rgba(30, 41, 59, 0.8);
        color: #e2e8f0;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    
    .stButton>button:hover {
        background: rgba(51, 65, 85, 0.9);
        border-color: rgba(100, 116, 139, 0.6);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        transform: translateY(-2px);
    }
    
    button[kind="primary"] {
        background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%) !important;
        color: white !important;
        border: none !important;
    }
    
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        box-shadow: 0 4px 16px rgba(59, 130, 246, 0.35) !important;
    }
    
    /* ===== Auth screen (login / signup) ===== */
    .auth-hero {
        text-align: center;
        margin: 0 auto 1.1rem;
        max-width: 420px;
        animation: authFadeUp 0.55s ease both;
    }
    .auth-logo-wrap {
        display: flex;
        justify-content: center;
        margin: 0 auto 0.7rem;
    }
    .auth-logo-svg {
        width: 2.85rem;
        height: 2.85rem;
        filter: drop-shadow(0 10px 24px rgba(0, 0, 0, 0.35));
        animation: authLogoIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .auth-title {
        font-family: 'Plus Jakarta Sans', 'DM Sans', sans-serif;
        font-size: clamp(1.55rem, 3.2vw, 1.85rem);
        font-weight: 700;
        color: #f8fafc;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.04em;
        line-height: 1.15;
    }
    .auth-subtitle {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.95rem;
        color: #94a3b8;
        margin: 0;
        line-height: 1.4;
        font-weight: 400;
    }
    .auth-form-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.02rem;
        font-weight: 650;
        letter-spacing: -0.02em;
        color: #f1f5f9;
        margin: 0 0 0.2rem 0;
    }
    .auth-form-hint {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.84rem;
        color: #94a3b8;
        margin: 0 0 0.85rem 0;
        line-height: 1.4;
    }
    .password-requirements {
        background: transparent;
        border: none;
        border-radius: 0;
        padding: 0 0 0.35rem 0;
        margin: 0 0 0.85rem 0;
    }
    .password-requirements-title {
        font-size: 0.78rem;
        font-weight: 600;
        color: #94a3b8;
        margin-bottom: 0.45rem;
        letter-spacing: 0.01em;
    }
    .password-req {
        font-size: 0.78rem;
        color: #64748b;
        margin: 0.2rem 0;
        display: flex;
        align-items: center;
        gap: 0.45rem;
        transition: color 0.15s ease;
    }
    .password-req::before {
        content: '';
        width: 0.4rem;
        height: 0.4rem;
        border-radius: 50%;
        background: #475569;
        flex-shrink: 0;
    }
    .password-req.met {
        color: #5eead4;
    }
    .password-req.met::before {
        background: #14b8a6;
    }
    @keyframes authFadeUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes authLogoIn {
        from { opacity: 0; transform: scale(0.86) translateY(6px); }
        to { opacity: 1; transform: scale(1) translateY(0); }
    }
    
    /* Input Fields - Fluid, soft focus */
    .stTextInput>div>div>input,
    .stTextArea>div>div>textarea {
        border-radius: 12px;
        padding: 0.75rem 1rem;
        border: 1px solid rgba(71, 85, 105, 0.5);
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        font-size: 0.9375rem;
        background: rgba(30, 41, 59, 0.6);
        color: #e2e8f0;
    }
    
    .stTextInput>div>div>input:focus,
    .stTextArea>div>div>textarea:focus {
        border-color: rgba(59, 130, 246, 0.6);
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
        outline: none;
        background: rgba(30, 41, 59, 0.8);
    }
    
    /* Select boxes */
    .stSelectbox>div>div>select {
        border-radius: 8px;
        padding: 0.625rem 0.875rem;
        border: 1px solid #d1d5db;
        transition: all 0.15s ease;
        font-size: 0.9375rem;
    }
    
    div[data-testid="stTabs"] > div:first-child {
        background: #1e293b !important;
        border-radius: 10px 10px 0 0 !important;
        padding: 0.25rem !important;
    }
    div[data-testid="stTabs"] [role="tab"] {
        color: #94a3b8 !important;
        font-weight: 500 !important;
    }
    div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: #3b82f6 !important;
        background: rgba(59, 130, 246, 0.15) !important;
        border-radius: 8px !important;
    }
    
    /* Status badges - Minimal design */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.625rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 500;
        margin: 0.25rem;
    }
    
    .status-online {
        background: #d1fae5;
        color: #065f46;
    }
    
    .status-offline {
        background: #fee2e2;
        color: #991b1b;
    }
    
    /* Example questions - Pill-style, fluid */
    .example-question {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(51, 65, 85, 0.4);
        border-radius: 24px;
        padding: 0.65rem 1.1rem;
        margin: 0.35rem 0;
        cursor: pointer;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        font-size: 0.875rem;
        color: #e2e8f0;
    }
    
    .example-question:hover {
        border-color: rgba(59, 130, 246, 0.5);
        background: rgba(59, 130, 246, 0.15);
        color: #f1f5f9;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
    }
    
    /* Logo - hide app name on very narrow screens to prevent overflow */
    @media (max-width: 480px) {
        .nav-brand-text { display: none !important; }
    }
    /* Example questions - responsive: 1 col mobile, 2 tablet, 3 desktop */
    @media (max-width: 640px) {
        div:has(.example-questions-marker) + div > div {
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
    }
    @media (min-width: 641px) and (max-width: 1024px) {
        div:has(.example-questions-marker) + div > div {
            flex: 1 1 50% !important;
            min-width: 45% !important;
        }
    }
    
    /* Sidebar - Knowledge Home rail */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a121c 0%, #0c1522 55%, #0a1018 100%);
        border-right: 1px solid rgba(148, 163, 184, 0.12);
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0.85rem;
    }
    [data-testid="stSidebar"] .stButton>button {
        width: 100%;
        margin-bottom: 0.2rem;
        border-radius: 10px;
        background: transparent;
        color: #cbd5e1;
        border: 1px solid transparent;
        text-align: left;
        justify-content: flex-start;
        padding: 0.48rem 0.8rem;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }
    [data-testid="stSidebar"] .stButton>button:hover {
        background: rgba(30, 41, 59, 0.55);
        border-color: rgba(148, 163, 184, 0.14);
        color: #f1f5f9;
        transform: none;
        box-shadow: none;
    }
    /* Active nav item */
    [data-testid="stSidebar"] .stButton>button[kind="primary"] {
        background: rgba(13, 148, 136, 0.16) !important;
        border: 1px solid rgba(45, 212, 191, 0.28) !important;
        color: #99f6e4 !important;
        font-weight: 600 !important;
        justify-content: flex-start !important;
        margin-bottom: 0.2rem !important;
    }
    [data-testid="stSidebar"] .stButton>button[kind="primary"]:hover {
        background: rgba(13, 148, 136, 0.24) !important;
        border-color: rgba(45, 212, 191, 0.4) !important;
        color: #ccfbf1 !important;
        box-shadow: none !important;
        transform: none !important;
    }
    /* Solid New chat CTA — must beat active-nav primary specificity */
    [data-testid="stSidebar"] div[class*="st-key-side_start_new_chat"] .stButton > button[kind="primary"] {
        background: #0d9488 !important;
        border: none !important;
        color: #fff !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 650 !important;
        justify-content: center !important;
        margin: 0.15rem 0 0.55rem !important;
    }
    [data-testid="stSidebar"] div[class*="st-key-side_start_new_chat"] .stButton > button[kind="primary"]:hover {
        background: #0f766e !important;
        color: #fff !important;
        box-shadow: 0 6px 16px rgba(13, 148, 136, 0.25) !important;
    }
    .sb-cta-marker { display: none; }
    [data-testid="stSidebar"] .stButton>button[kind="tertiary"] {
        color: #94a3b8 !important;
        background: transparent !important;
        border: none !important;
        justify-content: flex-start !important;
        padding-left: 0.35rem !important;
        margin-bottom: 0.05rem !important;
    }
    [data-testid="stSidebar"] .stButton>button[kind="tertiary"]:hover {
        color: #5eead4 !important;
        background: transparent !important;
    }
    .sb-user {
        padding: 0.15rem 0.15rem 0.85rem;
        margin-bottom: 0.35rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }
    .sb-user-name {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.98rem;
        font-weight: 650;
        color: #f8fafc;
        letter-spacing: -0.02em;
        margin: 0;
        line-height: 1.25;
    }
    .sb-user-meta {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        color: #94a3b8;
        margin: 0.2rem 0 0;
        line-height: 1.35;
        word-break: break-word;
    }
    .sb-section-label {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #64748b;
        margin: 0.85rem 0 0.4rem;
    }
    .sb-thread {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.8rem;
        color: #94a3b8;
        margin: 0 0 0.35rem;
    }
    .sb-footer {
        text-align: center;
        color: #475569;
        font-size: 0.72rem;
        font-family: 'DM Sans', sans-serif;
        padding: 0.5rem 0 0.25rem;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.35) !important;
        border: 1px solid rgba(148, 163, 184, 0.12) !important;
        border-radius: 10px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.84rem !important;
        color: #94a3b8 !important;
    }
    
    /* Ensure sidebar expand/collapse button is always visible and clickable */
    [data-testid="collapsedControl"],
    [data-testid="stSidebar"] [data-testid="collapsedControl"],
    button[kind="header"] {
        z-index: 9999 !important;
        position: relative !important;
        min-width: 44px !important;
        min-height: 44px !important;
        opacity: 1 !important;
        visibility: visible !important;
        pointer-events: auto !important;
    }
    
    /* Cards and containers */
    .stExpander {
        border-radius: 8px;
        border: 1px solid #334155;
        margin-bottom: 0.75rem;
        background: #1e293b;
    }
    
    /* Form styling */
    .stForm {
        border-radius: 8px;
        padding: 1.25rem;
        background: #1e293b;
        border: 1px solid #334155;
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        font-size: 1.75rem;
        font-weight: 600;
        color: #f1f5f9;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.875rem;
        color: #94a3b8;
        font-weight: 400;
    }
    
    /* Messages - Dark theme */
    .stSuccess {
        border-radius: 8px;
        border-left: 3px solid #10b981;
        background: #064e3b;
        border: 1px solid #065f46;
        color: #d1fae5;
    }
    
    .stError {
        border-radius: 8px;
        border-left: 3px solid #ef4444;
        background: #7f1d1d;
        border: 1px solid #991b1b;
        color: #fee2e2;
    }
    
    .stInfo {
        border-radius: 8px;
        border-left: 3px solid #3b82f6;
        background: #1e3a8a;
        border: 1px solid #1e40af;
        color: #dbeafe;
    }
    
    .stWarning {
        border-radius: 8px;
        border-left: 3px solid #f59e0b;
        background: #78350f;
        border: 1px solid #92400e;
        color: #fef3c7;
    }
    
    /* Checkboxes and radio buttons */
    .stCheckbox>label,
    .stRadio>label {
        font-weight: 400;
        color: #e2e8f0;
        font-size: 0.875rem;
    }
    
    /* File uploader */
    .stFileUploader {
        border-radius: 8px;
        border: 1px dashed #475569;
        padding: 1.5rem;
        transition: all 0.15s ease;
        background: #1e293b;
    }
    
    .stFileUploader:hover {
        border-color: #3b82f6;
        background: #1e3a8a;
    }
    
    /* Tables */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #334155;
        background: #1e293b;
    }
    
    /* Hide Streamlit default elements (including red status dot / running indicator) */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Header styling */
    [data-testid="stHeader"] {
        background: #1e293b;
        border-bottom: 1px solid #334155;
        box-shadow: none;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #0f172a;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #475569;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #64748b;
    }
    
    /* Help banner */
    .help-banner {
        display: none;
    }
    
    /* Input container for chat */
    .chat-input-container {
        position: sticky;
        bottom: 0;
        background: #0f172a;
        border-top: 1px solid #334155;
        padding: 1rem;
        margin-top: 2rem;
    }
    
    /* Code blocks */
    code {
        background: #1e293b;
        padding: 0.125rem 0.375rem;
        border-radius: 4px;
        font-size: 0.875em;
        color: #f1f5f9;
        border: 1px solid #334155;
    }
    
    /* Markdown content */
    .stMarkdown {
        color: #e2e8f0;
        line-height: 1.6;
    }
    
    /* Dividers */
    hr {
        border: none;
        border-top: 1px solid #334155;
        margin: 1.5rem 0;
    }
    
    /* Captions */
    .stCaption {
        color: #94a3b8;
        font-size: 0.8125rem;
    }
    
    /* Loading spinner */
    .stSpinner>div {
        border-color: #3b82f6 transparent #3b82f6 transparent;
    }
    
    /* Typing indicator - animated dots while waiting for first token */
    .typing-dots span {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #3b82f6;
        margin: 0 2px;
        animation: typing-blink 1.4s ease-in-out infinite both;
    }
    .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
    .typing-dots span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing-blink {
        0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
        40% { opacity: 1; transform: scale(1); }
    }
    /* Subtle pulse on assistant message while streaming */
    .message-bot.streaming {
        animation: streaming-pulse 2s ease-in-out infinite;
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.3);
    }
    @keyframes streaming-pulse {
        0%, 100% { box-shadow: 0 2px 8px rgba(0,0,0,0.2), 0 0 0 1px rgba(59, 130, 246, 0.2); }
        50% { box-shadow: 0 2px 12px rgba(0,0,0,0.25), 0 0 0 2px rgba(59, 130, 246, 0.4); }
    }
    
    /* Container padding - Zone layout: wider for center+right; standard for other views */
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1400px;
        margin: 0 auto;
        background: transparent;
    }
    
    /* Text colors */
    h1, h2, h3, h4, h5, h6 {
        color: #f1f5f9;
    }
    
    p, span, div {
        color: #e2e8f0;
    }
    
    /* Chat input - Command Palette style (Spotlight / VS Code) */
    [data-testid="stChatInputContainer"] {
        width: 100% !important;
        max-width: 720px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        background: rgba(30, 41, 59, 0.95) !important;
        backdrop-filter: blur(16px);
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        border-radius: 16px !important;
        position: relative !important;
        z-index: 400 !important;
        margin-top: 3rem !important;
        margin-bottom: 2rem !important;
        padding: 1.5rem 1.75rem !important;
        min-height: 180px !important;
        height: 180px !important;
        box-shadow: 0 4px 24px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.04), 0 0 40px rgba(59, 130, 246, 0.06) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    [data-testid="stChatInputContainer"]:focus-within {
        border-color: rgba(59, 130, 246, 0.5) !important;
        box-shadow: 0 4px 28px rgba(0,0,0,0.35), 0 0 0 1px rgba(59, 130, 246, 0.3), 0 0 32px rgba(59, 130, 246, 0.2), 0 0 64px rgba(59, 130, 246, 0.08) !important;
        transform: translateY(-2px) !important;
    }
    
    /* Parent block: chat input zone - extra spacing so input stands out */
    [data-testid="stVerticalBlock"]:has([data-testid="stChatInputContainer"]) {
        padding-top: 3rem !important;
        margin-top: 3rem !important;
        margin-bottom: 1.5rem !important;
    }
    
    /* Target both input and textarea - Streamlit uses textarea for chat_input */
    [data-testid="stChatInputContainer"] input,
    [data-testid="stChatInputContainer"] textarea,
    [data-testid="stChatInput"] {
        background: transparent !important;
        color: #f9fafb !important;
        font-size: 1.125rem !important;
        line-height: 1.6 !important;
        min-height: 120px !important;
        height: 120px !important;
        padding: 0.75rem 0 !important;
        border: none !important;
        resize: none !important;
    }
    [data-testid="stChatInputContainer"] input::placeholder,
    [data-testid="stChatInputContainer"] textarea::placeholder {
        color: #9ca3af !important;
    }
    
    /* Copilot-style empty state: greeting, centered layout */
    .copilot-greeting {
        text-align: center;
        padding: 2rem 0 1.5rem;
    }
    .copilot-greeting h2 {
        font-size: 1.5rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0 0 0.25rem 0;
    }
    .copilot-greeting p {
        font-size: 1rem;
        color: #94a3b8;
        margin: 0;
    }
    .copilot-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        justify-content: center;
        margin-top: 1.5rem;
    }
    .copilot-pill {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(71, 85, 105, 0.4);
        border-radius: 16px;
        padding: 0.35rem 0.75rem;
        font-size: 0.8rem;
        color: #94a3b8;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .copilot-pill:hover {
        background: rgba(51, 65, 85, 0.9);
        border-color: rgba(59, 130, 246, 0.5);
    }
    
    /* Copilot-style: greeting and centered empty state */
    .copilot-greeting {
        text-align: center;
        padding: 2rem 0 1.5rem;
        margin: 0 auto;
        max-width: 640px;
    }
    .copilot-greeting h2 {
        font-size: 1.75rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0 0 0.25rem;
        letter-spacing: -0.02em;
    }
    .copilot-greeting p {
        font-size: 1rem;
        color: #94a3b8;
        margin: 0;
    }
    /* Suggestion pills - row of buttons below chat bar, small & secondary */
    .copilot-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        justify-content: center;
        margin-top: 1rem;
    }
    
    /* De-emphasize expander (filters/options) - subtle so chat bar stands out */
    .streamlit-expanderHeader {
        font-size: 0.85rem !important;
        color: #94a3b8 !important;
    }
    
    /* Input bar DOMINANT - suggestions secondary: de-emphasize Example Questions & Popular queries */
    div[data-testid="stVerticalBlock"] > div:has(button) {
        opacity: 0.92;
    }
    /* Make suggestion headings smaller and muted */
    .stMarkdown h3 {
        font-size: 0.95rem !important;
        color: #94a3b8 !important;
        font-weight: 500 !important;
    }
    /* Empty-state message - subtle, don't compete with input */
    .stAlert {
        font-size: 0.875rem !important;
        opacity: 0.9;
    }
    /* Conversation header - compact */
    .stMarkdown h3:has(+ div) {
        font-size: 0.9rem !important;
        color: #64748b !important;
    }
    
    /* Secondary content - de-emphasized, compact */
    .chat-secondary-section {
        opacity: 0.9;
        font-size: 0.9rem;
    }
    
    /* Selectbox dropdown */
    .stSelectbox>div>div>div {
        background: #1e293b;
        color: #e2e8f0;
    }
    
    /* Typing indicator - animated dots while waiting for first token */
    .typing-dots span {
        animation: typing-blink 1.4s infinite;
        opacity: 0.4;
    }
    .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
    .typing-dots span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing-blink {
        0%, 60%, 100% { opacity: 0.4; }
        30% { opacity: 1; }
    }
    
    /* Pulse highlight on assistant message while streaming */
    .message-bot.streaming {
        animation: streaming-pulse 2s ease-in-out infinite;
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.3);
    }
    @keyframes streaming-pulse {
        0%, 100% { box-shadow: 0 2px 8px rgba(0,0,0,0.2), 0 0 0 1px rgba(59, 130, 246, 0.2); }
        50% { box-shadow: 0 2px 12px rgba(0,0,0,0.25), 0 0 0 2px rgba(59, 130, 246, 0.4); }
    }
    
    /* Copilot-style empty state: greeting, centered layout, pill suggestions */
    .copilot-greeting {
        text-align: center;
        padding: 3rem 0 2rem 0;
    }
    .copilot-greeting h2 {
        font-size: 1.75rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .copilot-greeting p {
        font-size: 1rem;
        color: #94a3b8;
        margin-top: 0.5rem;
    }
    .copilot-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        justify-content: center;
        margin: 1rem 0;
    }
    .copilot-pills .stButton {
        flex: 0 0 auto;
    }
    .copilot-pills .stButton > button {
        border-radius: 16px;
        padding: 0.35rem 0.75rem;
        font-size: 0.8rem;
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(71, 85, 105, 0.4);
    }

    /* Login / signup only — toggled via body:has(.auth-hero) in app */
    body:has(.auth-hero) section[data-testid="stSidebar"] {
        display: none !important;
    }
    body:has(.auth-hero) .stApp > div {
        flex-direction: row;
    }
    body:has(.auth-hero) section.main > div {
        flex: 1 1 100%;
        max-width: 100%;
    }
    body:has(.auth-hero) [data-testid="stAppViewContainer"] .main {
        min-height: 100vh;
        background:
            radial-gradient(ellipse 90% 55% at 50% -8%, rgba(20, 184, 166, 0.14), transparent 52%),
            radial-gradient(ellipse 50% 40% at 100% 100%, rgba(14, 165, 233, 0.08), transparent 50%),
            linear-gradient(180deg, #071018 0%, #0c1522 45%, #0a1018 100%);
    }
    body:has(.auth-hero) .main .block-container,
    body:has(.auth-hero) [data-testid="stMain"] .block-container,
    body:has(.auth-hero) [data-testid="stMainBlockContainer"] {
        max-width: 400px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1.15rem !important;
        padding-right: 1.15rem !important;
        width: 100%;
        box-sizing: border-box;
    }
    body:has(.auth-hero) [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"],
    body:has(.auth-hero) [data-testid="stVerticalBlock"] > div {
        gap: 0.45rem !important;
    }
    body:has(.auth-hero) .stForm [data-testid="stVerticalBlock"] {
        gap: 0.55rem !important;
    }
    body:has(.auth-hero) [data-testid="stHorizontalBlock"] {
        max-width: 420px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        width: 100% !important;
        justify-content: center !important;
        gap: 0.65rem !important;
    }
    body:has(.auth-hero) [data-testid="stAlert"] {
        max-width: 420px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        width: 100% !important;
        box-sizing: border-box;
    }
    body:has(.auth-hero) .stTextInput label,
    body:has(.auth-hero) .stSelectbox label,
    body:has(.auth-hero) .stCheckbox label {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.86rem !important;
        font-weight: 550 !important;
        color: #cbd5e1 !important;
        margin-bottom: 0.3rem !important;
    }
    body:has(.auth-hero) .stForm,
    body:has(.auth-hero) [data-testid="stForm"] {
        width: 100% !important;
        max-width: 400px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        box-sizing: border-box;
        padding: 1.2rem 1.2rem 0.95rem 1.2rem !important;
        border-radius: 16px !important;
        background: rgba(12, 20, 32, 0.72) !important;
        border: 1px solid rgba(148, 163, 184, 0.16) !important;
        box-shadow: 0 18px 48px -28px rgba(0, 0, 0, 0.75) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        animation: authFadeUp 0.55s ease 0.08s both;
    }
    body:has(.auth-hero) button[kind="primary"],
    body:has(.auth-hero) button[kind="primaryFormSubmit"] {
        background: #0d9488 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 10px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 650 !important;
        font-size: 0.95rem !important;
        padding-top: 0.65rem !important;
        padding-bottom: 0.65rem !important;
        margin-top: 0.35rem !important;
        transition: background 0.15s ease, transform 0.15s ease !important;
    }
    body:has(.auth-hero) button[kind="primary"]:hover,
    body:has(.auth-hero) button[kind="primaryFormSubmit"]:hover {
        background: #0f766e !important;
        box-shadow: 0 8px 20px rgba(13, 148, 136, 0.28) !important;
        transform: translateY(-1px) !important;
    }
    /* Secondary form actions (Create account / Forgot) stay quiet text links */
    body:has(.auth-hero) button[kind="tertiary"],
    body:has(.auth-hero) button[kind="secondary"],
    body:has(.auth-hero) button[kind="tertiaryFormSubmit"],
    body:has(.auth-hero) button[kind="secondaryFormSubmit"] {
        background: transparent !important;
        box-shadow: none !important;
        transform: none !important;
        color: #94a3b8 !important;
    }
    body:has(.auth-hero) button[kind="tertiaryFormSubmit"]:hover,
    body:has(.auth-hero) button[kind="tertiary"]:hover {
        color: #5eead4 !important;
        background: transparent !important;
    }
    body:has(.auth-hero) [data-baseweb="checkbox"] span[data-checked="true"],
    body:has(.auth-hero) [data-baseweb="checkbox"] > div {
        background-color: #0d9488 !important;
        border-color: #0d9488 !important;
    }
    body:has(.auth-hero) .stExpander {
        width: 100% !important;
        max-width: 420px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        box-sizing: border-box;
        border-radius: 12px !important;
        background: rgba(12, 20, 32, 0.45) !important;
        border: 1px solid rgba(148, 163, 184, 0.12) !important;
    }
    body:has(.auth-hero) .stTextInput > div > div > input,
    body:has(.auth-hero) .stTextArea > div > div > textarea {
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.28);
        background: rgba(15, 23, 42, 0.85);
        font-family: 'DM Sans', sans-serif;
        min-height: 2.6rem;
    }
    body:has(.auth-hero) .stTextInput > div > div > input:focus {
        border-color: rgba(45, 212, 191, 0.55);
        box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.16);
    }
    body:has(.auth-hero) button[kind="tertiary"] {
        color: #94a3b8 !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        text-decoration: none;
    }
    body:has(.auth-hero) button[kind="tertiary"]:hover {
        color: #e2e8f0 !important;
    }
    body:has(.auth-hero) .auth-switch-row {
        margin-top: 1rem;
        text-align: center;
    }
    body:has(.auth-hero) .auth-link-actions-marker + div [data-testid="stHorizontalBlock"] {
        align-items: center !important;
        gap: 0.5rem !important;
        margin: 0.85rem 0 0.15rem 0 !important;
    }
    body:has(.auth-hero) .auth-link-actions-marker + div .stButton > button[kind="tertiary"] {
        width: 100%;
        justify-content: center;
        border: none !important;
        border-radius: 0 !important;
        background: transparent !important;
        color: #94a3b8 !important;
        font-size: 0.84rem !important;
        font-weight: 500 !important;
        padding: 0.25rem 0.2rem !important;
        box-shadow: none !important;
        transform: none !important;
    }
    body:has(.auth-hero) .auth-link-actions-marker + div .stButton > button[kind="tertiary"]:hover {
        background: transparent !important;
        color: #5eead4 !important;
        border: none !important;
        box-shadow: none !important;
        transform: none !important;
    }
    @media (max-width: 480px) {
        body:has(.auth-hero) .main .block-container,
        body:has(.auth-hero) [data-testid="stMain"] .block-container,
        body:has(.auth-hero) [data-testid="stMainBlockContainer"] {
            padding-top: 2rem !important;
            max-width: 100% !important;
        }
        body:has(.auth-hero) .auth-title {
            font-size: 1.55rem;
        }
    }

    /* -------- Phase 1 chat modernization overrides -------- */
    :root {
        --ia-bg-card: rgba(17, 25, 40, 0.78);
        --ia-bg-card-soft: rgba(22, 32, 52, 0.62);
        --ia-bg-elevated: rgba(12, 19, 33, 0.92);
        --ia-text-strong: #f8fbff;
        --ia-text-muted: #9db0c9;
        --ia-text-subtle: #7f93ad;
        --ia-border-soft: rgba(130, 153, 187, 0.22);
        --ia-accent-a: #4f8cff;
        --ia-accent-b: #2f63ff;
        --ia-shadow-soft: 0 10px 28px rgba(2, 8, 23, 0.28);
        --ia-shadow-glow: 0 18px 48px rgba(2, 8, 23, 0.34);
    }

    /* Clean centered thread (Notion / Linear AI style) */
    .block-container {
        max-width: 1100px;
    }

    .thread {
        max-width: 720px;
        margin: 0 auto 1.25rem;
        padding: 0.25rem 0 0.5rem;
    }

    .msg {
        margin: 0 0 1.35rem;
        animation: authFadeUp 0.35s ease both;
    }

    .msg-user {
        display: flex;
        justify-content: flex-end;
    }

    .msg-user-bubble {
        max-width: 85%;
        padding: 0.7rem 0.95rem;
        border-radius: 16px 16px 4px 16px;
        background: rgba(13, 148, 136, 0.16);
        border: 1px solid rgba(45, 212, 191, 0.22);
        color: #f1f5f9;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.95rem;
        line-height: 1.55;
        word-wrap: break-word;
    }

    .msg-assistant {
        max-width: 100%;
        padding: 0.15rem 0.15rem 0.35rem;
        border-top: none;
        color: #e2e8f0;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.98rem;
        line-height: 1.65;
        word-wrap: break-word;
    }

    .msg-assistant .msg-body {
        color: #e2e8f0;
    }

    .msg-assistant.streaming .msg-body {
        opacity: 0.92;
    }

    .msg-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin-top: 0.55rem;
        opacity: 0.72;
    }

    /* Keep answer action labels readable (no Co… / He… / Im…) */
    .msg-actions-row [data-testid="stHorizontalBlock"] {
        gap: 0.45rem !important;
        align-items: center;
    }
    .msg-actions-row .stButton > button {
        width: auto !important;
        min-width: 4.75rem !important;
        padding: 0.28rem 0.75rem !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        white-space: nowrap !important;
        border-radius: 8px !important;
        background: transparent !important;
        border: 1px solid rgba(148, 163, 184, 0.2) !important;
        color: #94a3b8 !important;
        box-shadow: none !important;
    }
    .msg-actions-row .stButton > button:hover {
        color: #e2e8f0 !important;
        border-color: rgba(45, 212, 191, 0.35) !important;
        background: rgba(13, 148, 136, 0.1) !important;
        transform: none !important;
    }

    .sources-block {
        margin-top: 0.75rem;
        padding-top: 0.55rem;
        border-top: 1px solid rgba(148, 163, 184, 0.12);
    }

    .sources-summary {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #64748b;
        margin: 0 0 0.45rem;
    }

    .source-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.32rem 0.58rem;
        border-radius: 8px;
        background: rgba(148, 163, 184, 0.07);
        border: 1px solid rgba(148, 163, 184, 0.14);
        color: #cbd5e1;
        font-size: 0.76rem;
        line-height: 1.2;
        margin: 0 0.3rem 0.3rem 0;
    }

    .source-chip em {
        color: #64748b;
        font-style: normal;
        font-size: 0.72rem;
    }

    /* Legacy class hooks still used by streaming placeholders */
    .message-user,
    .message-bot {
        max-width: 720px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        box-shadow: none !important;
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
    }

    .message-bot.streaming {
        animation: none;
        box-shadow: none !important;
    }

    .zone-context-panel {
        display: none !important;
    }

    /* Modern composer shell */
    [data-testid="stChatInputContainer"] {
        max-width: 860px !important;
        border-radius: 20px !important;
        border: 1px solid var(--ia-border-soft) !important;
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.96) 0%, rgba(15, 23, 42, 0.88) 100%) !important;
        box-shadow: var(--ia-shadow-glow) !important;
        padding: 0.1rem 0.95rem 0.15rem 0.95rem !important;
        backdrop-filter: blur(14px) saturate(1.05);
        min-height: 78px !important;
        height: auto !important;
    }

    [data-testid="stChatInputContainer"]:focus-within {
        border-color: rgba(108, 160, 255, 0.58) !important;
        box-shadow: 0 0 0 2px rgba(79, 140, 255, 0.18), 0 16px 40px rgba(2, 8, 23, 0.42) !important;
    }

    [data-testid="stChatInputContainer"] input::placeholder,
    [data-testid="stChatInputContainer"] textarea::placeholder {
        color: #91a4be !important;
    }

    [data-testid="stChatInputContainer"] textarea,
    [data-testid="stChatInputContainer"] input,
    [data-testid="stChatInput"] {
        min-height: 40px !important;
        height: auto !important;
        font-size: 1rem !important;
        padding: 0.7rem 0 0.55rem 0 !important;
    }

    .composer-hint {
        max-width: 860px;
        margin: 0.7rem auto 0.25rem;
        color: var(--ia-text-subtle);
        font-size: 0.8rem;
        text-align: center;
    }

    .conversation-toolbar {
        margin: 0.35rem 0 0.9rem;
    }

    .section-kicker {
        color: var(--ia-text-subtle);
        font-size: 0.76rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
    }

    .conversation-title {
        color: var(--ia-text-strong);
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .conversation-subtitle {
        color: var(--ia-text-muted);
        font-size: 0.85rem;
        margin-top: 0.2rem;
    }

    .starter-grid-title {
        margin: 1rem 0 0.8rem;
        text-align: center;
        color: var(--ia-text-muted);
        font-size: 0.84rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .starter-card .stButton > button {
        min-height: 112px !important;
        height: 112px !important;
        padding: 0.9rem 1rem !important;
        border-radius: 18px !important;
        background: linear-gradient(180deg, rgba(17, 25, 40, 0.88) 0%, rgba(17, 25, 40, 0.72) 100%) !important;
        border: 1px solid rgba(130, 153, 187, 0.18) !important;
        box-shadow: var(--ia-shadow-soft) !important;
        text-align: left !important;
        white-space: pre-line !important;
        line-height: 1.35 !important;
    }

    .starter-card .stButton > button:hover {
        border-color: rgba(108, 160, 255, 0.42) !important;
        transform: translateY(-2px);
    }

    .copilot-greeting h2 {
        font-weight: 700 !important;
        letter-spacing: -0.03em !important;
    }

    .copilot-greeting p {
        color: #9fb2cb !important;
    }

    /* ===== Knowledge Home ===== */
    .kh-shell {
        max-width: 720px;
        margin: 0.5rem auto 1.5rem;
        text-align: center;
        animation: authFadeUp 0.45s ease both;
    }
    .kh-eyebrow {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #64748b;
        margin: 0 0 0.55rem 0;
    }
    .kh-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: clamp(1.55rem, 3vw, 1.95rem);
        font-weight: 700;
        letter-spacing: -0.035em;
        color: #f8fafc;
        margin: 0 0 0.45rem 0;
        line-height: 1.2;
    }
    .kh-subtitle {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.98rem;
        color: #94a3b8;
        margin: 0 0 1.35rem 0;
        line-height: 1.45;
    }
    .kh-chips {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.55rem;
        margin: 0.35rem 0 1.25rem;
    }
    .kh-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.4rem 0.75rem;
        border-radius: 999px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(15, 23, 42, 0.55);
        color: #cbd5e1;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.8rem;
        font-weight: 500;
    }
    .kh-chip strong {
        color: #f1f5f9;
        font-weight: 650;
    }
    .kh-chip-dot {
        width: 0.45rem;
        height: 0.45rem;
        border-radius: 50%;
        background: #14b8a6;
        display: inline-block;
    }
    .kh-chip-dot.warn {
        background: #f59e0b;
    }
    .kh-empty {
        margin: 1.1rem auto 0.35rem;
        max-width: 520px;
        padding: 1.1rem 1.15rem;
        border-radius: 14px;
        border: 1px dashed rgba(148, 163, 184, 0.28);
        background: rgba(12, 20, 32, 0.45);
        text-align: left;
    }
    .kh-empty h3 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1rem;
        color: #f1f5f9;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.02em;
    }
    .kh-empty p {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.88rem;
        color: #94a3b8;
        margin: 0;
        line-height: 1.45;
    }
    .kh-actions-marker + div [data-testid="stHorizontalBlock"] {
        max-width: 420px;
        margin-left: auto !important;
        margin-right: auto !important;
        gap: 0.75rem !important;
    }
    .kh-actions-marker + div .stButton > button {
        border-radius: 10px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 600 !important;
        min-height: 2.7rem;
    }
    .kh-actions-marker + div .stButton > button[kind="primary"] {
        background: #0d9488 !important;
        border: none !important;
        color: #fff !important;
    }
    .kh-actions-marker + div .stButton > button[kind="primary"]:hover {
        background: #0f766e !important;
    }
    .kh-composer-hint {
        text-align: center;
        color: #64748b;
        font-size: 0.8rem;
        margin: 0.55rem 0 0.85rem;
        font-family: 'DM Sans', sans-serif;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Browser Console Error Logging - Inject JavaScript to capture errors
st.markdown(
    """
    <script>
    // Global error handler for JavaScript errors
    window.addEventListener('error', function(event) {
        console.error('JavaScript Error:', {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            error: event.error
        });
    });
    
    // Global handler for unhandled promise rejections
    window.addEventListener('unhandledrejection', function(event) {
        console.error('Unhandled Promise Rejection:', event.reason);
    });
    
    // Intercept Streamlit error messages and log to console
    (function() {
        const originalConsoleError = console.error;
        console.error = function(...args) {
            originalConsoleError.apply(console, args);
            // Also log to browser console with more detail
            if (args.length > 0) {
                const errorMsg = args.map(arg => {
                    if (typeof arg === 'object') {
                        try {
                            return JSON.stringify(arg, null, 2);
                        } catch (e) {
                            return String(arg);
                        }
                    }
                    return String(arg);
                }).join(' ');
                console.error('[Streamlit Error]', errorMsg);
            }
        };
        
        // Monitor for Streamlit error elements and log them
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) { // Element node
                        // Check for Streamlit error elements
                        if (node.classList && (
                            node.classList.contains('stAlert') ||
                            node.classList.contains('stException') ||
                            node.querySelector && node.querySelector('.stAlert, .stException')
                        )) {
                            const errorText = node.textContent || node.innerText;
                            if (errorText && errorText.trim()) {
                                console.error('[Streamlit UI Error]', errorText.trim());
                            }
                        }
                        
                        // Check for error messages in the DOM
                        const errorElements = node.querySelectorAll ? node.querySelectorAll('[class*="error"], [class*="exception"], [class*="alert"]') : [];
                        errorElements.forEach(function(el) {
                            const text = el.textContent || el.innerText;
                            if (text && text.trim() && text.includes('❌')) {
                                console.error('[Streamlit Error Message]', text.trim());
                            }
                        });
                    }
                });
            });
        });
        
        // Start observing when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            });
        } else {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
        
        // Log page load
        console.log('[Streamlit App] Page loaded, error logging enabled');
    })();
    </script>
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
if "show_upload" not in st.session_state:
    st.session_state.show_upload = False
if "selected_documents" not in st.session_state:
    st.session_state.selected_documents = []  # List of document filenames to filter by
if "show_advanced_filters" not in st.session_state:
    st.session_state.show_advanced_filters = False
if "advanced_filters" not in st.session_state:
    st.session_state.advanced_filters = {}
if "enable_streaming" not in st.session_state:
    st.session_state.enable_streaming = True
if "current_conversation_id" not in st.session_state:
    st.session_state.current_conversation_id = None
if "conversations" not in st.session_state:
    st.session_state.conversations = []
if "show_health" not in st.session_state:
    st.session_state.show_health = False
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_view" not in st.session_state:
    st.session_state.auth_view = "login"  # "login" | "register" — unauthenticated shell only
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "show_login" not in st.session_state:
    st.session_state.show_login = False
if "show_register" not in st.session_state:
    st.session_state.show_register = False
if "show_user_management" not in st.session_state:
    st.session_state.show_user_management = False
if "show_change_password" not in st.session_state:
    st.session_state.show_change_password = False
if "show_password_reset" not in st.session_state:
    st.session_state.show_password_reset = False
if "password_reset_token" not in st.session_state:
    st.session_state.password_reset_token = None
if "password_reset_email" not in st.session_state:
    st.session_state.password_reset_email = None
if "show_2fa_setup" not in st.session_state:
    st.session_state.show_2fa_setup = False
if "pending_2fa_email" not in st.session_state:
    st.session_state.pending_2fa_email = None
# Back-compat if an older session still has the username key
if "pending_2fa_username" in st.session_state and not st.session_state.pending_2fa_email:
    st.session_state.pending_2fa_email = st.session_state.pending_2fa_username
if "pending_remember_me" not in st.session_state:
    st.session_state.pending_remember_me = True
if "2fa_setup_data" not in st.session_state:
    st.session_state["2fa_setup_data"] = None
if "show_profile" not in st.session_state:
    st.session_state.show_profile = False
if "show_sessions" not in st.session_state:
    st.session_state.show_sessions = False
if "show_audit_logs" not in st.session_state:
    st.session_state.show_audit_logs = False
if "show_export_backup" not in st.session_state:
    st.session_state.show_export_backup = False
if "show_history" not in st.session_state:
    st.session_state.show_history = False
if "show_saved_queries" not in st.session_state:
    st.session_state.show_saved_queries = False
if "show_conversations" not in st.session_state:
    st.session_state.show_conversations = False
if "conversation_order" not in st.session_state:
    st.session_state.conversation_order = "oldest_first"  # Chronological default; "newest_first" for reverse

MAX_HISTORY = 50

# Navigation: page ID -> (label, session_state_key)
NAV_OPTIONS = [
    ("🏠 Chat", "chat"),
    ("📚 Documents", "documents"),
    ("📤 Upload", "upload"),
    ("🕐 History", "history"),
    ("💾 Saved Queries", "saved_queries"),
    ("📋 Conversations", "conversations"),
    ("👤 Profile", "profile"),
    ("🔑 Change Password", "change_password"),
    ("🔐 2FA", "2fa"),
    ("📱 Sessions", "sessions"),
    ("👥 Manage Users", "user_management"),
    ("📋 Audit Logs", "audit_logs"),
    ("💾 Export & Backup", "export_backup"),
    ("📈 Metrics", "health"),
]
NAV_LABEL_TO_KEY = {label: key for label, key in NAV_OPTIONS}
NAV_KEY_TO_LABEL = {key: label for label, key in NAV_OPTIONS}
VALID_VIEW_KEYS = {key for _, key in NAV_OPTIONS}


def apply_view_from_query_params():
    """Deep linking: if URL has ?view=documents etc., navigate to that page on load."""
    view = st.query_params.get("view")
    if not view or view not in VALID_VIEW_KEYS:
        return
    # Admin-only views: require admin role
    admin_views = {"user_management", "audit_logs", "export_backup"}
    if view in admin_views:
        user = st.session_state.get("current_user") or {}
        if user.get("role") != "admin":
            return
    current = get_current_nav_page()
    if view != current:
        navigate_to_page(view)
        st.query_params["view"] = view


def get_current_nav_page():
    """Return the current page ID based on session state."""
    if st.session_state.show_documents:
        return "documents"
    if st.session_state.show_upload:
        return "upload"
    if st.session_state.show_history:
        return "history"
    if st.session_state.show_saved_queries:
        return "saved_queries"
    if st.session_state.show_conversations:
        return "conversations"
    if st.session_state.show_profile:
        return "profile"
    if st.session_state.show_change_password:
        return "change_password"
    if st.session_state.show_2fa_setup:
        return "2fa"
    if st.session_state.show_sessions:
        return "sessions"
    if st.session_state.show_user_management:
        return "user_management"
    if st.session_state.show_audit_logs:
        return "audit_logs"
    if st.session_state.show_export_backup:
        return "export_backup"
    if st.session_state.show_health:
        return "health"
    return "chat"

def navigate_to_page(page_key: str):
    """Clear all show flags and set the target page."""
    st.session_state.show_documents = False
    st.session_state.show_upload = False
    st.session_state.show_history = False
    st.session_state.show_saved_queries = False
    st.session_state.show_conversations = False
    st.session_state.show_profile = False
    st.session_state.show_change_password = False
    st.session_state.show_2fa_setup = False
    st.session_state.show_sessions = False
    st.session_state.show_user_management = False
    st.session_state.show_audit_logs = False
    st.session_state.show_export_backup = False
    st.session_state.show_health = False
    if page_key == "documents":
        st.session_state.show_documents = True
    elif page_key == "upload":
        st.session_state.show_upload = True
    elif page_key == "history":
        st.session_state.show_history = True
    elif page_key == "saved_queries":
        st.session_state.show_saved_queries = True
    elif page_key == "conversations":
        st.session_state.show_conversations = True
    elif page_key == "profile":
        st.session_state.show_profile = True
    elif page_key == "change_password":
        st.session_state.show_change_password = True
    elif page_key == "2fa":
        st.session_state.show_2fa_setup = True
    elif page_key == "sessions":
        st.session_state.show_sessions = True
    elif page_key == "user_management":
        st.session_state.show_user_management = True
    elif page_key == "audit_logs":
        st.session_state.show_audit_logs = True
    elif page_key == "export_backup":
        st.session_state.show_export_backup = True
    elif page_key == "health":
        st.session_state.show_health = True
    # chat: all show_* remain False

# Authentication check and login UI
def get_auth_headers():
    """Get authentication headers if user is authenticated."""
    if st.session_state.authenticated and st.session_state.access_token:
        return {"Authorization": f"Bearer {st.session_state.access_token}"}
    return {}

def validate_token(token: str) -> bool:
    """Validate token with API and restore session if valid."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_URL}/auth/me", headers=headers, timeout=5)
        if response.status_code == 200:
            user_data = response.json()
            st.session_state.authenticated = True
            st.session_state.access_token = token
            st.session_state.current_user = user_data
            return True
    except:
        pass
    return False

def restore_session_from_query():
    """Restore session from query parameters if token exists."""
    query_params = st.query_params
    token = query_params.get("token", None)
    
    if token and not st.session_state.authenticated:
        if validate_token(token):
            # Keep token in query params for persistence
            st.query_params.token = token
            return True
        else:
            # Remove invalid token from query params
            st.query_params.clear()
    return False

# Try to restore session from query parameters on page load
if not st.session_state.authenticated:
    restore_session_from_query()

# Login/Register UI
if not st.session_state.authenticated:
    def _is_streamlit_cloud_host() -> bool:
        cwd = os.getcwd().replace("\\", "/")
        return bool(
            os.environ.get("STREAMLIT_SHARING_MODE")
            or cwd.startswith("/mount/src")
        )

    # Only warn when localhost API_URL would actually break (hosted Streamlit Cloud)
    if _is_streamlit_cloud_host() and (
        API_URL.startswith("http://127.0.0.1") or API_URL.startswith("http://localhost")
    ):
        st.warning(
            "API URL is set to localhost, which won't work on Streamlit Cloud. "
            "Set `API_URL` in Streamlit Cloud secrets to your backend URL."
        )

    # Check for reset token in query parameters (for email links)
    query_params = st.query_params
    reset_token_from_url = query_params.get("reset_token", None)
    if reset_token_from_url and not st.session_state.password_reset_token:
        st.session_state.password_reset_token = reset_token_from_url
        st.session_state.show_password_reset = True
        st.session_state.auth_view = "login"
        try:
            verify_resp = requests.post(
                f"{API_URL}/auth/password-reset/verify",
                json={"token": reset_token_from_url},
                timeout=5
            )
            if verify_resp.status_code == 200:
                verify_data = verify_resp.json()
                st.session_state.password_reset_email = verify_data.get("email")
        except Exception:
            pass

    debug_mode = os.environ.get("DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    show_dev_helpers = debug_mode

    st.markdown(
        """
<div class="auth-hero">
    <div class="auth-logo-wrap" aria-hidden="true">
        <svg class="auth-logo-svg" viewBox="0 0 88 88" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="auth-book-a" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#2dd4bf"/>
                    <stop offset="100%" stop-color="#14b8a6"/>
                </linearGradient>
                <linearGradient id="auth-book-b" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#f472b6"/>
                    <stop offset="100%" stop-color="#db2777"/>
                </linearGradient>
                <linearGradient id="auth-book-c" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#7dd3fc"/>
                    <stop offset="100%" stop-color="#0ea5e9"/>
                </linearGradient>
            </defs>
            <rect x="10" y="22" width="26" height="46" rx="4" fill="url(#auth-book-a)" transform="rotate(-14 23 45)" opacity="0.98"/>
            <rect x="28" y="14" width="28" height="52" rx="4" fill="url(#auth-book-b)" transform="rotate(6 42 40)" opacity="0.98"/>
            <rect x="44" y="20" width="28" height="48" rx="4" fill="url(#auth-book-c)" transform="rotate(14 58 44)" opacity="0.98"/>
        </svg>
    </div>
    <h1 class="auth-title">Incident Assistant</h1>
    <p class="auth-subtitle">Ask your documents. Get answers with sources.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    if st.session_state.auth_view == "register":
        with st.form("register_form"):
            st.markdown(
                '<div class="auth-form-title">Create account</div>'
                '<div class="auth-form-hint">Upload documents and ask questions in plain English.</div>',
                unsafe_allow_html=True,
            )
            reg_first_name = st.text_input("First name", key="reg_first_name", placeholder="Your first name")
            reg_email = st.text_input("Email", key="reg_email", placeholder="you@example.com")
            reg_password = st.text_input("Password", type="password", key="reg_password", placeholder="Create a password")
            with st.expander("Password requirements", expanded=False):
                st.caption("8+ characters, with uppercase, lowercase, number, and special character.")
            reg_password_confirm = st.text_input("Confirm password", type="password", key="reg_password_confirm", placeholder="Repeat password")
            submit_reg = st.form_submit_button("Create account", use_container_width=True, type="primary")

            if submit_reg:
                if reg_first_name and reg_email and reg_password:
                    if reg_password != reg_password_confirm:
                        st.error("Passwords do not match")
                    else:
                        try:
                            response = requests.post(
                                f"{API_URL}/auth/register",
                                json={
                                    "first_name": reg_first_name.strip(),
                                    "email": reg_email.strip(),
                                    "password": reg_password,
                                    "role": "user"
                                },
                                timeout=5
                            )
                            if response.status_code == 200:
                                st.success("Account created. You can sign in now.")
                                st.session_state.auth_view = "login"
                            else:
                                st.error(f"Registration failed: {response.json().get('detail', 'Unknown error')}")
                        except requests.exceptions.ConnectionError:
                            st.error(get_api_connection_error_message())
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                else:
                    st.warning("Please fill in all fields")

        if st.button("Already have an account? Sign in", key="auth_switch_to_login", type="tertiary", use_container_width=True):
            st.session_state.auth_view = "login"
            st.rerun()
    else:
        if st.session_state.show_password_reset:
            if st.session_state.password_reset_token:
                if st.session_state.password_reset_email:
                    st.caption(f"Resetting password for {st.session_state.password_reset_email}")
                if show_dev_helpers:
                    st.info("Dev mode: token is available without email delivery.")

                with st.form("reset_password_form"):
                    st.markdown(
                        '<div class="auth-form-title">Set a new password</div>'
                        '<div class="auth-form-hint">Choose a strong password you have not used recently.</div>',
                        unsafe_allow_html=True,
                    )
                    st.text_input("Reset token", value=st.session_state.password_reset_token, disabled=True, key="display_token")
                    with st.expander("Password requirements", expanded=False):
                        st.markdown(
                            "- At least 8 characters\n"
                            "- Uppercase, lowercase, number, and special character\n"
                            "- Cannot reuse your last 5 passwords"
                        )
                    new_password = st.text_input("New password", type="password", key="reset_new_password")
                    confirm_password = st.text_input("Confirm new password", type="password", key="reset_confirm_password")
                    col1, col2 = st.columns(2)
                    with col1:
                        submit_reset = st.form_submit_button("Reset password", use_container_width=True, type="primary")
                    with col2:
                        cancel_reset = st.form_submit_button("Cancel", use_container_width=True)

                    if cancel_reset:
                        st.session_state.show_password_reset = False
                        st.session_state.password_reset_token = None
                        st.session_state.password_reset_email = None
                        st.rerun()

                    if submit_reset:
                        if not new_password or not confirm_password:
                            st.error("Please fill in all fields")
                        elif new_password != confirm_password:
                            st.error("Passwords do not match")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters long")
                        else:
                            try:
                                response = requests.post(
                                    f"{API_URL}/auth/password-reset/confirm",
                                    json={
                                        "token": st.session_state.password_reset_token,
                                        "new_password": new_password
                                    },
                                    timeout=30
                                )
                                if response.status_code == 200:
                                    st.success("Password updated. You can sign in now.")
                                    st.session_state.show_password_reset = False
                                    st.session_state.password_reset_token = None
                                    st.session_state.password_reset_email = None
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    error_detail = response.json().get('detail', 'Unknown error')
                                    st.error(f"Password reset failed: {error_detail}")
                            except requests.exceptions.ConnectionError:
                                st.error(get_api_connection_error_message())
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
            else:
                with st.form("request_reset_form"):
                    st.markdown(
                        '<div class="auth-form-title">Reset password</div>'
                        '<div class="auth-form-hint">Enter the email on your account and we will send a reset link.</div>',
                        unsafe_allow_html=True,
                    )
                    reset_email = st.text_input("Email address", key="reset_email", placeholder="you@example.com")
                    col1, col2 = st.columns(2)
                    with col1:
                        submit_request = st.form_submit_button("Send reset link", use_container_width=True, type="primary")
                    with col2:
                        cancel_request = st.form_submit_button("Cancel", use_container_width=True)

                    if cancel_request:
                        st.session_state.show_password_reset = False
                        st.rerun()

                    if submit_request:
                        if not reset_email:
                            st.error("Please enter your email address")
                        else:
                            try:
                                response = requests.post(
                                    f"{API_URL}/auth/password-reset/request",
                                    json={"email": reset_email},
                                    timeout=10
                                )
                                if response.status_code == 200:
                                    data = response.json()
                                    st.success(data.get("message", "Reset link sent"))
                                    if show_dev_helpers and data.get("token"):
                                        st.session_state.password_reset_token = data.get("token")
                                        st.session_state.password_reset_email = reset_email
                                        st.info("Dev mode: reset token ready.")
                                        st.rerun()
                                else:
                                    error_detail = response.json().get('detail', 'Unknown error')
                                    st.error(f"Request failed: {error_detail}")
                            except requests.exceptions.ConnectionError:
                                st.error(get_api_connection_error_message())
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
        elif st.session_state.pending_2fa_email:
            with st.form("2fa_verify_form"):
                st.markdown(
                    '<div class="auth-form-title">Two-factor authentication</div>'
                    f'<div class="auth-form-hint">Enter the 6-digit code for {st.session_state.pending_2fa_email}.</div>',
                    unsafe_allow_html=True,
                )
                twofa_code = st.text_input(
                    "Authentication code",
                    key="2fa_code",
                    placeholder="123456",
                    help="Spaces and dashes are ignored."
                )
                normalized_code = (twofa_code or "").strip().replace(" ", "").replace("-", "")
                submit_2fa = st.form_submit_button(
                    "Verify and sign in",
                    use_container_width=True,
                    type="primary",
                    disabled=not bool(normalized_code),
                )

                if submit_2fa:
                    if normalized_code:
                        code_is_numeric_otp = normalized_code.isdigit() and len(normalized_code) == 6
                        code_is_backup = len(normalized_code) >= 8
                        if not (code_is_numeric_otp or code_is_backup):
                            st.warning("Enter a valid 6-digit code or backup code.")
                        else:
                            try:
                                response = requests.post(
                                    f"{API_URL}/auth/2fa/verify-login",
                                    json={"code": normalized_code},
                                    params={"email": st.session_state.pending_2fa_email},
                                    timeout=5
                                )
                                if response.status_code == 200:
                                    data = response.json()
                                    st.session_state.authenticated = True
                                    st.session_state.access_token = data["access_token"]
                                    if "refresh_token" in data:
                                        st.session_state.refresh_token = data["refresh_token"]
                                    if "session_id" in data:
                                        st.session_state.session_id = data["session_id"]
                                    st.session_state.current_user = data["user"]
                                    st.session_state.pending_2fa_email = None
                                    if st.session_state.pending_remember_me:
                                        st.query_params.token = data["access_token"]
                                    else:
                                        st.query_params.clear()
                                    st.rerun()
                                else:
                                    try:
                                        error_detail = response.json().get('detail', 'Invalid 2FA code')
                                    except Exception:
                                        error_detail = response.text or "Invalid 2FA code"
                                    st.error(error_detail)
                            except requests.exceptions.ConnectionError:
                                st.error(get_api_connection_error_message())
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                    else:
                        st.warning("Please enter your 2FA code")

            if st.button("Cancel", key="cancel_2fa", type="tertiary", use_container_width=True):
                st.session_state.pending_2fa_email = None
                st.rerun()
        else:
            with st.form("login_form"):
                st.markdown(
                    '<div class="auth-form-title">Sign in</div>'
                    '<div class="auth-form-hint">Welcome back. Continue to your knowledge base.</div>',
                    unsafe_allow_html=True,
                )
                email = st.text_input("Email", key="login_email", placeholder="you@example.com")
                password = st.text_input(
                    "Password",
                    type="password",
                    key="login_password",
                    placeholder="Your password"
                )
                remember_me = st.checkbox("Keep me signed in", value=True, key="login_remember_me")

                _email = (email or "").strip()
                _password = password or ""

                submit = st.form_submit_button(
                    "Sign in",
                    use_container_width=True,
                    type="primary",
                )
                st.markdown('<div class="auth-link-actions-marker"></div>', unsafe_allow_html=True)
                _ac_l, _ac_r = st.columns(2)
                with _ac_l:
                    switch_to_register = st.form_submit_button("Create account", type="tertiary", use_container_width=True)
                with _ac_r:
                    trigger_forgot = st.form_submit_button("Forgot password?", type="tertiary", use_container_width=True)

                if switch_to_register:
                    st.session_state.auth_view = "register"
                    st.rerun()
                if trigger_forgot:
                    st.session_state.show_password_reset = True
                    st.rerun()

                if submit:
                    if _email and _password:
                        try:
                            with st.spinner("Signing in..."):
                                response = requests.post(
                                    f"{API_URL}/auth/login",
                                    json={"email": _email, "password": _password},
                                    timeout=5
                                )
                            if response.status_code == 200:
                                data = response.json()
                                if data.get("requires_2fa", False):
                                    st.session_state.pending_2fa_email = _email
                                    st.session_state.pending_remember_me = remember_me
                                    st.rerun()
                                else:
                                    st.session_state.authenticated = True
                                    st.session_state.access_token = data["access_token"]
                                    if "refresh_token" in data:
                                        st.session_state.refresh_token = data["refresh_token"]
                                    if "session_id" in data:
                                        st.session_state.session_id = data["session_id"]
                                    st.session_state.current_user = data["user"]
                                    if remember_me:
                                        st.query_params.token = data["access_token"]
                                    else:
                                        st.query_params.clear()
                                    st.rerun()
                            elif response.status_code == 423:
                                try:
                                    error_detail = response.json().get('detail', 'Account is locked')
                                except Exception:
                                    error_detail = "Account is locked"
                                st.error(error_detail)
                                st.caption("Contact an administrator, or wait for the lockout period to expire.")
                            else:
                                try:
                                    error_detail = response.json().get('detail', 'Unknown error')
                                except Exception:
                                    error_detail = response.text or "Unknown error"
                                if response.status_code in (400, 401):
                                    error_detail = error_detail or "Invalid email or password."
                                st.error(error_detail)
                                if "attempt" in error_detail.lower() and "remaining" in error_detail.lower():
                                    st.caption("Too many failed attempts will lock your account.")
                        except requests.exceptions.ConnectionError:
                            st.error(get_api_connection_error_message())
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                    else:
                        st.error("Please enter both email and password.")

    st.stop()

# Main app (only shown if authenticated)
# Deep linking: open view from URL (?view=documents etc.)
# Auth-only styles are scoped via body:has(.auth-hero); no class toggle needed.
apply_view_from_query_params()

def _sidebar_load_conversation(conversation_id: str) -> bool:
    """Load a conversation into the current chat session."""
    try:
        conv_detail = requests.get(f"{API_URL}/conversations/{conversation_id}", timeout=5).json()
        messages = conv_detail.get("messages", [])
        loaded_history = []
        for msg in messages:
            role = msg.get("role", "assistant")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")[:5] if msg.get("timestamp") else ""
            sources = msg.get("sources", [])
            if content and not (content.strip().startswith("<div") or content.strip().startswith("<span")):
                loaded_history.append((role, content, timestamp, sources))
        st.session_state.current_conversation_id = conversation_id
        st.session_state.chat_history = loaded_history
        st.session_state.pop("_last_processed_query", None)
        return True
    except Exception as e:
        logger.warning(f"Could not load conversation {conversation_id}: {e}")
        return False


# Sidebar - Knowledge Home rail
with st.sidebar:
    is_admin = st.session_state.current_user and st.session_state.current_user.get("role") == "admin"
    current_page = get_current_nav_page()

    def render_nav_button(label: str, page_key: str, btn_key: str):
        is_active = current_page == page_key
        btn_type = "primary" if is_active else "secondary"
        if st.button(label, key=btn_key, use_container_width=True, type=btn_type):
            if page_key != current_page:
                navigate_to_page(page_key)
                st.query_params["view"] = page_key
                st.rerun()

    if st.session_state.current_user:
        user = st.session_state.current_user
        _display = user.get("display_name") or user.get("first_name") or user.get("username", "User")
        _email = user.get("email") or ""
        _role = "Admin" if user.get("role") == "admin" else "Member"
        st.markdown(
            f"""
            <div class="sb-user">
                <p class="sb-user-name">{html.escape(str(_display))}</p>
                <p class="sb-user-meta">{html.escape(str(_email))}<br/>{_role}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Log out", key="sidebar_logout", type="tertiary", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.access_token = None
            st.session_state.current_user = None
            st.session_state.auth_view = "login"
            st.session_state.chat_history = []
            st.session_state.pop("_last_processed_query", None)
            st.query_params.clear()
            st.rerun()

    st.markdown('<div class="sb-cta-marker"></div>', unsafe_allow_html=True)
    if st.button("New chat", key="side_start_new_chat", use_container_width=True, type="primary"):
        st.session_state.pop("_last_processed_query", None)
        try:
            resp = requests.post(f"{API_URL}/conversations", json={}, timeout=5)
            if resp.status_code == 200:
                st.session_state.current_conversation_id = resp.json().get("id")
        except Exception:
            pass
        st.session_state.chat_history = []
        navigate_to_page("chat")
        st.query_params["view"] = "chat"
        st.rerun()

    st.markdown('<p class="sb-section-label">Navigate</p>', unsafe_allow_html=True)
    render_nav_button("Home", "chat", "side_nav_chat")
    render_nav_button("Library", "documents", "side_nav_documents")
    render_nav_button("Upload", "upload", "side_nav_upload")
    render_nav_button("History", "history", "side_nav_history")
    render_nav_button("Saved", "saved_queries", "side_nav_saved_queries")

    st.markdown('<p class="sb-section-label">Recent chats</p>', unsafe_allow_html=True)
    recent_conversations = []
    try:
        conv_resp = requests.get(f"{API_URL}/conversations", timeout=3)
        if conv_resp.status_code == 200:
            all_convs = conv_resp.json().get("conversations", []) or []
            recent_conversations = sorted(
                all_convs,
                key=lambda c: c.get("updated_at") or c.get("created_at") or "",
                reverse=True,
            )[:5]
    except Exception:
        recent_conversations = []

    if recent_conversations:
        for idx, conv in enumerate(recent_conversations):
            title = (conv.get("title") or "Untitled chat").strip() or "Untitled chat"
            if len(title) > 34:
                title = title[:31] + "…"
            is_current = conv.get("id") == st.session_state.current_conversation_id
            label = f"• {title}" if not is_current else f"• {title} (open)"
            if st.button(label, key=f"side_recent_conv_{idx}", use_container_width=True, type="tertiary"):
                if _sidebar_load_conversation(conv.get("id")):
                    navigate_to_page("chat")
                    st.query_params["view"] = "chat"
                    st.rerun()
    else:
        st.markdown('<p class="sb-thread">No chats yet. Start one from Home.</p>', unsafe_allow_html=True)

    with st.expander("Account", expanded=False):
        render_nav_button("Profile", "profile", "side_nav_profile")
        render_nav_button("Password", "change_password", "side_nav_change_password")
        render_nav_button("Two-factor auth", "2fa", "side_nav_2fa")
        render_nav_button("Sessions", "sessions", "side_nav_more_sessions")
        render_nav_button("All threads", "conversations", "side_nav_more_conversations")

    if is_admin:
        with st.expander("Admin", expanded=False):
            render_nav_button("Users", "user_management", "side_nav_more_user_management")
            render_nav_button("Audit", "audit_logs", "side_nav_more_audit_logs")
            render_nav_button("Backup", "export_backup", "side_nav_more_export_backup")
            render_nav_button("Metrics", "health", "side_nav_more_health")

    uploaded_file = None
    uploaded_files = None
    with st.expander("Tools", expanded=False):
        st.caption("Search scope and preferences")
        st.session_state.show_advanced_filters = st.checkbox(
            "Enable advanced filters",
            value=st.session_state.show_advanced_filters,
            key="advanced_filters_toggle",
        )

        if st.session_state.show_advanced_filters:
            try:
                docs_resp = requests.get(f"{API_URL}/documents", headers=get_auth_headers(), timeout=5)
                if docs_resp.status_code == 200:
                    available_docs = docs_resp.json().get("documents", [])
                    if available_docs:
                        doc_names = [doc.get("filename", "") for doc in available_docs]
                        file_types = list({
                            doc.get("file_type", "").upper()
                            for doc in available_docs
                            if doc.get("file_type")
                        })
                        selected_docs = st.multiselect(
                            "Include documents",
                            options=doc_names,
                            default=st.session_state.selected_documents,
                            help="Leave empty to search all.",
                        )
                        st.session_state.selected_documents = selected_docs
                        selected_types = st.multiselect("File types", options=file_types)
                        excluded_docs = st.multiselect("Exclude documents", options=doc_names)
                        date_from = st.date_input("From date", value=None)
                        date_to = st.date_input("To date", value=None)
                        min_relevance = st.slider("Minimum relevance", 0.0, 1.0, 0.0, 0.1)
                        max_results = st.number_input("Max results", 1, 20, 4)
                        st.session_state.advanced_filters = {
                            "document_names": selected_docs or None,
                            "file_types": [t.lower() for t in selected_types] if selected_types else None,
                            "date_from": date_from.strftime("%Y-%m-%d") if date_from else None,
                            "date_to": date_to.strftime("%Y-%m-%d") if date_to else None,
                            "min_relevance": min_relevance if min_relevance > 0 else None,
                            "max_results": max_results if max_results != 4 else None,
                            "exclude_documents": excluded_docs or None,
                        }
                    else:
                        st.caption("No documents available yet.")
                else:
                    st.caption("Unable to load documents.")
            except Exception:
                st.caption("Filters unavailable right now.")
        else:
            try:
                docs_resp = requests.get(f"{API_URL}/documents", headers=get_auth_headers(), timeout=8)
                if docs_resp.status_code == 200:
                    available_docs = docs_resp.json().get("documents", [])
                    if available_docs:
                        doc_names = [doc.get("filename", "") for doc in available_docs]
                        selected = st.multiselect(
                            "Limit search to documents",
                            options=doc_names,
                            default=st.session_state.selected_documents,
                            key="document_filter_select",
                        )
                        st.session_state.selected_documents = selected
                        if selected:
                            st.caption(f"Filtering by {len(selected)} document(s)")
                        else:
                            st.caption("Searching all documents")
                    else:
                        st.caption("No documents available yet.")
            except Exception:
                st.caption("Document filter unavailable.")

        st.checkbox(
            "Real-time streaming",
            key="enable_streaming",
            help="Show answers as they are generated",
        )

        if st.session_state.chat_history:
            if st.button("Clear current chat", use_container_width=True, key="side_clear_chat"):
                st.session_state.chat_history = []
                st.session_state.pop("_last_processed_query", None)
                if st.session_state.current_conversation_id:
                    try:
                        requests.post(
                            f"{API_URL}/conversations/{st.session_state.current_conversation_id}/clear",
                            timeout=5,
                        )
                    except Exception:
                        pass
                st.rerun()
            export_lines = []
            for msg in st.session_state.chat_history:
                role = msg[0]
                content = msg[1] if len(msg) > 1 else ""
                timestamp = msg[2] if len(msg) > 2 else ""
                if role == "user":
                    export_lines.append(f"**You** [{timestamp}]:\n{content}")
                else:
                    export_lines.append(f"**Assistant** [{timestamp}]:\n{content}")
            st.download_button(
                "Export chat",
                "\n\n---\n\n".join(export_lines),
                file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
                key="sidebar_export_chat",
            )

        st.caption("Quick upload")
        uploaded_file = st.file_uploader(
            "Upload single document",
            type=["pdf", "docx", "txt", "csv", "html"],
            key="sidebar_single_upload",
        )
        uploaded_files = st.file_uploader(
            "Upload multiple documents",
            type=["pdf", "docx", "txt", "csv", "html"],
            accept_multiple_files=True,
            key="sidebar_bulk_upload",
        )

    if uploaded_file:
        # Use session state to prevent re-uploading the same file
        upload_key = f"uploaded_{uploaded_file.name}_{uploaded_file.size}"
        if upload_key not in st.session_state:
            st.session_state[upload_key] = False
        
        if not st.session_state[upload_key]:
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
                    upload_resp = requests.post(
                        f"{API_URL}/upload", 
                        files=files, 
                        headers=get_auth_headers(),
                        timeout=30
                    )
                    
                    if upload_resp.status_code == 200:
                        st.session_state[upload_key] = True  # Mark as uploaded
                        st.success(f"✅ {uploaded_file.name} uploaded successfully!")
                        st.info("💡 Document is being processed in the background. It may take 10–30 seconds to appear in **Documents**. Open Documents and click **🔄 Refresh** to see it.")
                        logger.info(f"Uploaded: {uploaded_file.name}")
                        # Refresh KB status without rerun (to avoid infinite loop)
                        time.sleep(1)
                        try:
                            status_resp = requests.get(f"{API_URL}/status", headers=get_auth_headers(), timeout=2)
                            if status_resp.status_code == 200:
                                st.session_state.kb_status = status_resp.json()
                        except requests.exceptions.ConnectionError:
                            logger.warning("Cannot connect to API to refresh status")
                        except Exception as e:
                            logger.warning(f"Error refreshing status: {e}")
                    else:
                        st.error(f"❌ Upload failed: {upload_resp.status_code}")
                        try:
                            error_data = upload_resp.json()
                            st.error(f"Error: {error_data.get('detail', upload_resp.text)}")
                        except:
                            st.error(f"Error: {upload_resp.text}")
                except requests.exceptions.ConnectionError:
                    st.error(get_api_connection_error_message())
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        else:
            # File was already uploaded, show success message
            st.success(f"✅ {uploaded_file.name} (already uploaded)")
    
    # Handle bulk upload
    try:
        has_uploaded_files = uploaded_files is not None and len(uploaded_files) > 0
    except (NameError, TypeError):
        has_uploaded_files = False
    
    if has_uploaded_files:
        # Use session state to prevent re-uploading the same files
        files_key = "_".join([f"{f.name}_{f.size}" for f in uploaded_files])
        bulk_upload_key = f"bulk_uploaded_{files_key}"
        if bulk_upload_key not in st.session_state:
            st.session_state[bulk_upload_key] = False
        
        if not st.session_state[bulk_upload_key]:
            with st.spinner(f"Uploading {len(uploaded_files)} file(s)..."):
                try:
                    files_data = []
                    for uploaded_file in uploaded_files:
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        mime_types = {
                            "pdf": "application/pdf",
                            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "txt": "text/plain",
                            "csv": "text/csv",
                            "html": "text/html"
                        }
                        mime_type = mime_types.get(file_ext, "application/octet-stream")
                        files_data.append(("files", (uploaded_file.name, uploaded_file, mime_type)))
                    
                    upload_resp = requests.post(
                        f"{API_URL}/upload/bulk",
                        files=files_data,
                        headers=get_auth_headers(),
                        timeout=120
                    )
                    
                    if upload_resp.status_code == 200:
                        st.session_state[bulk_upload_key] = True  # Mark as uploaded
                        data = upload_resp.json()
                        successful = data.get("successful", 0)
                        failed = data.get("failed", 0)
                        results = data.get("results", [])
                        
                        if successful > 0:
                            st.success(f"✅ Successfully uploaded {successful} file(s)")
                        if failed > 0:
                            st.warning(f"⚠️ {failed} file(s) failed to upload")
                        
                        # Show detailed results
                        if results:
                            with st.expander("📋 Upload Details", expanded=False):
                                for result in results:
                                    status_icon = "✅" if result.get("status") == "success" else "❌"
                                    st.write(f"{status_icon} **{result.get('filename')}**: {result.get('message', '')}")
                        
                        st.info("💡 **Tip:** Processing happens in the background. Wait 5-10 seconds, then click '🔄 Check API Status' to see updated chunk count.")
                        
                        # Refresh KB status without rerun (to avoid infinite loop)
                        time.sleep(1)
                        try:
                            status_resp = requests.get(f"{API_URL}/status", headers=get_auth_headers(), timeout=2)
                            if status_resp.status_code == 200:
                                st.session_state.kb_status = status_resp.json()
                        except:
                            pass
                    else:
                        st.error(f"❌ Bulk upload failed: {upload_resp.status_code}")
                        try:
                            error_data = upload_resp.json()
                            st.error(f"Error: {error_data.get('detail', upload_resp.text)}")
                        except:
                            st.error(f"Error: {upload_resp.text}")
                except requests.exceptions.ConnectionError:
                    st.error(get_api_connection_error_message())
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

    st.markdown('<div class="sb-footer">Incident Assistant</div>', unsafe_allow_html=True)

def toggle_streamlit_sidebar():
    """Click Streamlit's native expand/collapse control (query-param open is first-load only)."""
    components.html(
        """
        <script>
        (function () {
          const doc = window.parent.document;
          const expand = doc.querySelector('[data-testid="stExpandSidebarButton"]');
          const collapse =
            doc.querySelector('[data-testid="stBaseButton-headerNoPadding"][aria-label="Collapse sidebar"]') ||
            doc.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
            doc.querySelector('[data-testid="stSidebarCollapseButton"]');
          if (expand) {
            expand.click();
            return;
          }
          if (collapse) {
            collapse.click();
          }
        })();
        </script>
        """,
        height=0,
        width=0,
    )


# Sidebar toggle helper banner
st.markdown(
    """
    <div class="help-banner">
    </div>
    """,
    unsafe_allow_html=True
)

# ===== ZONE-BASED LAYOUT: Top bar (Header + Primary Nav) =====
current_page = get_current_nav_page()
is_admin = st.session_state.current_user and st.session_state.current_user.get("role") == "admin"

# Top zone: brand + primary destinations + account menu
st.markdown(
    """
    <div class="zone-top-nav">
        <div class="nav-brand-row">
            <div class="nav-brand">
                <span class="nav-brand-icon">📚</span>
                <span class="nav-brand-text">Incident Assistant</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown('<div class="nav-bar-row">', unsafe_allow_html=True)
col_open_sidebar, col_nav, col_avatar = st.columns([1, 4, 1])
with col_open_sidebar:
    if st.button("☰", key="nav_toggle_sidebar", help="Open or close sidebar"):
        st.session_state["_do_sidebar_toggle"] = True
    if st.session_state.pop("_do_sidebar_toggle", False):
        toggle_streamlit_sidebar()
with col_nav:
    st.markdown('<div class="nav-buttons-marker"></div>', unsafe_allow_html=True)
    nav_items = [
        ("Home", "chat"),
        ("Library", "documents"),
        ("Upload", "upload"),
        ("History", "history"),
    ]
    if is_admin:
        nav_items.append(("Admin", "user_management"))
    cols = st.columns(len(nav_items))
    for i, (label, key) in enumerate(nav_items):
        with cols[i]:
            is_active = current_page == key or (key == "history" and current_page in ("history", "saved_queries", "conversations"))
            if key == "user_management":
                is_active = current_page in ("user_management", "audit_logs", "export_backup", "health")
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"nav_{key}", use_container_width=True, type=btn_type):
                if key == "documents" and current_page == "documents":
                    st.session_state.show_documents = False
                    st.query_params["view"] = "chat"
                    st.rerun()
                elif key == "upload" and current_page == "upload":
                    st.session_state.show_upload = False
                    st.query_params["view"] = "chat"
                    st.rerun()
                else:
                    navigate_to_page(key)
                    st.query_params["view"] = key
                    st.rerun()
with col_avatar:
    st.markdown('<div class="nav-avatar-col"></div>', unsafe_allow_html=True)
    user = st.session_state.get("current_user") or {}
    username = user.get("display_name") or user.get("first_name") or user.get("email") or user.get("username", "User")
    initial = (username[0] if username else "U").upper()
    _a1, _a2, _a3 = st.columns([1, 1, 1])
    with _a2:
        with st.popover(initial, use_container_width=True):
            st.caption(username)
            if st.button("Profile", key="nav_pop_profile", use_container_width=True):
                navigate_to_page("profile")
                st.query_params["view"] = "profile"
                st.rerun()
            if st.button("Password", key="nav_pop_password", use_container_width=True):
                navigate_to_page("change_password")
                st.query_params["view"] = "change_password"
                st.rerun()
            if st.button("Two-factor auth", key="nav_pop_2fa", use_container_width=True):
                navigate_to_page("2fa")
                st.query_params["view"] = "2fa"
                st.rerun()
            if st.button("Log out", key="nav_pop_logout", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.access_token = None
                st.session_state.current_user = None
                st.session_state.auth_view = "login"
                st.session_state.chat_history = []
                st.session_state.pop("_last_processed_query", None)
                st.query_params.clear()
                st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# Document Management Dashboard
if st.session_state.get("show_documents", False):
    st.markdown("---")
    col_title, col_refresh, col_close = st.columns([3, 1, 1])
    with col_title:
        st.markdown("### 📚 Document Management Dashboard")
    with col_refresh:
        if st.button("🔄 Refresh", key="refresh_documents", use_container_width=True, help="Refresh the document list (use after uploading new files)"):
            st.rerun()
    with col_close:
        if st.button("✕ Close", key="close_documents_dashboard", use_container_width=True, help="Close document dashboard and return to chat"):
            st.session_state.show_documents = False
            st.query_params["view"] = "chat"
            st.rerun()
    
    # Show loading spinner
    try:
        with st.spinner("Loading documents..."):
            try:
                docs_resp = requests.get(f"{API_URL}/documents", headers=get_auth_headers(), timeout=30)
            except requests.exceptions.ConnectionError:
                st.error(get_api_connection_error_message())
                docs_resp = None
            except requests.exceptions.Timeout:
                st.error("⏱️ Request timed out. Please try again.")
                docs_resp = None
        
        if docs_resp and docs_resp.status_code == 200:
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
                st.caption("💡 **Just uploaded?** Processing takes 10–30 seconds. Click **🔄 Refresh** above to check again.")
                st.caption("💡 If you just uploaded a file, wait 10–30 seconds for processing, then click **Refresh** above.")
            else:
                st.markdown("---")
                
                # Bulk Operations Section
                st.markdown("#### 🔧 Bulk Operations")
                bulk_col1, bulk_col2, bulk_col3 = st.columns(3)
                
                with bulk_col1:
                    if st.button("🔄 Reprocess All Documents", use_container_width=True, help="Reprocess all documents in the knowledge base"):
                        try:
                            with st.spinner("Queuing documents for reprocessing..."):
                                reprocess_resp = requests.post(
                                    f"{API_URL}/documents/bulk-reprocess",
                                    json={"filenames": None},  # None means all documents
                                    headers=get_auth_headers(),
                                    timeout=60
                                )
                                if reprocess_resp.status_code == 200:
                                    data = reprocess_resp.json()
                                    st.success(f"✅ Queued {data.get('successful', 0)} document(s) for reprocessing")
                                    if data.get('failed', 0) > 0:
                                        st.warning(f"⚠️ {data.get('failed', 0)} document(s) failed to queue")
                                    st.info("💡 Reprocessing happens in the background. Check back in a few minutes.")
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error(f"❌ Reprocess failed: {reprocess_resp.status_code}")
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Cannot connect to API")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                
                with bulk_col2:
                    if st.button("🗑️ Batch Delete Selected", use_container_width=True, help="Delete all selected documents"):
                        selected_for_delete = [doc["filename"] for doc in documents if st.session_state.get(f"select_{doc['filename']}", False)]
                        if not selected_for_delete:
                            st.warning("⚠️ No documents selected. Use checkboxes to select documents.")
                        else:
                            if st.session_state.get("confirm_batch_delete", False):
                                try:
                                    with st.spinner(f"Deleting {len(selected_for_delete)} document(s)..."):
                                        delete_resp = requests.post(
                                            f"{API_URL}/documents/batch-delete",
                                            json={"filenames": selected_for_delete},
                                            headers=get_auth_headers(),
                                            timeout=60
                                        )
                                        if delete_resp.status_code == 200:
                                            data = delete_resp.json()
                                            st.success(f"✅ Deleted {data.get('successful', 0)} document(s), {data.get('total_chunks_deleted', 0)} chunks removed")
                                            if data.get('failed', 0) > 0:
                                                st.warning(f"⚠️ {data.get('failed', 0)} document(s) failed to delete")
                                            # Clear selections
                                            for filename in selected_for_delete:
                                                st.session_state[f"select_{filename}"] = False
                                            st.session_state["confirm_batch_delete"] = False
                                            time.sleep(2)
                                            st.rerun()
                                        else:
                                            st.error(f"❌ Batch delete failed: {delete_resp.status_code}")
                                            st.session_state["confirm_batch_delete"] = False
                                except requests.exceptions.ConnectionError:
                                    st.error("❌ Cannot connect to API")
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                                    st.session_state["confirm_batch_delete"] = False
                            else:
                                st.session_state["confirm_batch_delete"] = True
                                st.warning(f"⚠️ Are you sure you want to delete {len(selected_for_delete)} document(s)?")
                                st.rerun()
                
                with bulk_col3:
                    if st.button("🔄 Reprocess Selected", use_container_width=True, help="Reprocess selected documents"):
                        selected_for_reprocess = [doc["filename"] for doc in documents if st.session_state.get(f"select_{doc['filename']}", False)]
                        if not selected_for_reprocess:
                            st.warning("⚠️ No documents selected. Use checkboxes to select documents.")
                        else:
                            try:
                                with st.spinner(f"Queuing {len(selected_for_reprocess)} document(s) for reprocessing..."):
                                    reprocess_resp = requests.post(
                                        f"{API_URL}/documents/bulk-reprocess",
                                        json={"filenames": selected_for_reprocess},
                                        headers=get_auth_headers(),
                                        timeout=60
                                    )
                                    if reprocess_resp.status_code == 200:
                                        data = reprocess_resp.json()
                                        st.success(f"✅ Queued {data.get('successful', 0)} document(s) for reprocessing")
                                        if data.get('failed', 0) > 0:
                                            st.warning(f"⚠️ {data.get('failed', 0)} document(s) failed to queue")
                                        st.info("💡 Reprocessing happens in the background. Check back in a few minutes.")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Reprocess failed: {reprocess_resp.status_code}")
                            except requests.exceptions.ConnectionError:
                                st.error("❌ Cannot connect to API")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                
                st.markdown("---")
                
                # Document table with selection checkboxes
                st.markdown("#### 📄 Documents")
                for idx, doc in enumerate(documents):
                    with st.container():
                        # Add checkbox for selection
                        filename = doc.get('filename', '')
                        checkbox_key = f"select_{filename}"
                        col_check, col1, col2, col3, col4 = st.columns([0.5, 2.5, 1, 1, 1])
                        
                        with col_check:
                            st.checkbox(
                                f"Select {filename or 'document'}",
                                value=st.session_state.get(checkbox_key, False),
                                key=checkbox_key,
                                label_visibility="collapsed"
                            )
                        
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
                            # Show version info
                            if doc.get("version_count") and doc.get("version_count", 0) > 1:
                                st.caption(f"📦 Version {doc.get('version', 'N/A')} of {doc.get('version_count')}")
                            elif doc.get("version"):
                                st.caption(f"📦 Version {doc.get('version')}")
                        
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
                            # Version history button
                            if doc.get("version_count") and doc.get("version_count", 0) > 1:
                                version_key = f"versions_{idx}_{doc.get('filename', '')}"
                                if st.button("📦 Versions", key=version_key, use_container_width=True):
                                    st.session_state[f"show_versions_{doc.get('filename')}"] = True
                                    st.rerun()
                            
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
                                                headers=get_auth_headers(),
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
        st.info("💡 **Tip:** Start the API server with: `python run.py api`")
    except Exception as e:
        st.error(f"❌ Error loading documents: {str(e)}")
        st.info("💡 **Tip:** Check the API logs in `logs/api.log` for more details.")
    
    st.markdown("---")

# Upload view - primary focus for adding documents to the knowledge base
if st.session_state.get("show_upload", False):
    st.markdown("---")
    col_title, col_close = st.columns([4, 1])
    with col_title:
        st.markdown("### 📤 Upload Documents")
        st.caption("Add documents to your knowledge base. Supported formats: PDF, Word, TXT, CSV, HTML.")
    with col_close:
        if st.button("✕ Close", key="close_upload_view", use_container_width=True, help="Return to chat"):
            st.session_state.show_upload = False
            st.query_params["view"] = "chat"
            st.rerun()
    
    st.markdown("---")
    
    # Upload UI - prominent in main area
    up_col1, up_col2 = st.columns(2)
    with up_col1:
        uploaded_file = st.file_uploader(
            "📄 Upload Single Document",
            type=["pdf", "docx", "txt", "csv", "html"],
            help="Upload a single document to enhance the knowledge base",
            key="upload_view_single"
        )
    with up_col2:
        uploaded_files = st.file_uploader(
            "📚 Upload Multiple Documents (Bulk)",
            type=["pdf", "docx", "txt", "csv", "html"],
            help="Upload multiple documents at once",
            accept_multiple_files=True,
            key="upload_view_bulk"
        )
    
    if uploaded_file:
        upload_key = f"upload_view_{uploaded_file.name}_{uploaded_file.size}"
        if upload_key not in st.session_state:
            st.session_state[upload_key] = False
        if not st.session_state[upload_key]:
            with st.spinner("Uploading..."):
                try:
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    mime_types = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "txt": "text/plain", "csv": "text/csv", "html": "text/html"}
                    mime_type = mime_types.get(file_ext, "application/octet-stream")
                    files = {"file": (uploaded_file.name, uploaded_file, mime_type)}
                    upload_resp = requests.post(f"{API_URL}/upload", files=files, headers=get_auth_headers(), timeout=30)
                    if upload_resp.status_code == 200:
                        st.session_state[upload_key] = True
                        st.success(f"✅ {uploaded_file.name} uploaded!")
                        st.info("💡 Processing in background (10–30s). Go to **Documents** and click **🔄 Refresh** to see it.")
                        st.rerun()
                    else:
                        st.error(f"❌ Upload failed: {upload_resp.status_code}")
                except requests.exceptions.ConnectionError:
                    st.error(get_api_connection_error_message())
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        else:
            st.success(f"✅ {uploaded_file.name} (already uploaded)")
    
    try:
        has_uploaded_files = uploaded_files is not None and len(uploaded_files) > 0
    except (NameError, TypeError):
        has_uploaded_files = False
    
    if has_uploaded_files:
        files_key = "_".join([f"{f.name}_{f.size}" for f in uploaded_files])
        bulk_upload_key = f"upload_view_bulk_{files_key}"
        if bulk_upload_key not in st.session_state:
            st.session_state[bulk_upload_key] = False
        if not st.session_state[bulk_upload_key]:
            with st.spinner(f"Uploading {len(uploaded_files)} file(s)..."):
                try:
                    files_data = []
                    for uf in uploaded_files:
                        file_ext = uf.name.split('.')[-1].lower()
                        mime_types = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "txt": "text/plain", "csv": "text/csv", "html": "text/html"}
                        mime_type = mime_types.get(file_ext, "application/octet-stream")
                        files_data.append(("files", (uf.name, uf, mime_type)))
                    upload_resp = requests.post(f"{API_URL}/upload/bulk", files=files_data, headers=get_auth_headers(), timeout=120)
                    if upload_resp.status_code == 200:
                        st.session_state[bulk_upload_key] = True
                        data = upload_resp.json()
                        st.success(f"✅ Uploaded {data.get('successful', 0)} file(s)")
                        if data.get('failed', 0) > 0:
                            st.warning(f"⚠️ {data.get('failed', 0)} failed")
                        st.info("💡 Processing in background. Go to **Documents** and click **🔄 Refresh**.")
                        st.rerun()
                    else:
                        st.error(f"❌ Bulk upload failed: {upload_resp.status_code}")
                except requests.exceptions.ConnectionError:
                    st.error(get_api_connection_error_message())
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        else:
            st.success(f"✅ Bulk upload already completed")
    
    st.markdown("---")
    if st.button("📚 View Documents", use_container_width=True, key="upload_view_docs"):
        st.session_state.show_upload = False
        st.session_state.show_documents = True
        st.query_params["view"] = "documents"
        st.rerun()

# Search History Dashboard
if st.session_state.get("show_history", False):
    st.markdown("---")
    st.markdown("### 📜 Search History")
    
    try:
        with st.spinner("Loading history..."):
            try:
                history_resp = requests.get(f"{API_URL}/history?limit=100", timeout=10)
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Make sure the API server is running.")
                history_resp = None
        
        if history_resp and history_resp.status_code == 200:
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
            try:
                saved_resp = requests.get(f"{API_URL}/saved-queries", timeout=10)
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Make sure the API server is running.")
                st.info("💡 **Tip:** Start the API server with: `python run.py api`")
                saved_resp = None
            except requests.exceptions.Timeout:
                st.error("⏱️ Request timed out. Please try again.")
                saved_resp = None
        
        if saved_resp and saved_resp.status_code == 200:
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

# Conversations Dashboard
if st.session_state.get("show_conversations", False):
    st.markdown("---")
    st.markdown("### 💬 Conversation Management")
    
    try:
        with st.spinner("Loading conversations..."):
            try:
                convs_resp = requests.get(f"{API_URL}/conversations", timeout=10)
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Make sure the API server is running.")
                convs_resp = None
        
        if convs_resp and convs_resp.status_code == 200:
            data = convs_resp.json()
            conversations = data.get("conversations", [])
            total = data.get("total", 0)
            
            if total == 0:
                st.info("📭 No conversations yet. Start chatting to create your first conversation!")
            else:
                st.metric("Total Conversations", total)
                st.markdown("---")
                
                # Display conversations
                for idx, conv in enumerate(conversations):
                    with st.container():
                        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                        
                        with col1:
                            is_current = conv.get("id") == st.session_state.current_conversation_id
                            title_style = "**" if is_current else ""
                            st.markdown(f"{title_style}💬 {conv.get('title', 'Untitled')}{title_style}")
                            st.caption(f"📅 {conv.get('created_at', '')[:10]}")
                            st.caption(f"💬 {conv.get('message_count', 0)} messages")
                            if is_current:
                                st.caption("✅ **Current conversation**")
                        
                        with col2:
                            if st.button("📂 Open", key=f"open_conv_{idx}", use_container_width=True):
                                st.session_state.current_conversation_id = conv.get("id")
                                # Load conversation messages
                                try:
                                    conv_detail = requests.get(
                                        f"{API_URL}/conversations/{conv.get('id')}",
                                        timeout=5
                                    ).json()
                                    messages = conv_detail.get("messages", [])
                                    loaded_history = []
                                    for msg in messages:
                                        role = msg.get("role", "assistant")
                                        content = msg.get("content", "")
                                        timestamp = msg.get("timestamp", "")[:5] if msg.get("timestamp") else ""
                                        sources = msg.get("sources", [])
                                        
                                        # Validate content - skip corrupted messages
                                        if content and not (content.strip().startswith("<div") or content.strip().startswith("<span")):
                                            loaded_history.append((role, content, timestamp, sources))
                                        elif content:
                                            logger.warning(f"Skipped corrupted message with HTML content: {content[:50]}")
                                    
                                    st.session_state.chat_history = loaded_history
                                except Exception as e:
                                    logger.error(f"Error loading conversation: {e}")
                                    st.session_state.chat_history = []
                                st.session_state.pop("_last_processed_query", None)
                                st.session_state.show_conversations = False
                                st.rerun()
                        
                        with col3:
                            if st.button("🗑️ Delete", key=f"delete_conv_{idx}", use_container_width=True):
                                try:
                                    delete_resp = requests.delete(
                                        f"{API_URL}/conversations/{conv.get('id')}",
                                        timeout=5
                                    )
                                    if delete_resp.status_code == 200:
                                        if conv.get("id") == st.session_state.current_conversation_id:
                                            st.session_state.current_conversation_id = None
                                        st.success("✅ Deleted")
                                        time.sleep(0.5)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                        
                        with col4:
                            if st.button("🗑️ Clear", key=f"clear_conv_{idx}", use_container_width=True):
                                try:
                                    clear_resp = requests.post(
                                        f"{API_URL}/conversations/{conv.get('id')}/clear",
                                        timeout=5
                                    )
                                    if clear_resp.status_code == 200:
                                        if conv.get("id") == st.session_state.current_conversation_id:
                                            st.session_state.chat_history = []
                                            st.session_state.pop("_last_processed_query", None)
                                        st.success("✅ Cleared")
                                        time.sleep(0.5)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                        
                        st.markdown("---")
        else:
            st.error(f"❌ Failed to load conversations: {convs_resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure the API server is running.")
    except Exception as e:
        st.error(f"❌ Error loading conversations: {str(e)}")
    
    # Close button
    if st.button("❌ Close Conversations", use_container_width=True):
        st.session_state.show_conversations = False
        st.rerun()
    
    st.markdown("---")

# Performance Metrics Dashboard
if st.session_state.get("show_health", False):
    st.markdown("---")
    st.markdown("### 📊 Performance Metrics Dashboard")
    
    # Time period selector
    col1, col2 = st.columns([3, 1])
    with col1:
        hours = st.selectbox("Time Period", [1, 6, 24, 48, 168], index=2, format_func=lambda x: f"Last {x} hours")
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    try:
        # Get performance stats
        with st.spinner("Loading performance metrics..."):
            perf_resp = requests.get(f"{API_URL}/health/performance?hours={hours}", timeout=60)
        
        if perf_resp.status_code == 200:
            data = perf_resp.json()
            stats = data.get("stats", {})
            
            # Overall metrics
            st.markdown("#### 📈 Query Performance")
            query_stats = stats.get("queries", {})
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Queries", query_stats.get("total", 0))
            with col2:
                st.metric("Last Hour", query_stats.get("last_hour", 0))
            with col3:
                st.metric("Throughput/Hour", f"{query_stats.get('throughput_per_hour', 0):.1f}")
            with col4:
                st.metric("Avg Sources", f"{query_stats.get('avg_sources_per_query', 0):.1f}")
            
            # Response time metrics
            st.markdown("#### ⏱️ Response Time Statistics")
            rt_stats = query_stats.get("response_time", {})
            
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Min", f"{rt_stats.get('min', 0):.3f}s")
            with col2:
                st.metric("Avg", f"{rt_stats.get('avg', 0):.3f}s")
            with col3:
                st.metric("Max", f"{rt_stats.get('max', 0):.3f}s")
            with col4:
                st.metric("P50", f"{rt_stats.get('p50', 0):.3f}s", help="50th percentile")
            with col5:
                st.metric("P95", f"{rt_stats.get('p95', 0):.3f}s", help="95th percentile")
            with col6:
                st.metric("P99", f"{rt_stats.get('p99', 0):.3f}s", help="99th percentile")
            
            # Error metrics
            st.markdown("#### ⚠️ Error Statistics")
            error_stats = stats.get("errors", {})
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Errors", error_stats.get("total", 0))
            with col2:
                error_rate = error_stats.get("rate_percent", 0)
                error_color = "normal" if error_rate < 5 else "inverse" if error_rate > 10 else "off"
                st.metric("Error Rate", f"{error_rate:.2f}%", delta=None)
            
            # Error breakdown by type
            error_types = error_stats.get("by_type", {})
            if error_types:
                st.markdown("**Error Breakdown:**")
                for error_type, count in error_types.items():
                    st.text(f"  • {error_type}: {count}")
            
            # Document processing metrics
            st.markdown("#### 📄 Document Processing")
            doc_stats = stats.get("document_processing", {})
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Processed", doc_stats.get("total_processed", 0))
            with col2:
                success_rate = doc_stats.get("success_rate_percent", 100)
                st.metric("Success Rate", f"{success_rate:.1f}%")
            with col3:
                st.metric("Avg Processing Time", f"{doc_stats.get('avg_processing_time_sec', 0):.3f}s")
            with col4:
                st.metric("Avg Chunks/Doc", f"{doc_stats.get('avg_chunks_per_doc', 0):.1f}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Successful", doc_stats.get("successful", 0))
            with col2:
                st.metric("Failed", doc_stats.get("failed", 0))
            
            total_size_mb = doc_stats.get("total_size_mb", 0)
            if total_size_mb > 0:
                st.metric("Total Size Processed", f"{total_size_mb:.2f} MB")
            
            # Cache statistics
            try:
                cache_resp = requests.get(f"{API_URL}/cache/stats", timeout=5)
                if cache_resp.status_code == 200:
                    cache_data = cache_resp.json()
                    if cache_data.get("enabled"):
                        st.markdown("#### ⚡ Query Cache Statistics")
                        cache_stats = cache_data
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            hit_rate = cache_stats.get("hit_rate", 0)
                            hit_color = "normal" if hit_rate > 50 else "inverse" if hit_rate < 20 else "off"
                            st.metric("Cache Hit Rate", f"{hit_rate:.1f}%", delta=None)
                        with col2:
                            st.metric("Cache Size", f"{cache_stats.get('size', 0)}/{cache_stats.get('max_size', 0)}")
                        with col3:
                            st.metric("Cache Hits", cache_stats.get("hits", 0))
                        with col4:
                            st.metric("Cache Misses", cache_stats.get("misses", 0))
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Total Requests", cache_stats.get("total_requests", 0))
                        with col2:
                            st.metric("Avg Access Count", f"{cache_stats.get('avg_access_count', 0):.1f}")
                        
                        # Cache management buttons
                        st.markdown("#### 🗑️ Cache Management")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Clear Cache", use_container_width=True, help="Remove all cached queries"):
                                try:
                                    clear_resp = requests.delete(f"{API_URL}/cache", timeout=5)
                                    if clear_resp.status_code == 200:
                                        st.success("✅ Cache cleared successfully!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed to clear cache: {clear_resp.status_code}")
                                except Exception as e:
                                    st.error(f"❌ Error clearing cache: {str(e)}")
                        with col2:
                            if st.button("Clear Expired", use_container_width=True, help="Remove expired cache entries"):
                                st.info("💡 Expired entries are automatically cleaned on access")
                        
                        # Cache insights
                        if hit_rate > 50:
                            st.success(f"✅ **Excellent cache performance** - {hit_rate:.1f}% of queries are served from cache!")
                        elif hit_rate > 20:
                            st.info(f"ℹ️ Cache is working - {hit_rate:.1f}% hit rate. More queries will improve this.")
                        else:
                            st.warning(f"⚠️ Low cache hit rate ({hit_rate:.1f}%) - System is still learning query patterns")
            except Exception as e:
                # Cache stats are optional, don't fail if unavailable
                pass
            
            # Performance insights
            st.markdown("#### 💡 Performance Insights")
            insights = []
            
            avg_time = rt_stats.get("avg", 0)
            if avg_time > 5:
                insights.append("⚠️ **Slow responses detected** - Average response time is above 5 seconds")
            elif avg_time > 2:
                insights.append("ℹ️ Response times are moderate - Consider optimization")
            else:
                insights.append("✅ **Excellent response times** - System is performing well")
            
            if error_rate > 10:
                insights.append("🔴 **High error rate** - Immediate attention required")
            elif error_rate > 5:
                insights.append("⚠️ **Elevated error rate** - Monitor closely")
            else:
                insights.append("✅ **Low error rate** - System is stable")
            
            for insight in insights:
                st.markdown(f"- {insight}")
        
        # Advanced Analytics Dashboard
        st.markdown("---")
        st.markdown("### 📊 Advanced Analytics Dashboard")
        
        # Analytics tabs
        tab1, tab2, tab3, tab4 = st.tabs(["📈 Query Analytics", "📚 Document Usage", "🎯 Knowledge Gaps", "👥 User Insights"])
        
        with tab1:
            try:
                with st.spinner("Loading query analytics..."):
                    auth_headers = get_auth_headers()
                    analytics_resp = requests.get(f"{API_URL}/analytics/queries?hours={hours}", headers=auth_headers, timeout=60)
                
                if analytics_resp.status_code == 200:
                    analytics_data = analytics_resp.json()
                    
                    # Overall stats
                    st.markdown("#### 📊 Overview")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Queries", analytics_data.get("total_queries", 0))
                    with col2:
                        cache_perf = analytics_data.get("cache_performance", {})
                        st.metric("Cache Hit Rate", f"{cache_perf.get('hit_rate', 0):.1f}%")
                    with col3:
                        conf_stats = analytics_data.get("confidence_stats")
                        if conf_stats:
                            st.metric("Avg Confidence", f"{conf_stats.get('avg', 0):.3f}")
                    
                    # Most asked queries
                    st.markdown("#### 🔝 Most Asked Queries")
                    most_asked = analytics_data.get("most_asked_queries", [])
                    if most_asked:
                        for idx, entry in enumerate(most_asked[:10], 1):
                            pattern = entry.get("pattern_data", {})
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.text(f"{idx}. {entry.get('query', '')[:80]}...")
                            with col2:
                                st.caption(f"Count: {entry.get('count', 0)}")
                            with col3:
                                avg_time = pattern.get("avg_response_time", 0)
                                st.caption(f"Avg: {avg_time:.2f}s")
                    else:
                        st.info("No query data available yet. Start asking questions to see analytics!")
                    
                    # Intent distribution
                    st.markdown("#### 🎯 Query Intent Distribution")
                    intent_dist = analytics_data.get("intent_distribution", {})
                    if intent_dist:
                        intent_perf = analytics_data.get("intent_performance", {})
                        for intent, count in sorted(intent_dist.items(), key=lambda x: x[1], reverse=True):
                            perf = intent_perf.get(intent, {})
                            col1, col2, col3 = st.columns([2, 1, 1])
                            with col1:
                                st.text(f"**{intent.replace('_', ' ').title()}**")
                            with col2:
                                st.caption(f"Queries: {count}")
                            with col3:
                                if perf:
                                    st.caption(f"Avg Time: {perf.get('avg_response_time', 0):.2f}s")
                    else:
                        st.info("No intent data available")
                    
                    # Confidence statistics
                    conf_stats = analytics_data.get("confidence_stats")
                    if conf_stats:
                        st.markdown("#### 📊 Answer Confidence Statistics")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Average", f"{conf_stats.get('avg', 0):.3f}")
                        with col2:
                            st.metric("High Confidence", conf_stats.get("high_confidence_count", 0), help="Confidence >= 0.7")
                        with col3:
                            st.metric("Low Confidence", conf_stats.get("low_confidence_count", 0), help="Confidence < 0.5")
                        with col4:
                            st.metric("Range", f"{conf_stats.get('min', 0):.2f} - {conf_stats.get('max', 0):.2f}")
                    
                    # Verification stats
                    verif_stats = analytics_data.get("verification_stats", {})
                    if verif_stats:
                        st.markdown("#### ✅ Answer Verification Statistics")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Supported", verif_stats.get("supported_count", 0))
                        with col2:
                            st.metric("Partial", verif_stats.get("partial_count", 0))
                        with col3:
                            st.metric("Unsupported", verif_stats.get("unsupported_count", 0))
                        with col4:
                            st.metric("Not Verified", verif_stats.get("not_verified_count", 0))
                    
                    # Query trends (hourly)
                    trends = analytics_data.get("query_trends", [])
                    if trends and len(trends) > 1:
                        st.markdown("#### 📈 Query Trends (Hourly)")
                        import pandas as pd
                        df_trends = pd.DataFrame(trends)
                        st.line_chart(df_trends.set_index("hour")["count"])
                else:
                    st.error(f"❌ Failed to load analytics: {analytics_resp.status_code}")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Make sure the API server is running.")
            except Exception as e:
                st.error(f"❌ Error loading analytics: {str(e)}")
        
        with tab2:
            try:
                with st.spinner("Loading document usage analytics..."):
                    # Get auth headers if available
                    auth_headers = {}
                    if st.session_state.authenticated and st.session_state.get("access_token"):
                        auth_headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
                    
                    analytics_resp = requests.get(f"{API_URL}/analytics/queries?hours={hours}", headers=auth_headers, timeout=60)
                
                if analytics_resp.status_code == 200:
                    analytics_data = analytics_resp.json()
                    doc_usage = analytics_data.get("document_usage", [])
                    
                    if doc_usage:
                        st.markdown("#### 📚 Most Queried Documents")
                        for idx, doc in enumerate(doc_usage[:10], 1):
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.text(f"{idx}. {doc.get('document', 'Unknown')}")
                            with col2:
                                st.caption(f"Queries: {doc.get('query_count', 0)}")
                            with col3:
                                last_acc = doc.get("last_accessed")
                                if last_acc:
                                    try:
                                        acc_time = datetime.fromisoformat(last_acc.replace('Z', '+00:00'))
                                        st.caption(f"Last: {acc_time.strftime('%H:%M')}")
                                    except:
                                        st.caption("Recent")
                        
                        # Document usage chart
                        if len(doc_usage) > 0:
                            st.markdown("#### 📊 Document Usage Chart")
                            import pandas as pd
                            df_docs = pd.DataFrame(doc_usage)
                            st.bar_chart(df_docs.set_index("document")["query_count"])
                    else:
                        st.info("No document usage data available yet.")
                else:
                    st.error(f"❌ Failed to load document usage: {analytics_resp.status_code}")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
        
        with tab3:
            try:
                with st.spinner("Analyzing knowledge gaps..."):
                    auth_headers = get_auth_headers()
                    gaps_resp = requests.get(f"{API_URL}/analytics/knowledge-gaps?hours={hours}", headers=auth_headers, timeout=60)
                
                if gaps_resp.status_code == 200:
                    gaps_data = gaps_resp.json()
                    gaps = gaps_data.get("gaps", [])
                    
                    if gaps:
                        st.markdown(f"#### 🎯 Identified Knowledge Gaps ({len(gaps)})")
                        st.info("💡 These are areas where queries have low confidence or no sources. Consider adding more content.")
                        
                        for gap in gaps:
                            with st.expander(f"**{gap.get('intent', 'Unknown').replace('_', ' ').title()}** - {gap.get('query_count', 0)} queries"):
                                st.metric("Average Confidence", f"{gap.get('avg_confidence', 0):.3f}")
                                st.markdown("**Sample Queries:**")
                                for query in gap.get("sample_queries", []):
                                    st.text(f"  • {query}")
                                st.info(f"💡 **Recommendation:** {gap.get('recommendation', '')}")
                    else:
                        st.success("✅ **No significant knowledge gaps detected!** Your knowledge base is well-covered.")
                else:
                    st.error(f"❌ Failed to load knowledge gaps: {gaps_resp.status_code}")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
        
        with tab4:
            try:
                with st.spinner("Loading user insights..."):
                    auth_headers = get_auth_headers()
                    users_resp = requests.get(f"{API_URL}/analytics/users?hours={hours}", headers=auth_headers, timeout=60)
                
                if users_resp.status_code == 200:
                    users_data = users_resp.json()
                    
                    st.markdown("#### 👥 User Activity")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Active Users", users_data.get("total_active_users", 0))
                    with col2:
                        st.metric("Total User Queries", users_data.get("total_user_queries", 0))
                    
                    top_users = users_data.get("top_users", [])
                    if top_users:
                        st.markdown("#### 🔝 Most Active Users")
                        for idx, user in enumerate(top_users[:10], 1):
                            col1, col2, col3 = st.columns([2, 1, 1])
                            with col1:
                                st.text(f"{idx}. User {user.get('user_id', 'Unknown')[:8]}...")
                            with col2:
                                st.caption(f"Queries: {user.get('query_count', 0)}")
                            with col3:
                                last_act = user.get("last_activity")
                                if last_act:
                                    try:
                                        act_time = datetime.fromisoformat(last_act.replace('Z', '+00:00'))
                                        st.caption(f"Last: {act_time.strftime('%H:%M')}")
                                    except:
                                        st.caption("Recent")
                    else:
                        st.info("No user activity data available.")
                else:
                    st.error(f"❌ Failed to load user insights: {users_resp.status_code}")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
        
        # Close button
        if st.button("❌ Close Dashboard", use_container_width=True):
            st.session_state.show_health = False
            st.rerun()
            
            p95_time = rt_stats.get("p95", 0)
            if p95_time > 10:
                insights.append("⚠️ **95% of queries take over 10 seconds** - Performance degradation detected")
            
            success_rate = doc_stats.get("success_rate_percent", 100)
            if success_rate < 80:
                insights.append("⚠️ **Low document processing success rate** - Check document formats and processing logs")
            
            for insight in insights:
                st.markdown(f"- {insight}")
            
        else:
            st.error(f"❌ Failed to load performance metrics: {perf_resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure the API server is running.")
    except Exception as e:
        st.error(f"❌ Error loading performance metrics: {str(e)}")
    
    # Close button
    if st.button("❌ Close Metrics Dashboard", use_container_width=True):
        st.session_state.show_health = False
        st.rerun()
    
    st.markdown("---")

# User Management Dashboard (Admin only)
if st.session_state.get("show_user_management", False):
    if st.session_state.current_user and st.session_state.current_user.get("role") == "admin":
        st.markdown("---")
        st.markdown("### 👥 User Management Dashboard")
        
        try:
            with st.spinner("Loading users..."):
                headers = get_auth_headers()
                users_resp = requests.get(f"{API_URL}/auth/users", headers=headers, timeout=10)
            
            if users_resp.status_code == 200:
                data = users_resp.json()
                users = data.get("users", [])
                total = data.get("total", 0)
                
                if total == 0:
                    st.info("📭 No users found.")
                else:
                    st.metric("Total Users", total)
                    st.markdown("---")
                    
                    # Display users
                    for idx, user in enumerate(users):
                        with st.container():
                            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1, 1, 1, 1])
                            
                            with col1:
                                role_icon = "👑" if user.get("role") == "admin" else "👤"
                                lock_icon = "🔒" if user.get("locked", False) else ""
                                st.markdown(f"**{role_icon} {lock_icon} {user.get('username', 'Unknown')}**")
                                st.caption(f"📧 {user.get('email', 'N/A')}")
                            
                            with col2:
                                role_badge = "Admin" if user.get("role") == "admin" else "User"
                                status_badge = "✅ Active" if user.get("active", True) else "❌ Inactive"
                                lockout_badge = "🔒 Locked" if user.get("locked", False) else "🔓 Unlocked"
                                st.markdown(f"**Role:** {role_badge}")
                                st.caption(status_badge)
                                if user.get("locked", False):
                                    st.caption(f"**{lockout_badge}**")
                                    if user.get("unlock_time"):
                                        from datetime import datetime
                                        try:
                                            unlock_dt = datetime.fromisoformat(user.get("unlock_time"))
                                            now = datetime.now()
                                            if unlock_dt > now:
                                                remaining = unlock_dt - now
                                                mins = int(remaining.total_seconds() / 60)
                                                st.caption(f"⏰ Unlocks in {mins} min")
                                        except:
                                            pass
                                if user.get("failed_attempts", 0) > 0 and not user.get("locked", False):
                                    st.caption(f"⚠️ {user.get('failed_attempts', 0)} failed attempt(s)")
                            
                            with col3:
                                if user.get("role") != "admin" or user.get("id") != st.session_state.current_user.get("id"):
                                    new_role = "admin" if user.get("role") == "user" else "user"
                                    if st.button("🔄", key=f"role_{idx}", help=f"Change to {new_role}"):
                                        try:
                                            headers = get_auth_headers()
                                            resp = requests.put(
                                                f"{API_URL}/auth/users/{user.get('id')}/role",
                                                json={"user_id": user.get("id"), "role": new_role},
                                                headers=headers,
                                                timeout=5
                                            )
                                            if resp.status_code == 200:
                                                st.success("✅ Role updated")
                                                time.sleep(0.5)
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Error: {resp.json().get('detail', 'Unknown error')}")
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                            
                            with col4:
                                if user.get("active", True):
                                    if st.button("🚫", key=f"deactivate_{idx}", help="Deactivate"):
                                        try:
                                            headers = get_auth_headers()
                                            resp = requests.post(
                                                f"{API_URL}/auth/users/{user.get('id')}/deactivate",
                                                headers=headers,
                                                timeout=5
                                            )
                                            if resp.status_code == 200:
                                                st.success("✅ User deactivated")
                                                time.sleep(0.5)
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Error: {resp.json().get('detail', 'Unknown error')}")
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                                else:
                                    if st.button("✅", key=f"activate_{idx}", help="Activate"):
                                        try:
                                            headers = get_auth_headers()
                                            resp = requests.post(
                                                f"{API_URL}/auth/users/{user.get('id')}/activate",
                                                headers=headers,
                                                timeout=5
                                            )
                                            if resp.status_code == 200:
                                                st.success("✅ User activated")
                                                time.sleep(0.5)
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Error: {resp.json().get('detail', 'Unknown error')}")
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                            
                            with col5:
                                if user.get("locked", False):
                                    if st.button("🔓", key=f"unlock_{idx}", help="Unlock Account"):
                                        try:
                                            headers = get_auth_headers()
                                            resp = requests.post(
                                                f"{API_URL}/auth/users/{user.get('id')}/unlock",
                                                headers=headers,
                                                timeout=5
                                            )
                                            if resp.status_code == 200:
                                                st.success("✅ Account unlocked")
                                                time.sleep(0.5)
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Error: {resp.json().get('detail', 'Unknown error')}")
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                            
                            with col6:
                                if user.get("created_at"):
                                    st.caption(f"Created: {user.get('created_at', '')[:10]}")
                                if user.get("last_login"):
                                    st.caption(f"Last login: {user.get('last_login', '')[:10]}")
                            
                            st.markdown("---")
            else:
                st.error(f"❌ Failed to load users: {users_resp.status_code}")
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to API. Make sure the API server is running.")
        except Exception as e:
            st.error(f"❌ Error loading users: {str(e)}")
        
        # Close button
        if st.button("❌ Close User Management", use_container_width=True):
            st.session_state.show_user_management = False
            st.rerun()
        
        st.markdown("---")
    else:
        st.error("❌ Access denied. Admin privileges required.")
        if st.button("❌ Close", use_container_width=True):
            st.session_state.show_user_management = False
            st.rerun()

# Change Password Section
if st.session_state.get("show_change_password", False):
    st.markdown("---")
    st.markdown("### 🔑 Change Password")
    
    # Password requirements info
    with st.expander("📋 Password Requirements", expanded=False):
        st.markdown("""
        Your new password must meet the following requirements:
        - **Minimum length:** 8 characters
        - **At least one uppercase letter** (A-Z)
        - **At least one lowercase letter** (a-z)
        - **At least one number** (0-9)
        - **At least one special character** (!@#$%^&*()_+-=[]{}|;:,.<>?)
        - **Cannot reuse** your last 5 passwords
        """)
    
    with st.form("change_password_form"):
        old_password = st.text_input("Current Password", type="password", key="old_password")
        new_password = st.text_input("New Password", type="password", key="new_password", help="See password requirements above")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_password")
        
        col1, col2 = st.columns(2)
        with col1:
            submit = st.form_submit_button("✅ Change Password", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
        
        if cancel:
            st.session_state.show_change_password = False
            st.rerun()
        
        if submit:
            if not old_password or not new_password or not confirm_password:
                st.error("❌ Please fill in all fields")
            elif new_password != confirm_password:
                st.error("❌ New passwords do not match")
            else:
                try:
                    headers = get_auth_headers()
                    response = requests.post(
                        f"{API_URL}/auth/change-password",
                        json={
                            "old_password": old_password,
                            "new_password": new_password
                        },
                        headers=headers,
                        timeout=10
                    )
                    if response.status_code == 200:
                        st.success("✅ Password changed successfully!")
                        st.info("💡 You will need to login again with your new password.")
                        time.sleep(2)
                        st.session_state.show_change_password = False
                        st.session_state.authenticated = False
                        st.session_state.access_token = None
                        st.session_state.current_user = None
                        st.session_state.auth_view = "login"
                        st.session_state.chat_history = []
                        st.rerun()
                    else:
                        error_detail = response.json().get('detail', 'Unknown error')
                        st.error(f"❌ Failed to change password: {error_detail}")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Cannot connect to API. Please ensure the server is running.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    
    # Close button
    if st.button("❌ Close", use_container_width=True, key="close_change_password"):
        st.session_state.show_change_password = False
        st.rerun()
    
    st.markdown("---")

# 2FA Setup Section
if st.session_state.get("show_2fa_setup", False):
    st.markdown("---")
    st.markdown("### 🔐 Two-Factor Authentication (2FA)")
    
    try:
        headers = get_auth_headers()
        
        # Check current 2FA status
        user_info_resp = requests.get(f"{API_URL}/auth/me", headers=headers, timeout=5)
        if user_info_resp.status_code == 200:
            current_user_info = user_info_resp.json()
            twofa_enabled = current_user_info.get("twofa_enabled", False)
            
            if twofa_enabled:
                st.success("✅ 2FA is currently **enabled** for your account")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📋 View Backup Codes", use_container_width=True):
                        try:
                            codes_resp = requests.get(f"{API_URL}/auth/2fa/backup-codes", headers=headers, timeout=5)
                            if codes_resp.status_code == 200:
                                codes_data = codes_resp.json()
                                codes = codes_data.get("backup_codes", [])
                                if codes:
                                    st.info("**Your unused backup codes:**")
                                    for code in codes:
                                        st.code(code, language=None)
                                    st.warning("⚠️ **Important:** Save these codes in a secure location. They can be used to access your account if you lose your authenticator device.")
                                else:
                                    st.warning("⚠️ No unused backup codes available. Consider regenerating them.")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                
                with col2:
                    if st.button("🔄 Regenerate Backup Codes", use_container_width=True):
                        try:
                            regen_resp = requests.post(f"{API_URL}/auth/2fa/regenerate-backup-codes", headers=headers, timeout=5)
                            if regen_resp.status_code == 200:
                                regen_data = regen_resp.json()
                                new_codes = regen_data.get("backup_codes", [])
                                st.success("✅ Backup codes regenerated!")
                                st.info("**Your new backup codes:**")
                                for code in new_codes:
                                    st.code(code, language=None)
                                st.warning("⚠️ **Important:** Save these codes in a secure location. Old backup codes are no longer valid.")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                
                st.markdown("---")
                
                if st.button("❌ Disable 2FA", use_container_width=True, type="primary"):
                    try:
                        disable_resp = requests.post(f"{API_URL}/auth/2fa/disable", headers=headers, timeout=5)
                        if disable_resp.status_code == 200:
                            st.success("✅ 2FA has been disabled")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {disable_resp.json().get('detail', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.info("🔐 2FA is currently **disabled** for your account")
                
                if st.button("🔧 Setup 2FA", use_container_width=True, type="primary"):
                    try:
                        setup_resp = requests.post(f"{API_URL}/auth/2fa/setup", headers=headers, timeout=5)
                        if setup_resp.status_code == 200:
                            setup_data = setup_resp.json()
                            st.session_state["2fa_setup_data"] = setup_data
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {setup_resp.json().get('detail', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                
                # Show setup UI if setup data is available
                if st.session_state.get("2fa_setup_data"):
                    setup_data = st.session_state["2fa_setup_data"]
                    qr_code_uri = setup_data.get("qr_code_uri")
                    backup_codes = setup_data.get("backup_codes", [])
                    
                    st.markdown("---")
                    st.markdown("#### 📱 Scan QR Code")
                    st.info("1. Open your authenticator app (Google Authenticator, Authy, etc.)")
                    st.info("2. Scan the QR code below or enter the secret manually")
                    
                    if qr_code_uri:
                        st.image(qr_code_uri, width=300)
                    
                    st.markdown("#### 🔑 Manual Entry")
                    st.code(setup_data.get("secret", ""), language=None)
                    
                    st.markdown("#### ✅ Verify Setup")
                    with st.form("verify_2fa_form"):
                        verify_code = st.text_input("Enter 6-digit code from your authenticator app", key="verify_2fa_code")
                        submit_verify = st.form_submit_button("Verify & Enable 2FA", use_container_width=True)
                        
                        if submit_verify:
                            if verify_code:
                                try:
                                    verify_resp = requests.post(
                                        f"{API_URL}/auth/2fa/verify",
                                        json={"code": verify_code},
                                        headers=headers,
                                        timeout=5
                                    )
                                    if verify_resp.status_code == 200:
                                        verify_data = verify_resp.json()
                                        st.success("✅ 2FA enabled successfully!")
                                        
                                        # Show backup codes
                                        backup_codes = verify_data.get("backup_codes", [])
                                        if backup_codes:
                                            st.warning("⚠️ **IMPORTANT:** Save these backup codes in a secure location!")
                                            st.info("**Your backup codes:**")
                                            for code in backup_codes:
                                                st.code(code, language=None)
                                            st.caption("You can use these codes to access your account if you lose your authenticator device.")
                                        
                                        st.session_state["2fa_setup_data"] = None
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {verify_resp.json().get('detail', 'Invalid code')}")
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                            else:
                                st.warning("⚠️ Please enter the verification code")
                    
                    if st.button("❌ Cancel Setup", use_container_width=True):
                        st.session_state["2fa_setup_data"] = None
                        st.rerun()
        else:
            st.error("❌ Failed to load user information")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Please ensure the server is running.")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    
    # Close button
    if st.button("❌ Close", use_container_width=True, key="close_2fa"):
        st.session_state.show_2fa_setup = False
        st.session_state["2fa_setup_data"] = None
        st.rerun()
    
    st.markdown("---")

# Session Management Section
if st.session_state.get("show_sessions", False):
    st.markdown("---")
    st.markdown("### 📱 Active Sessions")
    
    try:
        headers = get_auth_headers()
        
        with st.spinner("Loading sessions..."):
            sessions_resp = requests.get(f"{API_URL}/auth/sessions", headers=headers, timeout=5)
            
            if sessions_resp.status_code == 200:
                sessions_data = sessions_resp.json()
                sessions = sessions_data.get("sessions", [])
                total = sessions_data.get("total", 0)
                
                if total == 0:
                    st.info("📭 No active sessions found.")
                else:
                    st.metric("Active Sessions", total)
                    st.markdown("---")
                    
                    # Display sessions
                    for idx, session in enumerate(sessions):
                        with st.container():
                            col1, col2, col3 = st.columns([3, 2, 1])
                            
                            with col1:
                                if session.get("is_current", False):
                                    st.markdown(f"**🟢 Current Session** (This device)")
                                else:
                                    st.markdown(f"**⚪ Session {idx + 1}**")
                                
                                if session.get("ip_address"):
                                    st.caption(f"📍 IP: {session.get('ip_address')}")
                                if session.get("user_agent"):
                                    user_agent = session.get("user_agent", "")
                                    # Try to extract browser/device info
                                    device_info = user_agent[:50] + "..." if len(user_agent) > 50 else user_agent
                                    st.caption(f"🌐 {device_info}")
                            
                            with col2:
                                if session.get("created_at"):
                                    try:
                                        from datetime import datetime
                                        created = datetime.fromisoformat(session.get("created_at"))
                                        st.caption(f"Created: {created.strftime('%Y-%m-%d %H:%M')}")
                                    except:
                                        st.caption(f"Created: {session.get('created_at', '')[:10]}")
                                
                                if session.get("last_activity"):
                                    try:
                                        from datetime import datetime
                                        last_act = datetime.fromisoformat(session.get("last_activity"))
                                        now = datetime.now()
                                        diff = now - last_act
                                        if diff.days > 0:
                                            st.caption(f"Last activity: {diff.days} day(s) ago")
                                        elif diff.seconds > 3600:
                                            st.caption(f"Last activity: {diff.seconds // 3600} hour(s) ago")
                                        elif diff.seconds > 60:
                                            st.caption(f"Last activity: {diff.seconds // 60} minute(s) ago")
                                        else:
                                            st.caption("Last activity: Just now")
                                    except:
                                        st.caption(f"Last activity: {session.get('last_activity', '')[:10]}")
                            
                            with col3:
                                if not session.get("is_current", False):
                                    if st.button("🚫", key=f"revoke_{idx}", help="Revoke this session"):
                                        try:
                                            revoke_resp = requests.post(
                                                f"{API_URL}/auth/sessions/{session.get('session_id')}/revoke",
                                                headers=headers,
                                                timeout=5
                                            )
                                            if revoke_resp.status_code == 200:
                                                st.success("✅ Session revoked")
                                                time.sleep(0.5)
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Error: {revoke_resp.json().get('detail', 'Unknown error')}")
                                        except Exception as e:
                                            st.error(f"❌ Error: {str(e)}")
                            
                            st.markdown("---")
                    
                    # Revoke all other sessions button
                    if total > 1:
                        st.markdown("#### Revoke All Other Sessions")
                        st.warning("⚠️ This will log you out from all other devices. You will remain logged in on this device.")
                        if st.button("🚫 Revoke All Other Sessions", use_container_width=True, type="primary"):
                            try:
                                revoke_all_resp = requests.post(
                                    f"{API_URL}/auth/sessions/revoke-all",
                                    headers=headers,
                                    timeout=5
                                )
                                if revoke_all_resp.status_code == 200:
                                    st.success("✅ All other sessions revoked")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ Error: {revoke_all_resp.json().get('detail', 'Unknown error')}")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
            else:
                st.error(f"❌ Failed to load sessions: {sessions_resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Please ensure the server is running.")
    except Exception as e:
        st.error(f"❌ Error loading sessions: {str(e)}")
    
    # Close button
    if st.button("❌ Close", use_container_width=True, key="close_sessions"):
        st.session_state.show_sessions = False
        st.rerun()
    
    st.markdown("---")

# Export & Backup Dashboard (Admin only)
if st.session_state.get("show_export_backup", False):
    if st.session_state.current_user and st.session_state.current_user.get("role") == "admin":
        st.markdown("---")
        st.markdown("### 💾 Export & Backup Dashboard")
        
        headers = get_auth_headers()
        
        # Tabs for Export and Backup
        tab1, tab2 = st.tabs(["📤 Export Data", "💾 Backup & Restore"])
        
        with tab1:
            st.markdown("#### 📤 Export Data")
            st.info("Export system data in various formats. Exports are available for download for 7 days.")
            
            with st.form("export_form"):
                export_type = st.selectbox(
                    "Export Type",
                    ["documents", "conversations", "analytics", "users", "all"],
                    help="Select what data to export"
                )
                
                format_type = st.selectbox(
                    "Format",
                    ["json", "csv"],
                    help="Export format"
                )
                
                include_chunks = st.checkbox(
                    "Include Document Chunks",
                    value=False,
                    help="Include full chunk data for documents (large files)"
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    date_from = st.date_input("From Date (optional)", value=None)
                with col2:
                    date_to = st.date_input("To Date (optional)", value=None)
                
                submit_export = st.form_submit_button("📥 Create Export", use_container_width=True)
                
                if submit_export:
                    try:
                        export_data = {
                            "export_type": export_type,
                            "format": format_type,
                            "include_chunks": include_chunks
                        }
                        
                        if date_from:
                            export_data["date_from"] = date_from.isoformat()
                        if date_to:
                            export_data["date_to"] = date_to.isoformat()
                        
                        with st.spinner("Creating export..."):
                            export_resp = requests.post(
                                f"{API_URL}/export",
                                json=export_data,
                                headers=headers,
                                timeout=120
                            )
                        
                        if export_resp.status_code == 200:
                            export_result = export_resp.json()
                            st.success(f"✅ Export created successfully!")
                            st.info(f"📦 File size: {export_result.get('file_size', 0) / (1024*1024):.2f} MB")
                            
                            # Download button
                            filename = os.path.basename(export_result.get("file_path", ""))
                            download_url = f"{API_URL}/export/download/{filename}"
                            
                            st.markdown(f"**Download:** [{filename}]({download_url})")
                            st.caption(f"Expires: {export_result.get('expires_at', 'N/A')}")
                        else:
                            error_data = export_resp.json() if export_resp.status_code != 500 else {}
                            st.error(f"❌ Export failed: {error_data.get('detail', export_resp.text)}")
                    except requests.exceptions.ConnectionError:
                        st.error("❌ Cannot connect to API")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        with tab2:
            st.markdown("#### 💾 Backup & Restore")
            
            # Create Backup Section
            st.markdown("##### 📦 Create Backup")
            st.info("Create a full system backup including ChromaDB, data files, and uploaded documents.")
            
            with st.form("backup_form"):
                include_chromadb = st.checkbox("Include ChromaDB", value=True)
                include_data = st.checkbox("Include Data Files", value=True)
                include_files = st.checkbox("Include Uploaded Files", value=True)
                
                description = st.text_input("Description (optional)", help="Add a description for this backup")
                
                submit_backup = st.form_submit_button("💾 Create Backup", use_container_width=True)
                
                if submit_backup:
                    try:
                        backup_data = {
                            "include_chromadb": include_chromadb,
                            "include_data": include_data,
                            "include_files": include_files,
                            "description": description if description else None
                        }
                        
                        with st.spinner("Creating backup (this may take a while)..."):
                            backup_resp = requests.post(
                                f"{API_URL}/backup/create",
                                json=backup_data,
                                headers=headers,
                                timeout=300
                            )
                        
                        if backup_resp.status_code == 200:
                            backup_result = backup_resp.json()
                            st.success(f"✅ Backup created successfully!")
                            st.info(f"📦 Backup ID: {backup_result.get('backup_id')}")
                            st.info(f"💾 Size: {backup_result.get('backup_size', 0) / (1024*1024):.2f} MB")
                            st.info(f"📅 Created: {backup_result.get('created_at', 'N/A')}")
                            time.sleep(2)
                            st.rerun()
                        else:
                            error_data = backup_resp.json() if backup_resp.status_code != 500 else {}
                            st.error(f"❌ Backup failed: {error_data.get('detail', backup_resp.text)}")
                    except requests.exceptions.ConnectionError:
                        st.error("❌ Cannot connect to API")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            
            st.markdown("---")
            
            # List Backups Section
            st.markdown("##### 📋 Available Backups")
            
            try:
                with st.spinner("Loading backups..."):
                    backups_resp = requests.get(f"{API_URL}/backup/list", headers=headers, timeout=10)
                
                if backups_resp.status_code == 200:
                    backups_data = backups_resp.json()
                    backups = backups_data.get("backups", [])
                    total_size = backups_data.get("total_size", 0)
                    
                    st.metric("Total Backups", backups_data.get("total_backups", 0))
                    st.caption(f"Total size: {total_size / (1024*1024):.2f} MB")
                    
                    if backups:
                        st.markdown("---")
                        for backup in backups:
                            with st.container():
                                col1, col2, col3 = st.columns([3, 2, 1])
                                
                                with col1:
                                    st.markdown(f"**{backup.get('backup_id', 'Unknown')}**")
                                    if backup.get("description"):
                                        st.caption(backup.get("description"))
                                    st.caption(f"Created: {backup.get('created_at', 'N/A')}")
                                
                                with col2:
                                    size_mb = backup.get("backup_size", 0) / (1024*1024)
                                    st.metric("Size", f"{size_mb:.2f} MB")
                                    
                                    includes = backup.get("includes", {})
                                    includes_text = []
                                    if includes.get("chromadb"):
                                        includes_text.append("ChromaDB")
                                    if includes.get("data"):
                                        includes_text.append("Data")
                                    if includes.get("files"):
                                        includes_text.append("Files")
                                    st.caption(f"Includes: {', '.join(includes_text)}")
                                
                                with col3:
                                    backup_id = backup.get("backup_id", "")
                                    
                                    # Download button
                                    download_url = f"{API_URL}/backup/download/{backup_id}"
                                    st.markdown(f"[⬇️ Download]({download_url})")
                                    
                                    # Restore button with confirmation
                                    restore_key = f"restore_{backup_id}"
                                    if st.session_state.get(f"confirm_{restore_key}", False):
                                        st.warning("⚠️ Are you sure? This will overwrite existing data!")
                                        col_yes, col_no = st.columns(2)
                                        with col_yes:
                                            if st.button("✅ Yes", key=f"yes_{restore_key}", use_container_width=True):
                                                try:
                                                    restore_data = {
                                                        "backup_id": backup_id,
                                                        "restore_chromadb": True,
                                                        "restore_data": True,
                                                        "restore_files": True
                                                    }
                                                    
                                                    with st.spinner("Restoring backup (this may take a while)..."):
                                                        restore_resp = requests.post(
                                                            f"{API_URL}/backup/restore",
                                                            json=restore_data,
                                                            headers=headers,
                                                            timeout=300
                                                        )
                                                    
                                                    if restore_resp.status_code == 200:
                                                        restore_result = restore_resp.json()
                                                        st.success(f"✅ {restore_result.get('message', 'Backup restored successfully')}")
                                                        st.info(f"Restored {restore_result.get('restored_items', 0)} items")
                                                        st.session_state[f"confirm_{restore_key}"] = False
                                                        time.sleep(2)
                                                        st.rerun()
                                                    else:
                                                        error_data = restore_resp.json() if restore_resp.status_code != 500 else {}
                                                        st.error(f"❌ Restore failed: {error_data.get('detail', restore_resp.text)}")
                                                        st.session_state[f"confirm_{restore_key}"] = False
                                                except Exception as e:
                                                    st.error(f"❌ Error: {str(e)}")
                                                    st.session_state[f"confirm_{restore_key}"] = False
                                        with col_no:
                                            if st.button("❌ No", key=f"no_{restore_key}", use_container_width=True):
                                                st.session_state[f"confirm_{restore_key}"] = False
                                                st.rerun()
                                    else:
                                        if st.button("🔄 Restore", key=restore_key, use_container_width=True):
                                            st.session_state[f"confirm_{restore_key}"] = True
                                            st.rerun()
                                
                                st.markdown("---")
                    else:
                        st.info("📭 No backups found. Create your first backup above.")
                else:
                    st.error(f"❌ Failed to load backups: {backups_resp.status_code}")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Make sure the API server is running.")
            except Exception as e:
                st.error(f"❌ Error loading backups: {str(e)}")
        
        # Close button
        if st.button("❌ Close", use_container_width=True, key="close_export_backup"):
            st.session_state.show_export_backup = False
            st.rerun()
        
        st.markdown("---")
    else:
        st.error("❌ Access denied. Admin privileges required.")
        if st.button("❌ Close", use_container_width=True):
            st.session_state.show_export_backup = False
            st.rerun()

# User Profile Management Section
if st.session_state.get("show_profile", False):
    st.markdown("---")
    st.markdown("### 👤 My Profile")
    
    try:
        headers = get_auth_headers()
        
        # Get current profile
        with st.spinner("Loading profile..."):
            try:
                profile_resp = requests.get(f"{API_URL}/auth/profile", headers=headers, timeout=10)
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Make sure the API server is running.")
                profile_resp = None
        
        if profile_resp and profile_resp.status_code == 200:
            profile_data = profile_resp.json()
            user_info = profile_data.get("user", {})
            preferences = profile_data.get("preferences", {})
            # Store preferences in session so chat uses them (e.g. language)
            st.session_state.user_preferences = preferences
            
            # Display profile
            st.markdown('<div class="profile-avatar-section"></div>', unsafe_allow_html=True)
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # Avatar display
                avatar_url = user_info.get("avatar")
                if avatar_url:
                    try:
                        # Try to load avatar from API
                        avatar_resp = requests.get(f"{API_URL}{avatar_url}", timeout=5)
                        if avatar_resp.status_code == 200:
                            st.image(avatar_resp.content, width=150)
                        else:
                            st.image("https://ui-avatars.com/api/?name=" + user_info.get("username", "User"), width=150)
                    except:
                        st.image("https://ui-avatars.com/api/?name=" + user_info.get("username", "User"), width=150)
                else:
                    st.image("https://ui-avatars.com/api/?name=" + user_info.get("username", "User"), width=150)
                
                # Avatar upload
                uploaded_avatar = st.file_uploader("Upload Avatar", type=["jpg", "jpeg", "png", "gif"], key="avatar_upload")
                if uploaded_avatar:
                    if st.button("📤 Upload Avatar", use_container_width=True):
                        try:
                            files = {"file": (uploaded_avatar.name, uploaded_avatar.getvalue(), uploaded_avatar.type)}
                            upload_resp = requests.post(f"{API_URL}/auth/avatar", headers=headers, files=files, timeout=10)
                            if upload_resp.status_code == 200:
                                st.success("✅ Avatar uploaded successfully!")
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to upload avatar: {upload_resp.json().get('detail', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"❌ Error uploading avatar: {str(e)}")
                
                with col2:
                    st.markdown(f"#### {user_info.get('display_name') or user_info.get('username', 'User')}")
                    st.caption(f"@{user_info.get('username', '')}")
                    if user_info.get("bio"):
                        st.markdown(f"_{user_info.get('bio')}_")
                    else:
                        st.caption("No bio set")
                
                st.markdown("---")
                
                # Edit profile form
                with st.expander("✏️ Edit Profile", expanded=False):
                    with st.form("edit_profile_form"):
                        display_name = st.text_input(
                            "Display Name",
                            value=user_info.get("display_name") or "",
                            placeholder="Enter your display name"
                        )
                        email = st.text_input(
                            "Email",
                            value=user_info.get("email") or "",
                            placeholder="Enter your email"
                        )
                        bio = st.text_area(
                            "Bio",
                            value=user_info.get("bio") or "",
                            placeholder="Tell us about yourself...",
                            height=100
                        )
                        
                        submit_profile = st.form_submit_button("💾 Save Profile", use_container_width=True)
                        
                        if submit_profile:
                            try:
                                update_data = {}
                                if display_name != (user_info.get("display_name") or ""):
                                    update_data["display_name"] = display_name
                                if email != user_info.get("email"):
                                    update_data["email"] = email
                                if bio != (user_info.get("bio") or ""):
                                    update_data["bio"] = bio
                                
                                if update_data:
                                    update_resp = requests.put(
                                        f"{API_URL}/auth/profile",
                                        headers=headers,
                                        json=update_data,
                                        timeout=10
                                    )
                                    if update_resp.status_code == 200:
                                        st.success("✅ Profile updated successfully!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed to update profile: {update_resp.json().get('detail', 'Unknown error')}")
                                else:
                                    st.info("ℹ️ No changes to save")
                            except requests.exceptions.ConnectionError:
                                st.error(get_api_connection_error_message())
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                
                st.markdown("---")
                
                # User preferences
                st.markdown("#### ⚙️ Preferences")
                with st.expander("🎨 Theme & Notifications", expanded=False):
                    with st.form("preferences_form"):
                        theme = st.selectbox(
                            "Theme",
                            ["light", "dark", "auto"],
                            index=["light", "dark", "auto"].index(preferences.get("theme", "light"))
                        )
                        notifications_enabled = st.checkbox(
                            "Enable Notifications",
                            value=preferences.get("notifications_enabled", True)
                        )
                        email_notifications = st.checkbox(
                            "Email Notifications",
                            value=preferences.get("email_notifications", True)
                        )
                        language_options = ["en", "es", "fr", "de", "it", "pt", "zh", "ja", "ko", "ar", "ru", "hi"]
                        language_labels = {
                            "en": "English", "es": "Spanish", "fr": "French", "de": "German",
                            "it": "Italian", "pt": "Portuguese", "zh": "Chinese", "ja": "Japanese",
                            "ko": "Korean", "ar": "Arabic", "ru": "Russian", "hi": "Hindi"
                        }
                        current_lang = preferences.get("language", "en")
                        default_index = language_options.index(current_lang) if current_lang in language_options else 0
                        language = st.selectbox(
                            "Language",
                            options=language_options,
                            format_func=lambda x: language_labels.get(x, x),
                            index=default_index
                        )
                        
                        submit_prefs = st.form_submit_button("💾 Save Preferences", use_container_width=True)
                        
                        if submit_prefs:
                            try:
                                prefs_data = {
                                    "theme": theme,
                                    "notifications_enabled": notifications_enabled,
                                    "email_notifications": email_notifications,
                                    "language": language
                                }
                                prefs_resp = requests.put(
                                    f"{API_URL}/auth/preferences",
                                    headers=headers,
                                    json=prefs_data,
                                    timeout=10
                                )
                                if prefs_resp.status_code == 200:
                                    st.session_state.user_preferences = prefs_data
                                    st.success("✅ Preferences saved successfully!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to save preferences: {prefs_resp.json().get('detail', 'Unknown error')}")
                            except requests.exceptions.ConnectionError:
                                st.error(get_api_connection_error_message())
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                
                # Account information
                st.markdown("---")
                st.markdown("#### 📋 Account Information")
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.caption("**Username:**")
                    st.text(user_info.get("username", ""))
                    st.caption("**Role:**")
                    st.text(user_info.get("role", "").title())
                    st.caption("**Account Created:**")
                    if user_info.get("created_at"):
                        try:
                            from datetime import datetime
                            created = datetime.fromisoformat(user_info.get("created_at"))
                            st.text(created.strftime("%Y-%m-%d %H:%M:%S"))
                        except:
                            st.text(user_info.get("created_at", "N/A"))
                    else:
                        st.text("N/A")
                with info_col2:
                    st.caption("**Last Login:**")
                if user_info.get("last_login"):
                    try:
                        from datetime import datetime
                        last_login = datetime.fromisoformat(user_info.get("last_login"))
                        st.text(last_login.strftime("%Y-%m-%d %H:%M:%S"))
                    except:
                        st.text(user_info.get("last_login", "N/A"))
                else:
                    st.text("Never")
                st.caption("**2FA Status:**")
                if user_info.get("twofa_enabled"):
                    st.success("✅ Enabled")
                else:
                    st.info("❌ Disabled")
                st.caption("**Account Status:**")
                if user_info.get("active"):
                    st.success("✅ Active")
                else:
                    st.error("❌ Inactive")
        else:
            st.error(f"❌ Failed to load profile: {profile_resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Please ensure the server is running.")
    except Exception as e:
        st.error(f"❌ Error loading profile: {str(e)}")
    
    # Close button (always visible)
    st.markdown("---")
    if st.button("❌ Close", use_container_width=True, key="close_profile"):
        st.session_state.show_profile = False
        st.rerun()
    
    st.markdown("---")

# Example questions helper
def get_example_questions():
    raw = os.environ.get("EXAMPLE_QUESTIONS", "").strip()
    if not raw:
        return ["What is the billing process?", "How do I handle a student inquiry?", "What are the payment deadlines?"]
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    for sep in ("|", ","):
        if sep in raw:
            return [q.strip() for q in raw.split(sep) if q.strip()]
    return [raw]


def get_starter_prompts():
    """Curated empty-state prompts with short descriptions."""
    return [
        ("Summarize a policy\nTurn a long document or procedure into a quick answer.", "Summarize a policy"),
        ("Find the right source\nAsk for the exact document, section, or supporting evidence.", "Find the right source"),
        ("Compare two processes\nSee differences between teams, workflows, or deadlines.", "Compare two processes"),
        ("Draft a response\nGenerate a clear reply for a user, student, or teammate.", "Draft a response"),
    ]


def fetch_knowledge_home_stats():
    """Fetch compact knowledge-base stats for the home screen."""
    stats = {
        "document_count": 0,
        "chunk_count": 0,
        "pending_count": 0,
        "is_processing": False,
        "last_upload_label": "No uploads yet",
        "ready": True,
        "error": None,
    }
    try:
        status_resp = requests.get(f"{API_URL}/status", headers=get_auth_headers(), timeout=4)
        if status_resp.status_code == 200:
            data = status_resp.json()
            stats["document_count"] = int(data.get("document_count") or 0)
            stats["chunk_count"] = int(data.get("knowledge_base_chunks") or 0)
            stats["pending_count"] = int(data.get("pending_files_count") or 0)
            stats["is_processing"] = bool(data.get("is_processing"))
            stats["ready"] = not stats["is_processing"]
            st.session_state.kb_status = data
    except Exception as e:
        stats["error"] = str(e)

    try:
        docs_resp = requests.get(f"{API_URL}/documents", headers=get_auth_headers(), timeout=6)
        if docs_resp.status_code == 200:
            payload = docs_resp.json()
            documents = payload.get("documents") or []
            if documents:
                stats["document_count"] = int(payload.get("total_documents") or len(documents))
                stats["chunk_count"] = int(payload.get("total_chunks") or stats["chunk_count"])
                dated = []
                for doc in documents:
                    raw = doc.get("upload_date") or doc.get("uploaded_at")
                    if not raw:
                        continue
                    try:
                        dated.append(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
                    except Exception:
                        continue
                if dated:
                    latest = max(dated)
                    # Make timezone-naive for simple relative labels
                    if latest.tzinfo is not None:
                        latest = latest.replace(tzinfo=None)
                    delta = datetime.now() - latest
                    if delta.days <= 0:
                        stats["last_upload_label"] = "Today"
                    elif delta.days == 1:
                        stats["last_upload_label"] = "Yesterday"
                    elif delta.days < 7:
                        stats["last_upload_label"] = f"{delta.days} days ago"
                    else:
                        stats["last_upload_label"] = latest.strftime("%b %d, %Y")
    except Exception:
        pass
    return stats

# Zone-based layout: center (chat) + right (context panel) when on chat view
suggestions_placeholder = st.empty()
chat_empty = not st.session_state.chat_history
current_page = get_current_nav_page()
show_copilot_empty = chat_empty and current_page == "chat" and not st.session_state.get("show_documents", False)
use_zone_layout = current_page == "chat" and not st.session_state.get("show_documents", False)

# Handle example query (define query before use in col_chat)
if "example_query" in st.session_state:
    query = st.session_state.example_query
    del st.session_state.example_query
else:
    query = None

# Extract sources from last assistant message for right context panel
last_sources = []
if st.session_state.chat_history:
    for item in reversed(st.session_state.chat_history):
        if len(item) >= 4 and item[0] == "assistant":
            last_sources = item[3] if isinstance(item[3], list) else []
            break

if "selected_sources" not in st.session_state:
    st.session_state.selected_sources = []
if "selected_assistant_key" not in st.session_state:
    st.session_state.selected_assistant_key = None
if "selected_source_message" not in st.session_state:
    st.session_state.selected_source_message = ""

active_sources = st.session_state.selected_sources if st.session_state.selected_sources else last_sources

# Centered chat column — no side source panel (sources live under each answer)
if use_zone_layout:
    col_left, col_chat, col_right = st.columns([1, 3, 1], gap="large")
    col_context = None
else:
    col_chat = st.container()
    col_context = None

with col_chat:
    if show_copilot_empty:
        from datetime import datetime as dt
        hour = dt.now().hour
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 18:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"
        user_name = "there"
        if st.session_state.get("current_user"):
            user_name = (
                st.session_state.current_user.get("first_name")
                or st.session_state.current_user.get("display_name")
                or st.session_state.current_user.get("username", "there")
            )
            if user_name:
                user_name = user_name.split()[0] if " " in user_name else user_name

        kb_stats = fetch_knowledge_home_stats()
        doc_count = kb_stats.get("document_count", 0)
        status_label = "Indexing" if kb_stats.get("is_processing") else "Ready"
        status_dot = "warn" if kb_stats.get("is_processing") else ""
        last_upload = kb_stats.get("last_upload_label", "No uploads yet")

        st.markdown(
            f"""
            <div class="kh-shell">
                <p class="kh-eyebrow">Knowledge home</p>
                <h1 class="kh-title">{time_greeting}, {html.escape(str(user_name))}</h1>
                <p class="kh-subtitle">Ask your documents. Get answers with sources.</p>
                <div class="kh-chips">
                    <span class="kh-chip"><strong>{doc_count}</strong> document{"s" if doc_count != 1 else ""}</span>
                    <span class="kh-chip">Last upload: <strong>{html.escape(str(last_upload))}</strong></span>
                    <span class="kh-chip"><span class="kh-chip-dot {status_dot}"></span> {status_label}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if query is None:
            chat_val = st.chat_input(
                "Ask your documents…" if doc_count > 0 else "Upload documents, then ask a question…",
                key="chat_input",
            )
            if chat_val:
                st.session_state._pending_chat_query = chat_val
            query = chat_val if chat_val else query

        st.markdown(
            '<div class="kh-composer-hint">Answers cite the exact document or section they came from.</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="kh-actions-marker"></div>', unsafe_allow_html=True)
        action_l, action_r = st.columns(2)
        with action_l:
            if st.button("Upload documents", key="kh_upload_btn", use_container_width=True, type="primary"):
                navigate_to_page("upload")
                st.query_params["view"] = "upload"
                st.rerun()
        with action_r:
            if st.button("Browse library", key="kh_browse_btn", use_container_width=True):
                navigate_to_page("documents")
                st.query_params["view"] = "documents"
                st.rerun()

        if doc_count == 0:
            pending = kb_stats.get("pending_count", 0)
            if pending:
                empty_title = "Documents are still processing"
                empty_body = f"{pending} file(s) are indexing. This usually takes a few seconds — then you can ask questions."
            else:
                empty_title = "Your knowledge base is empty"
                empty_body = "Upload a PDF, Word doc, text file, or spreadsheet to start asking questions with sources."
            st.markdown(
                f"""
                <div class="kh-empty">
                    <h3>{html.escape(empty_title)}</h3>
                    <p>{html.escape(empty_body)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            # Light prompts once docs exist — keep secondary to the ask bar
            st.markdown('<div class="starter-grid-title">Try asking</div>', unsafe_allow_html=True)
            example_questions = get_example_questions()[:3]
            prompt_cols = st.columns(len(example_questions) or 1)
            for idx, question in enumerate(example_questions):
                with prompt_cols[idx]:
                    if st.button(question, key=f"kh_example_{idx}", use_container_width=True):
                        st.session_state.example_query = question
                        st.rerun()
    # Center zone: suggestions placeholder, chat history, input
    suggestions_placeholder = st.empty()
    if "last_query_input" not in st.session_state:
        st.session_state.last_query_input = ""
    current_input = ""
    if "query_input_text" in st.session_state:
        current_input = st.session_state.query_input_text
    if current_input and len(current_input.strip()) > 0:
        try:
            suggestions_resp = requests.get(
                f"{API_URL}/suggestions",
                params={"q": current_input.strip(), "limit": 5, "include_documents": True},
                timeout=3
            )
            if suggestions_resp.status_code == 200:
                suggestions_data = suggestions_resp.json()
                suggestions = suggestions_data.get("suggestions", [])
                if suggestions:
                    with suggestions_placeholder.container():
                        st.markdown("**💡 Query Suggestions:**")
                        for idx, suggestion in enumerate(suggestions):
                            sq = suggestion.get("query", "")
                            stype = suggestion.get("type", "")
                            icon = "⭐" if stype == "saved" else ("📚" if stype == "document" else "🕐")
                            label = f"{suggestion.get('name', '')}: {sq}" if stype == "saved" and suggestion.get("name") else sq
                            if st.button(f"{icon} {label}", key=f"suggestion_{idx}", use_container_width=True):
                                st.session_state.example_query = sq
                                st.rerun()
        except:
            pass
# Handle example query (from pill click) - only overwrite if we have one; don't wipe chat_input value
if "example_query" in st.session_state:
    query = st.session_state.example_query
    del st.session_state.example_query

def render_user_message_block(message_idx: int, message: str, msg_time: str):
    """Render a clean user message bubble."""
    safe_message = html.escape(str(message)).replace("\n", "<br/>")
    st.markdown(
        f'<div class="msg msg-user"><div class="msg-user-bubble">{safe_message}</div></div>',
        unsafe_allow_html=True,
    )


def build_assistant_message_key(msg_time: str, message: str) -> str:
    """Create a stable key for assistant-message-level UI actions."""
    basis = f"{msg_time}|{message}"
    return hashlib.sha1(basis.encode("utf-8", errors="ignore")).hexdigest()[:12]


def render_assistant_message_block(message_idx: int, message: str, msg_time: str, sources: list, user_query: str, message_key: str):
    """Render a clean assistant answer with collapsed sources."""
    _display_msg = str(message).strip()
    safe_message = html.escape(_display_msg).replace("\n", "<br/>")
    if _display_msg.strip().startswith("<"):
        safe_message = "An error occurred while displaying the response. Please try again."

    st.markdown(
        f'<div class="msg msg-assistant" id="answer_{message_idx}"><div class="msg-body">{safe_message}</div></div>',
        unsafe_allow_html=True,
    )

    source_list = sources if isinstance(sources, list) else []
    feedback_key = f"feedback_submitted_{message_idx}"

    # Actions sit under the answer (before sources) so labels stay readable
    st.markdown('<div class="msg-actions-row">', unsafe_allow_html=True)
    act1, act2, act3, _ = st.columns([2.2, 2.6, 2.6, 8], gap="small")
    with act1:
        escaped_message = (
            str(message)
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        if st.button("Copy", key=f"copy_answer_{message_idx}", help="Copy answer", use_container_width=True):
            st.markdown(
                f"""
                <script>
                (function() {{
                    const text = `{escaped_message}`;
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(text);
                    }}
                }})();
                </script>
                """,
                unsafe_allow_html=True,
            )
            st.toast("Copied")
    with act2:
        if not st.session_state.get(feedback_key, False):
            if st.button("Helpful", key=f"thumbs_up_{message_idx}", help="Good answer", use_container_width=True):
                try:
                    feedback_resp = requests.post(
                        f"{API_URL}/feedback",
                        json={
                            "query": user_query,
                            "response": message,
                            "rating": 1,
                            "feedback_type": "thumbs",
                            "sources_count": len(source_list),
                        },
                        timeout=5,
                    )
                    if feedback_resp.status_code == 200:
                        st.session_state[feedback_key] = True
                        st.rerun()
                except Exception:
                    st.error("Feedback failed")
        else:
            st.caption("Thanks")
    with act3:
        if not st.session_state.get(feedback_key, False):
            if st.button("Improve", key=f"thumbs_down_{message_idx}", help="Poor answer", use_container_width=True):
                st.session_state[f"show_feedback_form_{message_idx}"] = True
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get(f"show_feedback_form_{message_idx}", False):
        with st.form(f"feedback_form_{message_idx}"):
            rating = st.slider("Rating", 1, 5, 2, key=f"rating_{message_idx}")
            comment = st.text_area("What should improve?", key=f"comment_{message_idx}")
            c1, c2 = st.columns(2)
            with c1:
                if st.form_submit_button("Submit"):
                    try:
                        feedback_resp = requests.post(
                            f"{API_URL}/feedback",
                            json={
                                "query": user_query,
                                "response": message,
                                "rating": rating,
                                "feedback_type": "detailed",
                                "comment": comment,
                                "sources_count": len(source_list),
                            },
                            timeout=5,
                        )
                        if feedback_resp.status_code == 200:
                            st.session_state[feedback_key] = True
                            st.session_state[f"show_feedback_form_{message_idx}"] = False
                            st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c2:
                if st.form_submit_button("Cancel"):
                    st.session_state[f"show_feedback_form_{message_idx}"] = False
                    st.rerun()

    if source_list:
        label = f"{len(source_list)} source{'s' if len(source_list) != 1 else ''}"
        with st.expander(label, expanded=False):
            chips = []
            for source in source_list:
                name = source.get("source", "Unknown") if isinstance(source, dict) else str(source)
                rel = source.get("relevance", 0) if isinstance(source, dict) else 0
                rel_label = "High" if rel >= 0.7 else ("Medium" if rel >= 0.4 else "Low")
                chips.append(
                    f'<span class="source-chip">{html.escape(str(name))} <em>{rel_label}</em></span>'
                )
            st.markdown(
                '<div class="sources-block"><p class="sources-summary">Cited from</p>'
                + "".join(chips)
                + "</div>",
                unsafe_allow_html=True,
            )

# Message loop and chat input - in center zone when using zone layout
with col_chat:
    if not st.session_state.chat_history:
        # Greeting shown above in show_copilot_empty; only show here when not in that state
        if not show_copilot_empty:
            hour = datetime.now().hour
            if 5 <= hour < 12:
                time_greeting = "Good morning"
            elif 12 <= hour < 17:
                time_greeting = "Good afternoon"
            else:
                time_greeting = "Good evening"
            user_name = "there"
            if st.session_state.get("current_user"):
                user_name = (
                    st.session_state.current_user.get("display_name")
                    or st.session_state.current_user.get("first_name")
                    or st.session_state.current_user.get("username", "there")
                )
                if "@" in str(user_name):
                    user_name = str(user_name).split("@")[0]
                if user_name:
                    user_name = user_name.title()
            st.markdown(
                f"""
                <div class="copilot-greeting">
                    <h2>{time_greeting}, {user_name}</h2>
                    <p>What can I help you with today?</p>
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        hist = st.session_state.chat_history[-MAX_HISTORY:]
        # Chronological thread only — keep the conversation readable
        items_to_show = hist
        st.markdown('<div class="thread">', unsafe_allow_html=True)
        for idx, item in enumerate(items_to_show):
            # Handle both old format (3 items) and new format (4 items with sources)
            if len(item) == 3:
                role, message, msg_time = item
                sources = []
            else:
                role, message, msg_time, sources = item

            prev_user_query = ""
            if idx > 0 and len(items_to_show[idx - 1]) >= 2 and items_to_show[idx - 1][0] == "user":
                prev_user_query = items_to_show[idx - 1][1]
            if role == "user":
                render_user_message_block(idx, message, msg_time)
                continue
            msg_key = build_assistant_message_key(str(msg_time), str(message))
            render_assistant_message_block(idx, message, msg_time, sources, prev_user_query, msg_key)
        st.markdown("</div>", unsafe_allow_html=True)

    # Chat input - inside col_chat so it appears right below messages (responses above input)
    if not show_copilot_empty and query is None:
        chat_val = st.chat_input("Ask your documents…", key="chat_input")
        if chat_val:
            st.session_state._pending_chat_query = chat_val
        query = chat_val if chat_val else query
        st.markdown(
            '<div class="composer-hint">Enter to send · Sources stay under each answer</div>',
            unsafe_allow_html=True
        )

# Restore query from session if it was captured by chat_input but overwritten
if query is None and st.session_state.get("_pending_chat_query"):
    query = st.session_state.pop("_pending_chat_query", None)

if query:
    if query.strip():
        st.session_state.pop("_pending_chat_query", None)  # Clear so we don't re-use on next run
        # Guard: avoid double-processing when st.rerun() causes chat_input to resubmit
        # Use both session-state flag and history check for robustness
        hist = st.session_state.chat_history
        def _normalize_for_compare(s: str) -> str:
            # Normalize whitespace/casing to reliably detect "echo of the question".
            return " ".join((s or "").strip().split()).casefold()

        normalized_query = _normalize_for_compare(query.strip())
        already_responded = (
            st.session_state.get("_last_processed_query") == query.strip()
            or (
                len(hist) >= 2
                and hist[-2][0] == "user"
                and (hist[-2][1] if len(hist[-2]) > 1 else "") == query.strip()
                and hist[-1][0] == "assistant"
                # If the assistant message is blank or an echo of the question, don't treat as "already processed".
                and _normalize_for_compare(hist[-1][1] if len(hist[-1]) > 1 else "") not in ("", normalized_query)
            )
        )
        if already_responded:
            pass  # Skip - already responded to this query
        else:
            st.session_state.pop("_pending_chat_query", None)  # Clear so we don't re-use on next run
            logger.info(f"Query: {query}")
            
            # Auto-create conversation if none exists
            if not st.session_state.current_conversation_id:
                try:
                    resp = requests.post(f"{API_URL}/conversations", json={}, timeout=5)
                    if resp.status_code == 200:
                        conv = resp.json()
                        st.session_state.current_conversation_id = conv.get("id")
                except Exception:
                    pass
            
            # Add user message to history
            timestamp = datetime.now().strftime("%H:%M")
            st.session_state.chat_history.append(("user", query.strip(), timestamp))

            # Get response (streaming or regular)
            _use_streaming = st.session_state.enable_streaming
            if _use_streaming:
                # Streaming response (note: advanced filters not yet supported in streaming)
                try:
                    start_time = time.time()
                    # Prepare request payload with document filters and conversation
                    payload = {"query": query}
                    if st.session_state.selected_documents:
                        payload["document_filters"] = st.session_state.selected_documents
                    # Intentionally do not send conversation_id in reliability mode.
                    # Add language preference (default to "en" to avoid wrong auto-detection)
                    if st.session_state.get("user_language"):
                        payload["language"] = st.session_state.user_language
                    elif st.session_state.get("user_preferences", {}).get("language"):
                        payload["language"] = st.session_state.user_preferences["language"]
                    else:
                        payload["language"] = "en"
                    endpoint = f"{API_URL}/ask/stream"
                    
                    # Create placeholder in chat column so response appears right under input area
                    with col_chat:
                        answer_placeholder = st.empty()
                    answer_text = ""
                    sources = []
                    status_text = ""
                    received_any_chunk = False
                    received_done = False
                    # Show typing indicator (animated dots) while waiting for first token
                    answer_placeholder.markdown(
                        '<div class="msg msg-assistant streaming"><div class="msg-body">'
                        '<div class="typing-dots" style="display:inline-flex;gap:4px;">'
                        '<span style="width:6px;height:6px;border-radius:50%;background:#2dd4bf;"></span>'
                        '<span style="width:6px;height:6px;border-radius:50%;background:#2dd4bf;"></span>'
                        '<span style="width:6px;height:6px;border-radius:50%;background:#2dd4bf;"></span>'
                        '</div></div></div>',
                        unsafe_allow_html=True
                    )
                    # Stream the response (use appropriate endpoint)
                    # Use a longer read timeout for streaming; connect timeout stays short
                    try:
                        with requests.post(endpoint, json=payload, stream=True, timeout=(5, 300)) as response:
                            if response.status_code == 200:
                                for line in response.iter_lines(decode_unicode=True):
                                    if line:
                                        line_str = line
                                        if isinstance(line_str, bytes):
                                            line_str = line_str.decode("utf-8", errors="ignore")
                                        # Accept both `data: {...}` and `data: {...}` (with/without space)
                                        if isinstance(line_str, str) and line_str.startswith("data:"):
                                            try:
                                                json_str = line_str[5:]  # Remove `data:` prefix
                                                if json_str.startswith(" "):
                                                    json_str = json_str[1:]
                                                data = json.loads(json_str)
                                                event_type = data.get("type")
                                            
                                                if event_type == "status":
                                                    # Render lightweight progress updates while backend is working
                                                    stage = data.get("stage", "")
                                                    elapsed = data.get("elapsed")
                                                    if elapsed is not None:
                                                        status_text = f"_{stage.replace('_', ' ').title()}... ({elapsed:.1f}s)_"
                                                    else:
                                                        status_text = f"_{stage.replace('_', ' ').title()}..._"
                                                    answer_placeholder.markdown(
                                                        f'<div class="msg msg-assistant streaming"><div class="msg-body">'
                                                        f'{status_text}</div></div>',
                                                        unsafe_allow_html=True,
                                                    )
                                                elif event_type == "sources":
                                                    sources = data.get("sources", [])
                                                elif event_type == "chunk":
                                                    chunk = data.get("content", "")
                                                    if chunk:
                                                        received_any_chunk = True
                                                    answer_text += chunk
                                                    safe_text = html.escape(answer_text).replace("\n", "<br/>")
                                                    answer_placeholder.markdown(
                                                        f'<div class="msg msg-assistant streaming"><div class="msg-body">'
                                                        f'{safe_text}</div></div>',
                                                        unsafe_allow_html=True,
                                                    )
                                                elif event_type == "done":
                                                    received_done = True
                                                    full_response = data.get("full_response", answer_text)
                                                    if full_response and str(full_response).strip():
                                                        answer_text = str(full_response)
                                                    _safe_final = html.escape(answer_text).replace("\n", "<br/>")
                                                    answer_placeholder.markdown(
                                                        f'<div class="msg msg-assistant"><div class="msg-body">'
                                                        f'{_safe_final}</div></div>',
                                                        unsafe_allow_html=True,
                                                    )
                                                elif event_type == "error":
                                                    error_msg = data.get("content", "Unknown error")
                                                    answer_text = error_msg
                                                    answer_placeholder.empty()
                                            except json.JSONDecodeError:
                                                continue
                                
                                # If the stream ends without any chunks (or never receives `done`),
                                # retry once using the non-streaming endpoint.
                                # If we only got an "echo" of the question (common failure mode),
                                # retry using non-streaming to force a full regenerated answer.
                                if (not received_any_chunk) or (not received_done) or (_normalize_for_compare(answer_text) == normalized_query):
                                    try:
                                        fallback = requests.post(f"{API_URL}/ask", json=payload, timeout=180)
                                        if fallback.status_code == 200:
                                            rd = fallback.json()
                                            answer_text = rd.get("response", "No answer received")
                                            sources = rd.get("sources", [])
                                    except Exception:
                                        pass
                            else:
                                # Fall back to non-streaming on server error
                                try:
                                    fallback = requests.post(f"{API_URL}/ask", json=payload, timeout=180)
                                    if fallback.status_code == 200:
                                        rd = fallback.json()
                                        answer_text = rd.get("response", "No answer received")
                                        sources = rd.get("sources", [])
                                    else:
                                        answer_text = f"⚠️ Error {fallback.status_code}: {fallback.text}"
                                except Exception:
                                    answer_text = f"⚠️ Error {response.status_code}: {response.text}"
                    except (ProtocolError, ChunkedEncodingError) as e:
                        # Streaming connection dropped (often uvicorn reload or server restart). Retry once via non-streaming.
                        answer_placeholder.empty()
                        log_error_to_console(f"Streaming connection dropped: {str(e)}", "Warning", e)
                        try:
                            fallback = requests.post(f"{API_URL}/ask", json=payload, timeout=180)
                            if fallback.status_code == 200:
                                rd = fallback.json()
                                answer_text = rd.get("response", "No answer received")
                                sources = rd.get("sources", [])
                            else:
                                answer_text = f"⚠️ Stream dropped, and fallback failed ({fallback.status_code}). Please retry."
                        except Exception:
                            if answer_text.strip():
                                answer_text = answer_text.strip() + "\n\n⚠️ Connection dropped before completion. Please retry."
                            else:
                                answer_text = "⚠️ Connection dropped before completion. Please retry."
                
                    elapsed_time = time.time() - start_time
                    answer_timestamp = datetime.now().strftime("%H:%M")
                
                    # Validate response before storing - prevent empty or corrupted responses
                    if not answer_text or not answer_text.strip():
                        answer_text = "⚠️ No response received. Please try again."
                    if answer_text.strip().startswith("<div") or answer_text.strip().startswith("<span"):
                        # Detect accidentally captured HTML (should never happen, but safeguard)
                        logger.warning(f"Detected HTML in response, this indicates a bug: {answer_text[:100]}")
                        answer_text = "⚠️ An error occurred while processing the response. Please try again."
                
                    try:
                        _safe_final = html.escape(answer_text).replace("\n", "<br/>")
                        answer_placeholder.markdown(
                            f'<div class="msg msg-assistant"><div class="msg-body">{_safe_final}</div></div>',
                            unsafe_allow_html=True,
                        )
                    except Exception:
                        pass
                    st.session_state.chat_history.append(("assistant", answer_text, answer_timestamp, sources))
                    logger.info(f"Streaming response time: {elapsed_time:.2f}s, Sources: {len(sources)}")
                    # Mark as processed only when we actually got a non-echo answer.
                    normalized_answer = _normalize_for_compare(answer_text)
                    if normalized_answer and normalized_answer != normalized_query:
                        st.session_state._last_processed_query = query.strip()
                except requests.exceptions.ConnectionError:
                    error_msg = "Cannot connect to API. Please ensure the server is running."
                    st.session_state.chat_history.append(("assistant", f"❌ {error_msg}", timestamp, []))
                    log_error_to_console(error_msg, "ConnectionError")
                except requests.exceptions.Timeout:
                    error_msg = "Request timed out. The query may be taking longer than expected. Please try again or simplify your query."
                    try:
                        answer_placeholder.empty()
                    except Exception:
                        pass
                    st.session_state.chat_history.append(("assistant", f"⏱️ {error_msg}", timestamp, []))
                    log_error_to_console(error_msg, "Timeout")
                    st.info("💡 **Tip:** Complex queries or large knowledge bases may take longer. Try breaking down your question into smaller parts.")
                except Exception as e:
                    error_msg = f"Unexpected error: {str(e)}"
                    try:
                        answer_placeholder.empty()
                    except Exception:
                        pass
                    st.session_state.chat_history.append(("assistant", f"❌ {error_msg}", timestamp, []))
                    log_error_to_console(error_msg, "Exception", e)
            else:
                # Regular (non-streaming) response - runs only when streaming is disabled
                with st.spinner("🤔 Thinking..."):
                        try:
                            start_time = time.time()
                            # Prepare request payload with filters and conversation
                            if st.session_state.show_advanced_filters and st.session_state.get("advanced_filters"):
                                payload = {
                                    "query": query,
                                    "filters": st.session_state.advanced_filters
                                }
                                if st.session_state.current_conversation_id:
                                    payload["conversation_id"] = st.session_state.current_conversation_id
                                endpoint = f"{API_URL}/ask/advanced"
                            else:
                                payload = {"query": query}
                                if st.session_state.selected_documents:
                                    payload["document_filters"] = st.session_state.selected_documents
                                if st.session_state.current_conversation_id:
                                    payload["conversation_id"] = st.session_state.current_conversation_id
                                if st.session_state.get("user_language"):
                                    payload["language"] = st.session_state.user_language
                                elif st.session_state.get("user_preferences", {}).get("language"):
                                    payload["language"] = st.session_state.user_preferences["language"]
                                else:
                                    payload["language"] = "en"
                                endpoint = f"{API_URL}/ask"
                            
                            # Non-streaming calls can legitimately take longer (first model load, large context, etc.)
                            response = requests.post(endpoint, json=payload, timeout=180)
                            elapsed_time = time.time() - start_time
                            
                            if response.status_code == 200:
                                response_data = response.json()
                                answer = response_data.get("response", "No answer received")
                                sources = response_data.get("sources", [])
                                answer_timestamp = datetime.now().strftime("%H:%M")
                                
                                # Validate response before storing
                                if not answer or not answer.strip():
                                    answer = "⚠️ No response received. Please try again."
                                # Keep model output unchanged; only handle true transport/execution errors.
                                if answer.strip().startswith("<div") or answer.strip().startswith("<span"):
                                    logger.warning(f"Detected HTML in response: {answer[:100]}")
                                    answer = "⚠️ An error occurred while processing the response. Please try again."
                                
                                st.session_state.chat_history.append(("assistant", answer, answer_timestamp, sources))
                                logger.info(f"Response time: {elapsed_time:.2f}s, Sources: {len(sources)}")
                            else:
                                error_msg = f"⚠️ Error {response.status_code}: {response.text}"
                                st.session_state.chat_history.append(("assistant", error_msg, timestamp, []))
                        except requests.exceptions.ConnectionError:
                            error_msg = "Cannot connect to API. Please ensure the server is running."
                            st.session_state.chat_history.append(("assistant", f"❌ {error_msg}", timestamp, []))
                            log_error_to_console(error_msg, "ConnectionError")
                        except requests.exceptions.Timeout:
                            error_msg = "Request timed out. The query may be taking longer than expected. Please try again or simplify your query."
                            st.session_state.chat_history.append(("assistant", f"⏱️ {error_msg}", timestamp, []))
                            log_error_to_console(error_msg, "Timeout")
                            st.info("💡 **Tip:** Complex queries or large knowledge bases may take longer. Try breaking down your question into smaller parts.")
                        except Exception as e:
                            error_msg = f"Unexpected error: {str(e)}"
                            st.session_state.chat_history.append(("assistant", f"❌ {error_msg}", timestamp, []))
                            log_error_to_console(error_msg, "Exception", e)

                        # Mark as processed only when we actually got a non-echo answer.
                        normalized_answer = _normalize_for_compare(answer)
                        if normalized_answer and normalized_answer != normalized_query:
                            st.session_state._last_processed_query = query.strip()
        st.rerun()

