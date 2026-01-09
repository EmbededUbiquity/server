import random
from board import BOARD_SIZE, get_tile_effect

class Player:
    def __init__(self, pid):
        self.id = pid
        self.hp = 10
        self.pos = 0
        self.finished = False
        self.mini_score = 0     
        self.mini_done = False  
        self.sensor_state = "UNKNOWN"

class Game:
    def __init__(self, n_players=3):
        self.players = [Player(i) for i in range(n_players)]
        self.turn_order = []
        self.current_idx = 0
        self.state = "INITIATIVE" 
        self.winner = None
        self.current_minigame = None
        self.minigame_target = 0
        
    def update_sensor(self, pid, state):
        if 0 <= pid < len(self.players):
            self.players[pid].sensor_state = state

    def set_turn_order(self, rolls):
        rolls.sort(key=lambda x: (-x[1], x[2]))
        self.turn_order = [x[0] for x in rolls]
        self.state = "TURN"

    def get_current_player(self):
        return self.players[self.turn_order[self.current_idx]]

    def move_player(self, steps):
        p = self.get_current_player()
        p.pos = min(p.pos + steps, BOARD_SIZE)
        if p.pos == BOARD_SIZE:
            self.winner = p.id
            self.state = "GAME_OVER"
            return f"WINNER: P{p.id+1}!"
        t_type, hp_mod = get_tile_effect(p.pos)
        p.hp += hp_mod
        msg = f"P{p.id+1} to {p.pos} ({t_type})"
        if p.hp <= 0:
            p.pos = max(0, p.pos - 1)
            p.hp = 10
            msg = f"P{p.id+1} DIED! Rspwn"
        return msg
        
    def next_turn(self):
        self.current_idx += 1
        if self.current_idx >= len(self.players):
            self.current_idx = 0
            self.state = "MINIGAME_PRE"
            return True
        return False

    # --- RESULTS LOGIC ---
    def apply_minigame_penalties(self):
        is_high_score_better = (self.current_minigame == "MASH")
        
        results = []
        for p in self.players:
            score = p.mini_score
            if not is_high_score_better and score == 0:
                score = 999.0 
            
            results.append((p, score))
        if is_high_score_better:
            results.sort(key=lambda x: x[1], reverse=True) 
        else:
            results.sort(key=lambda x: x[1]) 
        # Format score
        def fmt_score(sc):
            if sc >= 999.0: return "DNF"
            if self.current_minigame == "MASH": return f"{int(sc)}"
            return f"{sc:.2f}s"

        w_p = results[0][0]
        w_score = fmt_score(results[0][1])
        logs = [f"Win:P{w_p.id + 1} ({w_score})"]
        
        if len(results) > 1:
            s_p = results[1][0]
            s_score = fmt_score(results[1][1])
            logs.append(f"2nd:P{s_p.id + 1} ({s_score})")
        if len(results) > 1:
            results[1][0].hp -= 1 
        if len(results) > 2:
            results[2][0].hp -= 2 
        for p in self.players:
            if p.hp <= 0:
                p.pos = max(0, p.pos - 1)
                p.hp = 10
                logs.append(f"P{p.id + 1} died! Reset")
            p.mini_score = 0
            p.mini_done = False

        self.state = "TURN"
        return logs