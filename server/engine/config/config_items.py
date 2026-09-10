# engine/config/config_items.py
"""
Configuration for items, equipment, trading, and inventory.
"""

# --- Inventory & Container Defaults ---
DEFAULT_INVENTORY_MAX_SLOTS = 20
DEFAULT_INVENTORY_MAX_WEIGHT = 100.0
CONTAINER_EMPTY_MESSAGE = "  (Empty)"

# --- Item Mechanics ---
ITEM_DURABILITY_LOSS_ON_HIT = 1
ITEM_DURABILITY_LOW_THRESHOLD = 0.30
# A failed lockpicking attempt costs durability scaled by how badly it
# missed (SkillSystem.attempt_check_with_margin's margin), not a flat
# amount -- a narrow miss barely wears the pick; a bad one costs more.
# Exact tuning is an implementation detail, not a design decision.
LOCKPICK_DURABILITY_LOSS_DIVISOR = 10

# --- Chest Traps ---
# Independent of the lock-difficulty and contents rolls (see
# ChestLootGenerator) -- a chest's difficulty says nothing about whether
# it's trapped. Chance a generated chest is trapped at all.
CHEST_TRAP_CHANCE = 0.25
# A disarm failure only sets the trap off if it misses by a lot; a narrow
# miss just fails safely and can be retried -- mirrors the margin-scaled
# lockpick wear idea above.
TRAP_DISARM_TRIGGER_MARGIN_THRESHOLD = 15
TRAP_DAMAGE_PER_DIFFICULTY = 0.5
TRAP_POISON_DAMAGE_PER_DIFFICULTY = 0.15
TRAP_POISON_DURATION = 12.0
TRAP_POISON_TICK_INTERVAL = 3.0

# --- Trading & Vendor Settings ---
DEFAULT_VENDOR_SELL_MULTIPLIER = 2.0  # Player Buys: Item Value * 2.0 (default)
DEFAULT_VENDOR_BUY_MULTIPLIER = 0.4   # Player Sells: Item Value * 0.4 (default)
VENDOR_CAN_BUY_JUNK = True
VENDOR_CAN_BUY_ALL_ITEMS = False # Should vendors only buy certain types?
VENDOR_MIN_BUY_PRICE = 1         # Minimum price player pays when buying
VENDOR_MIN_SELL_PRICE = 0        # Minimum price player gets when selling
# A still-locked container sells by weight alone (nobody knows what's
# inside), deliberately worse than unlocking it and selling the contents.
# Global, not per-vendor -- unlike DEFAULT_VENDOR_BUY_MULTIPLIER, which a
# vendor can override via its own `sell_rate_multiplier` property.
LOCKED_CONTAINER_SELL_RATE_PER_WEIGHT = 1.5

# --- Repair Settings ---
REPAIR_COST_PER_VALUE_POINT = 0.1 # e.g., 10% of item value to repair fully
REPAIR_MINIMUM_COST = 1

# --- Equipment Slots Definition ---
EQUIPMENT_SLOTS = [
    "main_hand", "off_hand", "head", "body", "hands", "feet", "neck"
]
EQUIPMENT_VALID_SLOTS_BY_TYPE = {
    "Weapon": ["main_hand", "off_hand"],
    "Armor": ["body", "head", "feet", "hands", "neck"],
    "Item": []
}