import json, random
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion

BROKER = "localhost"
PORT   = 1883

class Bus:
    def __init__(self, on_msg):
        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"GameServer_{random.randint(1000,9999)}",
            protocol=MQTTProtocolVersion.MQTTv311,
            clean_session=True
        )
        self.client.on_connect = self._on_connect
        self._user_on_message = on_msg
        self.client.on_message = self._on_message
        self.last_display = None
        self.ack_received = True

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to Broker (reason_code: {reason_code})")
        self.client.subscribe("base/button")
        self.client.subscribe("game/connection")
        self.client.subscribe("game/ack")
        self.client.subscribe("esp01/register")
        self.client.subscribe("esp01/player/+/sensor")
        self.client.subscribe("esp01/+/status")

    def _on_message(self, client, userdata, msg):
        if msg.topic == "game/ack":
            self.ack_received = True
            return
        self._user_on_message(client, userdata, msg) 

    def start(self):
        try:
            self.client.connect(BROKER, PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"MQTT Connection Error: {e}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def pub(self, topic, payload, retain=False, cache=True, wait_ack=True):
        import time
        if isinstance(payload, dict) or isinstance(payload, list):
            payload = json.dumps(payload)
            
        if topic == "game/display" and payload and wait_ack:
            wait_start = time.time()
            while not self.ack_received and (time.time() - wait_start < 0.5):
                time.sleep(0.05)
            
            if cache:
                self.last_display = payload
            self.ack_received = False
            
        self.client.publish(topic, payload, retain=retain)

    def subscribe(self, topic):
        self.client.subscribe(topic)