import os
import re
import streamlit as st
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


def _is_streamlit_cloud() -> bool:
    """True when running on Streamlit Community Cloud (or similarly hosted)."""
    cwd = os.getcwd().replace("\\", "/")
    return bool(
        os.environ.get("STREAMLIT_SHARING_MODE")
        or cwd.startswith("/mount/src")
    )


def _apply_streamlit_secrets_to_environ() -> None:
    """Copy st.secrets into os.environ so API_URL and friends work on Cloud."""
    try:
        secrets = st.secrets
    except Exception:
        return
    try:
        items = dict(secrets)
    except Exception:
        return
    for key, value in items.items():
        if isinstance(value, (dict, list)):
            continue
        os.environ.setdefault(str(key), str(value))


_apply_streamlit_secrets_to_environ()

# API URL: Streamlit Cloud secrets → env → local default
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")


def get_api_connection_error_message() -> str:
    """Get a helpful error message when API connection fails."""
    api_url = API_URL
    on_cloud = _is_streamlit_cloud()

    if (api_url.startswith("http://127.0.0.1") or api_url.startswith("http://localhost")) and on_cloud:
        return (
            "❌ Cannot connect to API.\n\n"
            "**The API URL is set to localhost, which won't work on Streamlit Cloud.**\n\n"
            "**To fix this:**\n"
            "1. Deploy your FastAPI backend to Railway, Render, Fly.io, or another platform\n"
            "2. In Streamlit Cloud, go to: Settings → Secrets\n"
            "3. Add: `API_URL = \"https://your-backend-url.com\"`\n"
            "4. Reboot the app\n\n"
            "See `docs/STREAMLIT_CLOUD_DEPLOYMENT.md` for detailed instructions."
        )
    elif api_url.startswith("http://127.0.0.1") or api_url.startswith("http://localhost"):
        return (
            f"❌ Cannot connect to local API at `{api_url}`.\n\n"
            "**This is a local run issue (not Streamlit Cloud).**\n"
            "**Please check:**\n"
            "1. Is FastAPI running on that exact port?\n"
            "2. Are Streamlit and API using the same `API_URL` / `PORT` values?\n"
            "3. Restart Streamlit after changing environment variables.\n\n"
            "Tip: run `python run.py api` and `python run.py app` from fresh terminals."
        )
    else:
        return (
            f"❌ Cannot connect to API at `{api_url}`.\n\n"
            "**Please check:**\n"
            "1. Is the backend server running?\n"
            "2. Is the API URL correct in Streamlit Cloud secrets?\n"
            "3. Can you access the backend directly? Try: `curl {api_url}/health`\n\n"
            "See `docs/STREAMLIT_CLOUD_DEPLOYMENT.md` for troubleshooting."
        )

# Get project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure logging (file handler is best-effort — Cloud filesystems can be picky)
log_dir = os.path.join(PROJECT_ROOT, "logs")
_log_handlers = [logging.StreamHandler()]
try:
    os.makedirs(log_dir, exist_ok=True)
    _log_handlers.insert(0, logging.FileHandler(os.path.join(log_dir, "streamlit.log")))
except OSError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=_log_handlers,
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

# Sidebar open/closed state is owned by the app (see nav_toggle_sidebar).
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
    /* Profile name sits in the nav column only.
       div:has() would also match the app shell and center the sidebar. */
    [data-testid="stHorizontalBlock"] > div:has(.nav-avatar-col) {
        display: flex !important;
        justify-content: flex-end !important;
        align-items: center !important;
    }
    [data-testid="stHorizontalBlock"] > div:has(.nav-avatar-col) [data-testid="stPopover"] {
        display: flex !important;
        justify-content: flex-end !important;
        width: 100% !important;
    }
    [data-testid="stHorizontalBlock"] > div:has(.nav-avatar-col) [data-testid="stPopover"] > button,
    [data-testid="stHorizontalBlock"] > div:has(.nav-avatar-col) .stPopover > button {
        border-radius: 10px !important;
        padding: 0.35rem 0.7rem 0.35rem 0.55rem !important;
        background: rgba(30, 41, 59, 0.9) !important;
        border: 1px solid rgba(71, 85, 105, 0.5) !important;
        color: #e2e8f0 !important;
        min-width: 5.5rem !important;
        width: auto !important;
        max-width: 11rem !important;
        height: 2.5rem !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0.4rem !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        letter-spacing: -0.01em !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
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
    
    /* One opener: the ☰ in the top bar. Hide Streamlit's own chevrons. */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"] {
        display: none !important;
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
    


    /* Suggestion pills - row of buttons below chat bar, small & secondary */
    
    /* De-emphasize expander (filters/options) - subtle so chat bar stands out */
    .streamlit-expanderHeader {
        font-size: 0.85rem !important;
        color: #94a3b8 !important;
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

    .answer-card {
        margin: 0 0 1.15rem;
        padding: 0.95rem 1.05rem 0.8rem;
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.62);
        border: 1px solid rgba(148, 163, 184, 0.16);
    }

    .msg-assistant .msg-body {
        color: #e2e8f0;
    }

    .answer-meta {
        margin-top: 0.9rem;
        padding-top: 0.65rem;
        border-top: 1px solid rgba(148, 163, 184, 0.16);
        display: flex;
        flex-direction: column;
        gap: 0.45rem;
    }

    .answer-confidence {
        margin: 0;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.75rem;
        font-weight: 500;
        letter-spacing: 0.01em;
        line-height: 1.3;
        color: #94a3b8;
    }
    .answer-confidence.high { color: #5eead4; }
    .answer-confidence.medium { color: #fbbf24; }
    .answer-confidence.low,
    .answer-confidence.very_low { color: #f87171; }

    .answer-sources {
        margin: 0;
        padding: 0;
        border-top: none;
    }
    .answer-sources summary {
        cursor: pointer;
        list-style: none;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.8rem;
        font-weight: 600;
        color: #94a3b8;
    }
    .answer-sources summary::-webkit-details-marker { display: none; }
    .answer-sources summary::before {
        content: "▸ ";
        color: #64748b;
    }
    .answer-sources[open] summary::before { content: "▾ "; }
    .answer-sources .sources-block {
        margin-top: 0.55rem;
        padding-top: 0;
        border-top: none;
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



    /* Fallback greeting (non Knowledge Home empty states) */
    .copilot-greeting {
        text-align: center;
        padding: 2rem 0 1.25rem;
        max-width: 640px;
        margin: 0 auto;
    }
    .copilot-greeting h2 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.55rem;
        font-weight: 700;
        color: #f8fafc;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.03em;
    }
    .copilot-greeting p {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.98rem;
        color: #94a3b8;
        margin: 0;
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
    .kh-steps {
        max-width: 520px;
        margin: 0.85rem auto 1rem;
        text-align: left;
        display: grid;
        gap: 0.55rem;
    }
    .kh-step {
        display: grid;
        grid-template-columns: 1.6rem 1fr;
        gap: 0.65rem;
        align-items: start;
        padding: 0.65rem 0.75rem;
        border-radius: 12px;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(12, 20, 32, 0.4);
    }
    .kh-step-num {
        width: 1.5rem;
        height: 1.5rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: rgba(13, 148, 136, 0.2);
        color: #5eead4;
        font-size: 0.75rem;
        font-weight: 700;
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    .kh-step strong {
        display: block;
        color: #f1f5f9;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.88rem;
        margin-bottom: 0.15rem;
    }
    .kh-step span {
        color: #94a3b8;
        font-size: 0.8rem;
        font-family: 'DM Sans', sans-serif;
        line-height: 1.4;
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
    .msg-confidence {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        margin: 0.45rem 0 0.35rem;
        padding: 0.28rem 0.65rem;
        border-radius: 999px;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.75rem;
        font-weight: 600;
        border: 1px solid rgba(148, 163, 184, 0.2);
        background: rgba(15, 23, 42, 0.55);
        color: #cbd5e1;
    }
    .msg-confidence.high { color: #5eead4; border-color: rgba(20, 184, 166, 0.35); }
    .msg-confidence.medium { color: #fbbf24; border-color: rgba(245, 158, 11, 0.35); }
    .msg-confidence.low, .msg-confidence.very_low { color: #f87171; border-color: rgba(248, 113, 113, 0.35); }
    .msg-gap {
        margin: 0.35rem 0 0.55rem;
        padding: 0.7rem 0.85rem;
        border-radius: 10px;
        border: 1px solid rgba(248, 113, 113, 0.28);
        background: rgba(127, 29, 29, 0.18);
        color: #fecaca;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.82rem;
        line-height: 1.45;
    }
    .msg-gap strong { color: #fee2e2; }
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
    .kh-composer-hint {
        text-align: center;
        color: #64748b;
        font-size: 0.8rem;
        margin: 0.55rem 0 0.85rem;
        font-family: 'DM Sans', sans-serif;
    }

    /* ===== Library ===== */
    .lib-shell {
        max-width: 820px;
        margin: 0.35rem auto 1.25rem;
        animation: authFadeUp 0.4s ease both;
    }
    .lib-header {
        text-align: center;
        margin-bottom: 1.15rem;
    }
    .lib-eyebrow {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #64748b;
        margin: 0 0 0.45rem 0;
    }
    .lib-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: clamp(1.45rem, 2.8vw, 1.85rem);
        font-weight: 700;
        letter-spacing: -0.035em;
        color: #f8fafc;
        margin: 0 0 0.4rem 0;
        line-height: 1.2;
    }
    .lib-subtitle {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.95rem;
        color: #94a3b8;
        margin: 0 0 1rem 0;
        line-height: 1.4;
    }
    .lib-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.95rem 0.15rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }
    .lib-row-main {
        min-width: 0;
        flex: 1;
    }
    .lib-name {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.98rem;
        font-weight: 600;
        color: #f1f5f9;
        letter-spacing: -0.02em;
        margin: 0 0 0.3rem 0;
        word-break: break-word;
    }
    .lib-meta {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.8rem;
        color: #64748b;
        margin: 0;
        line-height: 1.4;
    }
    .lib-status {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.74rem;
        font-weight: 550;
        color: #94a3b8;
        white-space: nowrap;
        margin-top: 0.15rem;
    }
    .lib-status-dot {
        width: 0.4rem;
        height: 0.4rem;
        border-radius: 50%;
        background: #14b8a6;
        display: inline-block;
    }
    .lib-status-dot.warn {
        background: #f59e0b;
    }
    .lib-status-dot.fail {
        background: #ef4444;
    }
    .lib-status-dot.muted {
        background: #64748b;
    }
    .lib-filters-marker + div {
        max-width: 820px;
        margin-left: auto !important;
        margin-right: auto !important;
        margin-bottom: 0.65rem !important;
    }
    .lib-toolbar-marker + div [data-testid="stHorizontalBlock"] {
        max-width: 820px;
        margin-left: auto !important;
        margin-right: auto !important;
        gap: 0.55rem !important;
        margin-bottom: 0.85rem !important;
    }
    .lib-toolbar-marker + div .stButton > button {
        border-radius: 10px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 600 !important;
        min-height: 2.5rem;
        background: transparent !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
        color: #cbd5e1 !important;
        box-shadow: none !important;
    }
    .lib-toolbar-marker + div .stButton > button:hover {
        border-color: rgba(45, 212, 191, 0.35) !important;
        color: #f1f5f9 !important;
        background: rgba(13, 148, 136, 0.1) !important;
        transform: none !important;
    }
    .lib-toolbar-marker + div .stButton > button[kind="primary"] {
        background: #0d9488 !important;
        border: none !important;
        color: #fff !important;
    }
    .lib-list-marker + div {
        max-width: 820px;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    .lib-bulk-marker + div {
        max-width: 820px;
        margin: 0.35rem auto 0.85rem !important;
    }
    .lib-bulk-marker + div .stButton > button {
        border-radius: 10px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.85rem !important;
        min-height: 2.4rem;
    }

    /* ===== Upload ===== */
    .up-shell {
        max-width: 640px;
        margin: 0.35rem auto 1.1rem;
        animation: authFadeUp 0.4s ease both;
    }
    .up-header { text-align: center; margin-bottom: 1.1rem; }
    .up-eyebrow {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #64748b;
        margin: 0 0 0.45rem 0;
    }
    .up-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: clamp(1.45rem, 2.8vw, 1.85rem);
        font-weight: 700;
        letter-spacing: -0.035em;
        color: #f8fafc;
        margin: 0 0 0.4rem 0;
        line-height: 1.2;
    }
    .up-subtitle {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.95rem;
        color: #94a3b8;
        margin: 0;
        line-height: 1.45;
    }
    .up-panel-marker + div {
        max-width: 640px;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    .up-panel-marker + div [data-testid="stFileUploader"] {
        border: 1px dashed rgba(148, 163, 184, 0.28) !important;
        border-radius: 14px !important;
        background: rgba(12, 20, 32, 0.45) !important;
        padding: 0.65rem !important;
    }
    .up-actions-marker + div [data-testid="stHorizontalBlock"] {
        max-width: 640px;
        margin-left: auto !important;
        margin-right: auto !important;
        gap: 0.55rem !important;
    }
    .up-actions-marker + div .stButton > button {
        border-radius: 10px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 600 !important;
        min-height: 2.55rem;
    }
    .up-actions-marker + div .stButton > button[kind="primary"] {
        background: #0d9488 !important;
        border: none !important;
        color: #fff !important;
    }
    .up-result {
        max-width: 640px;
        margin: 0.25rem auto 0.85rem;
        padding: 1rem 1.1rem 0.85rem;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(15, 23, 42, 0.62);
    }
    .up-result.ready {
        border-color: rgba(45, 212, 191, 0.28);
        background: rgba(13, 148, 136, 0.1);
    }
    .up-result.indexing {
        border-color: rgba(251, 191, 36, 0.32);
        background: rgba(245, 158, 11, 0.08);
    }
    .up-result.failed {
        border-color: rgba(248, 113, 113, 0.32);
        background: rgba(239, 68, 68, 0.08);
    }
    .up-result h3 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.05rem;
        color: #f8fafc;
        margin: 0 0 0.3rem 0;
        letter-spacing: -0.02em;
    }
    .up-result p {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.88rem;
        color: #94a3b8;
        margin: 0;
        line-height: 1.45;
    }
    .up-files {
        margin-top: 0.75rem;
        border-top: 1px solid rgba(148, 163, 184, 0.14);
    }
    .up-file {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.85rem;
        padding: 0.55rem 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1);
    }
    .up-file:last-child { border-bottom: none; padding-bottom: 0.15rem; }
    .up-file-name {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.9rem;
        color: #e2e8f0;
        word-break: break-word;
    }
    .up-file-detail {
        display: block;
        margin-top: 0.15rem;
        font-size: 0.75rem;
        color: #64748b;
    }
    .up-pill {
        flex: none;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.72rem;
        font-weight: 650;
        letter-spacing: 0.02em;
    }
    .up-pill.ready { color: #5eead4; }
    .up-pill.indexing { color: #fbbf24; }
    .up-pill.failed { color: #f87171; }
    .up-live {
        margin: 0.7rem 0 0;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        color: #94a3b8;
    }
    .up-formats {
        max-width: 640px;
        margin: 0.75rem auto 0;
        text-align: center;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.8rem;
        color: #64748b;
    }

    .quiet-row-marker + div,
    .quiet-form-marker + div {
        max-width: 820px;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    .quiet-row-marker + div .stButton > button,
    .quiet-form-marker + div .stButton > button {
        border-radius: 10px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 550 !important;
        min-height: 2.25rem;
        background: transparent !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
        color: #cbd5e1 !important;
        box-shadow: none !important;
    }
    .quiet-row-marker + div .stButton > button:hover,
    .quiet-form-marker + div .stButton > button:hover {
        border-color: rgba(45, 212, 191, 0.35) !important;
        color: #f8fafc !important;
        background: rgba(13, 148, 136, 0.1) !important;
        transform: none !important;
    }
    .quiet-empty {
        max-width: 820px;
        margin: 0.25rem auto 1.25rem;
        text-align: center;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.92rem;
        color: #94a3b8;
        line-height: 1.45;
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


def render_section_header(eyebrow: str, title: str, subtitle: str):
    """Centered header shared with Library and Upload."""
    st.markdown(
        f"""
        <div class="lib-shell">
            <div class="lib-header">
                <p class="lib-eyebrow">{html.escape(eyebrow)}</p>
                <h1 class="lib-title">{html.escape(title)}</h1>
                <p class="lib-subtitle">{html.escape(subtitle)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_links(links, key_prefix: str):
    """Compact page links used where the sidebar no longer lists them."""
    st.markdown('<div class="lib-toolbar-marker"></div>', unsafe_allow_html=True)
    cols = st.columns(len(links))
    for col, (label, page_key) in zip(cols, links):
        with col:
            if st.button(label, key=f"{key_prefix}_{page_key}", use_container_width=True):
                navigate_to_page(page_key)
                st.query_params["view"] = page_key
                st.rerun()

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
    # Only warn when localhost API_URL would actually break (hosted Streamlit Cloud)
    if _is_streamlit_cloud() and (
        API_URL.startswith("http://127.0.0.1") or API_URL.startswith("http://localhost")
    ):
        st.warning(
            "API URL is set to localhost, which won't work on Streamlit Cloud. "
            "Set `API_URL` in Streamlit Cloud secrets to your public backend URL. "
            "See docs/STREAMLIT_CLOUD_DEPLOYMENT.md."
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
                '<div class="auth-form-hint">No email verification — you can sign in right after creating an account.</div>',
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
                            elif response.status_code in (400, 401, 423):
                                st.error("Invalid email or password.")
                            else:
                                try:
                                    error_detail = response.json().get('detail', 'Unknown error')
                                except Exception:
                                    error_detail = response.text or "Unknown error"
                                st.error(error_detail or "Invalid email or password.")
                        except requests.exceptions.ConnectionError:
                            st.error(get_api_connection_error_message())
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                    else:
                        st.error("Please enter both email and password.")

            # One-click demo for reviewers (no email verification)
            _demo_enabled = False
            try:
                _demo_resp = requests.get(f"{API_URL}/auth/demo-status", timeout=3)
                if _demo_resp.status_code == 200:
                    _demo_enabled = bool(_demo_resp.json().get("enabled"))
            except Exception:
                _demo_enabled = False
            if _demo_enabled:
                st.markdown(
                    '<div class="auth-form-hint" style="margin-top:0.85rem;text-align:center;">'
                    "Reviewing the app? Skip signup — no email verification needed."
                    "</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Continue as demo reviewer", key="demo_login_btn", use_container_width=True):
                    try:
                        with st.spinner("Starting demo session…"):
                            demo_resp = requests.post(f"{API_URL}/auth/demo", timeout=15)
                        if demo_resp.status_code == 200:
                            data = demo_resp.json()
                            st.session_state.authenticated = True
                            st.session_state.access_token = data.get("access_token")
                            if data.get("refresh_token"):
                                st.session_state.refresh_token = data["refresh_token"]
                            if data.get("session_id"):
                                st.session_state.session_id = data["session_id"]
                            st.session_state.current_user = data.get("user")
                            st.query_params.clear()
                            st.rerun()
                        else:
                            try:
                                detail = demo_resp.json().get("detail", "Demo login failed")
                            except Exception:
                                detail = demo_resp.text or "Demo login failed"
                            st.error(detail)
                    except requests.exceptions.ConnectionError:
                        st.error(get_api_connection_error_message())
                    except Exception as e:
                        st.error(str(e))

    st.stop()

# Main app (only shown if authenticated)
# Deep linking: open view from URL (?view=documents etc.)
# Auth-only styles are scoped via body:has(.auth-hero); no class toggle needed.
apply_view_from_query_params()

def _messages_to_chat_history(messages) -> list:
    """Turn stored turns into chat tuples, keeping sources and the confidence line."""
    loaded_history = []
    for msg in messages or []:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")[:5] if msg.get("timestamp") else ""
        sources = msg.get("sources", []) or []
        if not content or content.strip().startswith("<div") or content.strip().startswith("<span"):
            continue
        meta = {}
        if role == "assistant" and (msg.get("confidence") or msg.get("verification")):
            meta = {
                "confidence": msg.get("confidence"),
                "verification": msg.get("verification"),
            }
        loaded_history.append((role, content, timestamp, sources, meta))
    return loaded_history


def _sidebar_load_conversation(conversation_id: str) -> bool:
    """Load a conversation into the current chat session."""
    try:
        conv_detail = requests.get(f"{API_URL}/conversations/{conversation_id}", timeout=5).json()
        st.session_state.current_conversation_id = conversation_id
        st.session_state.chat_history = _messages_to_chat_history(conv_detail.get("messages", []))
        st.session_state.pop("_last_processed_query", None)
        return True
    except Exception as e:
        logger.warning(f"Could not load conversation {conversation_id}: {e}")
        return False


# Sidebar — chat rail only. Pages and account live in the top bar.
with st.sidebar:
    st.markdown('<div class="sb-cta-marker"></div>', unsafe_allow_html=True)
    if st.button("New chat", key="side_start_new_chat", use_container_width=True, type="primary"):
        st.session_state.pop("_last_processed_query", None)
        st.session_state.current_conversation_id = None
        st.session_state.chat_history = []
        st.session_state.side_recent_pick = ""
        navigate_to_page("chat")
        st.query_params["view"] = "chat"
        st.rerun()

    recent_conversations = []
    try:
        conv_resp = requests.get(f"{API_URL}/conversations", timeout=3)
        if conv_resp.status_code == 200:
            all_convs = conv_resp.json().get("conversations", []) or []
            recent_conversations = sorted(
                all_convs,
                key=lambda c: c.get("updated_at") or c.get("created_at") or "",
                reverse=True,
            )[:8]
    except Exception:
        recent_conversations = []

    if recent_conversations:
        titles = {}
        option_ids = [""]
        for conv in recent_conversations:
            conv_id = conv.get("id")
            if not conv_id:
                continue
            title = (conv.get("title") or "Untitled chat").strip() or "Untitled chat"
            if len(title) > 32:
                title = title[:29] + "…"
            titles[conv_id] = title
            option_ids.append(conv_id)
        current_id = st.session_state.get("current_conversation_id")
        if st.session_state.get("side_recent_pick") not in option_ids:
            st.session_state.side_recent_pick = current_id if current_id in option_ids else ""
        picked = st.selectbox(
            "Recent",
            options=option_ids,
            format_func=lambda conv_id: titles.get(conv_id, "Recent"),
            key="side_recent_pick",
            label_visibility="collapsed",
        )
        if picked and picked != current_id:
            if _sidebar_load_conversation(picked):
                navigate_to_page("chat")
                st.query_params["view"] = "chat"
                st.rerun()
    else:
        st.markdown('<p class="sb-thread">No chats yet</p>', unsafe_allow_html=True)

def _toggle_native_sidebar():
    """Click Streamlit's sidebar control from the page itself.

    The chevron lives in the hidden header, so the top-bar button drives it.
    A nonce stops a remount from clicking a second time and undoing the toggle.
    """
    nonce = st.session_state.get("_sidebar_nonce", 0)
    st.html(
        f"""
        <script>
        (function () {{
          const nonce = "{nonce}";
          if (window.__iaSidebarNonce === nonce) return;
          window.__iaSidebarNonce = nonce;
          const clickOnce = () => {{
            const expand = document.querySelector('[data-testid="stExpandSidebarButton"]');
            const collapse = document.querySelector('[data-testid="stSidebarCollapseButton"] button');
            const target = expand || collapse;
            if (!target) return false;
            target.click();
            return true;
          }};
          if (clickOnce()) return;
          let tries = 0;
          const timer = setInterval(() => {{
            tries += 1;
            if (clickOnce() || tries > 20) clearInterval(timer);
          }}, 50);
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
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
col_open_sidebar, col_nav, col_avatar = st.columns([0.8, 4.8, 1.8], gap="small")
with col_open_sidebar:
    if st.button("☰", key="nav_toggle_sidebar", help="Open or close sidebar"):
        st.session_state._sidebar_nonce = st.session_state.get("_sidebar_nonce", 0) + 1
        st.session_state._sidebar_toggle_now = True
    if st.session_state.pop("_sidebar_toggle_now", False):
        _toggle_native_sidebar()
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
    username = (
        user.get("first_name")
        or user.get("display_name")
        or user.get("email")
        or user.get("username")
        or "User"
    )
    # Prefer a short first name on the button; fall back cleanly for emails
    display_name = str(username).strip()
    if "@" in display_name:
        display_name = display_name.split("@", 1)[0]
    if " " in display_name:
        display_name = display_name.split()[0]
    if len(display_name) > 14:
        display_name = display_name[:13] + "…"
    with st.popover(display_name or "Account", use_container_width=False):
        st.caption(str(username).strip())
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

# Library — clean document list (matches Knowledge Home)
if st.session_state.get("show_documents", False):
    def _lib_format_size(file_size):
        try:
            n = int(file_size or 0)
        except (TypeError, ValueError):
            return "—"
        if n <= 0:
            return "—"
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.2f} MB"

    def _lib_format_date(raw):
        if not raw:
            return None
        text = str(raw).strip()
        # Prefer a short date if ISO-like
        if "T" in text:
            return text.split("T", 1)[0]
        return text[:16]

    st.markdown(
        """
        <div class="lib-shell">
            <div class="lib-header">
                <p class="lib-eyebrow">Library</p>
                <h1 class="lib-title">Your documents</h1>
                <p class="lib-subtitle">Browse what the assistant can search. Upload more anytime.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="lib-toolbar-marker"></div>', unsafe_allow_html=True)
    tb1, tb2, tb3, tb4 = st.columns([1.2, 1.4, 1.2, 1.2])
    with tb1:
        if st.button("Back", key="close_documents_dashboard", use_container_width=True):
            st.session_state.show_documents = False
            st.query_params["view"] = "chat"
            st.rerun()
    with tb2:
        if st.button("Upload", key="lib_go_upload", use_container_width=True, type="primary"):
            navigate_to_page("upload")
            st.query_params["view"] = "upload"
            st.rerun()
    with tb3:
        if st.button("Refresh", key="refresh_documents", use_container_width=True):
            st.rerun()
    with tb4:
        pass

    try:
        with st.spinner("Loading library…"):
            try:
                docs_resp = requests.get(f"{API_URL}/documents", headers=get_auth_headers(), timeout=30)
            except requests.exceptions.ConnectionError:
                st.error(get_api_connection_error_message())
                docs_resp = None
            except requests.exceptions.Timeout:
                st.error("Request timed out. Try Refresh.")
                docs_resp = None

        if docs_resp is None:
            pass
        elif docs_resp.status_code != 200:
            st.error(f"Failed to load documents ({docs_resp.status_code})")
        else:
            data = docs_resp.json()
            documents = data.get("documents", []) or []
            total_docs = data.get("total_documents", len(documents))
            total_chunks = data.get("total_chunks", 0)

            st.markdown(
                f"""
                <div class="lib-shell" style="margin-top:0;margin-bottom:0.75rem;">
                    <div class="kh-chips">
                        <span class="kh-chip"><strong>{total_docs}</strong> document{"s" if total_docs != 1 else ""}</span>
                        <span class="kh-chip"><strong>{total_chunks}</strong> searchable chunk{"s" if total_chunks != 1 else ""}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if total_docs == 0:
                st.markdown(
                    """
                    <div class="kh-empty" style="margin-left:auto;margin-right:auto;">
                        <h3>Library is empty</h3>
                        <p>Upload a PDF, Word doc, text file, or spreadsheet. Processing usually takes a few seconds — then Refresh.</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                def _lib_status(doc):
                    raw = (doc.get("status") or "").lower().strip()
                    if raw in ("ready", "indexing", "failed"):
                        return raw
                    return "failed"

                st.markdown('<div class="lib-filters-marker"></div>', unsafe_allow_html=True)
                f1, f2, f3 = st.columns([2.4, 1.2, 1.4])
                with f1:
                    lib_search = st.text_input(
                        "Search documents",
                        key="lib_search_q",
                        placeholder="Filter by filename…",
                        label_visibility="collapsed",
                    )
                with f2:
                    type_options = sorted(
                        {
                            (d.get("file_type") or "file").lower()
                            for d in documents
                            if d.get("file_type")
                        }
                    )
                    lib_type = st.selectbox(
                        "Type",
                        options=["All types"] + [t.upper() for t in type_options],
                        key="lib_type_filter",
                        label_visibility="collapsed",
                    )
                with f3:
                    lib_status_filter = st.selectbox(
                        "Status",
                        options=["All statuses", "Ready", "Indexing", "Failed"],
                        key="lib_status_filter",
                        label_visibility="collapsed",
                    )

                filtered_docs = []
                for doc in documents:
                    name = (doc.get("filename") or "").lower()
                    if lib_search and lib_search.strip().lower() not in name:
                        continue
                    doc_type = (doc.get("file_type") or "file").upper()
                    if lib_type != "All types" and doc_type != lib_type:
                        continue
                    st_label = _lib_status(doc)
                    if lib_status_filter == "Ready" and st_label != "ready":
                        continue
                    if lib_status_filter == "Indexing" and st_label != "indexing":
                        continue
                    if lib_status_filter == "Failed" and st_label != "failed":
                        continue
                    filtered_docs.append(doc)

                ready_n = sum(1 for d in documents if _lib_status(d) == "ready")
                indexing_n = sum(1 for d in documents if _lib_status(d) == "indexing")
                failed_n = sum(1 for d in documents if _lib_status(d) == "failed")
                st.caption(
                    f"Showing {len(filtered_docs)} of {total_docs} · "
                    f"{ready_n} ready · {indexing_n} indexing"
                    + (f" · {failed_n} failed" if failed_n else "")
                )

                sel_all_c, clear_c, _ = st.columns([1.4, 1.4, 3])
                with sel_all_c:
                    if st.button("Select all shown", key="lib_select_all", use_container_width=True):
                        for doc in filtered_docs:
                            fn = doc.get("filename")
                            if fn:
                                st.session_state[f"select_{fn}"] = True
                        st.session_state["confirm_batch_delete"] = False
                        st.rerun()
                with clear_c:
                    if st.button("Clear selection", key="lib_clear_sel", use_container_width=True):
                        for doc in documents:
                            fn = doc.get("filename")
                            if fn:
                                st.session_state[f"select_{fn}"] = False
                        st.session_state["confirm_batch_delete"] = False
                        st.rerun()

                selected_names = [
                    doc.get("filename")
                    for doc in filtered_docs
                    if doc.get("filename") and st.session_state.get(f"select_{doc.get('filename')}", False)
                ]

                if selected_names:
                    st.markdown('<div class="lib-bulk-marker"></div>', unsafe_allow_html=True)
                    if st.session_state.get("confirm_batch_delete", False):
                        st.warning(
                            f"Delete {len(selected_names)} document(s)? This removes them from the knowledge base."
                        )
                        bc1, bc2, bc3 = st.columns([1.5, 1.5, 2])
                        with bc1:
                            if st.button("Confirm delete", key="lib_batch_delete_yes", use_container_width=True, type="primary"):
                                try:
                                    with st.spinner(f"Deleting {len(selected_names)}…"):
                                        delete_resp = requests.post(
                                            f"{API_URL}/documents/batch-delete",
                                            json={"filenames": selected_names},
                                            headers=get_auth_headers(),
                                            timeout=60,
                                        )
                                    if delete_resp.status_code == 200:
                                        for filename in selected_names:
                                            st.session_state[f"select_{filename}"] = False
                                        st.session_state["confirm_batch_delete"] = False
                                        st.toast(f"Deleted {len(selected_names)}")
                                        st.rerun()
                                    else:
                                        st.error(f"Delete failed ({delete_resp.status_code})")
                                        st.session_state["confirm_batch_delete"] = False
                                except Exception as e:
                                    st.error(str(e))
                                    st.session_state["confirm_batch_delete"] = False
                        with bc2:
                            if st.button("Cancel", key="lib_batch_delete_no", use_container_width=True):
                                st.session_state["confirm_batch_delete"] = False
                                st.rerun()
                        with bc3:
                            st.caption(f"{len(selected_names)} selected")
                    else:
                        b1, b2, b3 = st.columns([1.6, 1.6, 2])
                        with b1:
                            if st.button(
                                f"Delete {len(selected_names)}",
                                key="lib_batch_delete",
                                use_container_width=True,
                            ):
                                st.session_state["confirm_batch_delete"] = True
                                st.rerun()
                        with b2:
                            if st.button(
                                f"Reprocess {len(selected_names)}",
                                key="lib_batch_reprocess",
                                use_container_width=True,
                            ):
                                try:
                                    with st.spinner("Queuing reprocess…"):
                                        reprocess_resp = requests.post(
                                            f"{API_URL}/documents/bulk-reprocess",
                                            json={"filenames": selected_names},
                                            headers=get_auth_headers(),
                                            timeout=60,
                                        )
                                    if reprocess_resp.status_code == 200:
                                        st.toast("Reprocess queued")
                                        time.sleep(0.4)
                                        st.rerun()
                                    else:
                                        st.error(f"Reprocess failed ({reprocess_resp.status_code})")
                                except Exception as e:
                                    st.error(str(e))
                        with b3:
                            st.caption(f"{len(selected_names)} selected")

                if not filtered_docs:
                    st.info("No documents match these filters.")
                else:
                    st.markdown('<div class="lib-list-marker"></div>', unsafe_allow_html=True)
                    for idx, doc in enumerate(filtered_docs):
                        filename = doc.get("filename") or "Unknown"
                        checkbox_key = f"select_{filename}"
                        chunks = int(doc.get("chunk_count") or 0)
                        file_type = (doc.get("file_type") or "file").upper()
                        size_label = _lib_format_size(doc.get("file_size"))
                        date_label = _lib_format_date(doc.get("upload_date"))
                        st_key = _lib_status(doc)
                        status_map = {
                            "ready": ("Ready", ""),
                            "indexing": ("Indexing", "warn"),
                            "failed": ("Failed", "fail"),
                        }
                        status_label, status_dot = status_map.get(st_key, ("Indexing", "warn"))
                        status_detail = (doc.get("status_detail") or "").strip()
                        if st_key == "ready":
                            status_detail = ""
                        meta_bits = [file_type, f"{chunks} chunk{'s' if chunks != 1 else ''}", size_label]
                        if date_label:
                            meta_bits.append(date_label)
                        if doc.get("version_count") and int(doc.get("version_count") or 0) > 1:
                            meta_bits.append(f"v{doc.get('version', '?')}/{doc.get('version_count')}")

                        col_check, col_body, col_actions = st.columns([0.45, 4.2, 1.6], gap="small")
                        with col_check:
                            st.checkbox(
                                f"Select {filename}",
                                value=st.session_state.get(checkbox_key, False),
                                key=checkbox_key,
                                label_visibility="collapsed",
                            )
                        with col_body:
                            st.markdown(
                                f"""
                                <div class="lib-row" style="border-bottom:none;padding:0.35rem 0;">
                                    <div class="lib-row-main">
                                        <p class="lib-name">{html.escape(filename)}</p>
                                        <p class="lib-meta">{html.escape(" · ".join(meta_bits))}</p>
                                        <div class="lib-status"><span class="lib-status-dot {status_dot}"></span>{status_label}{(" · " + html.escape(status_detail)) if status_detail else ""}</div>
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with col_actions:
                            delete_key = f"delete_{idx}_{filename}"
                            confirm_key = f"confirm_{delete_key}"
                            if st.session_state.get(confirm_key, False):
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button("Confirm", key=f"yes_{delete_key}", use_container_width=True):
                                        try:
                                            delete_resp = requests.delete(
                                                f"{API_URL}/documents/{filename}",
                                                headers=get_auth_headers(),
                                                timeout=10,
                                            )
                                            if delete_resp.status_code == 200:
                                                st.session_state[confirm_key] = False
                                                st.toast(f"Deleted {filename}")
                                                st.rerun()
                                            else:
                                                st.error("Delete failed")
                                                st.session_state[confirm_key] = False
                                        except Exception as e:
                                            st.error(str(e))
                                            st.session_state[confirm_key] = False
                                with c2:
                                    if st.button("Cancel", key=f"no_{delete_key}", use_container_width=True):
                                        st.session_state[confirm_key] = False
                                        st.rerun()
                            else:
                                if st.button("Delete", key=delete_key, use_container_width=True):
                                    st.session_state[confirm_key] = True
                                    st.rerun()

                with st.expander("Advanced", expanded=False):
                    if st.button("Reprocess all documents", key="lib_reprocess_all", use_container_width=True):
                        try:
                            with st.spinner("Queuing all documents…"):
                                reprocess_resp = requests.post(
                                    f"{API_URL}/documents/bulk-reprocess",
                                    json={"filenames": None},
                                    headers=get_auth_headers(),
                                    timeout=60,
                                )
                            if reprocess_resp.status_code == 200:
                                st.toast("All documents queued for reprocess")
                            else:
                                st.error(f"Reprocess failed ({reprocess_resp.status_code})")
                        except Exception as e:
                            st.error(str(e))

    except requests.exceptions.Timeout:
        st.error("Request timed out. Try Refresh.")
    except requests.exceptions.ConnectionError:
        st.error(get_api_connection_error_message())
    except Exception as e:
        st.error(f"Error loading library: {e}")

# Upload — simple drop zone + explicit progress
if st.session_state.get("show_upload", False):
    MIME_BY_EXT = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "csv": "text/csv",
        "html": "text/html",
    }

    def _upload_mime(name: str) -> str:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        return MIME_BY_EXT.get(ext, "application/octet-stream")

    st.markdown(
        """
        <div class="up-shell">
            <div class="up-header">
                <p class="up-eyebrow">Upload</p>
                <h1 class="up-title">Add documents</h1>
                <p class="up-subtitle">Drop one or more files. We’ll index them so you can ask questions with sources.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="up-actions-marker"></div>', unsafe_allow_html=True)
    u1, u2, u3 = st.columns([1.2, 1.5, 1.5])
    with u1:
        if st.button("Back", key="close_upload_view", use_container_width=True):
            st.session_state.show_upload = False
            st.query_params["view"] = "chat"
            st.rerun()
    with u2:
        if st.button("Open library", key="upload_view_docs", use_container_width=True):
            navigate_to_page("documents")
            st.query_params["view"] = "documents"
            st.rerun()
    with u3:
        pass

    def _draw_upload_feedback() -> bool:
        """Show Ready / Still indexing / Failed for the last upload. Returns True while any file is still indexing."""
        last_result = st.session_state.get("upload_last_result") or {}
        names = list(last_result.get("names") or [])
        index_items = {}
        if names:
            try:
                status_resp = requests.get(
                    f"{API_URL}/index-status",
                    params={"filenames": ",".join(names)},
                    headers=get_auth_headers(),
                    timeout=8,
                )
                if status_resp.status_code == 200:
                    index_items = (status_resp.json() or {}).get("documents") or {}
            except Exception:
                index_items = {}

        ready_names = [
            name for name in names
            if (index_items.get(name) or {}).get("status") == "ready"
        ]
        failed_names = [
            name for name in names
            if (index_items.get(name) or {}).get("status") == "failed"
        ]
        pending_names = [name for name in names if name not in ready_names and name not in failed_names]

        if names and not pending_names and not failed_names:
            tone = "ready"
            headline = "Ready"
            body = "These files are searchable. You can ask about them now."
        elif pending_names:
            tone = "indexing"
            headline = "Still indexing"
            body = "Ask a question once every file says Ready."
        elif failed_names and not ready_names:
            tone = "failed"
            headline = "Indexing failed"
            body = "Nothing new was added. Check the file, then upload it again."
        elif ready_names and failed_names:
            tone = "mixed"
            headline = "Partly ready"
            body = "The ready files are searchable. The others did not index."
        else:
            tone = "mixed"
            headline = "Uploaded"
            body = "Check the library if a file does not appear below."

        rows = []
        for name in names:
            record = index_items.get(name) or {}
            state = record.get("status") or "indexing"
            if state not in ("ready", "failed", "indexing"):
                state = "indexing"
            label = {"ready": "Ready", "failed": "Failed", "indexing": "Indexing"}[state]
            detail = (record.get("detail") or "").strip()
            if state == "ready" and detail.lower() == "indexed":
                detail = ""
            if detail.endswith(" chunks"):
                count_text, _, _ = detail.partition(" ")
                if count_text.isdigit():
                    count = int(count_text)
                    detail = f"{count} chunk" if count == 1 else f"{count} chunks"
            detail_html = f'<span class="up-file-detail">{html.escape(detail)}</span>' if detail else ""
            rows.append(
                f'<div class="up-file"><div><span class="up-file-name">{html.escape(name)}</span>'
                f'{detail_html}</div><span class="up-pill {state}">{label}</span></div>'
            )
        live_html = '<p class="up-live">Updating on its own.</p>' if pending_names else ""
        st.markdown(
            f"""
            <div class="up-result {tone}">
                <h3>{html.escape(headline)}</h3>
                <p>{html.escape(body)}</p>
                <div class="up-files">{''.join(rows)}</div>
                {live_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="up-actions-marker"></div>', unsafe_allow_html=True)
        if not pending_names and ready_names:
            r1, r2, r3 = st.columns(3)
            with r1:
                if st.button("Ask a question", key="upload_goto_ask", use_container_width=True, type="primary"):
                    st.session_state.pop("upload_last_result", None)
                    st.session_state["upload_polling"] = False
                    st.session_state["onboarding_after_upload"] = True
                    navigate_to_page("chat")
                    st.query_params["view"] = "chat"
                    st.rerun()
            with r2:
                if st.button("View in library", key="upload_goto_library", use_container_width=True):
                    st.session_state.pop("upload_last_result", None)
                    st.session_state["upload_polling"] = False
                    navigate_to_page("documents")
                    st.query_params["view"] = "documents"
                    st.rerun()
            with r3:
                if st.button("Upload more", key="upload_clear_result", use_container_width=True):
                    st.session_state.pop("upload_last_result", None)
                    st.session_state["upload_polling"] = False
                    st.session_state["upload_widget_nonce"] = int(st.session_state.get("upload_widget_nonce", 0)) + 1
                    st.rerun()
        else:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("View in library", key="upload_goto_library", use_container_width=True):
                    st.session_state.pop("upload_last_result", None)
                    st.session_state["upload_polling"] = False
                    navigate_to_page("documents")
                    st.query_params["view"] = "documents"
                    st.rerun()
            with c2:
                if st.button("Upload more", key="upload_clear_result", use_container_width=True):
                    st.session_state.pop("upload_last_result", None)
                    st.session_state["upload_polling"] = False
                    st.session_state["upload_widget_nonce"] = int(st.session_state.get("upload_widget_nonce", 0)) + 1
                    st.rerun()
        return bool(pending_names)

    if st.session_state.get("upload_last_result"):
        poll_every = 2 if st.session_state.get("upload_polling", True) else None

        @st.fragment(run_every=poll_every)
        def _upload_feedback():
            still_indexing = _draw_upload_feedback()
            if st.session_state.get("upload_polling", True) != still_indexing:
                st.session_state["upload_polling"] = still_indexing
                st.rerun()

        _upload_feedback()

    if "upload_widget_nonce" not in st.session_state:
        st.session_state.upload_widget_nonce = 0

    if st.session_state.get("upload_last_result"):
        picked_files = []
    else:
        st.markdown('<div class="up-panel-marker"></div>', unsafe_allow_html=True)
        picked_files = st.file_uploader(
            "Choose files",
            type=["pdf", "docx", "txt", "csv", "html"],
            accept_multiple_files=True,
            key=f"upload_view_files_{st.session_state.upload_widget_nonce}",
            label_visibility="collapsed",
            help="PDF, Word, TXT, CSV, or HTML",
        )
        st.markdown(
            '<p class="up-formats">PDF · Word · TXT · CSV · HTML</p>',
            unsafe_allow_html=True,
        )

    file_list = list(picked_files or [])
    if file_list:
        st.caption(f"{len(file_list)} file{'s' if len(file_list) != 1 else ''} selected")
        st.markdown('<div class="up-actions-marker"></div>', unsafe_allow_html=True)
        if st.button("Upload now", key="upload_submit", use_container_width=True, type="primary"):
            progress = st.progress(0, text="Starting upload…")
            successful = 0
            failed = 0
            uploaded_names = []
            try:
                if len(file_list) == 1:
                    uf = file_list[0]
                    progress.progress(35, text=f"Uploading {uf.name}…")
                    files = {"file": (uf.name, uf, _upload_mime(uf.name))}
                    upload_resp = requests.post(
                        f"{API_URL}/upload",
                        files=files,
                        headers=get_auth_headers(),
                        timeout=60,
                    )
                    progress.progress(85, text="Finishing…")
                    if upload_resp.status_code == 200:
                        successful = 1
                        uploaded_names = [uf.name]
                    else:
                        failed = 1
                        detail = upload_resp.text
                        try:
                            detail = upload_resp.json().get("detail", detail)
                        except Exception:
                            pass
                        st.error(f"Upload failed: {detail}")
                else:
                    files_data = []
                    for i, uf in enumerate(file_list):
                        progress.progress(
                            int(10 + (70 * i / max(len(file_list), 1))),
                            text=f"Preparing {uf.name}…",
                        )
                        files_data.append(("files", (uf.name, uf, _upload_mime(uf.name))))
                    progress.progress(80, text=f"Uploading {len(file_list)} files…")
                    upload_resp = requests.post(
                        f"{API_URL}/upload/bulk",
                        files=files_data,
                        headers=get_auth_headers(),
                        timeout=180,
                    )
                    if upload_resp.status_code == 200:
                        data = upload_resp.json()
                        successful = int(data.get("successful", 0) or 0)
                        failed = int(data.get("failed", 0) or 0)
                        results = data.get("results") or []
                        uploaded_names = [
                            r.get("filename")
                            for r in results
                            if r.get("status") == "success" and r.get("filename")
                        ] or [f.name for f in file_list]
                    else:
                        failed = len(file_list)
                        st.error(f"Bulk upload failed ({upload_resp.status_code})")

                progress.progress(100, text="Done")
                if successful > 0:
                    st.session_state["upload_last_result"] = {
                        "successful": successful,
                        "failed": failed,
                        "names": uploaded_names,
                    }
                    st.session_state["upload_polling"] = True
                    # Reset file uploader widget so files don't linger in the box
                    st.session_state["upload_widget_nonce"] = int(st.session_state.get("upload_widget_nonce", 0)) + 1
                    try:
                        status_resp = requests.get(f"{API_URL}/status", headers=get_auth_headers(), timeout=2)
                        if status_resp.status_code == 200:
                            st.session_state.kb_status = status_resp.json()
                    except Exception:
                        pass
                    st.rerun()
            except requests.exceptions.ConnectionError:
                st.error(get_api_connection_error_message())
            except Exception as e:
                st.error(str(e))
            finally:
                try:
                    progress.empty()
                except Exception:
                    pass

# History
if st.session_state.get("show_history", False):
    render_section_header(
        "History",
        "Questions you asked",
        "Ask one again, or remove it from this list.",
    )
    render_page_links(
        [("History", "history"), ("Saved questions", "saved_queries"), ("All chats", "conversations")],
        "from_history",
    )

    try:
        with st.spinner("Loading history..."):
            try:
                history_resp = requests.get(f"{API_URL}/history?limit=100", timeout=10)
            except requests.exceptions.ConnectionError:
                st.error("Cannot reach the API.")
                history_resp = None

        if history_resp and history_resp.status_code == 200:
            data = history_resp.json()
            history = data.get("history", [])
            total = int(data.get("total", 0) or 0)

            if total == 0:
                st.markdown(
                    '<p class="quiet-empty">No questions yet. Ask from Home and they will show up here.</p>',
                    unsafe_allow_html=True,
                )
            else:
                for idx, entry in enumerate(history):
                    query_text = entry.get("query") or "Unknown question"
                    timestamp = entry.get("timestamp") or ""
                    when = timestamp
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            when = dt.strftime("%b %d, %Y · %H:%M")
                        except Exception:
                            when = timestamp
                    st.markdown('<div class="quiet-row-marker"></div>', unsafe_allow_html=True)
                    col_body, col_ask, col_delete = st.columns([4.2, 1.05, 1.15], gap="small")
                    with col_body:
                        st.markdown(
                            f'<p class="lib-name">{html.escape(query_text)}</p>'
                            f'<p class="lib-meta">{html.escape(when)}</p>',
                            unsafe_allow_html=True,
                        )
                    with col_ask:
                        if st.button("Ask", key=f"use_history_{idx}", use_container_width=True):
                            st.session_state.example_query = entry.get("query", "")
                            st.session_state.show_history = False
                            st.rerun()
                    with col_delete:
                        if st.button("Delete", key=f"delete_history_{idx}", use_container_width=True):
                            try:
                                delete_resp = requests.delete(
                                    f"{API_URL}/history/{entry.get('timestamp', '')}",
                                    timeout=5,
                                )
                                if delete_resp.status_code == 200:
                                    st.toast("Removed from history")
                                    st.rerun()
                                else:
                                    st.error("Could not delete that question.")
                            except Exception as e:
                                st.error(str(e))
                st.markdown('<div class="quiet-row-marker"></div>', unsafe_allow_html=True)
                clear_col, _, _ = st.columns(3)
                with clear_col:
                    if st.button("Clear history", key="clear_all_history", use_container_width=True):
                        try:
                            clear_resp = requests.delete(f"{API_URL}/history", timeout=5)
                            if clear_resp.status_code == 200:
                                st.toast("History cleared")
                                st.rerun()
                            else:
                                st.error("Could not clear history.")
                        except Exception as e:
                            st.error(str(e))
        elif history_resp is not None:
            st.error("Could not load history.")
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the API.")
    except Exception as e:
        st.error(f"Could not load history: {e}")

# Saved questions
if st.session_state.get("show_saved_queries", False):
    render_section_header(
        "Saved questions",
        "Questions you kept",
        "Ask one again, or change its name.",
    )
    render_page_links(
        [("History", "history"), ("Saved questions", "saved_queries"), ("All chats", "conversations")],
        "from_saved",
    )

    try:
        with st.spinner("Loading saved questions..."):
            try:
                saved_resp = requests.get(f"{API_URL}/saved-queries", timeout=10)
            except requests.exceptions.ConnectionError:
                st.error("Cannot reach the API.")
                saved_resp = None
            except requests.exceptions.Timeout:
                st.error("The request timed out.")
                saved_resp = None

        if saved_resp and saved_resp.status_code == 200:
            data = saved_resp.json()
            saved_queries = data.get("saved_queries", [])
            total = int(data.get("total", 0) or 0)

            if total == 0:
                st.markdown(
                    '<p class="quiet-empty">No saved questions yet.</p>',
                    unsafe_allow_html=True,
                )
            else:
                import urllib.parse
                for idx, query in enumerate(saved_queries):
                    name = query.get("name") or query.get("query") or "Untitled"
                    desc = (query.get("description") or "").strip()
                    asked = query.get("query") or ""
                    usage = int(query.get("usage_count") or 0)
                    meta_bits = []
                    if asked and asked != name:
                        meta_bits.append(asked if len(asked) <= 80 else asked[:77] + "…")
                    if desc:
                        meta_bits.append(desc)
                    if usage > 0:
                        meta_bits.append(f"Asked {usage} time" + ("s" if usage != 1 else ""))
                    st.markdown('<div class="quiet-row-marker"></div>', unsafe_allow_html=True)
                    col_body, col_ask, col_edit, col_delete = st.columns([3.4, 0.9, 0.9, 1.05], gap="small")
                    with col_body:
                        st.markdown(
                            f'<p class="lib-name">{html.escape(str(name))}</p>'
                            f'<p class="lib-meta">{html.escape(" · ".join(meta_bits))}</p>',
                            unsafe_allow_html=True,
                        )
                    with col_ask:
                        if st.button("Ask", key=f"use_saved_{idx}", use_container_width=True):
                            try:
                                requests.post(
                                    f"{API_URL}/saved-queries/{urllib.parse.quote(query.get('query', ''))}/use",
                                    timeout=5,
                                )
                            except Exception:
                                pass
                            st.session_state.example_query = query.get("query", "")
                            st.session_state.show_saved_queries = False
                            st.rerun()
                    with col_edit:
                        if st.button("Edit", key=f"edit_saved_{idx}", use_container_width=True):
                            st.session_state[f"editing_query_{idx}"] = True
                            st.rerun()
                    with col_delete:
                        if st.button("Delete", key=f"delete_saved_{idx}", use_container_width=True):
                            try:
                                delete_resp = requests.delete(
                                    f"{API_URL}/saved-queries/{urllib.parse.quote(query.get('query', ''))}",
                                    timeout=5,
                                )
                                if delete_resp.status_code == 200:
                                    st.toast("Saved question removed")
                                    st.rerun()
                                else:
                                    st.error("Could not delete that question.")
                            except Exception as e:
                                st.error(str(e))

                    if st.session_state.get(f"editing_query_{idx}", False):
                        st.markdown('<div class="quiet-form-marker"></div>', unsafe_allow_html=True)
                        with st.form(f"edit_form_{idx}"):
                            new_name = st.text_input("Name", value=query.get("name", ""), key=f"name_{idx}")
                            new_desc = st.text_area("Description", value=query.get("description", ""), key=f"desc_{idx}")
                            col_submit, col_cancel = st.columns(2)
                            with col_submit:
                                save_edit = st.form_submit_button("Save", use_container_width=True)
                            with col_cancel:
                                cancel_edit = st.form_submit_button("Cancel", use_container_width=True)
                            if save_edit:
                                try:
                                    update_resp = requests.put(
                                        f"{API_URL}/saved-queries",
                                        json={
                                            "query": query.get("query", ""),
                                            "name": new_name,
                                            "description": new_desc,
                                        },
                                        timeout=5,
                                    )
                                    if update_resp.status_code == 200:
                                        st.session_state[f"editing_query_{idx}"] = False
                                        st.toast("Saved question updated")
                                        st.rerun()
                                    else:
                                        st.error("Could not update that question.")
                                except Exception as e:
                                    st.error(str(e))
                            if cancel_edit:
                                st.session_state[f"editing_query_{idx}"] = False
                                st.rerun()
        elif saved_resp is not None:
            st.error("Could not load saved questions.")
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the API.")
    except Exception as e:
        st.error(f"Could not load saved questions: {e}")

# Conversations Dashboard
if st.session_state.get("show_conversations", False):
    st.markdown("---")
    render_page_links(
        [("History", "history"), ("Saved questions", "saved_queries"), ("All chats", "conversations")],
        "from_chats",
    )
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
                                try:
                                    conv_detail = requests.get(
                                        f"{API_URL}/conversations/{conv.get('id')}",
                                        timeout=5
                                    ).json()
                                    st.session_state.chat_history = _messages_to_chat_history(
                                        conv_detail.get("messages", [])
                                    )
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
    render_page_links(
        [("Users", "user_management"), ("Backup", "export_backup"), ("Metrics", "health")],
        "from_health",
    )
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

# Users (admin)
if st.session_state.get("show_user_management", False):
    if st.session_state.current_user and st.session_state.current_user.get("role") == "admin":
        render_section_header(
            "Users",
            "Accounts",
            "Change a role, turn an account off, or unlock a sign-in.",
        )
        render_page_links(
            [("Users", "user_management"), ("Backup", "export_backup"), ("Metrics", "health")],
            "from_users",
        )

        try:
            with st.spinner("Loading users..."):
                headers = get_auth_headers()
                users_resp = requests.get(f"{API_URL}/auth/users", headers=headers, timeout=10)

            if users_resp.status_code == 200:
                data = users_resp.json()
                users = data.get("users", [])
                if not users:
                    st.markdown(
                        '<p class="quiet-empty">No accounts yet.</p>',
                        unsafe_allow_html=True,
                    )
                else:
                    for idx, user in enumerate(users):
                        name = user.get("display_name") or user.get("first_name") or user.get("username") or "Unknown"
                        email = user.get("email") or ""
                        role_label = "Admin" if user.get("role") == "admin" else "User"
                        status_label = "Active" if user.get("active", True) else "Inactive"
                        meta_bits = [email, role_label, status_label]
                        if user.get("locked"):
                            meta_bits.append("Locked")
                            unlock_raw = user.get("unlock_time")
                            if unlock_raw:
                                try:
                                    unlock_dt = datetime.fromisoformat(unlock_raw)
                                    if unlock_dt > datetime.now():
                                        mins = int((unlock_dt - datetime.now()).total_seconds() / 60)
                                        meta_bits.append(f"Unlocks in {mins} min")
                                except Exception:
                                    pass
                        elif int(user.get("failed_attempts") or 0) > 0:
                            meta_bits.append(f"{int(user.get('failed_attempts') or 0)} failed sign-ins")
                        if user.get("last_login"):
                            meta_bits.append(f"Last sign-in {str(user.get('last_login'))[:10]}")
                        elif user.get("created_at"):
                            meta_bits.append(f"Joined {str(user.get('created_at'))[:10]}")

                        st.markdown('<div class="quiet-row-marker"></div>', unsafe_allow_html=True)
                        col_body, col_role, col_active, col_unlock = st.columns([3.2, 1.35, 1.25, 1.15], gap="small")
                        with col_body:
                            st.markdown(
                                f'<p class="lib-name">{html.escape(str(name))}</p>'
                                f'<p class="lib-meta">{html.escape(" · ".join(bit for bit in meta_bits if bit))}</p>',
                                unsafe_allow_html=True,
                            )
                        with col_role:
                            can_change_role = (
                                user.get("role") != "admin"
                                or user.get("id") != st.session_state.current_user.get("id")
                            )
                            if can_change_role:
                                new_role = "admin" if user.get("role") == "user" else "user"
                                role_label_btn = "Make admin" if new_role == "admin" else "Make user"
                                if st.button(role_label_btn, key=f"role_{idx}", use_container_width=True):
                                    try:
                                        headers = get_auth_headers()
                                        resp = requests.put(
                                            f"{API_URL}/auth/users/{user.get('id')}/role",
                                            json={"user_id": user.get("id"), "role": new_role},
                                            headers=headers,
                                            timeout=5,
                                        )
                                        if resp.status_code == 200:
                                            st.toast("Role updated")
                                            st.rerun()
                                        else:
                                            st.error(resp.json().get("detail", "Could not change that role."))
                                    except Exception as e:
                                        st.error(str(e))
                        with col_active:
                            if user.get("active", True):
                                if st.button("Deactivate", key=f"deactivate_{idx}", use_container_width=True):
                                    try:
                                        headers = get_auth_headers()
                                        resp = requests.post(
                                            f"{API_URL}/auth/users/{user.get('id')}/deactivate",
                                            headers=headers,
                                            timeout=5,
                                        )
                                        if resp.status_code == 200:
                                            st.toast("Account deactivated")
                                            st.rerun()
                                        else:
                                            st.error(resp.json().get("detail", "Could not deactivate that account."))
                                    except Exception as e:
                                        st.error(str(e))
                            elif st.button("Activate", key=f"activate_{idx}", use_container_width=True):
                                try:
                                    headers = get_auth_headers()
                                    resp = requests.post(
                                        f"{API_URL}/auth/users/{user.get('id')}/activate",
                                        headers=headers,
                                        timeout=5,
                                    )
                                    if resp.status_code == 200:
                                        st.toast("Account activated")
                                        st.rerun()
                                    else:
                                        st.error(resp.json().get("detail", "Could not activate that account."))
                                except Exception as e:
                                    st.error(str(e))
                        with col_unlock:
                            if user.get("locked") and st.button("Unlock", key=f"unlock_{idx}", use_container_width=True):
                                try:
                                    headers = get_auth_headers()
                                    resp = requests.post(
                                        f"{API_URL}/auth/users/{user.get('id')}/unlock",
                                        headers=headers,
                                        timeout=5,
                                    )
                                    if resp.status_code == 200:
                                        st.toast("Account unlocked")
                                        st.rerun()
                                    else:
                                        st.error(resp.json().get("detail", "Could not unlock that account."))
                                except Exception as e:
                                    st.error(str(e))
            else:
                st.error("Could not load accounts.")
        except requests.exceptions.ConnectionError:
            st.error("Cannot reach the API.")
        except Exception as e:
            st.error(f"Could not load accounts: {e}")
    else:
        render_section_header("Users", "Accounts", "Only an admin can open this page.")

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
        render_page_links(
            [("Users", "user_management"), ("Backup", "export_backup"), ("Metrics", "health")],
            "from_backup",
        )
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

# Zone-based layout: center (chat) when on chat view
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

# Centered chat column — no side source panel (sources live under each answer)
if use_zone_layout:
    col_left, col_chat, col_right = st.columns([1, 3, 1], gap="large")
else:
    col_chat = st.container()

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

        pending = kb_stats.get("pending_count", 0)
        if doc_count == 0:
            if pending:
                empty_title = "Documents are still processing"
                empty_body = f"{pending} file(s) are indexing. This usually takes a few seconds — then you can ask questions."
                st.markdown(
                    f"""
                    <div class="kh-empty">
                        <h3>{html.escape(empty_title)}</h3>
                        <p>{html.escape(empty_body)}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Refresh status", key="kh_refresh_pending", use_container_width=True):
                    st.rerun()
            else:
                st.markdown(
                    """
                    <div class="kh-empty">
                        <h3>Get started in 3 steps</h3>
                        <p>Upload → wait for Ready → ask your first question. No dead ends.</p>
                    </div>
                    <div class="kh-steps">
                        <div class="kh-step"><div class="kh-step-num">1</div><div><strong>Upload a document</strong><span>PDF, Word, text, CSV, or HTML</span></div></div>
                        <div class="kh-step"><div class="kh-step-num">2</div><div><strong>Wait for Ready</strong><span>Indexing usually finishes in a few seconds</span></div></div>
                        <div class="kh-step"><div class="kh-step-num">3</div><div><strong>Ask a question</strong><span>Answers cite the exact section they came from</span></div></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
# Handle example query (from history / saved queries) - only overwrite if we have one
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


def _answer_meta_flags(meta: dict, sources: list, message: str = "") -> dict:
    """Derive confidence / not-in-docs signals for an assistant message."""
    meta = meta if isinstance(meta, dict) else {}
    confidence = meta.get("confidence") if isinstance(meta.get("confidence"), dict) else {}
    verification = meta.get("verification") if isinstance(meta.get("verification"), dict) else {}
    factors = confidence.get("factors") if isinstance(confidence.get("factors"), dict) else {}
    level = (confidence.get("level") or "").lower()
    score = confidence.get("confidence")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    source_list = sources if isinstance(sources, list) else []
    ver_status = (verification.get("status") or "").lower()
    text = (message or "").lower()
    not_in_docs = (
        bool(factors.get("not_in_documents"))
        or ver_status == "unsupported"
        or "couldn't find that in your documents" in text
        or "could not find that in your documents" in text
    )
    return {
        "level": level or "unknown",
        "score": score_f,
        "not_in_docs": not_in_docs,
        "verification": verification,
        "source_names": [
            (s.get("source") if isinstance(s, dict) else str(s))
            for s in source_list
            if (s.get("source") if isinstance(s, dict) else s)
        ],
    }


def render_assistant_message_block(
    message_idx: int,
    message: str,
    msg_time: str,
    sources: list,
    user_query: str,
    message_key: str,
    meta: dict = None,
):
    """Render one answer card: the answer, one confidence line, and collapsed sources."""
    _display_msg = str(message).strip()
    safe_message = html.escape(_display_msg).replace("\n", "<br/>")
    if _display_msg.strip().startswith("<"):
        safe_message = "An error occurred while displaying the response. Please try again."

    source_list = sources if isinstance(sources, list) else []
    flags = _answer_meta_flags(meta or {}, source_list, _display_msg)

    if flags["not_in_docs"]:
        confidence_html = '<div class="answer-confidence very_low">Not in your documents</div>'
    elif flags["level"] and flags["level"] != "unknown":
        level_label = flags["level"].replace("_", " ").title()
        confidence_html = (
            f'<div class="answer-confidence {html.escape(flags["level"])}">'
            f'Confidence: {html.escape(level_label)}</div>'
        )
    else:
        confidence_html = ""

    sources_html = ""
    if source_list:
        chips = []
        for source in source_list:
            name = source.get("source", "Unknown") if isinstance(source, dict) else str(source)
            rel = source.get("relevance", 0) if isinstance(source, dict) else 0
            try:
                rel = float(rel or 0)
            except (TypeError, ValueError):
                rel = 0
            rel_label = "High" if rel >= 0.7 else ("Medium" if rel >= 0.4 else "Low")
            chips.append(
                f'<span class="source-chip">{html.escape(str(name))} <em>{rel_label}</em></span>'
            )
        count = len(source_list)
        label = f"{count} source" + ("s" if count != 1 else "")
        sources_html = (
            f'<details class="answer-sources"><summary>{label}</summary>'
            f'<div class="sources-block">{"".join(chips)}</div></details>'
        )

    meta_html = ""
    if confidence_html or sources_html:
        meta_html = f'<div class="answer-meta">{confidence_html}{sources_html}</div>'

    st.markdown(
        f'<article class="msg msg-assistant answer-card" id="answer_{message_idx}">'
        f'<div class="msg-body">{safe_message}</div>'
        f'{meta_html}</article>',
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
            # Formats: (role, msg, time) | (+ sources) | (+ sources, meta)
            meta = {}
            if len(item) >= 5:
                role, message, msg_time, sources, meta = item[:5]
            elif len(item) == 4:
                role, message, msg_time, sources = item
            else:
                role, message, msg_time = item[:3]
                sources = []

            prev_user_query = ""
            if idx > 0 and len(items_to_show[idx - 1]) >= 2 and items_to_show[idx - 1][0] == "user":
                prev_user_query = items_to_show[idx - 1][1]
            if role == "user":
                render_user_message_block(idx, message, msg_time)
                continue
            msg_key = build_assistant_message_key(str(msg_time), str(message))
            render_assistant_message_block(
                idx, message, msg_time, sources, prev_user_query, msg_key, meta=meta
            )
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
                    if st.session_state.current_conversation_id:
                        payload["conversation_id"] = st.session_state.current_conversation_id
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
                    answer_meta = {}
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
                                                    if data.get("confidence"):
                                                        answer_meta["confidence"] = data.get("confidence")
                                                    if data.get("verification"):
                                                        answer_meta["verification"] = data.get("verification")
                                                    if "sources" in data:
                                                        sources = data.get("sources") or []
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
                                            answer_meta = {
                                                "confidence": rd.get("confidence"),
                                                "verification": rd.get("verification"),
                                            }
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
                                        answer_meta = {
                                            "confidence": rd.get("confidence"),
                                            "verification": rd.get("verification"),
                                        }
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
                                answer_meta = {
                                    "confidence": rd.get("confidence"),
                                    "verification": rd.get("verification"),
                                }
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
                    st.session_state.chat_history.append(
                        ("assistant", answer_text, answer_timestamp, sources, answer_meta)
                    )
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
                answer = ""
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
                                answer_meta = {
                                    "confidence": response_data.get("confidence"),
                                    "verification": response_data.get("verification"),
                                }
                                answer_timestamp = datetime.now().strftime("%H:%M")
                                
                                # Validate response before storing
                                if not answer or not answer.strip():
                                    answer = "⚠️ No response received. Please try again."
                                # Keep model output unchanged; only handle true transport/execution errors.
                                if answer.strip().startswith("<div") or answer.strip().startswith("<span"):
                                    logger.warning(f"Detected HTML in response: {answer[:100]}")
                                    answer = "⚠️ An error occurred while processing the response. Please try again."
                                
                                st.session_state.chat_history.append(
                                    ("assistant", answer, answer_timestamp, sources, answer_meta)
                                )
                                logger.info(f"Response time: {elapsed_time:.2f}s, Sources: {len(sources)}")
                            else:
                                error_msg = f"⚠️ Error {response.status_code}: {response.text}"
                                st.session_state.chat_history.append(("assistant", error_msg, timestamp, [], {}))
                        except requests.exceptions.ConnectionError:
                            error_msg = "Cannot connect to API. Please ensure the server is running."
                            st.session_state.chat_history.append(("assistant", f"❌ {error_msg}", timestamp, [], {}))
                            log_error_to_console(error_msg, "ConnectionError")
                        except requests.exceptions.Timeout:
                            error_msg = "Request timed out. The query may be taking longer than expected. Please try again or simplify your query."
                            st.session_state.chat_history.append(("assistant", f"⏱️ {error_msg}", timestamp, [], {}))
                            log_error_to_console(error_msg, "Timeout")
                            st.info("💡 **Tip:** Complex queries or large knowledge bases may take longer. Try breaking down your question into smaller parts.")
                        except Exception as e:
                            error_msg = f"Unexpected error: {str(e)}"
                            st.session_state.chat_history.append(("assistant", f"❌ {error_msg}", timestamp, [], {}))
                            log_error_to_console(error_msg, "Exception", e)

                        # Mark as processed only when we actually got a non-echo answer.
                        normalized_answer = _normalize_for_compare(answer)
                        if normalized_answer and normalized_answer != normalized_query:
                            st.session_state._last_processed_query = query.strip()
        st.rerun()

