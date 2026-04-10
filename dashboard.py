# dashboard.py - WORKING VERSION with HTTP polling (no WebSocket issues)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import redis
import json
import asyncio
import aiohttp
import time
from config import SERVERS, REDIS_CONFIG

app = FastAPI()
r = redis.Redis(**REDIS_CONFIG)

# Simple HTML that auto-refreshes every 2 seconds
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>🏆 Distributed Leaderboard</title>
    <meta http-equiv="refresh" content="2">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 20px;
            margin: 0;
        }
        h1 { text-align: center; font-size: 2.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .container { max-width: 1200px; margin: 0 auto; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .panel {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .panel h2 { color: #ffd700; border-bottom: 2px solid rgba(255,215,0,0.3); padding-bottom: 10px; margin-bottom: 15px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { color: #ffd700; }
        .rank-1 { color: #ffd700; font-weight: bold; font-size: 1.2em; }
        .rank-2 { color: #c0c0c0; font-weight: bold; }
        .rank-3 { color: #cd7f32; font-weight: bold; }
        .score { color: #00ff88; font-weight: bold; }
        .server-box {
            display: inline-block;
            background: rgba(0,0,0,0.3);
            padding: 15px;
            margin: 5px;
            border-radius: 10px;
            min-width: 150px;
            text-align: center;
        }
        .server-box.leader { border: 3px solid #ffd700; background: rgba(255,215,0,0.2); }
        .status-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .online { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
        .offline { background: #ff4444; }
        .leader-dot { background: #ffd700; box-shadow: 0 0 10px #ffd700; }
        .error { color: #ff6b6b; text-align: center; padding: 20px; }
        .refresh-note { text-align: center; color: #aaa; font-size: 0.9em; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏆 Distributed Leaderboard System</h1>
        
        <div class="grid">
            <div class="panel">
                <h2>📊 Live Leaderboard (Top 10)</h2>
                {{LEADERBOARD}}
                <div class="refresh-note">Auto-refreshing every 2 seconds...</div>
            </div>
            
            <div class="panel">
                <h2>🖥️ Server Status</h2>
                {{SERVERS}}
                <h3 style="margin-top: 20px; color: #ffd700;">📈 Metrics</h3>
                <p>Total Users: <strong style="color: #00ff88;">{{TOTAL_USERS}}</strong></p>
                <p>Last Updated: {{TIMESTAMP}}</p>
            </div>
        </div>
        
        <div class="panel">
            <h2>🎮 Manual Score Entry</h2>
            <form action="/add-score" method="post" style="margin-top: 10px;">
                <input type="text" name="user_id" placeholder="Username" required style="padding: 8px; margin-right: 10px;">
                <input type="number" name="score" placeholder="Score" required style="padding: 8px; margin-right: 10px; width: 100px;">
                <button type="submit" style="padding: 8px 20px; background: #ffd700; color: #1e3c72; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">Submit Score</button>
            </form>
            <br>
            <a href="/simulate" style="display: inline-block; padding: 10px 20px; background: #00ff88; color: #1e3c72; text-decoration: none; border-radius: 5px; font-weight: bold;">🎲 Simulate 20 Random Users</a>
        </div>
    </div>
</body>
</html>
"""

async def fetch_from_all_servers():
    """Fetch data from all servers"""
    leaderboard = []
    server_status = []
    leader_found = False
    
    for sid, config in SERVERS.items():
        try:
            async with aiohttp.ClientSession() as session:
                # Check health
                try:
                    async with session.get(
                        f"http://{config['host']}:{config['port']}/health",
                        timeout=aiohttp.ClientTimeout(total=1)
                    ) as resp:
                        health = await resp.json()
                        is_leader = health.get('is_leader', False)
                        if is_leader:
                            leader_found = True
                        
                        server_status.append({
                            'id': sid,
                            'port': config['port'],
                            'healthy': True,
                            'is_leader': is_leader,
                            'role': health.get('role', 'unknown'),
                            'term': health.get('term', 0)
                        })
                except:
                    server_status.append({
                        'id': sid,
                        'port': config['port'],
                        'healthy': False,
                        'is_leader': False,
                        'role': 'offline',
                        'term': 0
                    })
                
                # Get leaderboard from this server
                try:
                    async with session.get(
                        f"http://{config['host']}:{config['port']}/leaderboard",
                        params={"top_k": 10},
                        timeout=aiohttp.ClientTimeout(total=2)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('data') and len(data['data']) > len(leaderboard):
                                leaderboard = data['data']
                except:
                    pass
                    
        except Exception as e:
            print(f"Error fetching from {sid}: {e}")
    
    return leaderboard, server_status, leader_found

def generate_leaderboard_html(data):
    """Generate HTML table for leaderboard"""
    if not data:
        return '<div class="error">No data available. Make sure servers are running and a leader is elected.</div>'
    
    html = '<table><tr><th>Rank</th><th>User</th><th>Score</th><th>Server</th></tr>'
    
    for i, entry in enumerate(data[:10]):
        rank = i + 1
        rank_class = f'rank-{rank}' if rank <= 3 else ''
        user_id = entry.get('user_id', 'Unknown')
        score = int(entry.get('score', 0))
        
        # Get server info
        details = entry.get('details', {})
        server = details.get('server_id', 'unknown') if isinstance(details, dict) else 'unknown'
        
        html += f'<tr class="{rank_class}">'
        html += f'<td>#{rank}</td>'
        html += f'<td>{user_id}</td>'
        html += f'<td class="score">{score} pts</td>'
        html += f'<td>{server}</td>'
        html += '</tr>'
    
    html += '</table>'
    return html

def generate_servers_html(servers):
    """Generate HTML for server status"""
    if not servers:
        return '<div class="error">No servers responding</div>'
    
    html = ''
    for s in servers:
        status_class = 'leader-dot' if s['is_leader'] else ('online' if s['healthy'] else 'offline')
        box_class = 'leader' if s['is_leader'] else ''
        
        html += f'<div class="server-box {box_class}">'
        html += f'<span class="status-dot {status_class}"></span>'
        html += f'<strong>{s["id"]}</strong><br>'
        html += f'Port: {s["port"]}<br>'
        html += f'Role: {s["role"]}<br>'
        if s['is_leader']:
            html += '<strong style="color: #ffd700;">👑 LEADER</strong>'
        html += '</div>'
    
    return html

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    try:
        # Fetch data from servers
        leaderboard_data, server_status, leader_found = await fetch_from_all_servers()
        
        # Get total users from Redis
        try:
            total_users = r.zcard("global:leaderboard")
        except:
            total_users = 0
        
        # Generate HTML
        leaderboard_html = generate_leaderboard_html(leaderboard_data)
        servers_html = generate_servers_html(server_status)
        
        # Fill template
        html = DASHBOARD_HTML.replace('{{LEADERBOARD}}', leaderboard_html)
        html = html.replace('{{SERVERS}}', servers_html)
        html = html.replace('{{TOTAL_USERS}}', str(total_users))
        html = html.replace('{{TIMESTAMP}}', time.strftime('%H:%M:%S'))
        
        if not leader_found and server_status:
            html = html.replace('</body>', '<div style="background: #ff4444; color: white; padding: 10px; text-align: center; margin: 20px 0; border-radius: 5px;">⚠️ WARNING: No leader elected! System cannot accept writes.</div></body>')
        
        return HTMLResponse(content=html)
        
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error</h1><p>{str(e)}</p><p>Make sure all servers are running!</p>")

@app.post("/add-score")
async def add_score(user_id: str, score: int):
    """Add a score manually"""
    # Try to find leader and submit
    for sid, config in SERVERS.items():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{config['host']}:{config['port']}/health",
                    timeout=aiohttp.ClientTimeout(total=1)
                ) as resp:
                    health = await resp.json()
                    if health.get('is_leader'):
                        # Submit to leader
                        async with session.post(
                            f"http://{config['host']}:{config['port']}/submit_score",
                            json={"user_id": user_id, "score": score},
                            timeout=aiohttp.ClientTimeout(total=2)
                        ) as submit_resp:
                            if submit_resp.status == 200:
                                return HTMLResponse(content=f'<meta http-equiv="refresh" content="0; url=/" />')
        except:
            continue
    
    return HTMLResponse(content='<h1>Error: No leader available</h1><a href="/">Go Back</a>')

@app.get("/simulate")
async def simulate():
    """Simulate random traffic"""
    import random
    import asyncio
    
    async def run_sim():
        async with aiohttp.ClientSession() as session:
            for i in range(20):
                user = f"player_{random.randint(1, 10)}"
                score = random.randint(100, 1000)
                
                # Find leader
                for sid, config in SERVERS.items():
                    try:
                        async with session.get(
                            f"http://{config['host']}:{config['port']}/health",
                            timeout=aiohttp.ClientTimeout(total=1)
                        ) as resp:
                            health = await resp.json()
                            if health.get('is_leader'):
                                await session.post(
                                    f"http://{config['host']}:{config['port']}/submit_score",
                                    json={"user_id": user, "score": score},
                                    timeout=aiohttp.ClientTimeout(total=2)
                                )
                                break
                    except:
                        continue
                
                await asyncio.sleep(0.1)
    
    asyncio.create_task(run_sim())
    return HTMLResponse(content='<meta http-equiv="refresh" content="0; url=/" />')

if __name__ == "__main__":
    print("="*60)
    print("🌐 Dashboard starting at http://localhost:8080")
    print("="*60)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)