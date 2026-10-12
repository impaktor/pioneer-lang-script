#!/usr/bin/env python3
"""
Bulk un-translate strings in a Transifex resource.

Generate API token: https://help.transifex.com/en/articles/6248858-generating-an-api-token
- login to user page
- click user profile top right
- see "API token" menu to left.

Example:
  python untranslate.py \
      --token YOUR_API_TOKEN \
      --org my-org \
      --project my-project \
      --resource BAR \
      --lang de fr es \
      --keys FOO_1 FOO_2 FOO_150 \
      --dry-run
"""

import argparse
import sys
import time
from loguru import logger

from transifex.api import transifex_api
from constants import settings as config

# print(f"Logger id in {__name__}: {id(logger)}")
# logger.info(f"Test log from {__name__}")

try:
    transifex_api.setup(auth=config.API_TOKEN.get_secret_value())
except:
    raise RuntimeError("Set API_TOKEN= config.env file or environment variable")


def parse_args():
    p = argparse.ArgumentParser(description="Bulk un-translate Transifex strings")
    p.add_argument("--org", required=True, help="Organization slug")
    p.add_argument("--project", required=True, help="Project slug")
    p.add_argument("--resource", required=True, help="Resource slug (e.g. BAR)")
    p.add_argument(
        "--lang",
        nargs="+",
        required=True,
        help="Target language code(s), e.g. de fr es",
    )
    p.add_argument(
        "--keys",
        nargs="+",
        required=True,
        help="Source string keys to un-translate, e.g. FOO_1 FOO_2",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be cleared, do not change anything",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=150,
        help="Max translations per bulk PATCH (API limit is 150)",
    )
    return p.parse_args()


def get_resource(org_slug: str, project_slug: str, resource_slug: str):
    """Does sloppy search for matching sub-string of input arguments,
    and assumes only one unique hit, fails if multiple matches, like
    with 'core'"""
    logger.info(f"{org_slug}, {project_slug}, {resource_slug}")
    org = transifex_api.Organization.get(slug=org_slug)
    project = org.fetch("projects").get(slug=project_slug)

    logger.trace(f"{project}")
    logger.trace(f"{resource_slug}")

    resource = project.fetch("resources").get(slug=resource_slug)

    logger.info(f"{org}, {project}, {resource}")
    return resource


def find_translations_to_clear(resource, language, wanted_keys: set[str]):
    """
    Returns list of ResourceTranslation objects that match the wanted keys
    and currently have a translation.
    """
    matches = []
    # include resource_string so we can see the key
    qs = transifex_api.ResourceTranslation.filter(
        resource=resource, language=language
    ).include("resource_string")

    for translation in qs.all():  # handles pagination automatically
        rs = translation.resource_string
        key = getattr(rs, "key", None)
        if key in wanted_keys and translation.strings:
            logger.trace(f"key: {key}, type: {type(key)}, rs: {rs}")
            matches.append(translation)
    return matches


def clear_translations(
    translations: list, batch_size: int = 150, dry_run: bool = False
):
    "Clear the translation content (makes the string untranslated again)."

    # We know the strings that were wrongly marked translated was
    # through an API push 20240704, thus only conside those:
    translations = [
        t
        for t in translations
        if t.attributes.get("origin") == "API"
        and t.attributes.get("datetime_translated")[0:10] == "2024-07-04"
    ]

    if not translations:
        logger.info("No set translations to clear")
        return 0

    logger.warning(f"Found {len(translations)} translated string(s) to clear.")

    n = 0
    for i in range(0, len(translations), batch_size):
        batch = translations[i : i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1} ({len(batch)} strings)...")

        if dry_run:
            for t in batch:
                logger.trace(f"[DRY-RUN] would clear {t.id}")
            continue

        # Clear content. Setting strings=None removes the translation.
        # (This is the documented "remove content" behaviour.)
        for t in batch:
            logger.info(f"Removing {t.id}: {t.attributes.get('strings').get('other')}")
            t.strings = None  # or {} – both work in practice
            # Optional: also drop review/proofread status
            # t.reviewed = False
            # t.proofread = False
            n = n + 1

        # Bulk save – the SDK will issue a bulk PATCH
        # (falls back to individual PATCHes if bulk is not available)
        try:
            # Preferred modern way (SDK ≥ recent versions)
            transifex_api.ResourceTranslation.bulk_update(batch, fields=["strings"])
        except AttributeError:
            # Older SDK – just save one by one
            for t in batch:
                t.save("strings")

        # Be nice to the rate limiter
        time.sleep(0.3)

    logger.success("Done")
    return n


def untranslate(
    org: str,
    project: str,
    resource: str,
    lang_code: str,
    wanted_keys: set[str],
    dry_run=False,
) -> int:
    """Like main, but don't parse from args, and only support one
    language at a time

    Returns
    -------
    N : int
        Number of strings marked as untranslated
    """

    resource = transifex_api.resources.get(id=f"o:{org}:p:{project}:r:{resource}")
    # resource = get_resource(org, project, resource)

    logger.trace(f"Resource:     {resource.id}")
    logger.trace(f"Suspect Keys: {sorted(wanted_keys)}")
    logger.trace(f"Language:     {lang_code}")
    if dry_run:
        logger.info("*** DRY-RUN MODE – no changes will be made ***")

    language = transifex_api.Language.get(code=lang_code)

    suspected_for_removal = find_translations_to_clear(resource, language, wanted_keys)
    logger.trace(f"{suspected_for_removal}")

    n = clear_translations(suspected_for_removal, batch_size=150, dry_run=dry_run)
    return n


def main():
    args = parse_args()

    resource = transifex_api.resources.get(
        id=f"o:{args.org}:p:{args.project}:r:{args.resource}"
    )
    # resource = get_resource(args.org, args.project, args.resource)
    wanted_keys = set(args.keys)

    logger.info(f"Resource : {resource.id}")
    logger.info(f"Keys     : {sorted(wanted_keys)}")
    logger.info(f"Languages: {args.lang}")
    if args.dry_run:
        logger.info("*** DRY-RUN MODE – no changes will be made ***")

    for lang_code in args.lang:
        logger.info(f"=== Language: {lang_code} ===")
        language = transifex_api.Language.get(code=lang_code)

        to_clear = find_translations_to_clear(resource, language, wanted_keys)
        clear_translations(to_clear, batch_size=args.batch_size, dry_run=args.dry_run)

    logger.success("All done.")


if __name__ == "__main__":
    # logger.remove()
    # logger.add(sys.stderr, level=config.LOGLEVEL)
    # logger.add(config.OUTPUT_DIRECTORY / "logfile-{time}.log", level=config.LOGLEVEL)

    main()
