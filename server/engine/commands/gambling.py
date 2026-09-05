# engine/commands/gambling.py
import random
from typing import Any, Dict, Optional
from engine.commands.command_system import command
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE,
    FORMAT_RED, FORMAT_GREEN, FORMAT_YELLOW, FORMAT_BLUE, FORMAT_GRAY, FORMAT_PURPLE,
    FORMAT_CYAN, VALID_DAMAGE_TYPES
)

# --- Card Constants ---
SUITS = ["S", "H", "D", "C"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

# --- Runebreaker (Mastermind-style code-breaking minigame) ---
# The symbol pool, per-symbol colors, and flavor text are dealer-authored
# (dealer.properties), not engine constants -- a content set names its own
# "runes". Falling back to the content set's own combat elements (already
# content-driven via combat/elements.json) keeps the fallback non-fantasy.
def _runebreaker_symbols(dealer) -> list[str]:
    symbols = dealer.properties.get("minigame_symbols")
    if isinstance(symbols, list) and symbols:
        return [str(s) for s in symbols]
    return list(VALID_DAMAGE_TYPES) or ["alpha", "beta", "gamma", "delta"]


def _runebreaker_symbol_color(dealer, symbol: str) -> str:
    colors = dealer.properties.get("minigame_symbol_colors", {})
    if isinstance(colors, dict) and symbol in colors:
        return str(colors[symbol])
    return FORMAT_HIGHLIGHT


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

@command("bet", ["gamble", "wager"], "interaction", "Bet your currency on a game of chance.\nUsage: bet <amount>", ruleset_system="economy")
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
    
    if player.runtime_state.gold < amount: return f"{FORMAT_ERROR}You don't have enough {world.currency_name()} (Have: {player.runtime_state.gold}).{FORMAT_RESET}"

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
        currency = player.world.currency_name()
        msg += f"\n{FORMAT_ERROR}Bust! You went over 21.{FORMAT_RESET}"
        msg += f"\nYou lose {amount} {currency}. ({currency.capitalize()}: {player.runtime_state.gold})"
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
        
    currency = world.currency_name()
    if dealer_val > 21:
        player.runtime_state.gold += amount
        routing = _grant_party_profit(world, player, amount)
        msg.append(f"{FORMAT_SUCCESS}Dealer busts! You win {amount} {currency}!{FORMAT_RESET}")
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
    msg.append(f"({currency.capitalize()}: {player.runtime_state.gold})")
    return "\n".join(msg)

@command("guess", [], "gambling", "Make a guess in Runebreaker.\nUsage: guess <element1> <element2> <element3>", ruleset_system="economy")
def guess_handler(args, context):
    world = context["world"]
    player = context.get("player")
    # Robust check
    game_state = player.active_minigame if player else None
    if not player or game_state is None or game_state.get("type") != "runebreaker":
        return "You are not playing Runebreaker."

    symbols = game_state.get("symbols") or list(VALID_DAMAGE_TYPES) or ["alpha", "beta", "gamma", "delta"]
    symbol_colors = game_state.get("symbol_colors", {})
    venue_name = game_state.get("venue_name", "the sealed chamber")
    item_name = game_state.get("item_name", "symbol")

    if not _check_location(player):
        return f"{FORMAT_ERROR}You must return to {venue_name} to make a guess.{FORMAT_RESET}"

    if len(args) != 3:
        return f"{FORMAT_ERROR}You must guess exactly 3 {item_name}s ({', '.join(symbols)}).{FORMAT_RESET}"

    guess = [arg.lower() for arg in args]
    for rune in guess:
        if rune not in symbols:
            return f"{FORMAT_ERROR}Invalid {item_name} '{rune}'. Valid: {', '.join(symbols)}.{FORMAT_RESET}"

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
    
    def _colorize(symbol: str) -> str:
        return f"{symbol_colors.get(symbol, FORMAT_HIGHLIGHT)}{symbol.upper()}{FORMAT_RESET}"

    guess_display = " ".join(_colorize(r) for r in guess)
    result_msg = f"Guess: {guess_display} -> {FORMAT_SUCCESS}{exact_matches} Perfect{FORMAT_RESET}, {FORMAT_HIGHLIGHT}{partial_matches} Partial{FORMAT_RESET}."

    if exact_matches == 3:
        amount = game_state["bet"]
        winnings = amount * 5
        player.runtime_state.gold += amount
        routing = _grant_party_profit(world, player, winnings - amount)
        player.active_minigame = None
        extra = f"\n{routing}" if routing else ""
        currency = world.currency_name()
        venue_sentence_case = venue_name[:1].upper() + venue_name[1:] if venue_name else venue_name
        return f"{result_msg}\n{FORMAT_SUCCESS}*** CODE BROKEN! ***{FORMAT_RESET}\n{venue_sentence_case} opens! You win {winnings} {currency}!{extra} ({currency.capitalize()}: {player.runtime_state.gold})"

    if game_state["attempts_left"] <= 0:
        amount = game_state["bet"]
        secret_display = " ".join(_colorize(r) for r in secret)
        player.active_minigame = None
        return f"{result_msg}\n{FORMAT_ERROR}Out of attempts!{FORMAT_RESET}\nThe code was: {secret_display}.\nYou lose {amount} {world.currency_name()}."
        
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
    
    currency = player.world.currency_name()
    msg = f"You place {amount} {currency}. {dealer.name} deals.\nDealer: {format_hand(d_hand, hide_first=True)}\nYou:    {format_hand(p_hand)} ({get_hand_value(p_hand)})"
    if get_hand_value(p_hand) == 21:
        player.active_minigame = None
        if get_hand_value(d_hand) == 21: player.runtime_state.gold += amount; return msg + f"\n{FORMAT_HIGHLIGHT}Push.{FORMAT_RESET}"
        else:
            win = int(amount * 1.5)
            player.runtime_state.gold += amount
            routing = _grant_party_profit(player.world, player, win)
            extra = f"\n{routing}" if routing else ""
            return msg + f"\n{FORMAT_SUCCESS}BLACKJACK! Win {win} {currency}!{FORMAT_RESET}{extra}"
    return msg + f"\nType '{FORMAT_HIGHLIGHT}hit{FORMAT_RESET}' or '{FORMAT_HIGHLIGHT}stand{FORMAT_RESET}'."

def _start_runebreaker(player, dealer, amount):
    player.runtime_state.gold -= amount
    symbols = _runebreaker_symbols(dealer)
    secret_code = [random.choice(symbols) for _ in range(3)]
    venue_name = dealer.properties.get("minigame_venue_name", "the sealed chamber")
    item_name = dealer.properties.get("minigame_item_name", "symbol")
    entry_flavor = dealer.properties.get(
        "minigame_entry_flavor", f"{dealer.name} seals the door. Three mechanisms spin and lock."
    )

    player.active_minigame = {
        "type": "runebreaker",
        "bet": amount,
        "secret_code": secret_code,
        "attempts_left": 8,
        "region_id": player.current_region_id,
        "room_id": player.current_room_id,
        "symbols": symbols,
        "symbol_colors": {s: _runebreaker_symbol_color(dealer, s) for s in symbols},
        "venue_name": venue_name,
        "item_name": item_name,
    }

    valid_symbols_display = ", ".join(
        f"{_runebreaker_symbol_color(dealer, s)}{s.upper()}{FORMAT_RESET}" for s in symbols
    )
    msg = [
        f"You pay the {amount} {player.world.currency_name()} entry fee to access {venue_name}.",
        entry_flavor,
        f"\"You have 8 attempts to deduce the sequence of 3 {item_name}s.\"",
        f"\"Valid {item_name}s: {valid_symbols_display}.\"",
        f"Type '{FORMAT_HIGHLIGHT}guess <{item_name}> <{item_name}> <{item_name}>{FORMAT_RESET}' to begin."
    ]
    return "\n".join(msg)

def _play_dice_high_roll(player, dealer, amount):
    # DEDUCT CURRENCY FOR BET
    player.runtime_state.gold -= amount
    currency = player.world.currency_name()

    player_roll = random.randint(1, 100)
    dealer_roll = random.randint(1, 100)
    msg = [f"You place {amount} {currency}.", f"{FORMAT_HIGHLIGHT}You roll {player_roll}.{FORMAT_RESET}", f"{FORMAT_HIGHLIGHT}Dealer rolls {dealer_roll}.{FORMAT_RESET}"]

    if player_roll > dealer_roll:
        player.runtime_state.gold += amount
        routing = _grant_party_profit(player.world, player, amount)
        msg.append(f"{FORMAT_SUCCESS}You win!{FORMAT_RESET}")
        if routing:
            msg.append(routing)
    else:
        msg.append(f"{FORMAT_ERROR}You lose.{FORMAT_RESET}")

    msg.append(f"({currency.capitalize()}: {player.runtime_state.gold})")
    return "\n".join(msg)

def _play_slots(player, dealer, amount):
    slot_data = [("[DAG]", FORMAT_GRAY, 35), ("[SHD]", FORMAT_BLUE, 30), ("[POT]", FORMAT_GREEN, 20), ("[CWN]", FORMAT_YELLOW, 10), ("[DRG]", FORMAT_RED, 5)]
    symbols = [x[0] for x in slot_data]; colors = {x[0]: x[1] for x in slot_data}; weights = [x[2] for x in slot_data]
    reel1 = random.choices(symbols, weights=weights, k=1)[0]; reel2 = random.choices(symbols, weights=weights, k=1)[0]; reel3 = random.choices(symbols, weights=weights, k=1)[0]
    r1_disp = f"{colors[reel1]}{reel1}{FORMAT_RESET}"; r2_disp = f"{colors[reel2]}{reel2}{FORMAT_RESET}"; r3_disp = f"{colors[reel3]}{reel3}{FORMAT_RESET}"
    msg = [f"{FORMAT_TITLE}| {r1_disp} | {r2_disp} | {r3_disp} |{FORMAT_RESET}"]
    currency = player.world.currency_name()
    player.runtime_state.gold -= amount
    if reel1 == reel2 == reel3:
        mult = 100 if reel1 == "[DRG]" else (25 if reel1 == "[CWN]" else (15 if reel1 == "[POT]" else (10 if reel1 == "[SHD]" else 5)))
        player.runtime_state.gold += amount
        routing = _grant_party_profit(player.world, player, amount * max(0, mult - 1))
        msg.append(f"{FORMAT_SUCCESS}Jackpot! {amount*mult} {currency}!{FORMAT_RESET}")
        if routing:
            msg.append(routing)
    elif (reel1 == reel2) or (reel2 == reel3) or (reel1 == reel3):
        player.runtime_state.gold += amount; msg.append(f"{FORMAT_HIGHLIGHT}Pair. Bet returned.{FORMAT_RESET}")
    else: msg.append(f"{FORMAT_ERROR}No match.{FORMAT_RESET}")
    msg.append(f"({currency.capitalize()}: {player.runtime_state.gold})")
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
    return msg + f" ({player.world.currency_name().capitalize()}: {player.runtime_state.gold})"
