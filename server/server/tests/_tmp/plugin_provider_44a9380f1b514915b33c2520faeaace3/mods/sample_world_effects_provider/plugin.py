class SampleWorldEffectsProvider:
    mode = "custom"
    provider_id = "sample.effects.balance"

    def __init__(self) -> None:
        self._seeded = False

    def _seed_examples(self, server) -> None:
        blight = server._ensure_field("blight")
        sanctity = server._ensure_field("sanctity")
        # Example negative pressure.
        blight.seed_cell(blight.width // 2, blight.height // 2, 0.85)
        # Example positive counter-pressure.
        sanctity.seed_cell(sanctity.width // 2 + 1, sanctity.height // 2, 0.75)
        self._seeded = True

    def tick(self, server, session_id: str):
        if not self._seeded:
            self._seed_examples(server)
        events = server._tick_world_field_builtin(session_id)
        return events


def setup(api):
    api.register_world_effects_provider(
        "sample.effects.balance",
        SampleWorldEffectsProvider(),
    )
