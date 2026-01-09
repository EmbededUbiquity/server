# board.py

BOARD_SIZE = 16

# Tile Types
TYPE_NORMAL = "normal"
TYPE_DMG_1  = "dmg_1" 
TYPE_DMG_2  = "dmg_2"  
TYPE_HEAL_1 = "heal_1"
TYPE_HEAL_2 = "heal_2" 
TYPE_GOAL   = "goal"

BOARD_MAP = {
    2:  TYPE_DMG_1,
    4:  TYPE_HEAL_1,
    6:  TYPE_DMG_2,
    8:  TYPE_HEAL_2,
    10: TYPE_DMG_1,
    12: TYPE_HEAL_1,
    14: TYPE_DMG_2,
    BOARD_SIZE: TYPE_GOAL
}

def get_tile_effect(pos):
    if pos >= BOARD_SIZE:
        return TYPE_GOAL, 0
    
    t_type = BOARD_MAP.get(pos, TYPE_NORMAL)
    
    if t_type == TYPE_DMG_1:  return t_type, -1
    if t_type == TYPE_DMG_2:  return t_type, -2
    if t_type == TYPE_HEAL_1: return t_type, 1
    if t_type == TYPE_HEAL_2: return t_type, 2
    
    return TYPE_NORMAL, 0