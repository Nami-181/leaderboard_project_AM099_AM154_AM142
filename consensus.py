# consensus.py - FIXED VERSION

import asyncio
import aiohttp
import time
from typing import Dict

class RaftConsensus:
    def __init__(self, server_id: str, servers: Dict, redis_client):
        self.server_id = server_id
        self.servers = servers
        self.redis = redis_client
        self.current_term = 0
        self.state = "follower"
        self.voted_for = None
        self.leader_id = None
        self.last_heartbeat = time.time()
        # Random timeout between 10-20 seconds so servers don't conflict
        self.election_timeout = 10 + (hash(server_id) % 10)
        
    async def start(self):
        """Main loop"""
        while True:
            if self.state == "follower":
                await self._follower_loop()
            elif self.state == "candidate":
                await self._candidate_loop()
            elif self.state == "leader":
                await self._leader_loop()
    
    async def _follower_loop(self):
        while self.state == "follower":
            await asyncio.sleep(0.1)
            if time.time() - self.last_heartbeat > self.election_timeout:
                self.state = "candidate"
                self.current_term += 1
                print(f"[{self.server_id}] Timeout! Becoming candidate for term {self.current_term}")
    
    async def _candidate_loop(self):
        votes = {self.server_id}  # Vote for self
        self.voted_for = self.server_id
        
        print(f"[{self.server_id}] Requesting votes for term {self.current_term}...")
        
        # Request votes from all other servers
        for sid, config in self.servers.items():
            if sid != self.server_id:
                try:
                    vote = await self._request_vote(sid, config)
                    if vote:
                        votes.add(sid)  # Add the server ID who voted, not boolean
                        print(f"[{self.server_id}] Got vote from {sid}")
                except Exception as e:
                    print(f"[{self.server_id}] Failed to get vote from {sid}: {e}")
        
        print(f"[{self.server_id}] Total votes: {len(votes)}/{len(self.servers)}")
        
        # Need majority (> 50%)
        if len(votes) > len(self.servers) / 2:
            await self._become_leader()
        else:
            print(f"[{self.server_id}] Election failed, returning to follower")
            self.state = "follower"
            self.last_heartbeat = time.time()
            await asyncio.sleep(2)  # Wait before trying again
    
    async def _request_vote(self, server_id: str, config: Dict) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://{config['host']}:{config['port']}/vote",
                    json={"term": self.current_term, "candidate_id": self.server_id},
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("vote_granted", False)
        except Exception as e:
            print(f"[{self.server_id}] Vote request to {server_id} failed: {e}")
        return False
    
    async def _become_leader(self):
        self.state = "leader"
        self.leader_id = self.server_id
        print(f"\n{'='*50}")
        print(f"[{self.server_id}] *** BECAME LEADER ***")
        print(f"{'='*50}\n")
        self.redis.set("current_leader", self.server_id)
        self.redis.set("current_term", self.current_term)
    
    async def _leader_loop(self):
        """Send heartbeats to followers"""
        while self.state == "leader":
            for sid, config in self.servers.items():
                if sid != self.server_id:
                    try:
                        async with aiohttp.ClientSession() as session:
                            await session.post(
                                f"http://{config['host']}:{config['port']}/heartbeat",
                                json={"term": self.current_term, "leader_id": self.server_id, "timestamp": time.time()},
                                timeout=aiohttp.ClientTimeout(total=1)
                            )
                    except:
                        pass  # Follower might be down
            await asyncio.sleep(2)  # Heartbeat every 2 seconds
    
    def handle_heartbeat(self, term: int, leader_id: str) -> Dict:
        if term >= self.current_term:
            if term > self.current_term:
                self.current_term = term
                self.voted_for = None
            
            if self.state != "follower":
                print(f"[{self.server_id}] Stepping down, {leader_id} is now leader")
            
            self.state = "follower"
            self.leader_id = leader_id
            self.last_heartbeat = time.time()
            return {"success": True}
        return {"success": False, "reason": "stale_term"}
    
    def handle_vote_request(self, term: int, candidate_id: str) -> Dict:
        # Reject if term is old
        if term < self.current_term:
            return {"vote_granted": False, "reason": "stale_term"}
        
        # Update term if newer
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
        
        # Grant vote if we haven't voted or already voted for this candidate
        if self.voted_for is None or self.voted_for == candidate_id:
            self.voted_for = candidate_id
            self.last_heartbeat = time.time()
            print(f"[{self.server_id}] Voted for {candidate_id} in term {term}")
            return {"vote_granted": True, "term": self.current_term}
        
        return {"vote_granted": False, "reason": "already_voted"}
    
    def is_leader(self) -> bool:
        return self.state == "leader"