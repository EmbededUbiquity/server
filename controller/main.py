# main.py
import time, random, json
from mqtt_bus import Bus
from game_fsm import Game

game = Game(n_players=3)
timer_start = 0
timer_state = "IDLE" 
reaction_trigger_time = 0 
time_limit = 0 

init_rolls = [] 

def start_minigame_sequence(bus):
    global timer_start, timer_state
    
    games = ["MASH", "REACTION", "TIME"]
    game.current_minigame = random.choice(games)
    
    if game.current_minigame == "TIME":
        game.minigame_target = random.randint(3, 8) 
    
    print(f"Minijuego: {game.current_minigame}")
    bus.pub("base/ui", {"screen": "info", "msg": f"Next: {game.current_minigame}"})
    
    timer_state = "ANNOUNCE"
    timer_start = time.time()

def on_message(client, userdata, msg):
    global game, init_rolls
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode()) if msg.payload else {}
        parts = topic.split("/")
        if len(parts) < 4: return
        player_id = int(parts[2])
        
        now = time.time()

        # --- FASE 1 & 2 (Iniciativa y Turnos) IGUAL QUE ANTES ---
        if game.state == "INITIATIVE":
            if not any(x[0] == player_id for x in init_rolls):
                val = random.randint(1, 6)
                init_rolls.append((player_id, val, now))
                bus.pub("base/ui", {"msg": f"P{player_id} rolled {val}"})
                if len(init_rolls) == 3:
                    game.set_turn_order(init_rolls)
                    bus.pub("base/ui", {"msg": f"Start: P{game.turn_order[0]}"})

        elif game.state == "TURN":
            if player_id == game.turn_order[game.current_idx]:
                dice = random.randint(1, 6)
                log = game.move_player(dice)
                print(log)
                bus.pub("base/ui", {"screen": "map", "positions": [p.pos for p in game.players]})
                if game.next_turn():
                    start_minigame_sequence(bus)
                else:
                    bus.pub("base/ui", {"msg": f"Turn: P{game.turn_order[game.current_idx]}"})

        # --- FASE 3: MINIJUEGOS (ACTUALIZADA) ---
        elif game.state == "MINIGAME_RUN":
            p = game.players[player_id]
            
            # MASH: Contar clicks
            if game.current_minigame == "MASH":
                p.mini_score += 1

            # REACTION: Calcular tiempo
            elif game.current_minigame == "REACTION":
                if now < reaction_trigger_time:
                    p.mini_score = 999.0 
                    p.mini_done = True
                elif not p.mini_done:
                    p.mini_score = now - reaction_trigger_time
                    p.mini_done = True

            # TIME: Calcular precisión
            elif game.current_minigame == "TIME":
                elapsed = now - reaction_trigger_time 
                diff = abs(elapsed - game.minigame_target)
                if not p.mini_done:
                    p.mini_score = diff
                    p.mini_done = True

    except Exception as e:
        print(f"Error msg: {e}")

bus = Bus(on_msg=on_message)

def main_loop():
    global timer_state, timer_start, reaction_trigger_time, time_limit
    
    bus.start()
    print("Servidor Iniciado...")
    
    while True:
        time.sleep(0.1) 
        now = time.time()
        # 1. Anuncio -> Cuenta atrás
        if timer_state == "ANNOUNCE" and (now - timer_start > 3):
            bus.pub("base/sound", {"cmd": "countdown"})
            timer_state = "COUNTDOWN"
            timer_start = now
            
        # 2. Cuenta atrás -> Inicio del juego (Bocina)
        elif timer_state == "COUNTDOWN" and (now - timer_start > 3):
            print("¡GO!")
            bus.pub("base/sound", {"cmd": "horn"})
            game.state = "MINIGAME_RUN"
            
            if game.current_minigame == "REACTION":
                delay = random.uniform(2, 4)
                reaction_trigger_time = now + delay
                timer_state = "WAITING_SIGNAL"
            
            elif game.current_minigame == "TIME":
                reaction_trigger_time = now 
                timer_state = "PLAYING"
                timer_start = now 
                bus.pub("base/ui", {"msg": f"Aim: {game.minigame_target}s"})
                time_limit = game.minigame_target + 3.0 
                
            else: 
                timer_state = "PLAYING"
                timer_start = now
                time_limit = 10.0 

        elif timer_state == "WAITING_SIGNAL":
            if now >= reaction_trigger_time:
                bus.pub("base/sound", {"cmd": "beep"}) 
                timer_state = "PLAYING"
                timer_start = now 
                time_limit = 3.0

        elif timer_state == "PLAYING":
            time_passed = now - timer_start
            
            if time_passed > time_limit:
                print("¡TIEMPO AGOTADO!")
                bus.pub("base/sound", {"cmd": "end"})
                logs = game.apply_minigame_penalties()
                print(logs)
                
                bus.pub("base/ui", {"screen": "results", "logs": logs})
                timer_state = "IDLE"

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        bus.stop()