#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import tarfile
import tempfile
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


INDEX_URL = "https://github.com/keiyoushi/extensions/raw/repo/index.json"
SOURCE_ARCHIVE_URL = "https://github.com/keiyoushi/extensions-source/archive/refs/heads/main.tar.gz"
PACKAGE_PREFIX = "eu.kanade.tachiyomi.extension."
THEME_PATTERN = re.compile(r'\btheme\s*=\s*"([^"]+)"')
RATING_MAP = {
    "CONTENT_WARNING_SAFE": "safe",
    "CONTENT_WARNING_MIXED": "mixed",
    "CONTENT_WARNING_NSFW": "nsfw",
}


def arguments():
    parser = argparse.ArgumentParser(description="Generate the MReader iOS source catalog")
    parser.add_argument("--index-file", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser.parse_args()


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": "MReader-Catalog-Sync/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def safe_extract(archive, destination):
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if destination not in target.parents and target != destination:
            raise ValueError(f"Unsafe archive path: {member.name}")
    archive.extractall(destination)


def acquire_inputs(args, temporary):
    if args.index_file:
        index_file = args.index_file.resolve()
    else:
        index_file = temporary / "index.json"
        download(INDEX_URL, index_file)

    if args.source_root:
        source_root = args.source_root.resolve()
    else:
        archive_file = temporary / "extensions-source.tar.gz"
        extracted = temporary / "extensions-source"
        extracted.mkdir()
        download(SOURCE_ARCHIVE_URL, archive_file)
        with tarfile.open(archive_file, "r:gz") as archive:
            safe_extract(archive, extracted)
        candidates = [item for item in extracted.iterdir() if item.is_dir()]
        if len(candidates) != 1:
            raise ValueError("Unexpected extensions-source archive layout")
        source_root = candidates[0]

    return index_file, source_root


def read_extensions(index_file):
    with index_file.open(encoding="utf-8") as file:
        payload = json.load(file)
    extensions = payload.get("extensionList", {}).get("extensions")
    if not isinstance(extensions, list) or not extensions:
        raise ValueError("The upstream index does not contain extensionList.extensions")
    return extensions


def theme_for(package_id, source_root):
    if not package_id.startswith(PACKAGE_PREFIX):
        return "custom"
    components = package_id[len(PACKAGE_PREFIX):].split(".")
    if len(components) < 2:
        return "custom"
    build_file = source_root / "src" / components[-2] / components[-1] / "build.gradle.kts"
    if not build_file.is_file():
        return "custom"
    match = THEME_PATTERN.search(build_file.read_text(encoding="utf-8"))
    return match.group(1) if match else "custom"


def load_override(output_root, package_id):
    path = output_root / "adapters" / "overrides" / f"{package_id}.json"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Adapter override must be an object: {path}")
    return value


def valid_web_url(value):
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_record(extension, source_root, output_root):
    package_id = extension.get("packageName", "").strip()
    if not package_id:
        raise ValueError("Extension is missing packageName")

    resources = extension.get("resources") or {}
    engine = theme_for(package_id, source_root)
    adapter = {
        "engine": engine,
        "status": "prototype" if engine == "madara" else "unimplemented",
        "options": {"requiresWebView": True} if engine == "madara" else {},
    }
    adapter.update(load_override(output_root, package_id))

    sources = []
    seen_source_ids = set()
    for source in extension.get("sources") or []:
        source_id = str(source.get("id", "")).strip()
        if not source_id or source_id in seen_source_ids:
            raise ValueError(f"Missing or duplicate source ID in {package_id}: {source_id}")
        seen_source_ids.add(source_id)

        base_url = (source.get("homeUrl") or "").strip()
        mirrors = list(dict.fromkeys(source.get("mirrorUrls") or []))
        for url in [base_url, *mirrors]:
            if not valid_web_url(url):
                raise ValueError(f"Invalid website URL in {package_id}: {url}")

        sources.append({
            "id": source_id,
            "name": str(source.get("name", "")).strip(),
            "language": str(source.get("language", "")).strip(),
            "baseURL": base_url,
            "mirrorURLs": mirrors,
        })

    return {
        "schemaVersion": 1,
        "packageID": package_id,
        "name": str(extension.get("name", "")).strip(),
        "version": str(extension.get("versionName", "")).strip(),
        "contentRating": RATING_MAP.get(extension.get("contentWarning"), "unknown"),
        "iconURL": resources.get("iconUrl"),
        "adapter": adapter,
        "sources": sources,
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def regenerate(args, index_file, source_root):
    output_root = args.output_root.resolve()
    source_output = output_root / "sources"
    catalog_output = output_root / "catalog"
    if source_output.exists():
        shutil.rmtree(source_output)
    if catalog_output.exists():
        shutil.rmtree(catalog_output)

    upstream = read_extensions(index_file)
    records = [build_record(item, source_root, output_root) for item in upstream]
    records.sort(key=lambda item: item["packageID"])

    package_ids = [item["packageID"] for item in records]
    if len(package_ids) != len(set(package_ids)):
        raise ValueError("Duplicate package IDs found")

    for record in records:
        relative = record["packageID"][len(PACKAGE_PREFIX):] if record["packageID"].startswith(PACKAGE_PREFIX) else record["packageID"]
        components = relative.split(".")
        language = components[-2] if len(components) >= 2 else "other"
        slug = components[-1]
        write_json(source_output / language / f"{slug}.json", record)

    source_count = sum(len(item["sources"]) for item in records)
    websites = {
        source["baseURL"]
        for item in records
        for source in item["sources"]
        if source["baseURL"]
    }
    engine_counts = Counter(item["adapter"]["engine"] for item in records)
    status_counts = Counter(item["adapter"]["status"] for item in records)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    index = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "upstream": {
            "repository": "https://github.com/keiyoushi/extensions",
            "indexURL": INDEX_URL,
            "sourceRepository": "https://github.com/keiyoushi/extensions-source",
        },
        "extensions": records,
    }
    summary = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "extensionCount": len(records),
        "sourceCount": source_count,
        "uniqueWebsiteCount": len(websites),
        "engineCounts": dict(sorted(engine_counts.items())),
        "adapterStatusCounts": dict(sorted(status_counts.items())),
    }
    write_json(catalog_output / "index.json", index)
    write_json(catalog_output / "summary.json", summary)
    return summary


def main():
    args = arguments()
    with tempfile.TemporaryDirectory(prefix="mreader-catalog-") as directory:
        temporary = Path(directory)
        index_file, source_root = acquire_inputs(args, temporary)
        summary = regenerate(args, index_file, source_root)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
