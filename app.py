import streamlit as st
import praw
from openai import OpenAI
import json
import os
import time
import pandas as pd

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Universal Insight Engine", page_icon="🧠", layout="wide")

# --- 2. SIDEBAR: CREDENTIALS ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    with st.expander("🔑 API Keys", expanded=True):
        env_reddit_id = os.getenv("REDDIT_CLIENT_ID", "")
        env_reddit_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        env_openai_key = os.getenv("OPENAI_API_KEY", "")

        reddit_client_id = st.text_input("Reddit Client ID", value=env_reddit_id, type="password")
        reddit_client_secret = st.text_input("Reddit Client Secret", value=env_reddit_secret, type="password")
        openai_api_key = st.text_input("OpenAI API Key", value=env_openai_key, type="password")
    
    st.divider()
    st.subheader("🤖 AI Model")
    model_options = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    selected_model = st.selectbox("Select Model Version", model_options, index=0)
    
    if st.button("Save & Connect"):
        if reddit_client_id and openai_api_key:
            st.session_state['credentials_set'] = True
            st.success("Credentials Loaded!")
        else:
            st.error("Please fill in all keys.")

# --- HELPER: ROBUST DATA EXTRACTOR (The Fix) ---
def get_list_from_data(data, column_name):
    """
    Extracts a list of values from ANY data structure (Dict, List, or DataFrame).
    Safely handles integers/row-indices to prevent crashes.
    """
    # 1. If it's a DataFrame (The likely format from your screenshot)
    if isinstance(data, pd.DataFrame):
        # Try finding the column safely
        matches = [c for c in data.columns if str(c).lower() == column_name.lower()]
        if matches:
            return data[matches[0]].dropna().astype(str).tolist()
        return []

    # 2. If it's a Dictionary (JSON)
    if isinstance(data, dict):
        # Direct check
        if column_name in data:
            val = data[column_name]
            return val if isinstance(val, list) else [str(val)]
        
        # Case-insensitive check (ignoring integer keys!)
        for key in data.keys():
            if isinstance(key, str): # <--- THIS FIXES THE CRASH
                if key.lower() == column_name.lower():
                    val = data[key]
                    return val if isinstance(val, list) else [str(val)]
        
        # Fallback: If dict keys are integers (row numbers), try looking inside values
        # This handles the case where Streamlit returns {0: 'val', 1: 'val'}
        first_val = next(iter(data.values()), None)
        if isinstance(first_val, dict) and column_name in first_val:
             return [row[column_name] for row in data.values() if column_name in row]

    # 3. If it's a List of Rows
    if isinstance(data, list):
        extracted = []
        for row in data:
            if isinstance(row, dict):
                # Check keys safely
                for k, v in row.items():
                    if str(k).lower() == column_name.lower():
                        extracted.append(v)
        if extracted: return extracted

    return [] # Found nothing

# --- 3. CORE LOGIC ---

def generate_recipe(user_query, model_name):
    try:
        client = OpenAI(api_key=openai_api_key)
        
        system_prompt = """
        You are a Research Architect. Convert the User Goal into a strict JSON configuration.
        Output JSON ONLY.
        
        Structure:
        {
          "project_name": "Short Name",
          "target_subreddits": ["list", "of", "5", "subreddits"],
          "search_keywords": ["list", "of", "5", "keywords"],
          "ai_instruction": "What to extract"
        }
        """
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"USER GOAL: {user_query}"}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
        
    except Exception as e:
        st.error(f"❌ Error generating recipe: {e}")
        return None

def run_universal_engine(recipe, model_name):
    # 1. Setup Reddit
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent="UniversalEngine/Fix_v5"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # 2. EXTRACT TARGETS (Safely)
    targets = get_list_from_data(recipe, 'target_subreddits')
    keywords = get_list_from_data(recipe, 'search_keywords')
    
    # Debugging help if it's still empty
    if not targets:
        st.warning("⚠️ Could not find 'target_subreddits'. Using Fallback.")
        # Fallback: If keywords exist but subreddits don't, try scanning 'all'
        if keywords: 
            targets = ["all"]
        else:
            return "❌ Error: Strategy is empty. Please regenerate."

    if not keywords:
        keywords = ["discussion", "review"]

    total_subs = len(targets)
    
    # 3. Scan Subreddits
    for i, sub in enumerate(targets):
        clean_sub = str(sub).replace("r/", "").replace("R/", "").strip()
        
        status_text.markdown(f"🕵️ Scanning **r/{clean_sub}**...")
        if total_subs > 0:
            progress_bar.progress((i + 1) / total_subs)
        
        try:
            subreddit = reddit.subreddit(clean_sub)
            query = " OR ".join([str(k) for k in keywords])
            
            # Fetch last 10 posts
            for post in subreddit.search(query, sort="relevance", time_filter="month", limit=10):
                if post.num_comments > 1: 
                    collected_data.append(f"Title: {post.title}\nBody: {post.selftext[:800]}\nUrl: {post.url}")
                time.sleep(0.1) 
                
        except Exception as e:
            print(f"Skipped r/{clean_sub}: {e}")

    # 4. Final Analysis
    status_text.text("🧠 Analyzing collected data with OpenAI...")
    
    if not collected_data:
        return f"⚠️ No relevant data found in {len(targets)} subreddits. Try changing your Keywords."

    full_text_blob = "\n---\n".join(collected_data[:20])
    
    client = OpenAI(api_key=openai_api_key)
    
    final_system_prompt = f"""
    You are a Senior Market Analyst.
    TASK: Write a structured Executive Report (Markdown). Highlight Winners, Risks, and Sentiment.
    """
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": f"RAW DATA:\n{full_text_blob}"}
            ]
        )
        status_text.empty()
        progress_bar.empty()
        return response.choices[0].message.content
        
    except Exception as e:
        return f"❌ Analysis Failed: {e}"

# --- 4. THE USER INTERFACE ---

st.title("🚀 Universal Insight Engine")
st.markdown("Research anything on Reddit. Describe your goal, and the AI will build a strategy.")

user_query = st.text_area("What do you want to find out?", placeholder="e.g. Compare top recruiter tools", height=100)

if st.button("Generate Strategy"):
    if not st.session_state.get('credentials_set'):
        st.error("Enter Keys in Sidebar!")
    elif not user_query:
        st.warning("Enter a topic.")
    else:
        with st.spinner("🤖 Designing strategy..."):
            recipe = generate_recipe(user_query, selected_model)
            if recipe:
                st.session_state['current_recipe'] = recipe
                st.success("Strategy Created!")

if 'current_recipe' in st.session_state:
    st.divider()
    st.subheader("📋 Research Strategy")
    
    # We force the data editor to be more forgiving
    edited_recipe = st.data_editor(st.session_state['current_recipe'], num_rows="dynamic", use_container_width=True)
    
    if st.button("🚀 Launch Research", type="primary"):
        with st.spinner("Running Engine..."):
            report = run_universal_engine(edited_recipe, selected_model)
            st.session_state['final_report'] = report

if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Report")
    st.markdown(st.session_state['final_report'])
