"""A tiny driver for playing a content set headless, command by command."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))
sys.path.insert(0, str(REPO))

ANSI = re.compile(r"\[\[[^\]]*\]\]|\x1b\[[0-9;]*m")


class Game:
    def __init__(self, set_id, name="Hero", seed=None, db_path=":memory:", player_id="walk", create=True):
        from engine.server.headless_server import HeadlessServer
        self.server = HeadlessServer(
            db_path=db_path,
            content_set_path=str(REPO / "content_sets" / set_id),
            deterministic_test_mode=True,
            default_presentation_mode="test",
        )
        self.session = self.server.create_session(player_id=player_id)
        self.sid = self.session.session_id
        self.log = []
        if create:
            self.run("char create %s" % name)

    @property
    def player(self):
        return self.server.get_player_for_session(self.sid)

    @property
    def world(self):
        return self.server.world

    def _text(self, events):
        return "\n".join(
            ANSI.sub("", str(e.get("payload")))
            for e in events
            if e.get("type") in ("text", "error")
        )

    def run(self, command, show=False):
        text = self._text(self.server.execute_command(self.sid, command))
        self.log.append((command, text))
        if show:
            print("> %s\n%s\n" % (command, text))
        return text

    def tick(self, n=1):
        out = []
        for _ in range(n):
            out.append(self._text(self.server.tick(self.sid)))
        return "\n".join(t for t in out if t)

    def where(self):
        p = self.player
        return "%s:%s" % (p.current_region_id, p.current_room_id)

    def items(self):
        return [slot.item.obj_id for slot in self.player.inventory.slots if slot.item]

    def go(self, *dirs, show=False):
        for d in dirs:
            t = self.run("go %s" % d)
            if show:
                print("go %s -> %s | %s" % (d, self.where(), t.splitlines()[0][:100] if t else ""))
        return self.where()

    def _alive(self, target):
        pl = self.player
        return [n for n in self.world.npcs.values()
                if target.lower() in n.name.lower() and n.is_alive
                and n.current_region_id == pl.current_region_id and n.current_room_id == pl.current_room_id]

    def fight(self, target, max_rounds=80, heal_below=0.4, potion="red potion", show=False):
        """Swing on every cooldown until the target or the player is down."""
        swings = 0
        for _ in range(max_rounds):
            if not self._alive(target):
                return "won in %d swings (hp %d/%d)" % (swings, self.player.health, self.player.max_health)
            pl = self.player
            if pl.health < heal_below * pl.max_health and any(
                    potion.replace(" ", "_") in i for i in self.items()):
                self.run("use %s" % potion)
            text = self.run("attack %s" % target)
            swings += 1
            if show:
                print("   swing:", text.replace(chr(10), " ")[:100])
            self.tick(21)
            if not self.player.is_alive:
                return "player died after %d swings" % swings
        return "no result after %d swings (hp %d/%d)" % (swings, self.player.health, self.player.max_health)

    def close(self):
        self.server.shutdown()
