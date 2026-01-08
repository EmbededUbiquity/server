import os, json
import paho.mqtt.client as mqtt

# Configuración básica 
BROKER = "localhost" 
PORT   = 1883

class Bus:
    def __init__(self, on_msg):
        self.client = mqtt.Client(client_id="GameServer", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = on_msg

    def _on_connect(self, client, userdata, flags, rc):
        print(f"Conectado al Broker (rc: {rc})")
        self.client.subscribe("game/player/+/button") 

    def start(self):
        try:
            self.client.connect(BROKER, PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Error conexión MQTT: {e}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def pub(self, topic, payload):
        if isinstance(payload, dict) or isinstance(payload, list):
            payload = json.dumps(payload)
        self.client.publish(topic, payload)