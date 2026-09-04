# Server Feature Profile Recipes

These profile files are ready-to-use server policy presets.

- `static_world.profile.json`
- `creative_world.profile.json`
- `social_no_combat.profile.json`
- `mobile_low_fx.profile.json`

Use any profile by setting:

```json
{
  "feature_profile": {
    "path": "server/data/profiles/static_world.profile.json"
  }
}
```

in `server/config/server_config.json` (or pass `--profile` at startup).
