# lounge-math-data

The airport and lounge data behind **LoungeMath**, the iOS app that answers "when can I start working airside, and is the paid lounge worth it?".

## Served URLs (GitHub Pages)

| File | URL |
|---|---|
| Airports | https://igalness.github.io/lounge-math-data/v1/airports.json |
| Countries (border table) | https://igalness.github.io/lounge-math-data/v1/countries.json |
| Schemas | https://igalness.github.io/lounge-math-data/schema/airports.schema.json · [countries](https://igalness.github.io/lounge-math-data/schema/countries.schema.json) |

The app bundles a snapshot of `v1/` at build time and does one `GET` on launch with `If-None-Match`; the file with the highest `data_version` wins. Nothing is sent from the app except that request.

## Layout

```
v1/airports.json             airports with dated, sourced lounge data (schema 0.2)
v1/countries.json            ISO-3166 country -> EU / Schengen border rule
schema/*.schema.json         JSON Schema 2020-12
scripts/validate.py          schema + stamp rules + data_version check (stdlib only)
scripts/test_validate.py     proves the validator rejects bad files
.github/workflows/validate.yml  runs both on every push and pull request
```

Run locally: `python3 scripts/validate.py && python3 -m unittest discover -s scripts`.

## Contributing

Every value carries a confidence, a date and a source, or it does not go in. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

## Licences

- Data (`v1/`): [CC BY 4.0](LICENSE-DATA)
- Code (`scripts/`, `schema/`, workflows): [MIT](LICENSE-CODE)
