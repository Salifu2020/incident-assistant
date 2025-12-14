import os
import streamlit as st
import requests
import logging
from datetime import datetime
import time
import json

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

# Copilot-style UI Design
st.markdown(
    """
    <style>
    /* Global Styles - Copilot Theme */
    * {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
    }
    
    /* Main container - Dark theme */
    .main {
        padding: 0;
        background: #0f172a;
        color: #e2e8f0;
    }
    
    /* Header - Dark theme */
    .header-container {
        text-align: left;
        padding: 1.5rem 2rem;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-bottom: 1px solid #334155;
        margin-bottom: 0;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    
    .header-title {
        font-size: 1.75rem;
        font-weight: 600;
        color: #f1f5f9;
        margin: 0;
        letter-spacing: -0.01em;
    }
    
    .header-subtitle {
        font-size: 0.875rem;
        color: #94a3b8;
        margin-top: 0.25rem;
        font-weight: 400;
    }
    
    /* Copilot-style Chat Interface */
    .chat-container {
        margin-bottom: 0;
        padding: 1rem 0;
    }
    
    .message-user {
        background: #2563eb;
        color: white;
        padding: 0.875rem 1.125rem;
        border-radius: 18px 18px 4px 18px;
        margin-left: 20%;
        margin-bottom: 1rem;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        word-wrap: break-word;
        font-size: 0.9375rem;
        line-height: 1.5;
        max-width: 75%;
    }
    
    .message-bot {
        background: #1e293b;
        color: #e2e8f0;
        padding: 0.875rem 1.125rem;
        border-radius: 18px 18px 18px 4px;
        margin-right: 20%;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        border: 1px solid #334155;
        word-wrap: break-word;
        font-size: 0.9375rem;
        line-height: 1.6;
        max-width: 75%;
    }
    
    .message-time {
        font-size: 0.75rem;
        color: #9ca3af;
        margin-top: 0.5rem;
        font-weight: 400;
    }
    
    /* Buttons - Dark theme */
    .stButton>button {
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.15s ease;
        border: 1px solid #475569;
        background: #1e293b;
        color: #e2e8f0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    }
    
    .stButton>button:hover {
        background: #334155;
        border-color: #64748b;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        transform: translateY(-1px);
    }
    
    button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        color: white !important;
        border-color: #3b82f6 !important;
    }
    
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        border-color: #2563eb !important;
    }
    
    /* Input Fields - Dark theme */
    .stTextInput>div>div>input,
    .stTextArea>div>div>textarea {
        border-radius: 8px;
        padding: 0.75rem 1rem;
        border: 1px solid #475569;
        transition: all 0.15s ease;
        font-size: 0.9375rem;
        background: #1e293b;
        color: #e2e8f0;
    }
    
    .stTextInput>div>div>input:focus,
    .stTextArea>div>div>textarea:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
        outline: none;
        background: #1e293b;
    }
    
    /* Select boxes */
    .stSelectbox>div>div>select {
        border-radius: 8px;
        padding: 0.625rem 0.875rem;
        border: 1px solid #d1d5db;
        transition: all 0.15s ease;
        font-size: 0.9375rem;
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
    
    /* Example questions - Dark theme */
    .example-question {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: all 0.15s ease;
        font-size: 0.875rem;
        color: #e2e8f0;
    }
    
    .example-question:hover {
        border-color: #3b82f6;
        background: #1e3a8a;
        color: #f1f5f9;
        transform: translateX(4px);
    }
    
    /* Sidebar - Dark theme */
    [data-testid="stSidebar"] {
        background: #1e293b;
        border-right: 1px solid #334155;
    }
    
    [data-testid="stSidebar"] .stButton>button {
        width: 100%;
        margin-bottom: 0.375rem;
        border-radius: 8px;
        background: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        text-align: left;
        padding-left: 0.875rem;
        font-size: 0.875rem;
    }
    
    [data-testid="stSidebar"] .stButton>button:hover {
        background: #334155;
        border-color: #475569;
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
    
    /* Hide Streamlit default elements */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    
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
    
    /* Container padding */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 1200px;
        background: #0f172a;
    }
    
    /* Text colors */
    h1, h2, h3, h4, h5, h6 {
        color: #f1f5f9;
    }
    
    p, span, div {
        color: #e2e8f0;
    }
    
    /* Streamlit chat input */
    [data-testid="stChatInputContainer"] {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
    }
    
    [data-testid="stChatInputContainer"] input {
        background: #1e293b !important;
        color: #e2e8f0 !important;
    }
    
    /* Selectbox dropdown */
    .stSelectbox>div>div>div {
        background: #1e293b;
        color: #e2e8f0;
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
if "selected_documents" not in st.session_state:
    st.session_state.selected_documents = []  # List of document filenames to filter by
if "show_advanced_filters" not in st.session_state:
    st.session_state.show_advanced_filters = False
if "advanced_filters" not in st.session_state:
    st.session_state.advanced_filters = {}
if "enable_streaming" not in st.session_state:
    st.session_state.enable_streaming = True  # Enable streaming by default
if "current_conversation_id" not in st.session_state:
    st.session_state.current_conversation_id = None
if "conversations" not in st.session_state:
    st.session_state.conversations = []
if "show_health" not in st.session_state:
    st.session_state.show_health = False
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
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
if "pending_2fa_username" not in st.session_state:
    st.session_state.pending_2fa_username = None
if "2fa_setup_data" not in st.session_state:
    st.session_state["2fa_setup_data"] = None

MAX_HISTORY = 50

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
    # Check for reset token in query parameters (for email links)
    query_params = st.query_params
    reset_token_from_url = query_params.get("reset_token", None)
    if reset_token_from_url and not st.session_state.password_reset_token:
        st.session_state.password_reset_token = reset_token_from_url
        st.session_state.show_password_reset = True
        # Verify token to get email
        try:
            verify_resp = requests.post(
                f"{API_URL}/auth/password-reset/verify",
                json={"token": reset_token_from_url},
                timeout=5
            )
            if verify_resp.status_code == 200:
                verify_data = verify_resp.json()
                st.session_state.password_reset_email = verify_data.get("email")
        except:
            pass  # Will show error in form
    
    st.title("🔐 Authentication Required")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.markdown("### Login")
        
        # Password reset link
        if st.session_state.show_password_reset:
            st.markdown("---")
            st.markdown("### 🔑 Password Reset")
            
            if st.session_state.password_reset_token:
                # Step 2: Reset password with token
                st.info(f"📧 Reset token received for: {st.session_state.password_reset_email}")
                st.warning("⚠️ **Development Mode:** In production, this token would be sent via email.")
                
                with st.form("reset_password_form"):
                    st.text_input("Reset Token", value=st.session_state.password_reset_token, disabled=True, key="display_token")
                    
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
                    
                    new_password = st.text_input("New Password", type="password", key="reset_new_password", help="See password requirements above")
                    confirm_password = st.text_input("Confirm New Password", type="password", key="reset_confirm_password")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        submit_reset = st.form_submit_button("✅ Reset Password", use_container_width=True)
                    with col2:
                        cancel_reset = st.form_submit_button("❌ Cancel", use_container_width=True)
                    
                    if cancel_reset:
                        st.session_state.show_password_reset = False
                        st.session_state.password_reset_token = None
                        st.session_state.password_reset_email = None
                        st.rerun()
                    
                    if submit_reset:
                        if not new_password or not confirm_password:
                            st.error("❌ Please fill in all fields")
                        elif new_password != confirm_password:
                            st.error("❌ Passwords do not match")
                        elif len(new_password) < 6:
                            st.error("❌ Password must be at least 6 characters long")
                        else:
                            try:
                                response = requests.post(
                                    f"{API_URL}/auth/password-reset/confirm",
                                    json={
                                        "token": st.session_state.password_reset_token,
                                        "new_password": new_password
                                    },
                                    timeout=10
                                )
                                if response.status_code == 200:
                                    st.success("✅ Password reset successful! You can now login with your new password.")
                                    st.session_state.show_password_reset = False
                                    st.session_state.password_reset_token = None
                                    st.session_state.password_reset_email = None
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    error_detail = response.json().get('detail', 'Unknown error')
                                    st.error(f"❌ Password reset failed: {error_detail}")
                            except requests.exceptions.ConnectionError:
                                st.error("❌ Cannot connect to API. Please ensure the server is running.")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
            else:
                # Step 1: Request password reset
                with st.form("request_reset_form"):
                    reset_email = st.text_input("Email Address", key="reset_email")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        submit_request = st.form_submit_button("📧 Send Reset Link", use_container_width=True)
                    with col2:
                        cancel_request = st.form_submit_button("❌ Cancel", use_container_width=True)
                    
                    if cancel_request:
                        st.session_state.show_password_reset = False
                        st.rerun()
                    
                    if submit_request:
                        if not reset_email:
                            st.error("❌ Please enter your email address")
                        else:
                            try:
                                response = requests.post(
                                    f"{API_URL}/auth/password-reset/request",
                                    json={"email": reset_email},
                                    timeout=10
                                )
                                if response.status_code == 200:
                                    data = response.json()
                                    st.success("✅ " + data.get("message", "Reset link sent"))
                                    
                                    # In development, show the token
                                    if data.get("token"):
                                        st.session_state.password_reset_token = data.get("token")
                                        st.session_state.password_reset_email = reset_email
                                        st.info("🔑 **Development Mode:** Your reset token is shown below. In production, this would be sent via email.")
                                        st.rerun()
                                else:
                                    error_detail = response.json().get('detail', 'Unknown error')
                                    st.error(f"❌ Request failed: {error_detail}")
                            except requests.exceptions.ConnectionError:
                                st.error("❌ Cannot connect to API. Please ensure the server is running.")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
            
            st.markdown("---")
        else:
            # Normal login form
            # Forgot password link (outside form)
            if st.button("🔑 Forgot Password?", use_container_width=True, key="forgot_password_btn"):
                st.session_state.show_password_reset = True
                st.rerun()
            
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                
                submit = st.form_submit_button("Login", use_container_width=True)
                
                if submit:
                    if username and password:
                        try:
                            response = requests.post(
                                f"{API_URL}/auth/login",
                                json={"username": username, "password": password},
                                timeout=5
                            )
                            if response.status_code == 200:
                                data = response.json()
                                
                                # Check if 2FA is required
                                if data.get("requires_2fa", False):
                                    st.session_state.pending_2fa_username = username
                                    st.info("🔐 Two-Factor Authentication required. Please enter your 2FA code.")
                                    st.rerun()
                                else:
                                    st.session_state.authenticated = True
                                    st.session_state.access_token = data["access_token"]
                                    if "refresh_token" in data:
                                        st.session_state.refresh_token = data["refresh_token"]
                                    if "session_id" in data:
                                        st.session_state.session_id = data["session_id"]
                                    st.session_state.current_user = data["user"]
                                    # Store token in query params for persistence across page refreshes
                                    st.query_params.token = data["access_token"]
                                    st.success("✅ Login successful!")
                                    st.rerun()
                            elif response.status_code == 423:  # Locked
                                error_detail = response.json().get('detail', 'Account is locked')
                                st.error(f"🔒 {error_detail}")
                                st.warning("💡 Contact an administrator to unlock your account, or wait for the lockout period to expire.")
                            else:
                                error_detail = response.json().get('detail', 'Unknown error')
                                st.error(f"❌ {error_detail}")
                                # Show attempts remaining if mentioned in error
                                if "attempt" in error_detail.lower() and "remaining" in error_detail.lower():
                                    st.warning("⚠️ Too many failed attempts will lock your account.")
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Cannot connect to API. Please ensure the server is running.")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("⚠️ Please enter both username and password")
        
        # 2FA verification form (shown when 2FA is required)
        if st.session_state.pending_2fa_username:
            st.markdown("---")
            st.markdown("### 🔐 Two-Factor Authentication")
            st.info(f"Please enter the 6-digit code from your authenticator app for user: **{st.session_state.pending_2fa_username}**")
            
            with st.form("2fa_verify_form"):
                twofa_code = st.text_input("2FA Code", key="2fa_code", help="Enter 6-digit code from your authenticator app or a backup code")
                submit_2fa = st.form_submit_button("Verify", use_container_width=True)
                
                if submit_2fa:
                    if twofa_code:
                        try:
                            response = requests.post(
                                f"{API_URL}/auth/2fa/verify-login",
                                json={"code": twofa_code},
                                params={"username": st.session_state.pending_2fa_username},
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
                                st.session_state.pending_2fa_username = None
                                # Store token in query params for persistence
                                st.query_params.token = data["access_token"]
                                st.success("✅ Login successful!")
                                st.rerun()
                            else:
                                error_detail = response.json().get('detail', 'Invalid 2FA code')
                                st.error(f"❌ {error_detail}")
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Cannot connect to API. Please ensure the server is running.")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                    else:
                        st.warning("⚠️ Please enter your 2FA code")
            
            if st.button("❌ Cancel", key="cancel_2fa"):
                st.session_state.pending_2fa_username = None
                st.rerun()
    
    with tab2:
        st.markdown("### Register")
        
        # Dynamic password requirements with real-time validation
        st.markdown("""
        <div id="password-requirements-reg" style="margin-bottom: 1rem; padding: 0.75rem; background: #1e293b; border-radius: 8px; border: 1px solid #334155;">
            <div style="font-weight: 600; margin-bottom: 0.75rem; color: #e2e8f0;">📋 Password Requirements:</div>
            <div id="req-list-reg" style="font-size: 0.875rem;">
                <div id="req-length-reg" style="margin: 0.375rem 0; color: #94a3b8; transition: color 0.2s;">❌ Minimum length: 8 characters</div>
                <div id="req-upper-reg" style="margin: 0.375rem 0; color: #94a3b8; transition: color 0.2s;">❌ At least one uppercase letter (A-Z)</div>
                <div id="req-lower-reg" style="margin: 0.375rem 0; color: #94a3b8; transition: color 0.2s;">❌ At least one lowercase letter (a-z)</div>
                <div id="req-number-reg" style="margin: 0.375rem 0; color: #94a3b8; transition: color 0.2s;">❌ At least one number (0-9)</div>
                <div id="req-special-reg" style="margin: 0.375rem 0; color: #94a3b8; transition: color 0.2s;">❌ At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)</div>
            </div>
        </div>
        <script>
        (function() {
            function checkPasswordRequirements(password) {
                const requirements = {
                    length: password.length >= 8,
                    upper: /[A-Z]/.test(password),
                    lower: /[a-z]/.test(password),
                    number: /[0-9]/.test(password),
                    special: /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)
                };
                
                // Update UI
                const updateReq = (id, met, text) => {
                    const el = document.getElementById(id);
                    if (el) {
                        if (met) {
                            el.innerHTML = '✅ ' + text;
                            el.style.color = '#10b981';
                        } else {
                            el.innerHTML = '❌ ' + text;
                            el.style.color = '#94a3b8';
                        }
                    }
                };
                
                updateReq('req-length-reg', requirements.length, 'Minimum length: 8 characters');
                updateReq('req-upper-reg', requirements.upper, 'At least one uppercase letter (A-Z)');
                updateReq('req-lower-reg', requirements.lower, 'At least one lowercase letter (a-z)');
                updateReq('req-number-reg', requirements.number, 'At least one number (0-9)');
                updateReq('req-special-reg', requirements.special, 'At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)');
            }
            
            // Monitor password input - find by label text
            function setupPasswordValidation() {
                const inputs = document.querySelectorAll('input[type="password"]');
                
                // Find the password input (not the confirm password)
                // In Streamlit, inputs are in forms, and we can find by looking for the one before "Confirm Password"
                let passwordInput = null;
                
                // Method 1: Find by looking for label containing "Password" but not "Confirm"
                const allLabels = document.querySelectorAll('label, [data-testid*="stTextInput"]');
                for (let label of allLabels) {
                    const text = label.textContent || '';
                    if (text.includes('Password') && !text.includes('Confirm')) {
                        // Find the input near this label
                        const form = label.closest('form') || label.closest('[data-testid*="stForm"]');
                        if (form) {
                            const formInputs = form.querySelectorAll('input[type="password"]');
                            if (formInputs.length > 0) {
                                passwordInput = formInputs[0];
                                break;
                            }
                        }
                    }
                }
                
                // Method 2: If in register form, use first password input
                if (!passwordInput) {
                    const registerForm = document.querySelector('form');
                    if (registerForm) {
                        const formInputs = registerForm.querySelectorAll('input[type="password"]');
                        if (formInputs.length >= 1) {
                            passwordInput = formInputs[0];
                        }
                    }
                }
                
                if (passwordInput) {
                    // Store original value to detect changes
                    let lastValue = passwordInput.value || '';
                    
                    const checkAndUpdate = function() {
                        const currentValue = passwordInput.value || '';
                        if (currentValue !== lastValue) {
                            lastValue = currentValue;
                            checkPasswordRequirements(currentValue);
                        }
                    };
                    
                    // Add event listeners
                    passwordInput.addEventListener('input', checkAndUpdate);
                    passwordInput.addEventListener('keyup', checkAndUpdate);
                    passwordInput.addEventListener('change', checkAndUpdate);
                    
                    // Check initial value
                    checkAndUpdate();
                } else {
                    // Retry after a delay if inputs aren't ready yet
                    setTimeout(setupPasswordValidation, 300);
                }
            }
            
            // Run after page load
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', function() {
                    setTimeout(setupPasswordValidation, 300);
                });
            } else {
                setTimeout(setupPasswordValidation, 300);
            }
            
            // Also monitor for Streamlit reruns
            const observer = new MutationObserver(function(mutations) {
                let shouldCheck = false;
                mutations.forEach(function(mutation) {
                    if (mutation.addedNodes.length > 0) {
                        shouldCheck = true;
                    }
                });
                if (shouldCheck) {
                    setTimeout(setupPasswordValidation, 100);
                }
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        })();
        </script>
        """, unsafe_allow_html=True)
        
        with st.form("register_form"):
            reg_username = st.text_input("Username", key="reg_username")
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password", help="See password requirements above")
            reg_password_confirm = st.text_input("Confirm Password", type="password", key="reg_password_confirm")
            reg_role = st.selectbox("Role", ["user", "admin"], key="reg_role", help="Note: Admin role creation may be restricted")
            submit_reg = st.form_submit_button("Register", use_container_width=True)
            
            if submit_reg:
                if reg_username and reg_email and reg_password:
                    if reg_password != reg_password_confirm:
                        st.error("❌ Passwords do not match")
                    else:
                        try:
                            response = requests.post(
                                f"{API_URL}/auth/register",
                                json={
                                    "username": reg_username,
                                    "email": reg_email,
                                    "password": reg_password,
                                    "role": reg_role
                                },
                                timeout=5
                            )
                            if response.status_code == 200:
                                st.success("✅ Registration successful! Please login.")
                                st.info("💡 Default admin credentials: username: admin, password: admin123")
                            else:
                                st.error(f"❌ Registration failed: {response.json().get('detail', 'Unknown error')}")
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Cannot connect to API. Please ensure the server is running.")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("⚠️ Please fill in all fields")
    
    st.info("💡 **Default Admin Credentials:** username: `admin`, password: `admin123`")
    st.stop()

# Main app (only shown if authenticated)
# Simplified Sidebar
with st.sidebar:
    # User info and logout
    if st.session_state.current_user:
        user = st.session_state.current_user
        role_badge = "👑 Admin" if user.get("role") == "admin" else "👤 User"
        st.markdown(f"### {user.get('username', 'User')}")
        st.caption(f"{role_badge}")
        
        if st.button("🚪 Logout", use_container_width=True):
            # Clear session state
            st.session_state.authenticated = False
            st.session_state.access_token = None
            st.session_state.current_user = None
            st.session_state.chat_history = []
            # Clear token from query params
            st.query_params.clear()
            st.rerun()
        
        st.markdown("---")
    
    # Quick Status (compact)
    if st.session_state.api_status:
        status_class = "status-online" if st.session_state.api_status == "online" else "status-offline"
        status_text = "🟢 Online" if st.session_state.api_status == "online" else "🔴 Offline"
        st.markdown(f'<div class="status-badge {status_class}">{status_text}</div>', unsafe_allow_html=True)
    
    if st.session_state.kb_status is not None:
        kb_data = st.session_state.kb_status
        if isinstance(kb_data, dict):
            chunk_count = kb_data.get("knowledge_base_chunks", 0)
            doc_count = kb_data.get("document_count", 0)
            if chunk_count > 0:
                st.caption(f"📚 {chunk_count} chunks • {doc_count} docs")
        else:
            chunk_count = kb_data if isinstance(kb_data, int) else 0
            if chunk_count > 0:
                st.caption(f"📚 {chunk_count} chunks")
    
    st.markdown("---")
    
    # Main Actions (most used)
    if st.button("📚 Documents", use_container_width=True):
        st.session_state.show_documents = True
        st.rerun()
    
    if st.button("💬 New Chat", use_container_width=True):
        try:
            resp = requests.post(f"{API_URL}/conversations", json={}, timeout=5)
            if resp.status_code == 200:
                conv = resp.json()
                st.session_state.current_conversation_id = conv.get("id")
                st.session_state.chat_history = []
                st.rerun()
        except:
            pass
    
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.chat_history = []
        if st.session_state.current_conversation_id:
            try:
                requests.post(f"{API_URL}/conversations/{st.session_state.current_conversation_id}/clear", timeout=5)
            except:
                pass
        st.rerun()
    
    st.markdown("---")
    
    # More Options (collapsible)
    with st.expander("⚙️ More Options", expanded=False):
        # Account Settings
        if st.session_state.current_user:
            if st.button("👤 Profile", use_container_width=True):
                st.session_state.show_profile = True
                st.rerun()
            
            if st.button("🔑 Change Password", use_container_width=True):
                st.session_state.show_change_password = True
                st.rerun()
            
            if st.button("🔐 2FA", use_container_width=True):
                st.session_state.show_2fa_setup = True
                st.rerun()
            
            if st.button("📱 Sessions", use_container_width=True):
                st.session_state.show_sessions = True
                st.rerun()
            
            # Admin only
            if user.get("role") == "admin":
                st.markdown("---")
                if st.button("👥 Manage Users", use_container_width=True):
                    st.session_state.show_user_management = True
                    st.rerun()
                
                if st.button("📋 Audit Logs", use_container_width=True):
                    st.session_state.show_audit_logs = True
                    st.rerun()
        
        st.markdown("---")
        
        # History & Data
        if st.button("🕐 History", use_container_width=True):
            st.session_state.show_history = True
            st.rerun()
        
        if st.button("💾 Saved Queries", use_container_width=True):
            st.session_state.show_saved_queries = True
            st.rerun()
        
        if st.button("📋 Conversations", use_container_width=True):
            st.session_state.show_conversations = True
            st.rerun()
        
        if st.button("📈 Metrics", use_container_width=True):
            st.session_state.show_health = True
            st.rerun()
        
        if st.button("📥 Export Chat", use_container_width=True):
            if st.session_state.chat_history:
                export_text = "\n\n".join([
                    f"**You:** {msg[0]}\n**Assistant:** {msg[1]}"
                    for msg in st.session_state.chat_history
                ])
                st.download_button(
                    "⬇️ Download",
                    export_text,
                    file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        # API Status Check
        if st.button("🔄 Check Status", use_container_width=True):
            try:
                status_resp = requests.get(f"{API_URL}/status", timeout=2)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    st.session_state.api_status = "online"
                    st.session_state.kb_status = status_data
                    st.success("✅ Connected")
                    st.rerun()
                else:
                    st.session_state.api_status = "offline"
                    st.error("❌ Error")
            except:
                st.session_state.api_status = "offline"
                st.error("❌ Offline")
    
    # File Upload (always visible at bottom)
    st.markdown("---")
    uploaded_file = st.file_uploader(
        "📤 Upload Document",
        type=["pdf", "docx", "txt", "csv", "html"],
        help="Upload documents to enhance the knowledge base",
        label_visibility="visible"
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
                    logger.info(f"Uploaded: {uploaded_file.name}")
                    # Refresh KB status after a delay
                    time.sleep(2)
                    try:
                        status_resp = requests.get(f"{API_URL}/status", timeout=2)
                        if status_resp.status_code == 200:
                            st.session_state.kb_status = status_resp.json()
                            st.rerun()
                    except:
                        pass
                else:
                    st.error(f"❌ Upload failed: {upload_resp.status_code}")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
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
    </div>
    """,
    unsafe_allow_html=True
)

# Main content - Copilot style header
st.markdown(
    """
    <div class="header-container">
        <h1 class="header-title">Knowledge Assistant</h1>
        <p class="header-subtitle">Ask questions about your documents</p>
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

# Conversations Dashboard
if st.session_state.get("show_conversations", False):
    st.markdown("---")
    st.markdown("### 💬 Conversation Management")
    
    try:
        with st.spinner("Loading conversations..."):
            convs_resp = requests.get(f"{API_URL}/conversations", timeout=10)
        
        if convs_resp.status_code == 200:
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
                                    st.session_state.chat_history = [
                                        (msg.get("role"), msg.get("content"), msg.get("timestamp", "")[:5], msg.get("sources", []))
                                        for msg in messages
                                    ]
                                except:
                                    st.session_state.chat_history = []
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
            perf_resp = requests.get(f"{API_URL}/health/performance?hours={hours}", timeout=10)
        
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

# User Profile Management Section
if st.session_state.get("show_profile", False):
    st.markdown("---")
    st.markdown("### 👤 My Profile")
    
    try:
        headers = get_auth_headers()
        
        # Get current profile
        with st.spinner("Loading profile..."):
            profile_resp = requests.get(f"{API_URL}/auth/profile", headers=headers, timeout=10)
        
        if profile_resp.status_code == 200:
            profile_data = profile_resp.json()
            user_info = profile_data.get("user", {})
            preferences = profile_data.get("preferences", {})
            
            # Display profile
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
                                st.error("❌ Cannot connect to API. Please ensure the server is running.")
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
                        language = st.selectbox(
                            "Language",
                            ["en", "es", "fr", "de", "it", "pt"],
                            index=["en", "es", "fr", "de", "it", "pt"].index(preferences.get("language", "en"))
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
                                    st.success("✅ Preferences saved successfully!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to save preferences: {prefs_resp.json().get('detail', 'Unknown error')}")
                            except requests.exceptions.ConnectionError:
                                st.error("❌ Cannot connect to API. Please ensure the server is running.")
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
""")

# Document Filter Section
st.markdown("### 📄 Search Filters")
col_filter_toggle, col_advanced = st.columns([3, 1])
with col_filter_toggle:
    if st.checkbox("🔍 Enable Advanced Filters", value=st.session_state.show_advanced_filters, key="advanced_filters_toggle"):
        st.session_state.show_advanced_filters = True
    else:
        st.session_state.show_advanced_filters = False

if st.session_state.show_advanced_filters:
    # Advanced Filters Section
    with st.expander("🔧 Advanced Search Filters", expanded=True):
        try:
            docs_resp = requests.get(f"{API_URL}/documents", timeout=5)
            if docs_resp.status_code == 200:
                data = docs_resp.json()
                available_docs = data.get("documents", [])
                
                if available_docs:
                    doc_names = [doc.get("filename", "") for doc in available_docs]
                    file_types = list(set([doc.get("file_type", "").upper() for doc in available_docs if doc.get("file_type")]))
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Document selection
                        selected_docs = st.multiselect(
                            "📄 Include Documents",
                            options=doc_names,
                            default=st.session_state.selected_documents,
                            help="Select documents to search. Leave empty to search all."
                        )
                        st.session_state.selected_documents = selected_docs
                        
                        # File type filter
                        selected_types = st.multiselect(
                            "📁 File Types",
                            options=file_types,
                            help="Filter by file types"
                        )
                        
                        # Exclude documents
                        excluded_docs = st.multiselect(
                            "🚫 Exclude Documents",
                            options=doc_names,
                            help="Documents to exclude from search"
                        )
                    
                    with col2:
                        # Date range
                        st.markdown("**📅 Date Range**")
                        date_from = st.date_input("From Date", value=None, help="Filter by processing date from")
                        date_to = st.date_input("To Date", value=None, help="Filter by processing date to")
                        
                        # Relevance threshold
                        min_relevance = st.slider(
                            "Minimum Relevance",
                            min_value=0.0,
                            max_value=1.0,
                            value=0.0,
                            step=0.1,
                            help="Minimum relevance score (0.0 = all results, 1.0 = only perfect matches)"
                        )
                        
                        # Max results
                        max_results = st.number_input(
                            "Max Results",
                            min_value=1,
                            max_value=20,
                            value=4,
                            help="Maximum number of results to return"
                        )
                    
                    # Store advanced filters in session state
                    st.session_state.advanced_filters = {
                        "document_names": selected_docs if selected_docs else None,
                        "file_types": [t.lower() for t in selected_types] if selected_types else None,
                        "date_from": date_from.strftime("%Y-%m-%d") if date_from else None,
                        "date_to": date_to.strftime("%Y-%m-%d") if date_to else None,
                        "min_relevance": min_relevance if min_relevance > 0 else None,
                        "max_results": max_results if max_results != 4 else None,
                        "exclude_documents": excluded_docs if excluded_docs else None
                    }
                    
                    # Show active filters
                    active_filters = []
                    if selected_docs:
                        active_filters.append(f"{len(selected_docs)} document(s)")
                    if selected_types:
                        active_filters.append(f"{len(selected_types)} file type(s)")
                    if date_from or date_to:
                        active_filters.append("date range")
                    if min_relevance > 0:
                        active_filters.append(f"relevance ≥ {min_relevance:.1f}")
                    if excluded_docs:
                        active_filters.append(f"excluding {len(excluded_docs)} doc(s)")
                    
                    if active_filters:
                        st.info(f"🔍 **Active filters:** {', '.join(active_filters)}")
                else:
                    st.caption("No documents available. Upload documents to enable filtering.")
            else:
                st.caption("Unable to load document list for filtering.")
        except:
            st.caption("Filtering unavailable (API connection issue)")
else:
    # Simple document filter
    try:
        docs_resp = requests.get(f"{API_URL}/documents", timeout=5)
        if docs_resp.status_code == 200:
            data = docs_resp.json()
            available_docs = data.get("documents", [])
            
            if available_docs:
                doc_names = [doc.get("filename", "") for doc in available_docs]
                
                selected = st.multiselect(
                    "Select documents to search (leave empty to search all documents)",
                    options=doc_names,
                    default=st.session_state.selected_documents,
                    key="document_filter_select",
                    help="Choose specific documents to search. Leave empty to search all documents in the knowledge base."
                )
                st.session_state.selected_documents = selected
                
                # Show filter status
                if selected:
                    st.info(f"🔍 **Filtering by {len(selected)} document(s):** {', '.join(selected[:3])}{'...' if len(selected) > 3 else ''}")
                else:
                    st.caption("💡 Searching all documents in knowledge base")
            else:
                st.caption("No documents available. Upload documents to enable filtering.")
    except:
        st.caption("Filtering unavailable (API connection issue)")

st.markdown("---")

# Streaming toggle
st.checkbox(
    "⚡ Enable Real-time Streaming",
    value=st.session_state.enable_streaming,
    key="streaming_toggle",
    help="Enable real-time streaming to see responses as they're generated"
)

st.markdown("---")

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

# Query suggestions/autocomplete (shown before chat input)
suggestions_placeholder = st.empty()

# Show popular queries when no input
if "last_query_input" not in st.session_state:
    st.session_state.last_query_input = ""

# Check for query input changes
current_input = ""
if "query_input_text" in st.session_state:
    current_input = st.session_state.query_input_text

# Show suggestions based on input
if current_input and len(current_input.strip()) > 0:
    try:
        suggestions_resp = requests.get(
            f"{API_URL}/suggestions",
            params={"q": current_input.strip(), "limit": 5},
            timeout=2
        )
        if suggestions_resp.status_code == 200:
            suggestions_data = suggestions_resp.json()
            suggestions = suggestions_data.get("suggestions", [])
            
            if suggestions:
                with suggestions_placeholder.container():
                    st.markdown("**💡 Query Suggestions:**")
                    for idx, suggestion in enumerate(suggestions):
                        suggestion_query = suggestion.get("query", "")
                        suggestion_type = suggestion.get("type", "")
                        suggestion_name = suggestion.get("name", "")
                        
                        # Create a button for each suggestion
                        label = suggestion_query
                        icon = "⭐" if suggestion_type == "saved" else "🕐"
                        if suggestion_type == "saved" and suggestion_name:
                            label = f"{suggestion_name}: {suggestion_query}"
                        
                        if st.button(
                            f"{icon} {label}",
                            key=f"suggestion_{idx}",
                            use_container_width=True,
                            help=f"Type: {suggestion_type}"
                        ):
                            st.session_state.example_query = suggestion_query
                            st.rerun()
    except:
        pass  # Silently fail if suggestions unavailable
elif not current_input:
    # Show popular queries when input is empty
    try:
        suggestions_resp = requests.get(
            f"{API_URL}/suggestions",
            params={"q": "", "limit": 3},
            timeout=2
        )
        if suggestions_resp.status_code == 200:
            suggestions_data = suggestions_resp.json()
            suggestions = suggestions_data.get("suggestions", [])
            
            if suggestions:
                with suggestions_placeholder.container():
                    st.caption("💡 **Popular queries - Click to use:**")
                    cols = st.columns(min(len(suggestions), 3))
                    for idx, (col, suggestion) in enumerate(zip(cols, suggestions[:3])):
                        with col:
                            suggestion_query = suggestion.get("query", "")
                            suggestion_type = suggestion.get("type", "")
                            icon = "⭐" if suggestion_type == "saved" else "🕐"
                            display_text = suggestion_query[:35] + ("..." if len(suggestion_query) > 35 else "")
                            if st.button(
                                f"{icon} {display_text}",
                                key=f"popular_{idx}",
                                use_container_width=True
                            ):
                                st.session_state.example_query = suggestion_query
                                st.rerun()
    except:
        pass

# Chat input
if query is None:
    query = st.chat_input("Ask anything...", key="chat_input")

if query:
    if query.strip():
        logger.info(f"Query: {query}")
        
        # Auto-create conversation if none exists
        if not st.session_state.current_conversation_id:
            try:
                resp = requests.post(f"{API_URL}/conversations", json={}, timeout=5)
                if resp.status_code == 200:
                    conv = resp.json()
                    st.session_state.current_conversation_id = conv.get("id")
            except:
                pass  # Continue without conversation if creation fails
        
        # Add user message to history
        timestamp = datetime.now().strftime("%H:%M")
        st.session_state.chat_history.append(("user", query.strip(), timestamp))
        
        # Get response (streaming or regular)
        if st.session_state.enable_streaming:
            # Streaming response (note: advanced filters not yet supported in streaming)
            try:
                start_time = time.time()
                # Prepare request payload with document filters and conversation
                payload = {"query": query}
                if st.session_state.selected_documents:
                    payload["document_filters"] = st.session_state.selected_documents
                if st.session_state.current_conversation_id:
                    payload["conversation_id"] = st.session_state.current_conversation_id
                endpoint = f"{API_URL}/ask/stream"
                
                # Create placeholder for streaming response
                answer_placeholder = st.empty()
                answer_text = ""
                sources = []
                
                # Stream the response (use appropriate endpoint)
                with requests.post(endpoint, json=payload, stream=True, timeout=60) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines():
                            if line:
                                line_str = line.decode('utf-8')
                                if line_str.startswith('data: '):
                                    try:
                                        data = json.loads(line_str[6:])  # Remove 'data: ' prefix
                                        event_type = data.get('type')
                                        
                                        if event_type == 'sources':
                                            sources = data.get('sources', [])
                                        elif event_type == 'chunk':
                                            chunk = data.get('content', '')
                                            answer_text += chunk
                                            # Update placeholder with current text
                                            answer_placeholder.markdown(f"**📚 Assistant**\n\n{answer_text}")
                                        elif event_type == 'done':
                                            full_response = data.get('full_response', answer_text)
                                            answer_text = full_response
                                            answer_placeholder.empty()  # Clear placeholder
                                        elif event_type == 'error':
                                            error_msg = data.get('content', 'Unknown error')
                                            answer_text = error_msg
                                            answer_placeholder.empty()
                                    except json.JSONDecodeError:
                                        continue
                
                elapsed_time = time.time() - start_time
                answer_timestamp = datetime.now().strftime("%H:%M")
                st.session_state.chat_history.append(("assistant", answer_text, answer_timestamp, sources))
                logger.info(f"Streaming response time: {elapsed_time:.2f}s, Sources: {len(sources)}")
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
        else:
            # Regular (non-streaming) response
            with st.spinner("🤔 Thinking..."):
                try:
                    start_time = time.time()
                    # Prepare request payload with filters and conversation
                    if st.session_state.show_advanced_filters and st.session_state.get("advanced_filters"):
                        # Use advanced search endpoint
                        payload = {
                            "query": query,
                            "filters": st.session_state.advanced_filters
                        }
                        if st.session_state.current_conversation_id:
                            payload["conversation_id"] = st.session_state.current_conversation_id
                        endpoint = f"{API_URL}/ask/advanced"
                    else:
                        # Use regular endpoint
                        payload = {"query": query}
                        if st.session_state.selected_documents:
                            payload["document_filters"] = st.session_state.selected_documents
                        if st.session_state.current_conversation_id:
                            payload["conversation_id"] = st.session_state.current_conversation_id
                        endpoint = f"{API_URL}/ask"
                    
                    response = requests.post(endpoint, json=payload, timeout=60)
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
            
            # Display message with feedback buttons
            col_msg, col_feedback = st.columns([5, 1])
            with col_msg:
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
            
            with col_feedback:
                # Get the user query for this response (previous message)
                user_query = ""
                if idx < len(st.session_state.chat_history) - 1:
                    prev_item = st.session_state.chat_history[-(idx+2)]
                    if len(prev_item) >= 2 and prev_item[0] == "user":
                        user_query = prev_item[1]
                
                # Check if feedback already submitted
                feedback_key = f"feedback_submitted_{idx}"
                if not st.session_state.get(feedback_key, False):
                    col_thumbs_up, col_thumbs_down = st.columns(2)
                    with col_thumbs_up:
                        if st.button("👍", key=f"thumbs_up_{idx}", help="Good answer", use_container_width=True):
                            try:
                                feedback_resp = requests.post(
                                    f"{API_URL}/feedback",
                                    json={
                                        "query": user_query,
                                        "response": message,
                                        "rating": 1,
                                        "feedback_type": "thumbs",
                                        "sources_count": len(sources)
                                    },
                                    timeout=5
                                )
                                if feedback_resp.status_code == 200:
                                    st.session_state[feedback_key] = True
                                    st.success("👍 Thanks!")
                                    time.sleep(1)
                                    st.rerun()
                            except:
                                st.error("Failed to submit feedback")
                    
                    with col_thumbs_down:
                        if st.button("👎", key=f"thumbs_down_{idx}", help="Poor answer", use_container_width=True):
                            # Show feedback form
                            st.session_state[f"show_feedback_form_{idx}"] = True
                            st.rerun()
                    
                    # Detailed feedback form
                    if st.session_state.get(f"show_feedback_form_{idx}", False):
                        with st.form(f"feedback_form_{idx}"):
                            st.write("**Help us improve:**")
                            rating = st.slider("Rating (1-5)", 1, 5, 2, key=f"rating_{idx}")
                            comment = st.text_area("Comments (optional)", key=f"comment_{idx}")
                            col_submit, col_cancel = st.columns(2)
                            with col_submit:
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
                                                "sources_count": len(sources)
                                            },
                                            timeout=5
                                        )
                                        if feedback_resp.status_code == 200:
                                            st.session_state[feedback_key] = True
                                            st.session_state[f"show_feedback_form_{idx}"] = False
                                            st.success("✅ Feedback submitted!")
                                            time.sleep(1)
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {str(e)}")
                            with col_cancel:
                                if st.form_submit_button("Cancel"):
                                    st.session_state[f"show_feedback_form_{idx}"] = False
                                    st.rerun()
                else:
                    st.caption("✅ Feedback submitted")

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
