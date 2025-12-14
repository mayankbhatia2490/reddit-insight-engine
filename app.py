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

# --- HELPER: NUCLEAR DATA EXTRACTOR ---
def get_list_from_data(data, column_name):
    """
    Uses Pandas to force-find the column, no matter how the data is structured.
    """
    try:
        # 1. Force convert to DataFrame
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # Handle the specific case where keys are row indices (from your screenshot)
            df = pd.DataFrame.from_dict(data, orient='index') if "0" in data else pd.DataFrame([data])
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            return []

        # 2. Normalize Column Names (Lowercase & Strip spaces)
        df.columns = [str(c).lower().strip() for c in df.columns]
        target_col = column_name.lower().strip()

        # 3. Find the column
        if target_col in df.columns:
            return df[target_col].dropna().astype(str).tolist()
        
        # 4. Fallback: Search for any column that contains the target string
        for col in df.columns:
            if target_col in col:
                return df[col].dropna().astype(str).tolist()
                
        return []

    except Exception as e:
        st.error(f"Data Extraction Error: {e}")
        return []

# --- 3. CORE LOGIC ---

def generate_recipe(user_query, model_name):
    try:
        client = OpenAI(api_key=openai_api_key)
        
        system_prompt = """
        You are a Research Architect. Convert the User Goal into a strict JSON configuration.
        Output JSON ONLY.
        
        Structure:
        [
          {
            "project_name": "Short Name",
            "target_subreddits": "r/subreddit1",
            "search_keywords": "keyword1",
            "ai_instruction": "What to extract"
          },
          {
            "project_name": "Short Name",
            "target_subreddits": "r/subreddit2",
            "search_keywords": "keyword2",
            "ai_instruction": "What to extract"
          }
        ]
        """
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"USER GOAL: {user_query}. Generate 5 rows."}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        
        # Handle cases where AI wraps the list in a dict key
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            # Grab the first list found in values
            for v in parsed.values():
                if isinstance(v, list): return v
            return [parsed] # Return as single row list
            
        return parsed
        
    except Exception as e:
        st.error(f"❌ Error generating recipe: {e}")
        return None

def run_universal_engine(recipe, model_name):
    # 1. Setup Reddit
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent="UniversalEngine/Nuclear_v7"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # 2. EXTRACT TARGETS (Nuclear Method)
    targets = get_list_from_data(recipe, 'target_subreddits')
    keywords = get_list_from_data(recipe, 'search_keywords')
    
    # Debugging: Show what we found if it fails
    if not targets:
        st.error("Debug Info: Could not find 'target_subreddits'.")
        st.write("Data received by Engine:", recipe)
        return "❌ Error: No subreddits found. Check the table above."

    # Remove duplicates and clean
    targets = list(set(targets))
    total_subs = len(targets)
    
    # 3. Scan Subreddits
    for i, sub in enumerate(targets):
        clean_sub = str(sub).replace("r/", "").replace("R/", "").strip()
        
        status_text.markdown(f"🕵️ Scanning **r/{clean_sub}**...")
        if total_subs > 0:
            progress_bar.progress((i + 1) / total_subs)
        
        try:
            subreddit = reddit.subreddit(clean_sub)
            # Use all keywords combined
            query = " OR ".join([str(k) for k in keywords[:5]]) # Limit to 5 keywords for query length
            
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
    
    # Using container width to ensure columns are visible
    edited_recipe = st.data_editor(st.session_state['current_recipe'], num_rows="dynamic", use_container_width=True)
    
    if st.button("🚀 Launch Research", type="primary"):
        with st.spinner("Running Engine..."):
            report = run_universal_engine(edited_recipe, selected_model)
            st.session_state['final_report'] = report

if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Report")
    st.markdown(st.session_state['final_report'])
