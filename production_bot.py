import praw
from openai import OpenAI
import sqlite3
import os
import time
import logging
from datetime import datetime, timedelta

# --- 1. CONFIGURATION ---
STRATEGY = {
    "project_name": "Recruiter Tool Watch",
    "target_subreddits": ["recruiting", "humanresources", "technicalrecruiting", "sales"],
    "search_keywords": ["ATS", "CRM", "AI sourcing", "automation", "pricing", "scam"],
    "report_hour": 18,  # 6:00 PM
    "min_heat_score": 2 # Only consider posts with at least 2 interactions for the 'Top' list
}

# Load Keys (Ensure these are set in your environment or .env file)
REDDIT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# Setup Logging (So you can see what happened while you were sleeping)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("watchdog.log"),
        logging.StreamHandler()
    ]
)

# --- 2. DATABASE LAYER (The Ironclad Storage) ---
DB_FILE = "market_intel.db"

def init_db():
    """Creates the database structure if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Create Posts Table
    c.execute('''CREATE TABLE IF NOT EXISTS posts
                 (id TEXT PRIMARY KEY, 
                  subreddit TEXT, 
                  title TEXT, 
                  body TEXT, 
                  url TEXT, 
                  heat_score INTEGER,
                  captured_at TIMESTAMP,
                  is_reported BOOLEAN DEFAULT 0)''')
    conn.commit()
    conn.close()

def save_post(post_data):
    """Saves a post safely. Ignores duplicates automatically."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO posts (id, subreddit, title, body, url, heat_score, captured_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                     (post_data['id'], post_data['subreddit'], post_data['title'], 
                      post_data['body'], post_data['url'], post_data['heat_score'], datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Database Write Error: {e}")
        return False

def get_unreported_data():
    """Fetches all data collected today that hasn't been in a report yet."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Get posts from the last 24 hours
    since_time = datetime.now() - timedelta(hours=24)
    c.execute("SELECT * FROM posts WHERE captured_at > ? ORDER BY heat_score DESC", (since_time,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- 3. THE WATCHDOG (Resilient Scanner) ---
def run_hourly_scan():
    logging.info("🐺 Watchdog waking up for scan...")
    
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_ID,
            client_secret=REDDIT_SECRET,
            user_agent="ProductionWatchdog/2.0"
        )
        
        total_new = 0
        
        for sub in STRATEGY['target_subreddits']:
            try:
                subreddit = reddit.subreddit(sub)
                query = " OR ".join(STRATEGY['search_keywords'])
                
                # Fetch up to 50 recent posts to ensure coverage
                for post in subreddit.search(query, sort="new", time_filter="day", limit=50):
                    
                    # Calculate "Heat Score" (Simple Engagement Metric)
                    heat = post.score + post.num_comments
                    
                    post_data = {
                        "id": post.id,
                        "subreddit": sub,
                        "title": post.title,
                        "body": post.selftext[:1000], # Store more text for better context
                        "url": post.url,
                        "heat_score": heat
                    }
                    
                    # save_post returns True if it's new, False if it already existed
                    save_post(post_data)
                    total_new += 1
                    
            except Exception as e:
                logging.error(f"Failed scanning r/{sub}: {e}")
                continue # Keep scanning other subreddits even if one fails
                
        logging.info(f"✅ Scan Complete. Processed {total_new} items.")
        
    except Exception as e:
        logging.critical(f"🔥 CRITICAL FAILURE in Watchdog: {e}")

# --- 4. THE ANALYST (Smart Reporter) ---
def generate_daily_report():
    logging.info("📊 Analyst starting Daily Report generation...")
    
    raw_data = get_unreported_data()
    
    if not raw_data:
        logging.warning("No data found for report. Skipping.")
        return

    # Convert DB rows to text format
    # Row indices: 0=id, 1=sub, 2=title, 3=body, 4=url, 5=heat
    
    # Priority 1: High Heat Items (The Signal)
    high_heat = [r for r in raw_data if r[5] >= STRATEGY['min_heat_score']]
    # Priority 2: Everything else (The Noise - limit this to save tokens)
    low_heat = [r for r in raw_data if r[5] < STRATEGY['min_heat_score']][:20]
    
    combined_data = high_heat + low_heat
    
    text_blob = "\n".join([f"[{row[5]} pts] r/{row[1]}: {row[2]}\nContext: {row[3][:300]}..." for row in combined_data])
    
    client = OpenAI(api_key=OPENAI_KEY)
    
    system_prompt = f"""
    You are a Strategic Intelligence Analyst.
    
    INPUT DATA:
    A list of {len(combined_data)} Reddit discussions about {STRATEGY['project_name']}.
    Format: [Engagement Score] r/Subreddit: Title...
    
    OBJECTIVE:
    Write a "Daily Market Intelligence Brief" (Markdown).
    
    STRUCTURE:
    1. 🚨 **Flash Alerts:** Any urgent negative sentiment or scam warnings?
    2. 🔥 **Heat Map:** What is the #1 most discussed topic today?
    3. ⚔️ **Vendor Battle:** Compare specific tools mentioned. (Who is winning?)
    4. 💡 **Strategic Opportunity:** One actionable recommendation based on today's data.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text_blob}
            ]
        )
        
        report_text = response.choices[0].message.content
        
        # Save Report
        filename = f"Daily_Intel_{datetime.now().strftime('%Y-%m-%d')}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_text)
            
        logging.info(f"🚀 Report successfully saved: {filename}")
        
    except Exception as e:
        logging.error(f"AI Analysis Failed: {e}")

# --- 5. MAIN EXECUTION LOOP ---
if __name__ == "__main__":
    init_db()
    logging.info("🛡️ System Online. Database Initialized.")
    
    # Run an immediate scan on startup to verify connectivity
    run_hourly_scan()
    
    while True:
        now = datetime.now()
        
        # Check if it is Report Hour (and we are in the first few minutes of that hour)
        if now.hour == STRATEGY['report_hour'] and now.minute < 5:
            generate_daily_report()
            # Sleep 65 minutes to ensure we don't double-report
            logging.info("💤 Report generated. Long sleep initiated.")
            time.sleep(3900) 
            continue
            
        # Normal Hourly Sleep (3600 seconds)
        logging.info("💤 Sleeping for 60 minutes...")
        time.sleep(3600)
        
        # Wake up and Scan
        run_hourly_scan()
