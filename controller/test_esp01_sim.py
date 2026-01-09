import time
import json
import uuid
import paho.mqtt.client as mqtt

# Simulate 3 Devices
DEVICES = [f"MAC_{i}" for i in range(3)]
CONFIGS = {}

def on_connect(client, userdata, flags, rc):
    print(f"[{userdata}] Connected")
    # Subscribe to personal config topic
    client.subscribe(f"esp01/config/{userdata}")

def on_message(client, userdata, msg):
    print(f"[{userdata}] Msg on {msg.topic}: {msg.payload.decode()}")
    if "config" in msg.topic:
        data = json.loads(msg.payload.decode())
        CONFIGS[userdata] = data
        print(f"[{userdata}] Configured as P{data.get('player_id')}")

def run_sim():
    clients = []
    
    print("--- Starting ESP-01 Simulation ---")
    
    # Create clients
    for mac in DEVICES:
        client = mqtt.Client(client_id=f"SIM_ESP01_{mac}", userdata=mac)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect("localhost", 1883, 60)
        client.loop_start()
        clients.append(client)
        time.sleep(0.1)

    print("--- Sending Register Requests ---")
    # Send Register Requests
    for client in clients:
        mac = client._userdata
        payload = json.dumps({"mac": mac})
        client.publish("esp01/register", payload)
        print(f"[{mac}] Sent Register Request")
        time.sleep(0.5)
        
    print("--- Waiting for Configs ---")
    time.sleep(3)
    
    # Verification
    print("\n--- RESULTS ---")
    passed = True
    ids = set()
    for mac in DEVICES:
        if mac in CONFIGS:
            pid = CONFIGS[mac].get("player_id")
            ids.add(pid)
            print(f"PASS: {mac} -> P{pid}")
        else:
            print(f"FAIL: {mac} -> No Config")
            passed = False
            
    if len(ids) == 3:
        print("PASS: All 3 IDs transmitted unique")
    else:
        print(f"FAIL: Duplicate or missing IDs: {ids}")
        passed = False
        
    for c in clients:
        c.loop_stop()
        c.disconnect()

if __name__ == "__main__":
    run_sim()
