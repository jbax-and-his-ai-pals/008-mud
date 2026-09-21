# tests/singles/test_environment_reader.py
"""One hazard declaration, resolved once.

What this replaces: "this room is dangerous" used to be three expressions of the
same fact. `combat/elements.json` said which damage channel a hazard was, the same
file said what it read like **keyed by that channel** -- so two hazards sharing a
channel shared one sentence and a hazard's own name never reached a player -- and
each room restated its damage and tick interval as untyped properties.

Now a hazard is one record in the content set's own words and a room names it.
These tests hold both halves of that: the reader composes what it is given
(unit), and a second theme damages through its *own* channel in its *own* prose
(journey), which is the part no amount of unit testing can prove.

The fantasy rooms keep their authored numbers, so the migration is asserted to be
behaviour-preserving by the pre-existing
`test_content_set_runtime.test_fantasy_frontier_hazards_are_runtime_active`.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.config import config_combat
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer
from engine.world import environment


REPO_ROOT = Path(__file__).resolve().parents[3]
ORBITAL_SALVAGE = REPO_ROOT / "content_sets" / "orbital_salvage"


class _Entity:
    """Enough of an entity for the reader: an id, health, and take_damage."""

    def __init__(self, obj_id="thing", health=50, region="station"):
        self.obj_id = obj_id
        self.health = health
        self.is_alive = True
        self.current_region_id = region
        self.hits = []

    def take_damage(self, amount, damage_type=None):
        self.hits.append((amount, damage_type))
        dealt = min(self.health, int(amount))
        self.health -= dealt
        return dealt


class _Room:
    def __init__(self, properties=None):
        self.properties = dict(properties or {})
        self._hazard_last_tick_by_entity = {}

    def apply_hazards(self, entity, now):
        from engine.world import environment as reader

        return reader.apply(
            getattr(entity, "world", None), self, entity, now, self._hazard_last_tick_by_entity
        )


class _World:
    def __init__(self):
        self.game = None

    def get_region(self, region_id):
        return region_id or None


HAZARDS = {
    "hull_frost": {
        "channel": "thermal",
        "flavor": "The cold gets through your layers.",
        "damage": 3,
        "tick_interval": 5.0,
    },
    "extreme_heat": {"channel": "fire", "flavor": "The heat comes off the rock."},
}


def _install_hazards(*, normalized: bool) -> None:
    """Put the fixture records where the loader would put them.

    `normalized` mirrors `config_combat._normalize_hazard`: the runtime table is
    filled by that function, so a test that writes raw records into it is testing a
    state no load can produce. The reader stays tolerant of it anyway, and one test
    below asserts that.
    """
    entries = HAZARDS if normalized else {key: dict(value) for key, value in HAZARDS.items()}
    if normalized:
        entries = {
            key: config_combat._normalize_hazard(value) for key, value in HAZARDS.items()
        }
    config_combat.HAZARD_TYPES.clear()
    config_combat.HAZARD_TYPES.update({key: dict(value) for key, value in entries.items()})


class _HazardFixture(unittest.TestCase):
    """Saves and restores the process-wide hazard table around each test."""

    normalized = True

    def setUp(self):
        self._saved = dict(config_combat.HAZARD_TYPES)
        _install_hazards(normalized=self.normalized)
        self.addCleanup(self._restore)

    def _restore(self):
        config_combat.HAZARD_TYPES.clear()
        config_combat.HAZARD_TYPES.update(self._saved)


class TestTheDeclarationIsOneRecord(_HazardFixture):
    def test_a_record_carries_everything_about_a_hazard(self):
        record = environment.declared("hull_frost")
        self.assertEqual("thermal", record["channel"])
        self.assertEqual("The cold gets through your layers.", record["flavor"])
        self.assertEqual(3, record["damage"])
        self.assertEqual(5.0, record["tick_interval"])

    def test_an_undeclared_hazard_is_inert_rather_than_guessed(self):
        self.assertIsNone(environment.declared("no_such_hazard"))
        room = _Room({"hazard_type": "no_such_hazard"})
        self.assertIsNone(environment.hazard_in(_World(), room))
        self.assertIsNone(room.apply_hazards(_Entity(), 1_000_000.0))

    def test_a_record_without_a_channel_or_a_sentence_is_not_loaded(self):
        """The loader refuses to half-load; the validator names the field.

        A hazard that damages through a guessed channel, in engine prose, is the
        failure this whole collapse exists to remove, so the unsafe direction is
        inert rather than creative.
        """
        self.assertIsNone(config_combat._normalize_hazard({"flavor": "Something."}))
        self.assertIsNone(config_combat._normalize_hazard({"channel": "thermal"}))
        self.assertIsNone(config_combat._normalize_hazard("thermal"))
        record = config_combat._normalize_hazard({"channel": "thermal", "flavor": "Cold."})
        self.assertEqual(config_combat.HAZARD_DEFAULT_DAMAGE, record["damage"])
        self.assertEqual(config_combat.HAZARD_DEFAULT_TICK_INTERVAL, record["tick_interval"])

    def test_a_declaration_that_omits_the_numbers_gets_the_engine_defaults_once(self):
        record = environment.declared("extreme_heat")
        self.assertEqual(config_combat.HAZARD_DEFAULT_DAMAGE, record["damage"])
        self.assertEqual(config_combat.HAZARD_DEFAULT_TICK_INTERVAL, record["tick_interval"])

    def test_an_unnormalized_record_is_read_rather_than_crashing(self):
        """Defence in depth: the table is filled by the loader, not by trust."""
        config_combat.HAZARD_TYPES["bare"] = {"channel": "thermal", "flavor": "Cold."}
        hazard = environment.hazard_in(_World(), _Room({"hazard_type": "bare"}))
        self.assertEqual(config_combat.HAZARD_DEFAULT_DAMAGE, hazard["damage"])
        self.assertEqual(config_combat.HAZARD_DEFAULT_TICK_INTERVAL, hazard["tick_interval"])


class TestTheRoomComposesTheDeclaration(_HazardFixture):
    def setUp(self):
        super().setUp()
        self.world = _World()

    def test_a_room_that_only_names_the_hazard_gets_the_declared_numbers(self):
        room = _Room({"hazard_type": "hull_frost"})
        hazard = environment.hazard_in(self.world, room)
        self.assertEqual(3, hazard["damage"])
        self.assertEqual(5.0, hazard["tick_interval"])

    def test_a_room_may_say_this_instance_is_worse(self):
        room = _Room({"hazard_type": "hull_frost", "hazard_damage": 9, "hazard_tick_interval": 1.5})
        hazard = environment.hazard_in(self.world, room)
        self.assertEqual(9, hazard["damage"])
        self.assertEqual(1.5, hazard["tick_interval"])

    def test_an_unusable_override_falls_back_to_the_declaration(self):
        for bad in (0, -4, True, "often", None):
            with self.subTest(override=bad):
                room = _Room({"hazard_type": "hull_frost", "hazard_damage": bad})
                self.assertEqual(3, environment.hazard_in(self.world, room)["damage"])

    def test_a_room_with_no_hazard_property_has_no_hazard(self):
        self.assertIsNone(environment.hazard_in(self.world, _Room({})))
        self.assertIsNone(environment.hazard_in(self.world, _Room({"hazard_type": "  "})))


class TestWhatItDoes(_HazardFixture):
    def setUp(self):
        super().setUp()
        self.world = _World()

    def test_it_damages_through_the_declared_channel_and_says_the_declared_sentence(self):
        room = _Room({"hazard_type": "hull_frost"})
        entity = _Entity()
        message = room.apply_hazards(entity, 1_000_000.0)
        self.assertEqual([(3, "thermal")], entity.hits)
        self.assertIn("The cold gets through your layers.", message)
        self.assertIn("(-3 HP)", message)

    def test_it_ticks_once_per_interval_and_not_once_per_call(self):
        room = _Room({"hazard_type": "hull_frost"})
        entity = _Entity()
        self.assertIsNotNone(room.apply_hazards(entity, 1_000_000.0))
        self.assertIsNone(room.apply_hazards(entity, 1_000_004.9), "too soon")
        self.assertIsNotNone(room.apply_hazards(entity, 1_000_005.0), "due exactly at the interval")
        self.assertEqual(2, len(entity.hits))

    def test_two_entities_tick_independently(self):
        room = _Room({"hazard_type": "hull_frost"})
        first, second = _Entity("a"), _Entity("b")
        self.assertIsNotNone(room.apply_hazards(first, 1_000_000.0))
        self.assertIsNotNone(room.apply_hazards(second, 1_000_000.0))
        self.assertIsNone(room.apply_hazards(first, 1_000_001.0))

    def test_a_dead_entity_takes_nothing(self):
        room = _Room({"hazard_type": "hull_frost"})
        entity = _Entity()
        entity.is_alive = False
        self.assertIsNone(room.apply_hazards(entity, 1_000_000.0))
        self.assertEqual([], entity.hits)

    def test_damage_fully_shrugged_off_says_nothing(self):
        class _Immune(_Entity):
            def take_damage(self, amount, damage_type=None):
                self.hits.append((amount, damage_type))
                return 0

        room = _Room({"hazard_type": "hull_frost"})
        self.assertIsNone(room.apply_hazards(_Immune(), 1_000_000.0))

    def test_weather_scales_the_declared_damage(self):
        room = _Room({"hazard_type": "hull_frost", "weather_hazard_multipliers": {"storm": 2.0}})

        class _Weather:
            def effective_weather(self, region, room_):
                return "storm"

        class _Game:
            weather_manager = _Weather()

        self.world.game = _Game()
        self.assertEqual("storm", _Weather().effective_weather("station", room))
        self.assertEqual(2.0, environment.weather_multiplier(self.world, environment.hazard_in(self.world, room), "station", room))
        self.assertEqual(6, environment.damage_of(self.world, room, environment.hazard_in(self.world, room), "station"))

    def test_weather_that_does_not_apply_changes_nothing(self):
        room = _Room({"hazard_type": "hull_frost", "weather_hazard_multipliers": {"storm": 2.0}})

        class _Weather:
            def effective_weather(self, region, room_):
                return "clear"

        class _Game:
            weather_manager = _Weather()

        self.world.game = _Game()
        self.assertEqual(1.0, environment.weather_multiplier(self.world, environment.hazard_in(self.world, room), "station", room))

    def test_a_world_with_no_weather_leaves_the_damage_alone(self):
        room = _Room({"hazard_type": "hull_frost", "weather_hazard_multipliers": {"storm": 2.0}})
        self.assertEqual(1.0, environment.weather_multiplier(self.world, environment.hazard_in(self.world, room), "station", room))

    def test_damage_never_falls_below_one(self):
        """A hazard that deals nothing is a room whose danger is decorative."""
        room = _Room({"hazard_type": "hull_frost", "weather_hazard_multipliers": {"storm": 0.1}})

        class _Weather:
            def effective_weather(self, region, room_):
                return "storm"

        class _Game:
            weather_manager = _Weather()

        self.world.game = _Game()
        self.assertEqual(1, environment.damage_of(self.world, room, environment.hazard_in(self.world, room), "station"))


class TestTheSecondTheme(unittest.TestCase):
    """`orbital_salvage` fills the seat it shipped empty, in its own words."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(ORBITAL_SALVAGE),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="salvager")
        self.server.execute_command(self.session.session_id, "char create Vess")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def _text(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        return "\n".join(str(e.get("payload")) for e in events if e.get("type") == "text")

    def _hold(self):
        return self.server.world.get_region("station").get_room("hold")

    def test_the_station_declares_a_hazard_of_its_own(self):
        declared = config_combat.HAZARD_TYPES
        self.assertIn("hull_frost", declared, "the seat orbital left empty is filled")
        self.assertEqual("thermal", declared["hull_frost"]["channel"])
        self.assertNotIn("fire", declared, "and none of fantasy's hazards came with it")

    def test_the_hold_damages_through_the_sets_own_channel_in_its_own_words(self):
        room = self._hold()
        self.assertEqual("hull_frost", room.get_property("hazard_type"))
        starting = self.player.health

        with patch.object(type(self.player), "take_damage", autospec=True,
                          side_effect=lambda self_, amount, damage_type=None: amount) as spy:
            message = room.apply_hazards(self.player, self.server.world.clock.now())

        self.assertIsNotNone(message)
        amount, channel = spy.call_args[0][1], spy.call_args[0][2]
        self.assertEqual(3, amount)
        self.assertEqual("thermal", channel, "the channel is this set's own, not a fantasy element")
        self.assertIn("The cold in here gets through your layers and stays there.", message)
        self.assertNotIn("scorches", message, "no fantasy sentence reaches a sci-fi player")
        self.assertGreater(starting, 0)

    def test_the_vest_the_set_authors_reduces_it(self):
        """Mitigation has to be measurable, or `resistances` is decoration.

        The vest is the set's own gear and the resistance sits under `properties`,
        the convention fantasy's neckwear already uses. The set's `resistance` role
        names `insulation`, which a salvager carries none of, so the vest is the
        whole of the mitigation a player has -- by design: gear keeps you alive in
        this set, not heritage.
        """
        room = self._hold()
        vest = ItemFactory.create_item_from_template("item_impact_vest", self.server.world)
        self.assertIsNotNone(vest)
        added, message = self.player.inventory.add_item(vest, 1)
        self.assertTrue(added, message)
        self._text("equip vest")
        self.assertIsNotNone(self.player.equipment.get("body"), "the vest is worn")
        self.assertGreater(self.player.get_resistance("thermal"), 0,
                           "the declared resistance is readable on the wearer")

        before = self.player.health
        room._hazard_last_tick_by_entity.clear()
        room.apply_hazards(self.player, self.server.world.clock.now())
        hurt_wearing = before - self.player.health

        self.player.equipment["body"] = None
        before = self.player.health
        room._hazard_last_tick_by_entity.clear()
        room.apply_hazards(self.player, self.server.world.clock.now())
        hurt_bare = before - self.player.health

        self.assertEqual(3, hurt_bare, "the declared damage reaches an uninsulated salvager")
        self.assertEqual(2, hurt_wearing, "and 30% less through the set's own vest")

    def test_a_five_second_interval_is_five_seconds(self):
        """In game days or real seconds, the interval is the clock's own unit."""
        room = self._hold()
        now = self.server.world.clock.now()
        self.assertIsNotNone(room.apply_hazards(self.player, now))
        self.assertIsNone(room.apply_hazards(self.player, now + 4.0))
        self.assertIsNotNone(room.apply_hazards(self.player, now + 5.0))


class TestTheRetiredShape(unittest.TestCase):
    """A content set written against the old shape is told what changed."""

    def test_the_loader_does_not_read_the_old_keys_as_hazards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "combat").mkdir()
            (root / "combat" / "elements.json").write_text(json.dumps({
                "hazards": {"mapping": {"cold": "ice"}, "flavor": {"ice": "Cold."}},
            }), encoding="utf-8")
            saved = dict(config_combat.HAZARD_TYPES)
            self.addCleanup(lambda: (config_combat.HAZARD_TYPES.clear(),
                                     config_combat.HAZARD_TYPES.update(saved)))
            config_combat.configure_combat_elements(str(root))
            self.assertEqual({}, config_combat.HAZARD_TYPES)


if __name__ == "__main__":
    unittest.main()
