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

# --- Trading & Vendor Settings ---
DEFAULT_VENDOR_SELL_MULTIPLIER = 2.0  # Player Buys: Item Value * 2.0 (default)
DEFAULT_VENDOR_BUY_MULTIPLIER = 0.4   # Player Sells: Item Value * 0.4 (default)
VENDOR_CAN_BUY_JUNK = True
VENDOR_CAN_BUY_ALL_ITEMS = False # Should vendors only buy certain types?
VENDOR_MIN_BUY_PRICE = 1         # Minimum price player pays when buying
VENDOR_MIN_SELL_PRICE = 0        # Minimum price player gets when selling
VENDOR_ID_HINTS = ["shop", "merchant", "bartender"] # Lowercase hints in NPC IDs

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
    "Shield": ["off_hand"],
    "Item": []
}