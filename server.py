# server.py - The actual server that runs

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import asyncio
import uvicorn
import sys
from contextlib import asynccontextmanager

from config import SERVERS, REDIS_CONFIG
from leaderboard_service import DistributedLeaderboard
from consensus import RaftConsensus

class ScoreSubmission(BaseModel):
    user_id: str
    score: float

class VoteRequest(BaseModel):
    term: int
    candidate_id: str

class Heartbeat(BaseModel):
    term: int
    leader_id: str
    timestamp: float

leaderboard_service = None
consensus = None
server_config = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global leaderboard_service, consensus, server_config
    
    server_id = sys.argv[1] if len(sys.argv) > 1 else "server1"
    server_config = SERVERS[server_id]
    
    redis_client = redis.Redis(**REDIS_CONFIG)
    leaderboard_service = DistributedLeaderboard(server_id, redis_client)
    consensus = RaftConsensus(server_id, SERVERS, redis_client)
    
    consensus_task = asyncio.create_task(consensus.start())
    
    print(f"\n{'='*50}")
    print(f"🚀 SERVER {server_id.upper()} STARTED")
    print(f"📡 Port: {server_config['port']}")
    print(f"🎯 Role: {server_config['role']}")
    print(f"{'='*50}\n")
    
    yield
    
    consensus_task.cancel()
    redis_client.close()

app = FastAPI(title=f"Leaderboard Server", lifespan=lifespan)

@app.post("/submit_score")
async def submit_score(submission: ScoreSubmission):
    """Submit a new score - only leader accepts writes"""
    if not consensus.is_leader():
        leader = consensus.leader_id
        if leader:
            raise HTTPException(
                status_code=307, 
                headers={"Location": f"http://localhost:{SERVERS[leader]['port']}/submit_score"},
                detail=f"Redirect to leader {leader}"
            )
        raise HTTPException(status_code=503, detail="No leader elected")
    
    result = leaderboard_service.submit_score(submission.user_id, submission.score)
    return result

@app.get("/leaderboard")
async def get_leaderboard(top_k: int = 10, user_id: str = None):
    """Get leaderboard - any server can serve reads"""
    if user_id:
        data = leaderboard_service.get_leaderboard_around_user(user_id)
    else:
        data = leaderboard_service.get_top_k(top_k)
    
    return {
        "server": server_config['port'],
        "role": consensus.state,
        "data": data,
        "timestamp": __import__('time').time()
    }

@app.get("/rank/{user_id}")
async def get_rank(user_id: str):
    rank = leaderboard_service.get_user_rank(user_id)
    if rank is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "rank": rank}

@app.post("/vote")
async def request_vote(vote_req: VoteRequest):
    result = consensus.handle_vote_request(vote_req.term, vote_req.candidate_id)
    return result

@app.post("/heartbeat")
async def receive_heartbeat(heartbeat: Heartbeat):
    result = consensus.handle_heartbeat(heartbeat.term, heartbeat.leader_id)
    return result

@app.get("/health")
async def health_check():
    return {
        "server_id": [k for k,v in SERVERS.items() if v == server_config][0] if server_config else "unknown",
        "status": "healthy",
        "role": consensus.state if consensus else "unknown",
        "is_leader": consensus.is_leader() if consensus else False,
        "term": consensus.current_term if consensus else 0
    }

if __name__ == "__main__":
    server_id = sys.argv[1] if len(sys.argv) > 1 else "server1"
    port = SERVERS[server_id]['port']
    uvicorn.run(app, host="0.0.0.0", port=port)