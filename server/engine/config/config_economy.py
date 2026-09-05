# engine/config/config_economy.py
"""
Engine-wide defaults for the economy system. Content sets override the
display name of their currency via a top-level "economy" ruleset section,
e.g. {"economy": {"currency_name": "credits"}}.
"""

DEFAULT_CURRENCY_NAME = "gold"
