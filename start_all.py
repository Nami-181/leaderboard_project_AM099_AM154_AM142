import subprocess
import time
import sys

print("Starting all servers...")

# Start server 1
p1 = subprocess.Popen([sys.executable, "server.py", "server1"], 
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
print(f"Server 1 started (PID: {p1.pid})")
time.sleep(2)

# Start server 2  
p2 = subprocess.Popen([sys.executable, "server.py", "server2"],
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
print(f"Server 2 started (PID: {p2.pid})")
time.sleep(2)

# Start server 3
p3 = subprocess.Popen([sys.executable, "server.py", "server3"],
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
print(f"Server 3 started (PID: {p3.pid})")
time.sleep(3)

# Start dashboard
p4 = subprocess.Popen([sys.executable, "dashboard.py"],
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
print(f"Dashboard started (PID: {p4.pid})")

print("\n✅ All systems started!")
print("📊 Open http://localhost:8080")
print("\nPress Ctrl+C to stop all")
input()