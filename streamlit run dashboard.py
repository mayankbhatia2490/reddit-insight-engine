import streamlit as st
import sqlite3
import pandas as pd
import os

st.set_page_config(page_title="Intel Watchdog Dashboard", layout="wide")

DB_FILE = "market_intel.db"

def load_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    
    conn = sqlite3.connect(DB_FILE)
    # Load all posts, newest first
    df = pd.read_sql_query("SELECT * FROM posts ORDER BY captured_at DESC", conn)
    conn.close()
    return df

st.title("🐺 Watchdog Live Feed")

if st.button("🔄 Refresh Data"):
    st.rerun()

df = load_data()

if df.empty:
    st.warning("⚠️ No data found yet. Make sure 'production_bot.py' is running in your terminal!")
else:
    # Top Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Posts Captured", len(df))
    col2.metric("High Interest (Heat > 2)", len(df[df['heat_score'] >= 2]))
    col3.metric("Last Scan", df['captured_at'].iloc[0][:16] if not df.empty else "N/A")

    st.divider()
    
    # The Data Table
    st.subheader("📥 Incoming Intelligence")
    
    # Show highest heat first
    st.dataframe(
        df[['heat_score', 'subreddit', 'title', 'captured_at', 'url']],
        use_container_width=True,
        column_config={
            "url": st.column_config.LinkColumn("Link"),
            "heat_score": st.column_config.NumberColumn("Heat 🔥")
        }
    )
