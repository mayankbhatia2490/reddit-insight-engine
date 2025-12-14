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

# --- HELPER: SMART DATA EXTRACTOR (The Fix) ---
def get_list_from_data(data, column_name):
    """
    Robustly extracts a list of values (e.g. subreddits) from ANY data structure
    (Dict, List of Rows, or DataFrame).
    """
    # 1. If it's a Dictionary (Standard)
    if isinstance(data, dict):
        # Check exact key
        if column_name in data:
            val = data[column_name]
            if isinstance(val, list): return val
            return [str(val)]
        # Check for matching keys (case-insensitive)
        for key in data.keys():
            if key.lower() == column_name.lower():
                val = data[key]
                return val if isinstance(val, list) else [str(val)]

    # 2. If it's a DataFrame (Table view like in your screenshot)
    if isinstance(data, pd.DataFrame):
        if column_name in data.columns:
            return data[column_name].dropna().tolist()
        
    # 3. If it's a List of Dictionaries (Rows)
    if isinstance(data, list):
        extracted = []
        for row in data:
            if isinstance(row, dict) and column_name in row:
                extracted.append(row[column_name])
        if extracted: return extracted

    return [] # Failed to find anything

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
            user_agent="UniversalEngine/Fix_v3"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # 2. ROBUST EXTRACTION (Fixing the "No subreddits" error)
    # We use the helper to find the list even if it's hidden in a table
    targets = get_list_from_data(recipe, 'target_subreddits')
    keywords = get_list_from_data(recipe, 'search_keywords')
    
    # Fallback: If keywords is empty, use the project name
    if not keywords and isinstance(recipe, dict):
        keywords = [recipe.get('project_name', 'review')]

    if not targets:
        return "⚠️ Error: Could not find 'target_subreddits' in the data. Please ensure the column name matches."

    total_subs = len(targets)
    
    # 3. Scan Subreddits
    for i, sub in enumerate(targets):
        # Clean the subreddit name (Remove 'r/' if user added it, remove spaces)
        clean_sub = str(sub).replace("r/", "").replace("R/", "").strip()
        
        status_text.markdown(f"🕵️ Scanning **r/{clean_sub}**...")
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
            # Don't stop the whole app, just warn about this one subreddit
            print(f"Skipped r/{clean_sub}: {e}")

    # 4. Final Analysis
    status_text.text("🧠 Analyzing collected data with OpenAI...")
    
    if not collected_data:
        return f"⚠️ No relevant data found in {len(targets)} subreddits. Try changing your Keywords."

    full_text_blob = "\n---\n".join(collected_data[:20])
    
    client = OpenAI(api_key=openai_api_key)
    
    # Extract project name safely
    p_name = "Research Project"
    if isinstance(recipe, dict): p_name = recipe.get('project_name', p_name)
    elif isinstance(recipe, pd.DataFrame) and 'project_name' in recipe.columns: p_name = recipe['project_name'].iloc[0]

    final_system_prompt = f"""
    You are a Senior Market Analyst.
    PROJECT: {p_name}
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
    # This editor handles both Dicts and DataFrames now
    edited_recipe = st.data_editor(st.session_state['current_recipe'], num_rows="dynamic")
    
    if st.button("🚀 Launch Research", type="primary"):
        with st.spinner("Running Engine..."):
            report = run_universal_engine(edited_recipe, selected_model)
            st.session_state['final_report'] = report

if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Report")
    st.markdown(st.session_state['final_report'])
