import time
import json
import sys
import threading
from mqtt_bus import Bus

# --- ESP01 Manager (Test Logic) ---
class TestManager:
    def __init__(self, bus):
        self.bus = bus
        self.assignments = {} # mac -> player_id (0-2)
        self.assigned_ids = set()
        
    def handle_register(self, payload):
        mac = payload.get("mac")
        if not mac: return
        
        if mac in self.assignments:
            self._send_config(mac, self.assignments[mac])
        else:
            for pid in range(3):
                if pid not in self.assigned_ids:
                    self.assignments[mac] = pid
                    self.assigned_ids.add(pid)
                    print(f"\n[NEW] Assigned P{pid+1} to MAC {mac}")
                    self._send_config(mac, pid)
                    return
            print(f"\n[FULL] No slots for {mac}")

    def _send_config(self, mac, pid):
        config = {
            "player_id": pid + 1,
            "sensor_topic": f"esp01/player/{pid+1}/sensor",
            "led_topic": f"esp01/player/{pid+1}/led"
        }
        self.bus.pub(f"esp01/{mac}/config", config)

    def reset(self):
        self.assignments.clear()
        self.assigned_ids.clear()
        print("\n[RESET] All assignments cleared. restart ESPs to re-register.")

# --- Main Test Script ---
def run_test():
    print("="*50)
    print(" ESP-01 HARDWARE TESTER")
    print("="*50)
    print(" Commands:")
    print("  1, 2, 3 : Toggle LED for Player 1, 2, 3")
    print("  r       : Reset Assignments")
    print("  q       : Quit")
    print("-" * 50)
    print(" Waiting for ESP-01 connections...")

    # Shared State
    led_states = {1: "OFF", 2: "OFF", 3: "OFF"}

    def on_message(client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode()) if msg.payload else {}
        except:
            payload = msg.payload.decode()

        # Debug: Print everything to see what's happening
        # print(f" [DEBUG] {topic}: {payload}")

        if topic == "esp01/register":
            manager.handle_register(payload)
        
        elif topic.startswith("esp01/player/") and topic.endswith("/sensor"):
            # esp01/player/1/sensor
            try:
                parts = topic.split("/") 
                pid = int(parts[2])
                print(f" [SENSOR P{pid}] {payload}")
            except:
                print(f" [SENSOR ?] {payload}")

        elif topic.startswith("esp01/log/"):
            mac = topic.split("/")[-1]
            print(f" [LOG {mac}] {payload}")
            
        elif topic.startswith("esp01/") and topic.endswith("/status"):
            mac = topic.split("/")[1]
            print(f" [STATUS {mac}] {payload}")
            if payload == "ONLINE":
                # Auto-assign if not already assigned
                manager.handle_register({"mac": mac})     

        else:
            print(f" [UNKNOWN TOPIC] {topic}: {payload}")


    bus = Bus(on_msg=on_message)
    bus.subscribe("esp01/register")
    bus.subscribe("esp01/player/+/sensor")
    bus.subscribe("esp01/log/+")
    bus.subscribe("esp01/+/status")
    bus.start()

    manager = TestManager(bus)

    # Input Loop
    try:
        while True:
            cmd = input().strip().lower()
            if cmd == 'q':
                break
            elif cmd == 'r':
                manager.reset()
            elif cmd in ['1', '2', '3']:
                pid = int(cmd)
                new_state = "ON" if led_states[pid] == "OFF" else "OFF"
                led_states[pid] = new_state
                bus.pub(f"esp01/player/{pid}/led", new_state)
                print(f" [LED P{pid}] -> {new_state}")
            elif cmd == 'blink':
                 # Hidden command just to test BLINK
                 print(" Blinking all LEDs...")
                 for i in range(1,4):
                     bus.pub(f"esp01/player/{i}/led", "BLINK")
            
    except KeyboardInterrupt:
        pass
    finally:
        bus.stop()
        print("\nTest Stopped.")

if __name__ == "__main__":
    run_test()
