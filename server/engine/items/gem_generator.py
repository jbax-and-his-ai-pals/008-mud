"""The historic name for the generated-instance pipeline.

The pipeline itself is `engine/items/instance_generator.py`, and it is neutral:
it rolls whatever a family's generation profile describes. This module is the
*pre-P9 binding* to it — the name that resource nodes, chest loot and the tests
call, kept so that the migration to contracts did not have to be a flag day in
the call sites.

What is actually gem-specific here is nothing. The `gem_*` property keys an
instance carries are written by the resolver because the shipped profile
declares `"property_prefix": "gem"`; a content set whose instances are salvage
components declares its own prefix and gets its own keys.

The one thing that used to live here and deliberately does not any more is the
fallback that treated `"type": "Gem"` as "this template rolls instances". That
was a genre word standing in for a contract, and it is what the registry exists
to replace: a template declares a family, the family declares the capability and
the profile. Content that has not migrated yet is reported by the content checks
rather than silently honoured.

Retire this module when nothing calls it: `resource_node.py`,
`chest_loot_generator.py` and `tests/singles/test_gem_generator.py` are the
remaining readers.
"""

from typing import Any, Optional

from engine.items.instance_generator import (  # noqa: F401  (re-exported tables)
    DEFAULT_NAME_TEMPLATE,
    QUALITY_TIERS,
    RARITY_TIERS,
    SIZE_TIERS,
    InstanceGenerator,
)
from engine.items.item import Item


class GemGenerator:
    """Pre-P9 entry point, delegating to the contract-driven resolver."""

    is_generated_instance_template = staticmethod(InstanceGenerator.is_generated_template)

    # Kept as the historic name: resource nodes and loot call it, and the tests
    # that describe gem behaviour read better for it.
    is_gem_template = staticmethod(InstanceGenerator.is_generated_template)

    @staticmethod
    def generate_gem(
        world: Any,
        level: int = 1,
        template_id: Optional[str] = None,
        quality_score: Optional[int] = None,
    ) -> Optional[Item]:
        """Create one distinct gem instance."""
        return InstanceGenerator.generate(
            world, level=level, template_id=template_id, quality_score=quality_score
        )

    pick_template_id = staticmethod(InstanceGenerator.pick_template_id)
    template_rarity = staticmethod(InstanceGenerator.template_rarity)
    name_template = staticmethod(InstanceGenerator.name_template)
    instance_name = staticmethod(InstanceGenerator.instance_name)
    instance_properties = staticmethod(InstanceGenerator.instance_properties)

    @staticmethod
    def decorate_gem(
        item: Item,
        template: dict,
        level: int = 1,
        quality_score: Optional[int] = None,
        world: Any = None,
    ) -> Item:
        """Roll this gem's size and quality onto an already-created item.

        The argument order is the historic one (`item` first), which is why this
        is a wrapper rather than an alias.
        """
        return InstanceGenerator.decorate(world, item, template, level, quality_score)

    _roll_size = staticmethod(InstanceGenerator._roll_size)
    _roll_quality = staticmethod(InstanceGenerator._roll_quality)
    _quality_for_score = staticmethod(InstanceGenerator._quality_for_score)
