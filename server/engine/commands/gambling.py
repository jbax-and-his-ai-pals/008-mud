# engine/commands/gambling.py
import random
from typing import Any, Dict, Optional
from engine.commands.command_system import command
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE,
    FORMAT_RED, FORMAT_GREEN, FORMAT_YELLOW, FORMAT_BLUE, FORMAT_GRAY, FORMAT_PURPLE,
    FORMAT_CYAN
)

# --- Card Constants ---
SUITS = ["S", "H", "D", "C"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

# --- Runebreaker Constants ---
RUNE_TYPES = ["fire", "water", "earth", "air"]
RUNE_COLORS = {
    "fire": FORMAT_RED,
    "water": FORMAT_BLUE,
    "earth": FORMAT_GREEN,
    "air": FORMAT_CYAN
}


def _grant_party_profit(world, player, profit_amount: int) -> str:
    profit = int(profit_amount or 0)
    if profit <= 0:
        return ""
    server = getattr(world, "server", None)
    if server is not None and hasattr(server, "grant_party_gold"):
        return str(server.grant_party_gold(player, profit))
    player.runtime_state.gold += profit
    return ""

def draw_card():
    rank = random.choice(RANKS)
    suit = random.choice(SUITS)
    return (rank, suit)

def get_hand_value(hand):
    value = 0
    aces = 0
    for rank, suit in hand:
        if rank in ["J", "Q", "K"]:
            value += 10
        elif rank == "A":
            aces += 1
            value += 11
        else:
            value += int(rank)
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def format_hand(hand, hide_first=False):
    display = []
    for i, (rank, suit) in enumerate(hand):
        if hide_first and i == 0:
            display.append("[??]")
        else:
            color = FORMAT_RED if suit in ["H", "D"] else FORMAT_CYAN
            display.append(f"{color}[{rank}-{suit}]{FORMAT_RESET}")
    return " ".join(display)

def _check_location(player):
    """Returns True if player is in the same location where the minigame started."""
    # Capture state in a local variable for type narrowing
    state = player.active_minigame
    if state is None: return False
    
    # Older minigame records may not carry a location; treat them as stationary.
    if "region_id" not in state or "room_id" not in state: return True
    
    return (player.current_region_id == state["region_id"] and 
            player.current_room_id == state["room_id"])

# --- Command Handlers ---

@command("rules", ["payouts", "odds"], "interaction", "Show the rules and payouts for the current room's game.", ruleset_system="economy")
def rules_handler(args, context):
    world = context["world"]
    player = context.get("player")
    dealer = None
    for npc in world.get_npcs_for_player(player):
        if npc.properties.get("is_dealer"):
            dealer = npc
            break
    if not dealer: return f"{FORMAT_ERROR}There are no active games in this room.{FORMAT_RESET}"
    rules_text = dealer.dialog.get("rules", "The dealer refuses to explain the rules.")
    game_name = dealer.properties.get('dealer_game', 'Unknown').replace('_', ' ').title()
    return f"{FORMAT_TITLE}Game Rules: {game_name}{FORMAT_RESET}\n{rules_text}"

@command("bet", ["gamble", "wager"], "interaction", "Bet gold on a game of chance.\nUsage: bet <amount>", ruleset_system="economy")
def bet_handler(args, context):
    world = context["world"]
    player = context.get('player')
    
    if not player: return f"{FORMAT_ERROR}Player not found.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You cannot gamble while dead.{FORMAT_RESET}"
    
    # Check if already in a game using local var for type safety
    current_game = player.active_minigame
    if current_game is not None:
        game_type = current_game.get("type", "unknown")
        return f"{FORMAT_ERROR}You are already playing {game_type}. Finish that game first!{FORMAT_RESET}"

    if not args: return f"{FORMAT_ERROR}Usage: bet <amount>{FORMAT_RESET}"
    
    try:
        amount = int(args[0])
        if amount <= 0: return f"{FORMAT_ERROR}You must bet a positive amount.{FORMAT_RESET}"
    except ValueError: return f"{FORMAT_ERROR}Invalid amount.{FORMAT_RESET}"
    
    if player.runtime_state.gold < amount: return f"{FORMAT_ERROR}You don't have enough gold (Have: {player.runtime_state.gold}).{FORMAT_RESET}"

    dealer = None
    for npc in world.get_npcs_for_player(player):
        if npc.properties.get("is_dealer"):
            dealer = npc
            break
    
    if not dealer: return f"{FORMAT_ERROR}There is no one here to take your bet.{FORMAT_RESET}"

    game_type = dealer.properties.get("dealer_game", "dice")

    # --- Game Dispatch ---
    if game_type == "blackjack":
        return _start_blackjack(player, dealer, amount)
    elif game_type == "dice_high_roll":
        return _play_dice_high_roll(player, dealer, amount)
    elif game_type == "slots":
        return _play_slots(player, dealer, amount)
    elif game_type == "wheel":
        return _play_elemental_wheel(player, dealer, amount)
    elif game_type == "runebreaker":
        return _start_runebreaker(player, dealer, amount)
    else:
        return f"{dealer.name} looks confused."

@command("hit", [], "gambling", "Request another card in Blackjack.", ruleset_system="economy")
def hit_handler(args, context):
    player = context.get("player")
    # Robust check
    game_state = player.active_minigame if player else None
    if not player or game_state is None or game_state.get("type") != "blackjack":
        return "You are not playing a card game right now."
    
    if not _check_location(player):
        return f"{FORMAT_ERROR}You must return to the table to play.{FORMAT_RESET}"
    
    card = draw_card()
    # Safe access because game_state is confirmed not None
    game_state["hand"].append(card)
    val = get_hand_value(game_state["hand"])
    msg = f"You draw a {format_hand([card])}.\nYour Hand: {format_hand(game_state['hand'])} ({val})"
    
    if val > 21:
        amount = game_state["bet"]
        msg += f"\n{FORMAT_ERROR}Bust! You went over 21.{FORMAT_RESET}"
        msg += f"\nYou lose {amount} gold. (Gold: {player.runtime_state.gold})"
        player.active_minigame = None
    return msg

@command("stand", ["stay"], "gambling", "End your turn in Blackjack.", ruleset_system="economy")
def stand_handler(args, context):
    world = context["world"]
    player = context.get("player")
    # Robust check
    game_state = player.active_minigame if player else None
    if not player or game_state is None or game_state.get("type") != "blackjack":
        return "You are not playing a card game right now."

    if not _check_location(player):
        return f"{FORMAT_ERROR}You must return to the table to play.{FORMAT_RESET}"
    
    # Use local variable game_state
    amount = game_state["bet"]
    player_val = get_hand_value(game_state["hand"])
    msg = [f"You stand with {player_val}."]
    msg.append(f"Dealer reveals: {format_hand(game_state['dealer_hand'])}")
    dealer_val = get_hand_value(game_state["dealer_hand"])
    
    while dealer_val < 17:
        card = draw_card()
        game_state["dealer_hand"].append(card)
        dealer_val = get_hand_value(game_state["dealer_hand"])
        msg.append(f"Dealer draws {format_hand([card])}. Total: {dealer_val}")
        
    if dealer_val > 21:
        player.runtime_state.gold += amount
        routing = _grant_party_profit(world, player, amount)
        msg.append(f"{FORMAT_SUCCESS}Dealer busts! You win {amount} gold!{FORMAT_RESET}")
    elif dealer_val > player_val:
        msg.append(f"{FORMAT_ERROR}Dealer wins.{FORMAT_RESET} ({dealer_val} vs {player_val})")
    elif dealer_val < player_val:
        player.runtime_state.gold += amount
        routing = _grant_party_profit(world, player, amount)
        msg.append(f"{FORMAT_SUCCESS}You win!{FORMAT_RESET} ({player_val} vs {dealer_val})")
    else:
        player.runtime_state.gold += amount
        routing = ""
        msg.append(f"{FORMAT_HIGHLIGHT}Push.{FORMAT_RESET} You keep your wager.")
    if dealer_val > 21 or dealer_val < player_val:
        if routing:
            msg.append(routing)
    player.active_minigame = None
    msg.append(f"(Gold: {player.runtime_state.gold})")
    return "\n".join(msg)

@command("guess", [], "gambling", "Make a guess in Runebreaker.\nUsage: guess <element1> <element2> <element3>", ruleset_system="economy")
def guess_handler(args, context):
    world = context["world"]
    player = context.get("player")
    # Robust check
    game_state = player.active_minigame if player else None
    if not player or game_state is None or game_state.get("type") != "runebreaker":
        return "You are not playing Runebreaker."

    if not _check_location(player):
        return f"{FORMAT_ERROR}You must return to the Arcane Vault to make a guess.{FORMAT_RESET}"

    if len(args) != 3:
        return f"{FORMAT_ERROR}You must guess exactly 3 elements (fire, water, earth, air).{FORMAT_RESET}"

    guess = [arg.lower() for arg in args]
    for rune in guess:
        if rune not in RUNE_TYPES:
            return f"{FORMAT_ERROR}Invalid element '{rune}'. Valid: fire, water, earth, air.{FORMAT_RESET}"

    # Use local variable game_state
    secret = game_state["secret_code"]
    game_state["attempts_left"] -= 1
    
    exact_matches = 0
    partial_matches = 0
    secret_matched = [False] * 3
    guess_matched = [False] * 3
    
    for i in range(3):
        if guess[i] == secret[i]:
            exact_matches += 1
            secret_matched[i] = True
            guess_matched[i] = True
            
    for i in range(3):
        if not guess_matched[i]:
            for j in range(3):
                if not secret_matched[j] and guess[i] == secret[j]:
                    partial_matches += 1
                    secret_matched[j] = True
                    break
    
    guess_display = " ".join([f"{RUNE_COLORS[r]}{r.upper()}{FORMAT_RESET}" for r in guess])
    result_msg = f"Guess: {guess_display} -> {FORMAT_SUCCESS}{exact_matches} Perfect{FORMAT_RESET}, {FORMAT_HIGHLIGHT}{partial_matches} Partial{FORMAT_RESET}."
    
    if exact_matches == 3:
        amount = game_state["bet"]
        winnings = amount * 5
        player.runtime_state.gold += amount
        routing = _grant_party_profit(world, player, winnings - amount)
        player.active_minigame = None
        extra = f"\n{routing}" if routing else ""
        return f"{result_msg}\n{FORMAT_SUCCESS}*** CODE BROKEN! ***{FORMAT_RESET}\nThe Vault opens! You win {winnings} gold!{extra} (Gold: {player.runtime_state.gold})"
        
    if game_state["attempts_left"] <= 0:
        amount = game_state["bet"]
        secret_display = " ".join([f"{RUNE_COLORS[r]}{r.upper()}{FORMAT_RESET}" for r in secret])
        player.active_minigame = None
        return f"{result_msg}\n{FORMAT_ERROR}Out of attempts!{FORMAT_RESET}\nThe code was: {secret_display}.\nYou lose {amount} gold."
        
    return f"{result_msg}\nAttempts remaining: {game_state['attempts_left']}"

# --- Game Implementations ---

def _start_blackjack(player, dealer, amount):
    player.runtime_state.gold -= amount
    p_hand = [draw_card(), draw_card()]
    d_hand = [draw_card(), draw_card()]
    
    player.active_minigame = {
        "type": "blackjack", 
        "bet": amount, 
        "hand": p_hand, 
        "dealer_hand": d_hand,
        "region_id": player.current_region_id,
        "room_id": player.current_room_id
    }
    
    msg = f"You place {amount} gold. {dealer.name} deals.\nDealer: {format_hand(d_hand, hide_first=True)}\nYou:    {format_hand(p_hand)} ({get_hand_value(p_hand)})"
    if get_hand_value(p_hand) == 21:
        player.active_minigame = None
        if get_hand_value(d_hand) == 21: player.runtime_state.gold += amount; return msg + f"\n{FORMAT_HIGHLIGHT}Push.{FORMAT_RESET}"
        else:
            win = int(amount * 1.5)
            player.runtime_state.gold += amount
            routing = _grant_party_profit(player.world, player, win)
            extra = f"\n{routing}" if routing else ""
            return msg + f"\n{FORMAT_SUCCESS}BLACKJACK! Win {win} gold!{FORMAT_RESET}{extra}"
    return msg + f"\nType '{FORMAT_HIGHLIGHT}hit{FORMAT_RESET}' or '{FORMAT_HIGHLIGHT}stand{FORMAT_RESET}'."

def _start_runebreaker(player, dealer, amount):
    player.runtime_state.gold -= amount
    secret_code = [random.choice(RUNE_TYPES) for _ in range(3)]
    
    player.active_minigame = {
        "type": "runebreaker",
        "bet": amount,
        "secret_code": secret_code,
        "attempts_left": 8,
        "region_id": player.current_region_id,
        "room_id": player.current_room_id
    }
    
    msg = [
        f"You pay the {amount} gold entry fee to access The Vault.",
        f"{dealer.name} seals the door. Three magical tumblers spin and lock.",
        f"\"You have 8 attempts to deduce the sequence of 3 Runes.\"",
        f"\"Valid Runes: {FORMAT_RED}FIRE{FORMAT_RESET}, {FORMAT_BLUE}WATER{FORMAT_RESET}, {FORMAT_GREEN}EARTH{FORMAT_RESET}, {FORMAT_CYAN}AIR{FORMAT_RESET}.\"",
        f"Type '{FORMAT_HIGHLIGHT}guess <rune> <rune> <rune>{FORMAT_RESET}' to begin."
    ]
    return "\n".join(msg)

def _play_dice_high_roll(player, dealer, amount):
    # DEDUCT GOLD FOR BET
    player.runtime_state.gold -= amount
    
    player_roll = random.randint(1, 100)
    dealer_roll = random.randint(1, 100)
    msg = [f"You place {amount} gold.", f"{FORMAT_HIGHLIGHT}You roll {player_roll}.{FORMAT_RESET}", f"{FORMAT_HIGHLIGHT}Dealer rolls {dealer_roll}.{FORMAT_RESET}"]
    
    if player_roll > dealer_roll: 
        player.runtime_state.gold += amount
        routing = _grant_party_profit(player.world, player, amount)
        msg.append(f"{FORMAT_SUCCESS}You win!{FORMAT_RESET}")
        if routing:
            msg.append(routing)
    else: 
        msg.append(f"{FORMAT_ERROR}You lose.{FORMAT_RESET}")
    
    msg.append(f"(Gold: {player.runtime_state.gold})")
    return "\n".join(msg)

def _play_slots(player, dealer, amount):
    slot_data = [("[DAG]", FORMAT_GRAY, 35), ("[SHD]", FORMAT_BLUE, 30), ("[POT]", FORMAT_GREEN, 20), ("[CWN]", FORMAT_YELLOW, 10), ("[DRG]", FORMAT_RED, 5)]
    symbols = [x[0] for x in slot_data]; colors = {x[0]: x[1] for x in slot_data}; weights = [x[2] for x in slot_data]
    reel1 = random.choices(symbols, weights=weights, k=1)[0]; reel2 = random.choices(symbols, weights=weights, k=1)[0]; reel3 = random.choices(symbols, weights=weights, k=1)[0]
    r1_disp = f"{colors[reel1]}{reel1}{FORMAT_RESET}"; r2_disp = f"{colors[reel2]}{reel2}{FORMAT_RESET}"; r3_disp = f"{colors[reel3]}{reel3}{FORMAT_RESET}"
    msg = [f"{FORMAT_TITLE}| {r1_disp} | {r2_disp} | {r3_disp} |{FORMAT_RESET}"]
    player.runtime_state.gold -= amount
    if reel1 == reel2 == reel3:
        mult = 100 if reel1 == "[DRG]" else (25 if reel1 == "[CWN]" else (15 if reel1 == "[POT]" else (10 if reel1 == "[SHD]" else 5)))
        player.runtime_state.gold += amount
        routing = _grant_party_profit(player.world, player, amount * max(0, mult - 1))
        msg.append(f"{FORMAT_SUCCESS}Jackpot! {amount*mult} gold!{FORMAT_RESET}")
        if routing:
            msg.append(routing)
    elif (reel1 == reel2) or (reel2 == reel3) or (reel1 == reel3):
        player.runtime_state.gold += amount; msg.append(f"{FORMAT_HIGHLIGHT}Pair. Bet returned.{FORMAT_RESET}")
    else: msg.append(f"{FORMAT_ERROR}No match.{FORMAT_RESET}")
    msg.append(f"(Gold: {player.runtime_state.gold})")
    return "\n".join(msg)

def _play_elemental_wheel(player, dealer, amount):
    outcomes = [("VOID", 0, FORMAT_GRAY, 60), ("EARTH", 1, FORMAT_GREEN, 20), ("FIRE", 2, FORMAT_RED, 10), ("ICE", 5, FORMAT_BLUE, 9), ("AETHER", 10, FORMAT_PURPLE, 1)]
    result = random.choices(outcomes, weights=[x[3] for x in outcomes], k=1)[0]
    player.runtime_state.gold -= amount
    winnings = amount * result[1]
    player.runtime_state.gold += min(amount, winnings)
    routing = _grant_party_profit(player.world, player, max(0, winnings - amount))
    msg = f"Wheel: {result[2]}{result[0]}{FORMAT_RESET}. "
    msg += f"{FORMAT_SUCCESS}Win {winnings}!{FORMAT_RESET}" if result[1] > 0 else f"{FORMAT_ERROR}Loss.{FORMAT_RESET}"
    if routing:
        msg += f"\n{routing}"
    return msg + f" (Gold: {player.runtime_state.gold})"
