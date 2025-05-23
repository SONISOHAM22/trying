import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
import re
from datetime import datetime
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="Job Application Assistant",
    page_icon="💼",
    layout="centered"
)

# Custom CSS for white text on black background
st.markdown("""
<style>
    .stApp {
        background: #000000;
        color: #ffffff;
    }
    
    .chat-container {
        background: #1a1a1a;
        border-radius: 15px;
        padding: 20px;
        margin: 20px 0;
        box-shadow: 0 10px 30px rgba(255,255,255,0.1);
        color: #ffffff;
    }
    
    .agent-header {
        text-align: center;
        padding: 20px;
        background: linear-gradient(45deg, #4facfe 0%, #00f2fe 100%);
        border-radius: 15px;
        color: #ffffff;
        margin-bottom: 20px;
    }
    
    .status-success {
        background: #d4edda;
        color: #155724;
        padding: 10px;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin: 10px 0;
    }
    
    .status-error {
        background: #f8d7da;
        color: #721c24;
        padding: 10px;
        border-radius: 8px;
        border-left: 4px solid #dc3545;
        margin: 10px 0;
    }
    
    .job-details {
        background: #2a2a2a;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #ffffff;
        margin: 10px 0;
        color: #ffffff;
    }
    
    .stTextInput > div > div > input {
        background-color: #333333;
        color: #ffffff;
        border: 1px solid #ffffff;
    }
    
    .stButton > button {
        background-color: #4facfe;
        color: #ffffff;
        border: none;
    }
    
    .stButton > button:hover {
        background-color: #00f2fe;
    }
    
    .stExpander {
        background-color: #1a1a1a;
        color: #ffffff;
    }
    
    .stExpander > div > div > div > div {
        color: #ffffff;
    }
    
    .stMarkdown {
        color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'initialized' not in st.session_state:
    st.session_state.initialized = False
if 'config_status' not in st.session_state:
    st.session_state.config_status = {'gemini': False, 'sheets': False}

class JobTracker:
    def __init__(self):
        self.gemini_configured = False
        self.sheets_configured = False
        self.sheet = None
        self.setup_services()
    
    def setup_services(self):
        """Initialize Gemini and Google Sheets from Streamlit secrets"""
        try:
            # Setup Gemini
            try:
                gemini_api_key = st.secrets["secrets"]["GEMINI_API_KEY"]
                if gemini_api_key:
                    genai.configure(api_key=gemini_api_key)
                    self.gemini_configured = True
                    st.session_state.config_status['gemini'] = True
                else:
                    st.error("GEMINI_API_KEY not found in secrets")
            except KeyError:
                st.error("GEMINI_API_KEY not found in Streamlit secrets. Please add it to your app secrets.")
            
            # Setup Google Sheets
            try:
                google_creds = st.secrets["secrets"]["GOOGLE_CREDENTIALS"]
                sheet_id = st.secrets["secrets"]["GOOGLE_SHEET_ID"]
                
                if google_creds and sheet_id:
                    try:
                        # Convert the TOML section to dictionary
                        credentials_dict = dict(google_creds)
                        
                        scope = [
                            'https://spreadsheets.google.com/feeds',
                            'https://www.googleapis.com/auth/drive'
                        ]
                        creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
                        client = gspread.authorize(creds)
                        self.sheet = client.open_by_key(sheet_id).sheet1
                        self.sheets_configured = True
                        st.session_state.config_status['sheets'] = True
                    except Exception as e:
                        st.error(f"Google Sheets setup error: {str(e)}. Ensure GOOGLE_CREDENTIALS and GOOGLE_SHEET_ID are correct and the sheet is shared with the service account.")
                else:
                    st.error("Missing GOOGLE_CREDENTIALS or GOOGLE_SHEET_ID in secrets")
            except KeyError as e:
                st.error(f"Google Sheets credentials not found in Streamlit secrets: {str(e)}. Please add GOOGLE_CREDENTIALS and GOOGLE_SHEET_ID to your app secrets.")
            
        except Exception as e:
            st.error(f"Service setup error: {str(e)}")
    
    def extract_job_details(self, text, conversation_history):
        """Extract job application details using Gemini AI"""
        details = {
            'Company_Name': '',
            'Role': '',
            'Date': '',
            'Platform': '',
            'Accept': 'Pending'
        }
        
        if not self.gemini_configured:
            return details, False, "Gemini AI not configured"
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
You are a Job Application Assistant that extracts job application details from user input. The user has provided the following text: "{text}"

Extract the following details:
- Company Name
- Role
- Date (in YYYY-MM-DD format, use today's date {datetime.now().strftime('%Y-%m-%d')} if not specified, convert 'today' or 'yesterday' appropriately)
- Platform (e.g., LinkedIn, Indeed, company website, etc.)
- Status (default to 'Pending' unless specified)

Return the details in JSON format. If any detail is missing or unclear, leave it as an empty string, except for Date (use today's date) and Status (use 'Pending'). If the input doesn't seem to be a job application, return empty details and indicate it's not a valid application.

Conversation history for context (last 6 messages):
"""
            for msg in conversation_history[-6:]:
                prompt += f"{msg['role'].title()}: {msg['content']}\n"
            
            prompt += "\nReturn: ```json\n{}\n```"
            
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                try:
                    extracted_details = json.loads(json_match.group(1))
                    details.update({
                        'Company_Name': extracted_details.get('Company Name', '').strip().title(),
                        'Role': extracted_details.get('Role', '').strip().title(),
                        'Date': extracted_details.get('Date', datetime.now().strftime('%Y-%m-%d')).strip(),
                        'Platform': extracted_details.get('Platform', '').strip().title(),
                        'Accept': extracted_details.get('Status', 'Pending').strip()
                    })
                    is_valid = bool(details['Company_Name'] and details['Role'])
                    return details, is_valid, "Successfully extracted details"
                except json.JSONDecodeError:
                    return details, False, "Failed to parse Gemini AI response"
            else:
                return details, False, "No valid job application details found"
                
        except Exception as e:
            return details, False, f"Error extracting details with Gemini AI: {str(e)}"
    
    def add_to_sheet(self, details):
        """Add job application to Google Sheet"""
        if not self.sheets_configured or not self.sheet:
            return False, "Google Sheets not configured. Please check your secrets and sheet permissions."
        
        try:
            # Verify sheet structure
            headers = self.sheet.row_values(1)
            expected_headers = ['Company Name', 'Role', 'Date', 'Platform', 'Accept']
            if not all(h in headers for h in expected_headers):
                return False, "Invalid sheet structure. Ensure columns are: Company Name, Role, Date, Platform, Accept"
            
            # Check for duplicates
            records = self.sheet.get_all_records()
            for record in records:
                if (record.get('Company Name', '').lower() == details['Company_Name'].lower() and 
                    record.get('Role', '').lower() == details['Role'].lower() and 
                    record.get('Date') == details['Date']):
                    return False, "This job application already exists"
            
            # Add new row
            row_data = [
                details['Company_Name'],
                details['Role'],
                details['Date'],
                details['Platform'],
                details['Accept']
            ]
            
            self.sheet.append_row(row_data)
            return True, "Successfully added to your job tracker!"
            
        except Exception as e:
            return False, f"Error saving to sheet: {str(e)}. Ensure the service account has edit permissions."
    
    def remove_from_sheet(self, company_name):
        """Remove all rows from Google Sheet based on company name"""
        if not self.sheets_configured or not self.sheet:
            return False, "Google Sheets not configured. Please check your secrets and sheet permissions."
        
        try:
            records = self.sheet.get_all_records()
            rows_to_delete = []
            
            # Find all rows with matching company name
            for i, record in enumerate(records, start=2):  # Start from 2 to account for header row
                if record.get('Company Name', '').lower() == company_name.lower():
                    rows_to_delete.append(i)
            
            if rows_to_delete:
                # Delete rows in reverse order to avoid index shifting
                for row_index in sorted(rows_to_delete, reverse=True):
                    self.sheet.delete_rows(row_index)
                return True, f"Successfully removed {len(rows_to_delete)} application(s) for {company_name.title()} from your job tracker!"
            else:
                return False, f"No application found for {company_name.title()} in your job tracker."
                
        except Exception as e:
            return False, f"Error removing from sheet: {str(e)}. Ensure the service account has edit permissions."
    
    def get_ai_response(self, prompt, conversation_history):
        """Get response from Gemini AI for general conversation"""
        if not self.gemini_configured:
            return "I'm having trouble connecting to my AI service. Please check the GEMINI_API_KEY in your secrets."
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            context = """You are a Job Application Assistant developed by Soham. You help users track their job applications in a friendly, conversational way.

Your main functions:
1. Help users log their job applications (details are handled separately)
2. Provide encouragement and support during their job search
3. Answer questions about job searching and applications
4. Maintain a positive, helpful attitude

When users mention job applications, acknowledge their effort and let them know you're tracking it.

Conversation history:
"""
            
            # Add recent conversation for context
            for msg in conversation_history[-6:]:
                context += f"{msg['role'].title()}: {msg['content']}\n"
            
            full_prompt = context + f"\nUser: {prompt}\nAssistant:"
            
            response = model.generate_content(full_prompt)
            return response.text
            
        except Exception as e:
            return f"I'm having some technical difficulties right now. Error: {str(e)}"
    
    def is_job_application(self, text):
        """Check if message contains job application information or removal request"""
        job_keywords = [
            'applied', 'application', 'applying', 'job', 'position', 
            'role', 'interview', 'company', 'submitted', 'sent resume'
        ]
        remove_pattern = r'remove\s+(.+?)\s+row'
        
        if re.search(remove_pattern, text, re.IGNORECASE):
            return 'remove'
        if any(keyword in text.lower() for keyword in job_keywords):
            return 'application'
        return None

# Initialize the job tracker
if not st.session_state.initialized:
    st.session_state.job_tracker = JobTracker()
    st.session_state.initialized = True

# Header
st.markdown("""
<div class="agent-header">
    <h1>💼 Job Application Assistant</h1>
    <p><em>Developed by Soham</em></p>
    <p>Hi there! 👋 I'm here to help you track your job applications!</p>
</div>
""", unsafe_allow_html=True)

# Configuration status (only show if there are issues)
if not all(st.session_state.config_status.values()):
    with st.expander("⚙️ Configuration Status", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            if st.session_state.config_status['gemini']:
                st.success("✅ Gemini AI Connected")
            else:
                st.error("❌ Gemini AI Not Connected")
                st.caption("Add GEMINI_API_KEY to your Streamlit secrets")
        
        with col2:
            if st.session_state.config_status['sheets']:
                st.success("✅ Google Sheets Connected")
            else:
                st.error("❌ Google Sheets Not Connected")
                st.caption("Add GOOGLE_CREDENTIALS and GOOGLE_SHEET_ID to your Streamlit secrets")

# Chat container
with st.container():
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and "job_details" in message:
                # Special formatting for job application confirmations
                st.markdown(message["content"])
                details = message["job_details"]
                st.markdown(f"""
                <div class="job-details">
                    <strong>📋 Application Details:</strong><br>
                    🏢 <strong>Company:</strong> {details['Company_Name']}<br>
                    💼 <strong>Role:</strong> {details['Role']}<br>
                    📅 <strong>Date:</strong> {details['Date']}<br>
                    🌐 <strong>Platform:</strong> {details['Platform']}<br>
                    ⏳ <strong>Status:</strong> {details['Accept']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Tell me about your job applications..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Process the message
    job_tracker = st.session_state.job_tracker
    message_type = job_tracker.is_job_application(prompt)
    
    if message_type == 'application':
        # Extract job details using Gemini AI
        job_details, is_valid, extraction_message = job_tracker.extract_job_details(prompt, st.session_state.messages)
        
        if is_valid:
            # Add to sheet if valid details extracted
            success, sheet_message = job_tracker.add_to_sheet(job_details)
            
            if success:
                response = f"Great! I've recorded your job application. {sheet_message} 🎉\n\nKeep up the great work with your job search! 💪"
                
                # Add message with job details for special formatting
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response,
                    "job_details": job_details
                })
            else:
                response = f"I see you applied for a job! However, there was an issue saving it: {sheet_message}\n\nBut don't worry, I've still noted your application effort! 👍"
                st.session_state.messages.append({"role": "assistant", "content": response})
        else:
            response = f"I couldn't extract enough details from your input: {extraction_message}. Could you clarify? For example: 'I applied for a Software Engineer role at Google yesterday via LinkedIn'"
            st.session_state.messages.append({"role": "assistant", "content": response})
    
    elif message_type == 'remove':
        # Extract company name from remove request
        remove_pattern = r'remove\s+(.+?)\s+row'
        match = re.search(remove_pattern, prompt, re.IGNORECASE)
        if match:
            company_name = match.group(1).strip()
            success, message = job_tracker.remove_from_sheet(company_name)
            response = message
            st.session_state.messages.append({"role": "assistant", "content": response})
        else:
            response = "Please specify the company name to remove, like: 'remove Google row'"
            st.session_state.messages.append({"role": "assistant", "content": response})
    
    else:
        # Get AI response for general conversation
        response = job_tracker.get_ai_response(prompt, st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": response})
    
    # Display assistant response
    with st.chat_message("assistant"):
        last_message = st.session_state.messages[-1]
        if "job_details" in last_message:
            st.markdown(last_message["content"])
            details = last_message["job_details"]
            st.markdown(f"""
            <div class="job-details">
                <strong>📋 Application Details:</strong><br>
                🏢 <strong>Company:</strong> {details['Company_Name']}<br>
                💼 <strong>Role:</strong> {details['Role']}<br>
                📅 <strong>Date:</strong> {details['Date']}<br>
                🌐 <strong>Platform:</strong> {details['Platform']}<br>
                ⏳ <strong>Status:</strong> {details['Accept']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(last_message["content"])

# Sidebar with buttons
with st.sidebar:
    if st.button("🗑️ Reset Chat"):
        st.session_state.messages = []
        st.rerun()
    
    if st.button("📝 Test with Sample Data"):
        sample_message = "I applied for Software Engineer at Google yesterday via LinkedIn"
        st.session_state.messages.append({"role": "user", "content": sample_message})
        st.rerun()

# Footer with instructions
st.markdown("---")
with st.expander("📋 How to Use & Setup"):
    st.markdown("""
    ### 🚀 Quick Setup for Streamlit Cloud:
    
    Add the following secrets to your Streamlit Cloud app:
    
    1. Go to your app dashboard on Streamlit Cloud
    2. Click on "Settings" → "Secrets"
    3. Add the secrets as shown in the configuration file
    
    ### 📊 Google Sheet Setup:
    1. Create a Google Sheet with columns: `Company Name`, `Role`, `Date`, `Platform`, `Accept`
    2. Create a Service Account in Google Cloud Console
    3. Enable Google Sheets API and Google Drive API
    4. Share your sheet with the service account email
    
    ### 💬 How to Chat:
    Tell me about your job applications in any natural way:
    - "I applied for a Software Engineer role at Google yesterday via LinkedIn"
    - "Submitted an application to Microsoft for Data Scientist on 23-05-2025"
    - "Got an interview with Apple for Product Manager!"
    - To remove an application: "remove Google row"
    
    ### 🎯 Features:
    - ✅ Intelligent job application tracking using AI
    - ✅ Remove all applications by company name
    - ✅ Natural language processing
    - ✅ Google Sheets integration
    - ✅ Duplicate prevention
    - ✅ Conversational AI support
    - ✅ Reset chat history
    """)