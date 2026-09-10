"""
Damisile AI Telegram Bot - Live Web Analytics Dashboard
======================================================
Serves real-time usage statistics, action distributions, and activity logs.
"""

from flask import Flask, render_template, jsonify, request
from database import get_analytics_stats, get_recent_downloads, get_connection
from config import logger

app = Flask(__name__)

@app.route("/")
def dashboard_home():
    stats = get_analytics_stats()
    return render_template("dashboard.html", stats=stats)

@app.route("/api/stats")
def api_stats():
    return jsonify(get_analytics_stats())

@app.route("/api/logs")
def api_logs():
    conn = get_connection()
    limit = request.args.get("limit", 100, type=int)
    action = request.args.get("action", "", type=str)
    
    if action:
        rows = conn.execute(
            "SELECT * FROM activity_logs WHERE action_type=? ORDER BY timestamp DESC LIMIT ?",
            (action, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
    
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    logger.info(f"🌐 Starting Web Analytics Dashboard on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
