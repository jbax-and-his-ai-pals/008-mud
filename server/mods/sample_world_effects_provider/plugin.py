class SampleWorldEffectsProvider:
    mode = "custom"
    provider_id = "sample.effects.balance"

    def __init__(self) -> None:
        self._seeded = False

    def _seed_examples(self) -> None:
        self._seeded = True

    def tick(self, server, session_id: str):
        if not self._seeded:
            self._seed_examples()
        return [
            server._event(
                "world_state",
                session_id,
                {
                    "system": "world_effects",
                    "provider": self.provider_id,
                    "effects": ["pressure", "relief"],
                },
            )
        ]


def setup(api):
    api.register_world_effects_provider(
        "sample.effects.balance",
        SampleWorldEffectsProvider(),
    )
