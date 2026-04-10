# config.py - Settings for all servers

SERVERS = {
    'server1': {'host': 'localhost', 'port': 8001, 'role': 'leader'},
    'server2': {'host': 'localhost', 'port': 8002, 'role': 'follower'},
    'server3': {'host': 'localhost', 'port': 8003, 'role': 'follower'}
}

REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0
}

HEARTBEAT_INTERVAL = 5
SYNC_INTERVAL = 2