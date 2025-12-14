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

# --- HELPER: DATA EXTRACTOR ---
def get_list_from_data(data, column_name):
    """
    Robustly finds a column in the data, handling any format Streamlit throws at us.
    """
    try:
        # Convert whatever we have into a Pandas DataFrame
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            return []

        # clean column names
        df.columns = [str(c).lower().strip() for c in df.columns]
        target = column_name.lower().strip()

        # Find the column
        if target in df.columns:
            return df[target].dropna().astype(str).tolist()
        
        # Fallback: Check if any column contains the name
        for col in df.columns:
            if target in col:
                return df[col].dropna().astype(str).tolist()

        return []
    except:
        return []

# --- 3. CORE LOGIC ---

def generate_recipe(user_query, model_name):
    try:
        client = OpenAI(api_key=openai_api_key)
        
        # WE FORCE THE AI TO GENERATE A LIST OF 5 OBJECTS
        system_prompt = """
        You are a Research Architect. 
        Create a search strategy for the User's Goal.
        
        CRITICAL RULE: You must return a JSON LIST of exactly 5 distinct dictionaries (rows). 
        Do not group them into one line.
        
        Structure:
        [
           { "target_subreddit": "r/example1", "search_keywords": "keyword1 OR keyword2", "ai_instruction": "Extract pricing" },
           { "target_subreddit": "r/example2", "search_keywords": "keyword3", "ai_instruction": "Extract features" },
           ... (3 more rows)
        ]
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
        parsed = json.loads(content)
        
        # Handle if AI wraps it in a key like {"strategy": [...]}
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list): return v
            # If no list found, wrap the dict in a list
            return [parsed]
            
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
            user_agent="UniversalEngine/Visible_v9"
        )
    except Exception as e:
        return f"Error connecting to Reddit: {e}"

    collected_data = []
    
    # 2. EXTRACT TARGETS
    targets = get_list_from_data(recipe, 'target_subreddit') # Note singular 'subreddit'
    # fallback to plural if needed
    if not targets: targets = get_list_from_data(recipe, 'target_subreddits')
        
    keywords = get_list_from_data(recipe, 'search_keywords')
    
    # Clean up the list
    targets = [str(t).replace("r/", "").strip() for t in targets if t]
    targets = list(set(targets)) # Remove duplicates

    if not targets:
        return "❌ Error: No subreddits found. Please click 'Generate Strategy' again."

    # 3. VISIBLE SCANNING LOOP
    with st.status("🕵️ Scouring Reddit...", expanded=True) as status:
        
        for i, sub in enumerate(targets):
            try:
                st.write(f"**Scanning r/{sub}...**")
                subreddit = reddit.subreddit(sub)
                
                # Get specific keywords for this row if possible, else use first
                query = keywords[i] if i < len(keywords) else keywords[0]
                
                posts_found = 0
                # Fetch last 15 posts
                for post in subreddit.search(query, sort="relevance", time_filter="month", limit=15):
                    if post.num_comments > 0: 
                        collected_data.append(f"Source: r/{sub}\nTitle: {post.title}\nBody: {post.selftext[:500]}\nUrl: {post.url}")
                        posts_found += 1
                
                if posts_found > 0:
                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;✅ Found {posts_found} posts.")
                else:
                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;⚠️ No recent results.")
                    
                time.sleep(0.5) 
                
            except Exception as e:
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;❌ Failed to access: {e}")

        status.update(label="Scanning Complete!", state="complete", expanded=False)

    # 4. Final Analysis
    if not collected_data:
        return f"⚠️ No relevant data found. Try broader keywords."

    full_text_blob = "\n---\n".join(collected_data[:40])
    
    client = OpenAI(api_key=openai_api_key)
    
    final_system_prompt = f"""
    You are a Senior Market Analyst.
    TASK: Write a structured Executive Report (Markdown) based ONLY on the provided Reddit data.
    - Highlight "Winners" (Products/Tools mentioned positively).
    - Highlight "Complaints" (Specific negatives).
    - Quote specific user sentiments.
    """
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": f"RAW DATA:\n{full_text_blob}"}
            ]
        )
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
                st.success("Strategy Created! Check the table below to see the 5 targets.")

if 'current_recipe' in st.session_state:
    st.divider()
    st.subheader("📋 Research Strategy")
    
    # Using container width to ensure columns are visible
    edited_recipe = st.data_editor(st.session_state['current_recipe'], num_rows="dynamic", use_container_width=True)
    
    if st.button("🚀 Launch Research", type="primary"):
        # We don't use st.spinner here because we use the custom st.status inside the function
        report = run_universal_engine(edited_recipe, selected_model)
        st.session_state['final_report'] = report

if 'final_report' in st.session_state:
    st.divider()
    st.subheader("📊 Final Report")
    st.markdown(st.session_state['final_report'])
