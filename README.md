# MReader iOS Adapters

An iOS-friendly catalog of the websites listed by the Keiyoushi extension repository.

This repository does **not** contain APKs and does not execute Android code. It converts upstream extension metadata into declarative JSON that an iOS app can read, while grouping extensions by their shared website engine whenever that information is available.

## Current catalog

The generated catalog contains:

- Every extension in the current upstream compatibility index.
- Every source name, language, source ID, website URL, and mirror URL exposed by that index.
- Upstream version and icon metadata.
- A derived engine name such as `madara` or `mangathemesia` when the extension declares a shared theme.
- An adapter status so the app never mistakes catalog presence for working iOS support.

See `catalog/summary.json` for exact counts and `catalog/index.json` for the complete machine-readable catalog. Individual extension records are under `sources/<language>/`.

## Adapter states

- `prototype`: an adapter exists but still needs broader testing.
- `supported`: the adapter is intended for normal use.
- `unimplemented`: metadata is available, but the app cannot browse this source yet.
- `blocked`: the source is known to require functionality the current iOS engine cannot provide.

An engine classification does not automatically mean that the source works. It tells us which shared Swift adapter should eventually handle it.

## Updating from upstream

Run:

```sh
python3 scripts/sync_catalog.py
```

The script downloads the current Keiyoushi compatibility index and source definitions, regenerates the catalog, and validates package IDs, URLs, source IDs, and duplicate records.

For an offline rebuild:

```sh
python3 scripts/sync_catalog.py \
  --index-file /path/to/index.json \
  --source-root /path/to/extensions-source
```

Source-specific iOS settings belong in `adapters/overrides/`. Generated files should not be edited directly.

## Relationship to upstream

Extension metadata and engine classifications are derived from the public [Keiyoushi extension repository](https://github.com/keiyoushi/extensions) and [extension source repository](https://github.com/keiyoushi/extensions-source). This project is not affiliated with Keiyoushi, Mihon, Tachiyomi, or any content provider.

Websites can move, close, change structure, require authentication, or block automated clients. The application must respect provider terms, copyright, age restrictions, and applicable law.
