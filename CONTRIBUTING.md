# Contributing data

LoungeMath shows a traveller *a time*. A wrong time sends someone to the wrong lounge, or makes them pay for a lounge that closes before they board. The rules below are product rules, not style.

## The four data rules

1. **`unknown` is a real answer.** A missing value never becomes `false` or `0`; the app shows `— NO DATA`. If you don't know, leave the field out or mark the block `unknown`.
2. **Every value that can go stale is stamped**: `confidence` + `verified_on` + `source`. A stamp with no date renders as NO DATA even when a value is present.
3. **Wrong-zone lounges stay in the file.** A Schengen-only lounge is listed with `"zone": "schengen"`; the app strikes it through for non-Schengen departures. Never delete a lounge to "simplify".
4. **Only airports with sourced data exist.** An airport enters `airports.json` only with at least one dated fact beyond its border block. Never add an airport from memory.

## What each confidence means

| `confidence` | App shows | Needs `verified_on` | Needs `source` | Use for |
|---|---|---|---|---|
| `verified` | ■ HUMAN · date | yes | yes | a person vouched on that date: a voucher, a receipt, a boarding pass, a first-hand visit, a friend report (`friend report · <name> · <date>`) |
| `scraped` | □ AUTO · date | yes | yes | read from an airport or lounge website on that date (`<domain> · <date>`) |
| `rule` | ■ HUMAN · RULE | no | no | border policy (EU / Schengen), not a datapoint |
| `unknown` | — NO DATA | no | no | nothing to claim yet |

## Dated sources only, never from memory

`verified_on` is the date of the evidence: the email date of a voucher, the flight date of a boarding pass, the day you read the website. It is not the day you opened the PR. "I think it closes at 20:00" is not a source. If you can't date it, it doesn't go in.

## Adding an airport

1. Copy the **LCA** entry in `v1/airports.json` as your template. It has every block filled in.
2. Set `iata`, `name`, `city`, `country` (ISO 3166-1 alpha-2). The country must already be in `v1/countries.json`; if it isn't, add the country in its own PR first.
3. Fill each block from your source and stamp it. Delete any block you have no dated source for. Don't leave it with guessed values.
4. Set the airport's `updated_at` to today and add your handle to `contributors`.
5. Bump the top-level `data_version` by 1 and set `generated_at` to now (UTC).
6. Leave out `verdict` unless you are the maintainer. The app computes the verdict from the data.
7. Run `python3 scripts/validate.py` and open a PR. Put your evidence in the PR body: a screenshot, a redacted receipt, a link.

## CI rejects bad stamps

`.github/workflows/validate.yml` runs on every push and pull request and fails when:

- a `verified` or `scraped` stamp has no `verified_on` or no `source`;
- a date is not a real calendar day, or is in the future;
- a field is not in the schema, or has the wrong type or enum value;
- `v1/` changed but `data_version` was not bumped above the value on `main`.

A PR with a red check is not reviewed.
