# Test content sets

`story_fixture/` is a **frozen copy** of the `ff4_slice` content set (as of the story-slice hardening), kept here so that tests of
*engine features* do not depend on a game's story.

The engine tests that need a world with a hero, a quest with a scene, an ability that costs health, a conversation that must be
answered, and so on, use this copy. `content_sets/ff4_slice` is then free to be rewritten: new rooms, new names, a different story.
Only the tests that are *about* the slice (`test_adaptation_slices.py`, `test_slice_geography.py`, `test_story_beats.py`' story
classes, `test_every_enemy_pays.py`, the content gates) are pinned to the real set, and those are meant to change with it.

Rules:

* Never edit it to follow the story. Edit it only when an engine feature needs a new shape of content to be tested, and say why in
  the commit.
* `test_story_fixture.py` checks that the engine's validator still accepts it, so engine changes that would strand it are noticed
  at its source rather than as a dozen unrelated failures.
* It is not a shipped set: the content gates do not sweep it and the editor does not open it.
