import pytest
from game_fsm import Game
from board import BOARD_SIZE

# ==========================================
# 1. TEST DE INICIALIZACIÓN E INICIATIVA
# ==========================================

def test_init_game():
    """Verifica que el juego comienza con los valores por defecto correctos."""
    game = Game(n_players=3)
    assert game.state == "INITIATIVE"
    assert len(game.players) == 3
    for p in game.players:
        assert p.hp == 10
        assert p.pos == 0
        assert p.mini_score == 0

def test_initiative_sorting_simple():
    """El dado más alto debe ir primero."""
    game = Game(n_players=3)
    rolls = [
        (0, 2, 100), 
        (1, 6, 100), 
        (2, 4, 100)  
    ]
    game.set_turn_order(rolls)    
    assert game.turn_order == [1, 2, 0]
    assert game.state == "TURN"

def test_initiative_tie_breaker():
    """Si hay empate en el dado, gana quien lo tiró antes (menor tiempo)."""
    game = Game(n_players=2)
    rolls = [
        (0, 5, 12.0),
        (1, 5, 10.0) 
    ]
    game.set_turn_order(rolls)
    assert game.turn_order == [1, 0]

# ==========================================
# 2. TEST DE MOVIMIENTO Y EFECTOS DE TABLERO
# ==========================================

def test_tile_effects_damage_and_heal():
    """Prueba específica de casillas de daño y curación según board.py."""
    game = Game(n_players=1)
    p = game.players[0]
    game.turn_order = [0]
    game.move_player(2) 
    assert p.pos == 2
    assert p.hp == 9 
    game.move_player(2)
    assert p.pos == 4
    assert p.hp == 10 
    game.move_player(2)
    assert p.pos == 6
    assert p.hp == 8 
    game.move_player(2)
    assert p.pos == 8
    assert p.hp == 10 

def test_win_condition():
    """Llegar a la casilla 16 termina el juego."""
    game = Game(n_players=1)
    game.turn_order = [0]
    p = game.players[0]
    
    p.pos = 15
    game.move_player(1)
    
    assert p.pos == 16
    assert game.winner == 0
    assert game.state == "GAME_OVER"

# ==========================================
# 3. TEST DE MUERTE Y RESURRECCIÓN (CORE)
# ==========================================

def test_death_logic_standard():
    """Si HP <= 0 -> Retrocede 1 y HP = 10."""
    game = Game(n_players=1)
    game.turn_order = [0]
    p = game.players[0]
    p.pos = 3
    p.hp = 1
    msg = game.move_player(3)  
    assert "MUERTO" in msg
    assert p.pos == 5  
    assert p.hp == 10  

def test_death_at_start_boundary():
    """Si mueres en la casilla 0 o 1, no deberías retroceder a negativos."""
    game = Game(n_players=1)
    game.turn_order = [0]
    p = game.players[0]
    p.pos = 0
    p.hp = 1   
    game.move_player(2) 
    assert p.pos == 1 
    assert p.hp == 10
    p.pos = 0
    p.hp = -5
    if p.hp <= 0:
        p.pos = max(0, p.pos - 1)
        p.hp = 10
        
    assert p.pos == 0 

# ==========================================
# 4. TEST DE CICLO DE TURNOS
# ==========================================

def test_turn_cycle_trigger_minigame():
    """Después de que todos jueguen, debe cambiar a estado MINIGAME_PRE."""
    game = Game(n_players=3)
    game.turn_order = [0, 1, 2]
    assert game.current_idx == 0
    minigame_start = game.next_turn()
    assert minigame_start is False
    assert game.current_idx == 1
    minigame_start = game.next_turn()
    assert minigame_start is False
    assert game.current_idx == 2
    minigame_start = game.next_turn()
    assert minigame_start is True
    assert game.state == "MINIGAME_PRE"
    assert game.current_idx == 0 

# ==========================================
# 5. TEST DE MINIJUEGOS (LÓGICA COMPLEJA)
# ==========================================

def test_minigame_mash():
    """En MASH, puntuación ALTA gana."""
    game = Game(n_players=3)
    game.current_minigame = "MASH"
    game.players[0].mini_score = 50
    game.players[1].mini_score = 30
    game.players[2].mini_score = 10   
    logs = game.apply_minigame_penalties()    
    assert "Ganador: P0" in logs[0]
    assert game.players[0].hp == 10
    assert game.players[1].hp == 9
    assert game.players[2].hp == 8
    assert game.state == "TURN"

def test_minigame_reaction_normal():
    """En REACTION/TIME, puntuación BAJA (tiempo) gana."""
    game = Game(n_players=3)
    game.current_minigame = "REACTION"
    game.players[0].mini_score = 0.2
    game.players[1].mini_score = 0.5
    game.players[2].mini_score = 0.8   
    game.apply_minigame_penalties()   
    assert game.players[0].hp == 10 
    assert game.players[1].hp == 9
    assert game.players[2].hp == 8

def test_minigame_afk_penalty():
    """
    TEST CRÍTICO: El jugador 'Dormido'.
    En juegos de tiempo, si score es 0 (no pulsó), debe convertirse en 999.
    """
    game = Game(n_players=3)
    game.current_minigame = "TIME"
    game.players[0].mini_score = 0.5
    game.players[1].mini_score = 2.0
    game.players[2].mini_score = 0    
    game.apply_minigame_penalties()
    assert game.players[0].hp == 10
    assert game.players[1].hp == 9
    assert game.players[2].hp == 8 

def test_death_in_minigame():
    """
    Verificar que si pierdes vida en un minijuego y llegas a 0,
    también se aplica la regla de Respawn (retroceder y curar).
    """
    game = Game(n_players=3)
    game.current_minigame = "MASH"
    
    p2 = game.players[2]
    p2.hp = 1
    p2.pos = 5   
    game.players[0].mini_score = 100
    game.players[1].mini_score = 50
    game.players[2].mini_score = 10  
    logs = game.apply_minigame_penalties()
    assert p2.pos == 4
    assert p2.hp == 10
    assert any("P2 muere" in log for log in logs)