"""Parse pioneer's data/lang folder and compare strings with base
English to estimate how many are not translated.

1. Go through all languages and modules to compare each translated
string with the value for the same key with en.json.

2. If the string is identical AND that string has been translated to
something different in fi.json or sv.json, add it to our list of
strings to remove translation in transifex.

(compare with fi & sv to not remove things likely similar across
languages - like "km", "kg", or across germanic lanuages, like "Jul",
"Aug", "Sep")

3. If the string is not translated on transifex side, no operation is
done, it is still marked as not translated on transifex side.

4. If the string is marked as translated (i.e. has metadata), AND the
metadata for the string indicates it was created through the 'API'
(rather than 'Editor'), AND it was added on 2024-07-04, then remove
the translation!

Rinse and repeat across strings, modules, lanuages.

"""

# DOCUMENTATION
# -------------
# eglot:
# C-h .    display-local-help, documentation for method under cursor
# C-c ! H  eldoc-doc-buffer, buffer showing doc for method under cursor
# M-.      jump to definition
# M-,      jump back
# M-x eldoc                 ; refresh doc at point
# M-x eglot-find-declaration
# M-x eglot-find-implementation
# M-x eglot-find-typeDefinition

# OTHER
# -----
# C-c C-p run-python
# C-C C-c python-shell-send-buffer
# C-c C-r python-shell-send-region

import json
import os
import sys

from loguru import logger
from pathlib import Path
from push_to_transifex import untranslate
from pprint import pformat

from constants import settings as config

logger.remove()
logger.add(sys.stderr, level=config.LOGLEVEL)
logger.add("logfile-{time}.log", level=config.LOGLEVEL)

# Print parsed variables to log
logger.info(f"Parsed environment variables:\n{pformat(config.model_dump())}")

# print(f"Logger id in {__name__}: {id(logger)}")
# logger.info(f"Test log from {__name__}")


def get_modules() -> list[str]:
    "List of all translated modules"
    logger.info("Getting modules")
    lang_module_path = config.PIONEER_PATH / "data/lang"
    module_folders = [f.path for f in os.scandir(lang_module_path) if f.is_dir()]
    return module_folders


def get_languages() -> list[str]:
    "Get languages"
    logger.info("Getting languages")
    module_path = config.PIONEER_PATH / "data/lang/core/"
    langs = [f.name for f in os.scandir(module_path)]
    return langs


def get_strings(json_file: Path | str) -> dict:
    "Get strings in the json file for lang_code"
    logger.trace(f"Getting json strings from {json_file}")

    with open(json_file) as f:
        # lines = f.readlines()
        d = json.load(f)

    return d


def untranslate_keys() -> dict:
    """Find strings matching English translation - but that we keep.
    e.g. kg, AU, etc.

    Take Hungarian and Finish as truth / good translations. If any of
    these match an egnlish word, we white list the key as OK in all
    languages.

    Returns
    -------
    N : int
        Number of translations removed
    """

    langs = get_languages()  # list of names of language: xx.json
    modules = get_modules()  # list of full paths to modules

    # These modules are newer than 2023, when the all strings were
    # marked 'translated' thus need not process these.
    remove_modules = [
        "module-findperson",
        "about",
        "persons",
        "module-easteregg-message",  # also ignore, hard to translate
    ]
    modules = [s for s in modules if not any(word in s for word in remove_modules)]

    # These languages are defined as "ground truth" translations.
    remove_langs = [
        "fi.json",
        "en.json",
        "sv.json",
    ]
    langs = [s for s in langs if not any(word in s for word in remove_langs)]

    count = {}

    for lang in langs:
        # lang = "hu.json" # xxx test

        count[lang] = 0

        logger.info(f"Doing language: {lang}")

        for module in modules:
            # Hold keys to mark for untranslation, for this lang & module
            keys = set()

            # Process translation keys
            path = Path(module) / Path(lang)
            d = get_strings(path)

            # Compare each key to english translation
            path_en = Path(module) / Path("en.json")
            d_en = get_strings(path_en)

            # but ignore if also same in Finish (best translation)
            path_fi = Path(module) / Path("fi.json")
            d_fi = get_strings(path_fi)

            # ..or swedish
            path_sv = Path(module) / Path("sv.json")
            d_sv = get_strings(path_sv)

            logger.info(f"Doing file: {path}")

            for k, v in d.items():
                if d_en[k]["message"] == v["message"] and (
                    d_fi[k]["message"] != v["message"]
                    and d_sv[k]["message"] != v["message"]
                ):
                    # string is identical to en.json, and both fi and
                    # sv have translated it to something different
                    # than en.json:
                    logger.debug(f"Adding: {k}: {v['message']}")
                    keys.add(k)
                else:
                    pass

            if len(keys) > 0:
                module_name = Path(module).name
                logger.info(
                    f"Identified {len(keys)} from module: {module_name} in lang: {lang}"
                )
                logger.trace(f"Keys: {keys}")

                l = Path(lang).stem
                n = untranslate(
                    org="pioneer",
                    project="pioneer",
                    resource=module_name,
                    lang_code=l,
                    wanted_keys=keys,
                    dry_run=True,
                )
                logger.success(f"Removed: {n} {l} translations from {module_name}")
                count[lang] = count[lang] + n
        logger.success(f"Language: {l} finished, untranslated: {count[lang]} strings")
    return count


def print_keys_to_file():

    modules = get_modules()
    d_all = {}  # tmp, just for collecting all English strings.

    for module in modules:
        languages = get_languages(module)

        # get path to english, as ground truth
        # (Invalid if no en.json, (which should be impossible))
        lang_en = next(f for f in languages if "en.json" in f)

        languages = [next(f for f in languages if "fi.json" in f)]

        # dictionary with english base strings
        d_en = get_strings(lang_en)

        # for each language
        for lang in languages:
            print(f"processing file {lang}")
            d = get_strings(lang)

            # Store non-English strings to dictionary
            d_new = {}

            for k, v in d.items():
                # print(f"English: {d_en[k]['message']}")
                # print(f"{lang.split('/')[-1]}: {v['message']}")

                if d_en[k]["message"] != v["message"]:
                    d_new[k] = v
                else:
                    d_all[k] = v

            # write d_new to file
            file_new = lang.replace(".json", "_new.json")

            if d_new:
                with open(file_new, "w", encoding="utf8") as fp:
                    json.dump(d_new, fp, indent=4, sort_keys=True, ensure_ascii=False)
                print(f"Wrote file: {file_new}")
            break  ## fi / xxx

    with open("/home/karlf/all.json", "w", encoding="utf8") as fp:
        json.dump(d_all, fp, indent=4, sort_keys=True, ensure_ascii=False)

    print(f"Total size of d_all: {len(d_all)}")


if __name__ == "__main__":
    # print_keys_to_file()

    d = untranslate_keys()

    for k, v in d.items():
        logger.success(f"Total untranslated: {k}: {v}")
