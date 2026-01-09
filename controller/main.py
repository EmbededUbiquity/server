import time, random, json
from mqtt_bus import Bus
from game_fsm import Game
from logger import log

game = None
n_players = 0
timer_start = 0
timer_state = "LOBBY"
reaction_trigger_time = 0 
time_limit = 0 
ignore_inputs_until = 0
disconnected_at = 0
meeple_disconnect_at = 0
meeple_disconnect_pid = -1
low_player_at = 0
prev_timer_state = "IDLE"

init_rolls = [] 

class ESP01Manager:
    def __init__(self, bus):
        self.bus = bus
        self.assignments = {}
        self.assigned_ids = set()
        self.connection_status = {}
        
    def handle_register(self, payload):
        mac = payload.get("mac")
        if not mac:
            return
            
        if mac in self.assignments:
            self._send_config(mac, self.assignments[mac])
            return
            
        max_players = n_players if n_players > 0 else 3
        for pid in range(max_players):
            if pid not in self.assigned_ids:
                self.assignments[mac] = pid
                self.assigned_ids.add(pid)
                self.connection_status[mac] = "ONLINE"
                log("ESP01", f"Assigned P{pid+1} to MAC {mac}")
                self._send_config(mac, pid)
                return
                
        log("ESP01", f"No slots available for MAC {mac}", level="WARN")
        
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
        self.connection_status.clear()
        log("ESP01", "Assignments Reset")
    
    def handle_status(self, mac, status):
        """Handle ESP-01 ONLINE/OFFLINE status from LWT."""
        self.connection_status[mac] = status
        if mac in self.assignments:
            pid = self.assignments[mac]
            log("ESP01", f"P{pid+1} ({mac}) is now {status}")
            return pid, status
        return None, status
    
    def connected_count(self):
        """Count how many assigned players are currently ONLINE."""
        return sum(1 for mac in self.assignments if self.connection_status.get(mac) == "ONLINE")

esp01_manager = None 

 

def start_minigame_sequence(bus):
    global timer_start, timer_state
    
    games = ["MASH", "REACTION", "TIME"]
    game.current_minigame = random.choice(games)
    
    if game.current_minigame == "TIME":
        game.minigame_target = random.randint(3, 8) 
    
    log("GAME", f"Minigame: {game.current_minigame}")
    
    if game.current_minigame == "MASH":
        bus.pub("game/display", {
            "line1": "MASH Buttons!", 
            "line2": "Most clicks wins",
            "buttons": []  
        })
    elif game.current_minigame == "REACTION":
        bus.pub("game/display", {
            "line1": "Wait for signal!", 
            "line2": "Press FAST!",
            "buttons": []  
        })
    elif game.current_minigame == "TIME":
        bus.pub("game/display", {
            "line1": f"Guess {game.minigame_target}s!", 
            "line2": "Press when ready",
            "buttons": []  
        })
    
    timer_state = "ANNOUNCE"
    timer_start = time.time()

def on_message(client, userdata, msg):
    global game, init_rolls, ignore_inputs_until, timer_state, timer_start, disconnected_at, meeple_disconnect_at, meeple_disconnect_pid, n_players, low_player_at, prev_timer_state
    try:
        # Handle Connection Status
        if msg.topic == "game/connection":
            status = msg.payload.decode()
            log("MQTT", f"Connection Status: {status}")
            if status == "DISCONNECTED":
                if disconnected_at == 0:
                    disconnected_at = time.time()
                    log("MQTT", "ESP32 Disconnected! Game Paused.", level="WARN")
            elif status == "CONNECTED":
                if disconnected_at > 0:
                    log("MQTT", f"ESP32 Reconnected after {time.time() - disconnected_at:.1f}s")
                    disconnected_at = 0
                
                timer_state = "REFRESH_PENDING"
                timer_start = time.time()
            return

        if msg.topic == "esp01/register":
            if esp01_manager:
                 esp01_manager.handle_register(json.loads(msg.payload.decode()))
            return

        if msg.topic.startswith("esp01/") and msg.topic.endswith("/status"):
            mac = msg.topic.split("/")[1]
            status = msg.payload.decode()
            if esp01_manager:
                pid, _ = esp01_manager.handle_status(mac, status)
                if pid is not None:
                    if status == "OFFLINE":
                        meeple_disconnect_at = time.time()
                        meeple_disconnect_pid = pid
                        if timer_state != "MEEPLE_DISCONNECT":
                            prev_timer_state = timer_state 
                        timer_state = "MEEPLE_DISCONNECT"
                        timer_start = time.time()
                        log("GAME", f"P{pid+1} meeple disconnected! Starting countdown.")
                    elif status == "ONLINE":
                        log("GAME", f"P{pid+1} meeple reconnected!")
                        connected = esp01_manager.connected_count()
                        if connected >= 2 and timer_state == "MEEPLE_DISCONNECT":
                            meeple_disconnect_at = 0
                            meeple_disconnect_pid = -1
                            timer_state = prev_timer_state
                            if bus.last_display:
                                bus.pub("game/display", json.loads(bus.last_display))
                            else:
                                bus.pub("game/display", {"line1": "Resumed!", "line2": "Play on...", "buttons": []})
            return

        if msg.topic.startswith("esp01/player/") and msg.topic.endswith("/sensor"):
            try:
                parts = msg.topic.split("/")
                pid_idx = int(parts[2]) - 1
                state = msg.payload.decode()
                
                if 0 <= pid_idx < 3:
                    log("SENSOR", f"P{pid_idx+1}: {state}")
                    if game:
                        game.update_sensor(pid_idx, state)
                        
                        if timer_state == "WAIT_FOR_MOVE":
                            current_p_idx = game.turn_order[game.current_idx]
                            if pid_idx == current_p_idx:
                                current_p = game.players[current_p_idx]
                                
                                if not hasattr(current_p, 'lifted_piece'):
                                    current_p.lifted_piece = False
                                    
                                if state == "CLEAN":
                                    current_p.lifted_piece = True
                                    log("GAME", f"P{current_p.id+1} Lifted piece")
                                    
                                if getattr(current_p, 'lifted_piece', False) and state == "DETECTED":
                                    log("GAME", f"P{current_p.id+1} Placed piece")
                                    bus.pub("game/sound", "MOVE")
                                    bus.pub(f"esp01/player/{current_p.id+1}/led", "OFF")
                                    
                                    timer_state = "WAIT_CONFIRM"
                                    current_p.move_verified = True
                                    if hasattr(current_p, 'lifted_piece'):
                                        del current_p.lifted_piece
                                        
                                    bus.pub("game/display", {
                                        "line1": f"P{current_p.id+1} Moved!",
                                        "line2": "Confirm?",
                                        "buttons": [1, 2, 3]
                                    })
                                    
            except Exception as e:
                log("SENSOR", f"Error: {e}", level="ERROR")
            return

        if disconnected_at > 0:
             return

        if "COOLDOWN" in timer_state:
             return
        
        if timer_state == "WAIT_CONFIRM":
             log("GAME", "Move confirmed")
             bus.pub("game/sound", "MOVE")
             timer_state = "TURN_NEXT"
             timer_start = time.time()
             return

        topic = msg.topic
        payload = json.loads(msg.payload.decode()) if msg.payload else {}
        
        button = payload.get("button")
        if button is None:
            log("MQTT", f"No button in payload: {payload}", level="WARN")
            return

        if timer_state == "LOBBY":
            btn = int(button)
            if btn in [2, 3]:
                n_players = btn
                game = Game(n_players=n_players)
                log("GAME", f"Starting {n_players}-player game")
                timer_state = "IDLE"
                
                players_str = " ".join([f"P{i+1}:-" for i in range(n_players)])
                bus.pub("game/display", {
                    "line1": "Roll initiative!",
                    "line2": players_str,
                    "buttons": list(range(1, n_players+1))
                })
            return

        if time.time() < ignore_inputs_until:
             log("INPUT", f"Ignored buffered input: {button}")
             return
        
        player_id = int(button) - 1 if int(button) > 0 else int(button)
        
        if not game:
            log("INPUT", f"Button {button} ignored (game not started)")
            return
        
        if player_id < 0 or player_id >= len(game.players):
            log("INPUT", f"Invalid button {button} -> player_id {player_id}", level="WARN")
            return
        
        log("INPUT", f"Button {button} pressed (P{player_id+1})")
        
        now = time.time()

        if game.state == "INITIATIVE":
            if not any(x[0] == player_id for x in init_rolls):
                val = random.randint(1, 6)
                init_rolls.append((player_id, val, now))
                bus.pub("game/sound", "ROLL")
                
                roll_dict = {r[0]: r[1] for r in init_rolls}
                summary = " ".join([f"P{i+1}:{roll_dict.get(i, '-')}" for i in range(len(game.players))])
                
                rolled_ids = {r[0] for r in init_rolls}
                remain = [pid for pid in range(len(game.players)) if pid not in rolled_ids]
                
                if len(init_rolls) == len(game.players):
                    bus.pub("game/display", {
                        "line1": f"P{player_id+1} rolled: {val}",
                        "line2": summary
                    })
                    timer_state = "INITIATIVE_COOLDOWN"
                    timer_start = time.time()
                else:
                    next_p = remain[0] + 1 if remain else 0
                    bus.pub("game/display", {
                        "line1": f"P{player_id+1} rolled: {val}",
                        "line2": summary,
                        "buttons": [p+1 for p in remain]
                    })

        elif game.state == "TURN":
            if not game.turn_order:
                log("GAME", "Turn order not set yet")
                return
            if player_id == game.turn_order[game.current_idx]:
                dice = random.randint(1, 3)
                bus.pub("game/sound", "ROLL")
                
                roll_log = game.move_player(dice)
                log("GAME", roll_log)
                
                hp_summary = " ".join([f"{p.id+1}:{p.hp}" for p in game.players])
                bus.pub(f"esp01/player/{player_id+1}/led", "BLINK")
                
                bus.pub("game/display", {
                    "line1": roll_log,
                    "line2": "Move Meeple!",
                    "buttons": []
                })
                
                if game.state == "GAME_OVER":
                     bus.pub("game/display", {
                         "line1": roll_log, 
                         "line2": "GAME OVER!!",
                         "buttons": []
                     })
                     bus.pub("game/sound", "WIN")
                     timer_state = "GAME_OVER"
                     timer_start = time.time()
                     return

                timer_state = "WAIT_FOR_MOVE"
                game.players[player_id].move_verified = False
                ignore_inputs_until = time.time() + 1.0 
                
        elif timer_state == "WAIT_FOR_MOVE":
             pass

     

        elif game.state == "MINIGAME_RUN":
            p = game.players[player_id]
            
            if game.current_minigame == "MASH":
                p.mini_score += 1
                scores = " ".join([f"{pl.id+1}:{int(pl.mini_score)}" for pl in game.players])
                bus.pub("game/display", {
                    "line1": "MASH!!!",
                    "line2": scores,
                    "buttons": [1, 2, 3]
                }, wait_ack=False)

            elif game.current_minigame == "REACTION":
                if now < reaction_trigger_time:
                    p.mini_score = 999.0 
                    p.mini_done = True
                elif not p.mini_done:
                    p.mini_score = now - reaction_trigger_time
                    p.mini_done = True

            elif game.current_minigame == "TIME":
                elapsed = now - reaction_trigger_time 
                diff = abs(elapsed - game.minigame_target)
                if not p.mini_done:
                    p.mini_score = diff
                    p.mini_done = True

    except Exception as e:
        log("ERROR", f"Message handler error: {e}", level="ERROR")

bus = Bus(on_msg=on_message)
esp01_manager = ESP01Manager(bus)


def main_loop():
    global timer_state, timer_start, reaction_trigger_time, time_limit, ignore_inputs_until, disconnected_at, game, init_rolls, meeple_disconnect_at, meeple_disconnect_pid, n_players, low_player_at, prev_timer_state
    
    bus.start()
    log("SERVER", "Started")
    
    time.sleep(0.5)
    bus.pub("game/status", "LOBBY")
    bus.pub("game/display", {
        "line1": "Players: 2 or 3?",
        "line2": "Press 2 or 3",
        "buttons": [2, 3]
    })
    
    while True:
        time.sleep(0.1) 
        now = time.time()
        
        if game and timer_state not in ["LOBBY"]:
            connected = esp01_manager.connected_count() if esp01_manager else 0
            if connected < 2:
                if low_player_at == 0:
                    low_player_at = now
                    log("GAME", f"Only {connected} players connected! Need 2 to continue.")
                elif now - low_player_at > 30.0:
                    log("GAME", "Not enough players. Ending game.")
                    bus.pub("game/display", {
                        "line1": "Game Over",
                        "line2": "Not enough players",
                        "buttons": []
                    })
                    bus.pub("game/sound", "LOSE")
                    game = None
                    n_players = 0
                    timer_state = "LOBBY"
                    low_player_at = 0
                    esp01_manager.reset()
                    time.sleep(3.0)
                    bus.pub("game/display", {
                        "line1": "Players: 2 or 3?",
                        "line2": "Press 2 or 3",
                        "buttons": [2, 3]
                    })
                    continue
                else:
                    remaining = 30 - int(now - low_player_at)
                    bus.pub("game/display", {
                        "line1": f"Need 2 players!",
                        "line2": f"Ending in {remaining}s",
                        "buttons": []
                    }, cache=False)
                    continue
            else:
                if low_player_at > 0:
                    log("GAME", "Player count recovered!")
                    low_player_at = 0
                    if bus.last_display:
                         bus.pub("game/display", json.loads(bus.last_display))
                    else:
                         bus.pub("game/display", {"line1": "Resumed!", "line2": "Play on...", "buttons": []})
        
        if disconnected_at > 0:
            if now - disconnected_at > 60.0:
                log("GAME", "Disconnection Timeout! Resetting Game...")
                game = Game(n_players=3)
                init_rolls = []
                timer_state = "IDLE"
                disconnected_at = 0
                bus.pub("game/status", "RESET") 
                bus.pub("game/display", {
                    "line1": "Resetting...", 
                    "line2": "New Game", 
                    "buttons": []
                })
                time.sleep(2.0)
                bus.pub("game/status", "INITIATIVE")
                bus.pub("game/display", {"line1": "Roll Initiative!", "line2": "P1 P2 P3", "buttons": [1, 2, 3]})
            continue

        if timer_state == "MEEPLE_DISCONNECT":
            elapsed = now - meeple_disconnect_at
            remaining = max(0, 30 - int(elapsed))
            
            bus.pub("game/display", {
                "line1": f"P{meeple_disconnect_pid+1} Offline!",
                "line2": f"Reconnect: {remaining}s",
                "buttons": []
            }, cache=False)
            
            if elapsed > 30.0:
                log("GAME", f"P{meeple_disconnect_pid+1} meeple timeout! Continuing without player.")
                meeple_disconnect_at = 0
                meeple_disconnect_pid = -1
                
                if not game:
                    timer_state = "LOBBY"
                    bus.pub("game/display", {
                        "line1": "Players: 2 or 3?",
                        "line2": "Press 2 or 3",
                        "buttons": [2, 3]
                    })
                else:
                    timer_state = "IDLE"
                    next_p = game.turn_order[game.current_idx] + 1
                    bus.pub("game/display", {
                        "line1": "Game Continues!",
                        "line2": f"P{next_p} turn",
                        "buttons": [next_p]
                    })
            continue

        if timer_state == "REFRESH_PENDING" and (now - timer_start > 2.0):
             log("MQTT", "Refreshing ESP32 display state")
             if not game:
                  bus.pub("game/display", {
                      "line1": "Players: 2 or 3?",
                      "line2": "Press 2 or 3",
                      "buttons": [2, 3]
                  })
                  timer_state = "LOBBY"
             elif bus.last_display:
                  log("MQTT", f"Sending cached display")
                  bus.pub("game/display", json.loads(bus.last_display))
                  timer_state = "IDLE"
             else:
                  log("MQTT", "No cache, sending initial screen")
                  bus.pub("game/display", {"line1": "Roll initiative!", "line2": "P1:- P2:- P3:-", "buttons": [1, 2, 3]})
                  timer_state = "IDLE"

        if timer_state == "INITIATIVE_COOLDOWN" and (now - timer_start > 3.0):
             game.set_turn_order(init_rolls)
             bus.pub("game/status", "PLAYING")
             first_player = game.turn_order[0] + 1
             bus.pub("game/display", {
                 "line1": f"P{first_player} starts!",
                 "line2": f"Turn: P{first_player} ROLL!",
                 "buttons": [first_player]
             })
             timer_state = "IDLE"

        elif timer_state == "TURN_NEXT":
             if game.next_turn():
                 start_minigame_sequence(bus)
             else:
                 next_player = game.turn_order[game.current_idx] + 1
                 hp_summary = " ".join([f"{p.id+1}:{p.hp}" for p in game.players])
                 bus.pub("game/display", {
                     "line1": f"Turn: P{next_player} ROLL!",
                     "line2": hp_summary,
                     "buttons": [next_player]
                 })
                 timer_state = "IDLE"

        if timer_state == "ANNOUNCE" and (now - timer_start > 3):
            bus.pub("game/sound", "MINIGAME_START")
            bus.pub("game/display", {"buttons": [1, 2, 3]})
            timer_state = "COUNTDOWN"
            timer_start = now
            
        elif timer_state == "COUNTDOWN" and (now - timer_start > 3):
            bus.pub("game/sound", "MINIGAME_START")
            game.state = "MINIGAME_RUN"
            
            if game.current_minigame == "MASH":
                bus.pub("game/display", {"line1": "MASH!!!", "line2": "P1:0 P2:0 P3:0", "buttons": [1,2,3]})
            elif game.current_minigame == "REACTION":
                bus.pub("game/display", {"line1": "WAIT FOR IT...", "line2": "...", "buttons": [1,2,3]})
            elif game.current_minigame == "TIME":
                bus.pub("game/display", {"line1": "TIME IT!", "line2": f"Target: {game.minigame_target}s", "buttons": [1,2,3]})
            
            if game.current_minigame == "REACTION":
                delay = random.uniform(2, 4)
                reaction_trigger_time = now + delay
                timer_state = "WAITING_SIGNAL"
            
            elif game.current_minigame == "TIME":
                reaction_trigger_time = now 
                timer_state = "PLAYING"
                timer_start = now 
                bus.pub("game/display", {"line1": "Time Challenge", "line2": f"Aim: {game.minigame_target}s"})
                time_limit = game.minigame_target + 3.0 
                
            else: 
                timer_state = "PLAYING"
                timer_start = now
                time_limit = 10.0 

        elif timer_state == "WAITING_SIGNAL":
            if now >= reaction_trigger_time:
                bus.pub("game/sound", "SIGNAL") 
                timer_state = "PLAYING"
                timer_start = now 
                time_limit = 3.0

        elif timer_state == "PLAYING":
            time_passed = now - timer_start
            
            if time_passed > time_limit:
                log("GAME", "TIME'S UP!")
                ignore_inputs_until = time.time() + 5.0
                
                bus.pub("game/sound", "WIN")
                logs = game.apply_minigame_penalties()
                log("GAME", f"Results: {logs}")
                
                l1 = logs[0] if len(logs) > 0 else "Results"
                l2 = logs[1] if len(logs) > 1 else ""
                next_p = game.turn_order[game.current_idx] + 1
                
                bus.pub("game/display", {
                    "line1": l1,
                    "line2": l2,
                    "buttons": []
                })
                
                time.sleep(4.0)

                bus.pub("game/display", {
                    "line1": f"Turn: P{next_p} ROLL!",
                    "line2": "Next: Roll!",
                    "buttons": [next_p]
                })

                timer_state = "IDLE"
            
        elif timer_state == "GAME_OVER":
            if now - timer_start > 10.0:
                log("GAME", "Resetting to Lobby")
                game = None
                n_players = 0
                init_rolls = []
                esp01_manager.reset()
                timer_state = "LOBBY"
                bus.pub("game/status", "LOBBY")
                bus.pub("game/display", {
                    "line1": "Players: 2 or 3?",
                    "line2": "Press 2 or 3",
                    "buttons": [2, 3]
                })

def cleanup():
    """Clear retained MQTT topics on shutdown."""
    log("SERVER", "Shutting down, clearing topics...")
    
    bus.pub("game/status", "OFFLINE", retain=True)
    bus.pub("game/display", {
        "line1": "Server Offline",
        "line2": "Reconnecting...",
        "buttons": []
    }, retain=True)
    
    for i in range(1, 4):
        bus.pub(f"esp01/player/{i}/sensor", "", retain=True)
        bus.pub(f"esp01/player/{i}/led", "", retain=True)
    
    if esp01_manager:
        for mac in list(esp01_manager.assignments.keys()):
            bus.pub(f"esp01/{mac}/config", "", retain=True)
            bus.pub(f"esp01/{mac}/status", "", retain=True)
    
    time.sleep(0.5)
    bus.stop()
    log("SERVER", "Stopped")

import atexit
atexit.register(cleanup)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log("SERVER", f"Crash: {e}", level="ERROR")