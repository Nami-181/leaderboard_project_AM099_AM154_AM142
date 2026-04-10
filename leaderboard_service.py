# leaderboard_service.py - The brain that handles scores

import redis
import json
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class ScoreEntry:
    user_id: str
    score: float
    timestamp: float
    server_id: str
    version: int = 1
    
    def to_dict(self):
        return asdict(self)

class DistributedLeaderboard:
    def __init__(self, server_id: str, redis_client: redis.Redis):
        self.server_id = server_id
        self.redis = redis_client
        self.leaderboard_key = "global:leaderboard"
        self.updates_channel = "score:updates"
        
    def submit_score(self, user_id: str, score: float) -> Dict:
        """Add a new score"""
        timestamp = time.time()
        
        entry = ScoreEntry(
            user_id=user_id,
            score=score,
            timestamp=timestamp,
            server_id=self.server_id,
            version=self._get_next_version(user_id)
        )
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        pipe.zadd(self.leaderboard_key, {user_id: float(score)})
        pipe.hset(f"user:{user_id}", mapping=entry.to_dict())
        pipe.publish(self.updates_channel, json.dumps(entry.to_dict()))
        pipe.execute()
        
        return {
            "status": "success",
            "rank": self.get_user_rank(user_id),
            "entry": entry.to_dict()
        }
    
    def _get_next_version(self, user_id: str) -> int:
        current = self.redis.hget(f"user:{user_id}", "version")
        return int(current) + 1 if current else 1
    
    def get_user_rank(self, user_id: str) -> Optional[int]:
        rank = self.redis.zrevrank(self.leaderboard_key, user_id)
        return rank + 1 if rank is not None else None
    
    def get_top_k(self, k: int = 10) -> List[Dict]:
        """Get top K players"""
        top_users = self.redis.zrevrange(
            self.leaderboard_key, 0, k - 1, withscores=True
        )
        
        result = []
        for user_id, score in top_users:
            user_id = user_id.decode() if isinstance(user_id, bytes) else user_id
            user_data = self.redis.hgetall(f"user:{user_id}")
            
            details = {}
            for k, v in user_data.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else v
                details[key] = val
            
            result.append({
                "user_id": user_id,
                "score": score,
                "details": details
            })
        return result
    
    def get_leaderboard_around_user(self, user_id: str, window: int = 5) -> List[Dict]:
        """Get ranks around a specific user"""
        rank = self.get_user_rank(user_id)
        if not rank:
            return []
        
        start = max(0, rank - window - 1)
        end = rank + window - 1
        
        users = self.redis.zrevrange(
            self.leaderboard_key, start, end, withscores=True
        )
        
        result = []
        for idx, (uid, score) in enumerate(users, start=start+1):
            uid = uid.decode() if isinstance(uid, bytes) else uid
            user_data = self.redis.hgetall(f"user:{uid}")
            
            server = "unknown"
            if user_data:
                s = user_data.get(b'server_id') or user_data.get('server_id')
                if s:
                    server = s.decode() if isinstance(s, bytes) else s
            
            result.append({
                "rank": idx,
                "user_id": uid,
                "score": score,
                "is_current_user": uid == user_id,
                "server": server
            })
        return result