import streamlit as st
import praw
from openai import OpenAI
import json
import os
import time

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
    # Defaulting to 4o-mini as it's the most reliable for JSON structure vs cost
    model_options = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
    selected_model = st.selectbox("Select Model Version", model_options, index=0)
    
    if st.button("Save & Connect"):
        if reddit_client_id and openai_api_key:
            st.session_state['credentials_set'] = True
            st.success("Credentials Loaded!")
        else:
            st.error("Please fill in all keys.")

# --- HELPER: DATA NORMALIZER (The Fix for KeyError) ---
def normalize_recipe(data):
    """
    Fixes the AI's JSON if it uses slightly different key names.
    """
    # 1. Fix Subreddits
    if "target_subreddits" not in data:
        # Check common synonyms the AI might have used
        if "subreddits" in data:
            data["target_subreddits"] = data.pop("subreddits")
        elif "targets" in data:
             data["target_subreddits"] = data.pop("targets")
        else:
            data["target_subreddits"] = [] # Fail safe
            
    # 2. Fix Keywords
    if "search_keywords" not in data:
        if "keywords" in data:
            data["search_keywords"] = data.pop("keywords")
        elif "search_terms" in data:
            data["search_keywords"] = data.pop("search_terms")
        else:
            data["search_keywords"] = []

    # 3. Fix Project Name
    if "project_name" not in data:
        data["project_name"] = "Reddit Research"
        
    return data

# --- 3. CORE LOGIC ---

def generate_recipe(user_query, model_name):
    try:
        client = OpenAI(api_key=openai_api_key)
        
        system_prompt = """
        You are a Research Architect. Convert the User Goal into a strict JSON configuration.
        Output JSON ONLY.
        
        REQUIRED KEYS:
        - "project_name": (String) Short title.
        - "target_subreddits": (List of strings) Top 5 relevant subreddits (no "r/" prefix).
        - "search_keywords": (List of strings) Top 5 search terms (use OR logic).
        - "ai_instruction": (String) What specific insights to look for.
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
        raw_json = json.loads(content)
        
        # Apply the fix immediately
        return normalize_recipe(raw_json)
        
    except Exception as e:
        st.error(f"❌ Error generating recipe: {e}")
        return None

def run_universal_engine(recipe, model_name):
    # 1. Setup Reddit
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent="UniversalEngine/OpenAI_v2"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # SAFE GET: Use .get() to avoid crashing if keys are still missing
    targets = recipe.get('target_subreddits', [])
    keywords = recipe.get('search_keywords', [])
    
    if not targets:
        return "⚠️ Error: No subreddits found in the strategy. Please edit the list above."

    total_subs = len(targets)
    
    # 2. Scan Subreddits
    for i, sub in enumerate(targets):
        status_text.markdown(f"🕵️ Scanning **r/{sub}**...")
        progress_bar.progress((i + 1) / total_subs)
        
        try:
            subreddit = reddit.subreddit(sub)
            query = " OR ".join(keywords)
            
            # Fetch last 10 posts
            for post in subreddit.search(query, sort="relevance", time_filter="month", limit=10):
                if post.num_comments > 1: 
                    collected_data.append(f"Title: {post.title}\nBody: {post.selftext[:800]}\nUrl: {post.url}")
                time.sleep(0.2) 
                
        except Exception as e:
            st.warning(f"Skipped r/{sub}: {e}")

    # 3. Final Analysis
    status_text.text("🧠 Analyzing collected data with OpenAI...")
    
    if not collected_data:
        return "⚠️ No relevant data found. Try broader keywords in the Strategy editor."

    full_text_blob = "\n---\n".join(collected_data[:20])
    
    client = OpenAI(api_key=openai_api_key)
    
    final_system_prompt = f"""
    You are a Senior Market Analyst.
    PROJECT: {recipe.get('project_name', 'Research')}
    GOAL: {recipe.get('ai_instruction', 'Summarize findings')}
    
    TASK:
    Write a clear Executive Report (Markdown).
    Highlight "Winners", "Risks", and specific user sentiments.
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
    # Use dynamic editing
    edited_recipe = st.data_editor(st.session_state['current_recipe'], num_rows="dynamic")
    
    if st.button("🚀 Launch Research", type="primary"):
        with st.spinner("Running Engine..."):
            report = run_universal_engine(edited_recipe, selected_model)
            st.session_state['final_report'] = report

if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Report")
    st.markdown(st.session_state['final_report'])
