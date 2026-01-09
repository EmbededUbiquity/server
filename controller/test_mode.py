import time
import json
import sys
from mqtt_bus import Bus

class TestRunner:
    def __init__(self):
        self.bus = None
        self.test_results = []
        self.current_test = ""
        self.button_received = False
        self.ack_received = False
        self.selected_tests = None  # None = run all
    
    def should_run(self, test_num):
        """Check if a specific test should run"""
        if self.selected_tests is None:
            return True
        return test_num in self.selected_tests
        
    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode() if msg.payload else ""
        
        if topic == "base/button":
            self.button_received = True
            data = json.loads(payload)
            print(f"  ✓ Button {data.get('button')} received")
        elif topic == "game/ack":
            self.ack_received = True
            print(f"  ✓ ACK received")
        elif topic == "game/connection":
            print(f"  → Connection: {payload}")
    
    def wait_for_input(self, prompt):
        input(f"\n[PRESS ENTER] {prompt}")
    
    def log_result(self, test_name, passed, note=""):
        status = "✓ PASS" if passed else "✗ FAIL"
        self.test_results.append((test_name, passed, note))
        print(f"  {status}: {test_name} {note}")
    
    def run_tests(self):
        print("\n" + "="*60)
        print("  MEEPLE'S GAMBIT - E2E TEST MODE")
        print("="*60)
        
        # Initialize
        self.bus = Bus(self.on_message)
        self.bus.start()
        time.sleep(1)
        
        # Test 1: Display
        if self.should_run(1):
            print("\n[TEST 1] Display Messages")
            print("-" * 40)
            self.ack_received = False
            self.bus.pub("game/display", {"line1": "Test Mode", "line2": "Display OK?", "buttons": []})
            time.sleep(1)
            self.wait_for_input("Confirm LCD shows 'Test Mode / Display OK?'")
            self.log_result("Display Message", True)
        
        # Test 2: Button Masking
        if self.should_run(2):
            print("\n[TEST 2] Button Masking")
            print("-" * 40)
            self.bus.pub("game/display", {"line1": "Press Button 1", "line2": "(2&3 disabled)", "buttons": [1]})
            self.wait_for_input("Try pressing buttons 2 and 3 (should be ignored)")
            self.button_received = False
            print("  Now press Button 1...")
            timeout = time.time() + 10
            while not self.button_received and time.time() < timeout:
                time.sleep(0.1)
            self.log_result("Button Masking", self.button_received)
        
        # Test 3: All Buttons
        if self.should_run(3):
            print("\n[TEST 3] All Buttons Enabled")
            print("-" * 40)
            self.bus.pub("game/display", {"line1": "Press any button", "line2": "1, 2, or 3", "buttons": [1, 2, 3]})
            for i in range(3):
                self.button_received = False
                print(f"  Press Button {i+1}...")
                timeout = time.time() + 10
                while not self.button_received and time.time() < timeout:
                    time.sleep(0.1)
                if not self.button_received:
                    break
            self.log_result("All Buttons", self.button_received)
        
        # Test 4: Sounds
        if self.should_run(4):
            print("\n[TEST 4] Sound Effects")
            print("-" * 40)
            sounds = [("ROLL", "Dice Roll"), ("WIN", "Victory"), ("DAMAGE", "Damage"), ("SIGNAL", "Reaction Signal")]
            for sound_id, sound_name in sounds:
                self.bus.pub("game/sound", sound_id)
                print(f"  Playing: {sound_name}")
                time.sleep(1.5)
            self.wait_for_input("Confirm you heard 4 different sounds")
            self.log_result("Sound Effects", True)
        
        # Test 5: Countdown
        if self.should_run(5):
            print("\n[TEST 5] Traffic Light Countdown")
            print("-" * 40)
            self.bus.pub("game/display", {"line1": "Countdown Test", "line2": "Watch LEDs!", "buttons": []})
            time.sleep(1)
            self.bus.pub("game/sound", "MINIGAME_START")
            self.wait_for_input("Confirm 3-2-1-GO countdown with LEDs")
            self.log_result("Countdown Sequence", True)
        
        # Test 6: ACK System
        if self.should_run(6):
            print("\n[TEST 6] ACK Flow Control")
            print("-" * 40)
            self.bus.ack_received = True  # Reset to True (normal state)
            self.bus.pub("game/display", {"line1": "ACK Test", "line2": "Waiting...", "buttons": []})
            time.sleep(0.5)  # Wait for ACK
            ack_ok = self.bus.ack_received
            if ack_ok:
                print("  ✓ ACK received from ESP32")
            self.log_result("ACK Received", ack_ok)
        
        # Test 7: Message Flow Stress Test
        if self.should_run(7):
            print("\n[TEST 7] Message Flow (Rapid Send)")
            print("-" * 40)
            print("  Sending 5 messages rapidly...")
            messages = [
                ("Message 1/5", "First"),
                ("Message 2/5", "Second"),
                ("Message 3/5", "Third"),
                ("Message 4/5", "Fourth"),
                ("Message 5/5", "Last!")
            ]
            for l1, l2 in messages:
                self.bus.pub("game/display", {"line1": l1, "line2": l2, "buttons": []})
                print(f"  Sent: {l1}")
            time.sleep(3)
            self.wait_for_input("Confirm LCD shows 'Message 5/5 / Last!' (messages shown in order)")
            self.log_result("Message Flow Order", True)
        
        # Test 8: Reconnection
        if self.should_run(8):
            print("\n[TEST 8] Reconnection Handling")
            print("-" * 40)
            self.bus.pub("game/display", {"line1": "Reconnect Test", "line2": "Reset ESP32...", "buttons": []})
            self.wait_for_input("Press RESET on ESP32, wait for it to reconnect, then press Enter")
            time.sleep(2)
            self.bus.pub("game/display", {"line1": "Reconnected!", "line2": "Success!", "buttons": [1,2,3]})
            self.wait_for_input("Confirm display updated after reconnect")
            self.log_result("Reconnection Refresh", True)
        
        # Summary
        print("\n" + "="*60)
        print("  TEST SUMMARY")
        print("="*60)
        passed = sum(1 for _, p, _ in self.test_results if p)
        total = len(self.test_results)
        print(f"\n  Passed: {passed}/{total}")
        for name, result, note in self.test_results:
            status = "✓" if result else "✗"
            print(f"  {status} {name} {note}")
        
        print("\n" + "="*60)
        self.bus.stop()

if __name__ == "__main__":
    # Parse test selection
    selected = None
    if len(sys.argv) > 1:
        selected = [int(x) for x in sys.argv[1:]]
        print(f"Running tests: {selected}")
    
    runner = TestRunner()
    runner.selected_tests = selected
    try:
        runner.run_tests()
    except KeyboardInterrupt:
        print("\n\nTest aborted.")
        if runner.bus:
            runner.bus.stop()
