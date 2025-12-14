import streamlit as st
import praw
import google.generativeai as genai
import json
import os
import time

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Universal Insight Engine", page_icon="🔍", layout="wide")

# --- 2. SIDEBAR: CREDENTIALS (BYOK Model) ---
with st.sidebar:
    st.header("🔑 API Keys")
    st.info("Your keys are safe. They are only used for this session.")
    
    # Check if keys exist in environment (for local dev), otherwise ask user
    env_reddit_id = os.getenv("REDDIT_CLIENT_ID", "")
    env_reddit_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    env_gemini_key = os.getenv("GEMINI_API_KEY", "")

    reddit_client_id = st.text_input("Reddit Client ID", value=env_reddit_id, type="password")
    reddit_client_secret = st.text_input("Reddit Client Secret", value=env_reddit_secret, type="password")
    gemini_api_key = st.text_input("Gemini API Key", value=env_gemini_key, type="password")
    
    if st.button("Save & Connect"):
        if reddit_client_id and gemini_api_key:
            st.session_state['credentials_set'] = True
            st.success("Credentials Loaded!")
        else:
            st.error("Please fill in all keys.")

# --- 3. CORE LOGIC (THE BRAINS) ---

def generate_recipe(user_query):
    """
    Brain 1: The Architect. Converts natural language -> JSON Recipe.
    """
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a Research Architect. Convert this User Goal into a strict JSON configuration for a Reddit scraper.
    
    USER GOAL: "{user_query}"
    
    Output JSON ONLY with this structure:
    {{
      "project_name": "Short Name",
      "target_subreddits": ["list", "of", "5", "most", "relevant", "subreddits"],
      "search_keywords": ["list", "of", "5", "specific", "search", "terms"],
      "ai_instruction": "Specific instructions on what data to extract (e.g. prices, pros/cons, specific features)."
    }}
    """
    try:
        response = model.generate_content(prompt)
        # Clean up markdown if AI adds it
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Error generating recipe: {e}")
        return None

def run_universal_engine(recipe):
    """
    Brain 2: The Engine. Scrapes and Analyzes based on the Recipe.
    """
    # 1. Setup Reddit
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent="UniversalEngine/1.0"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    # 2. Scan Subreddits
    total_subs = len(recipe['target_subreddits'])
    
    for i, sub in enumerate(recipe['target_subreddits']):
        status_text.text(f"🕵️ Scanning r/{sub} for '{recipe['project_name']}'...")
        progress_bar.progress((i + 1) / total_subs)
        
        try:
            subreddit = reddit.subreddit(sub)
            query = " OR ".join(recipe['search_keywords'])
            
            # Fetch last 10 relevant posts
            for post in subreddit.search(query, sort="relevance", time_filter="month", limit=10):
                post_content = f"Title: {post.title}\nBody: {post.selftext[:500]}\nComments: {post.num_comments}"
                collected_data.append(post_content)
                
        except Exception as e:
            st.warning(f"Skipped r/{sub}: {e}")

    # 3. Final Analysis (The Verdict)
    status_text.text("🧠 Analyzing collected data with AI...")
    
    if not collected_data:
        return "No relevant data found. Try broader keywords."

    # Send aggregated data to Gemini for the Final Report
    full_text_blob = "\n---\n".join(collected_data[:20]) # Limit to 20 posts to save tokens
    
    final_prompt = f"""
    You are a Senior Market Analyst.
    
    PROJECT: {recipe['project_name']}
    GOAL: {recipe['ai_instruction']}
    
    RAW DATA FROM REDDIT:
    {full_text_blob}
    
    TASK:
    Write a clear, structured Executive Report. 
    - Highlight the "Winners" (Products/Ideas).
    - Expose the "Red Flags" (Complaints/Risks).
    - Provide a direct answer to the user's goal.
    - Use Markdown formatting (Bold, Bullet points).
    """
    
    model = genai.GenerativeModel('gemini-1.5-pro') # Use Pro for better writing
    response = model.generate_content(final_prompt)
    
    status_text.empty()
    progress_bar.empty()
    return response.text

# --- 4. THE USER INTERFACE ---

st.title("🚀 Universal Insight Engine")
st.markdown("""
This tool allows you to **research anything** on Reddit. 
Just describe what you want, and the AI will build a custom research strategy.
""")

# Input Area
user_query = st.text_area("What do you want to find out?", 
                          placeholder="e.g., What are the best investment banks in UAE right now? or Compare the top 3 recruiter tools.")

if st.button("Generate Strategy"):
    if not st.session_state.get('credentials_set'):
        st.error("Please enter your API Keys in the Sidebar first!")
    elif not user_query:
        st.warning("Please enter a topic.")
    else:
        with st.spinner("🤖 AI is designing your research strategy..."):
            recipe = generate_recipe(user_query)
            if recipe:
                st.session_state['current_recipe'] = recipe
                st.success("Strategy Created!")

# Display Recipe & Run Button
if 'current_recipe' in st.session_state:
    st.divider()
    st.subheader("📋 Research Strategy (Editable)")
    
    # Allow user to edit the JSON before running
    edited_recipe = st.data_editor(st.session_state['current_recipe'])
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🚀 Launch Research", type="primary"):
            with st.spinner("Running Universal Engine... (This may take 30s)"):
                report = run_universal_engine(edited_recipe)
                st.session_state['final_report'] = report

# Final Report Display
if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Intelligence Report")
    st.markdown(st.session_state['final_report'])
    
    st.download_button(
        label="📥 Download Report",
        data=st.session_state['final_report'],
        file_name="reddit_insight_report.md",
        mime="text/markdown"
    )