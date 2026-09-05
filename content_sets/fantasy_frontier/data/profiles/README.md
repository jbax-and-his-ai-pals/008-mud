# Content-set feature profiles

A feature profile is authored with its content set and selected by that set's
`content_set.manifest.json`:

```json
{
  "paths": {
    "feature_profile": "data/profiles/default.profile.json"
  }
}
```

Server configuration and command-line transport options never select a profile.