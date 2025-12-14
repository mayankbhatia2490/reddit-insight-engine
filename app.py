import streamlit as st
import praw
from openai import OpenAI
import json
import os
import time

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Universal Insight Engine (OpenAI)", page_icon="🧠", layout="wide")

# --- 2. SIDEBAR: CREDENTIALS & SETTINGS ---
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
    # OpenAI Model Options
    model_options = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    selected_model = st.selectbox("Select Model Version", model_options, index=1) # Default to mini (cheaper)
    
    if st.button("Save & Connect"):
        if reddit_client_id and openai_api_key:
            st.session_state['credentials_set'] = True
            st.success("Credentials Loaded!")
        else:
            st.error("Please fill in all keys.")

# --- 3. CORE LOGIC (OPENAI VERSION) ---

def generate_recipe(user_query, model_name):
    """
    Brain 1: The Architect. Converts natural language -> JSON Recipe.
    """
    try:
        client = OpenAI(api_key=openai_api_key)
        
        system_prompt = """
        You are a Research Architect. Convert the User Goal into a strict JSON configuration for a Reddit scraper.
        Output JSON ONLY. No markdown, no conversational text.
        Structure:
        {
          "project_name": "Short Name",
          "target_subreddits": ["list", "of", "5", "subreddits"],
          "search_keywords": ["list", "of", "5", "keywords"],
          "ai_instruction": "Specific data extraction goal"
        }
        """
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"USER GOAL: {user_query}"}
            ],
            response_format={"type": "json_object"} # OpenAI's native JSON mode ensures valid JSON
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
        
    except Exception as e:
        st.error(f"❌ Error generating recipe: {e}")
        return None

def run_universal_engine(recipe, model_name):
    """
    Brain 2: The Engine. Scrapes and Analyzes based on the Recipe.
    """
    # 1. Setup Reddit
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent="UniversalEngine/OpenAI_v1"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # 2. Scan Subreddits
    total_subs = len(recipe['target_subreddits'])
    
    for i, sub in enumerate(recipe['target_subreddits']):
        status_text.markdown(f"🕵️ Scanning **r/{sub}**...")
        progress_bar.progress((i + 1) / total_subs)
        
        try:
            subreddit = reddit.subreddit(sub)
            query = " OR ".join(recipe['search_keywords'])
            
            # Fetch last 15 posts
            for post in subreddit.search(query, sort="relevance", time_filter="month", limit=15):
                if post.num_comments > 2: 
                    collected_data.append(f"Title: {post.title}\nBody: {post.selftext[:800]}\nUrl: {post.url}")
                time.sleep(0.2) # Polite delay
                
        except Exception as e:
            st.warning(f"Skipped r/{sub}: {e}")

    # 3. Final Analysis
    status_text.text("🧠 Analyzing collected data with OpenAI...")
    
    if not collected_data:
        return "⚠️ No relevant data found. Try broader keywords."

    full_text_blob = "\n---\n".join(collected_data[:25])
    
    client = OpenAI(api_key=openai_api_key)
    
    final_system_prompt = f"""
    You are a Senior Market Analyst.
    PROJECT: {recipe['project_name']}
    GOAL: {recipe['ai_instruction']}
    
    TASK:
    Write a clear, structured Executive Report based on the provided Reddit data.
    - Highlight 'Winners' and 'Red Flags'.
    - Use Markdown (Bold, Tables, Bullet points).
    - Be specific (mention specific brands/tools found in text).
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

st.title("🚀 Universal Insight Engine (OpenAI)")
st.markdown("Research anything on Reddit. Describe your goal, and the AI will build a strategy.")

user_query = st.text_area("What do you want to find out?", placeholder="e.g. Compare top recruiter tools or Find best credit cards in Dubai", height=100)

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
    edited_recipe = st.data_editor(st.session_state['current_recipe'], num_rows="dynamic")
    
    if st.button("🚀 Launch Research", type="primary"):
        with st.spinner("Running Engine..."):
            report = run_universal_engine(edited_recipe, selected_model)
            st.session_state['final_report'] = report

if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Report")
    st.markdown(st.session_state['final_report'])
