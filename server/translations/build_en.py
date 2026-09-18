#!/usr/bin/env python3
"""Generate the Briefdesk Portal English label catalogue.

The portal reuses newsroom-core's own English strings as message ids and overrides them with the
Briefdesk wording. Every id here has to match newsroom-core's ``messages.pot`` character for
character, or the override silently does nothing, so the ids are read from that file rather than
typed out.

Usage::

    python3 build_en.py                      # reads the pot from the newsroom-core checkout
    python3 build_en.py /path/to/messages.pot

By default the pot is read from ``origin/develop`` of the newsroom-core checkout given by
``NEWSROOM_CORE``, because the working tree of that checkout may be on another branch.

Writes ``en/LC_MESSAGES/messages.po`` and the compiled ``en/LC_MESSAGES/messages.mo``. Both are
committed: nothing in the Dockerfile or the Procfile compiles catalogues at build or boot time, and
newsroom-core likewise commits the compiled ``.mo`` for its fi and fr_CA catalogues.

Standard library only, so it runs without the server's virtualenv.
"""

import array
import os
import re
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "en" / "LC_MESSAGES"
DEFAULT_CORE = HERE.parents[3] / "Core" / "newsroom-core"

# Ids whose rule based rewrite would read badly, or that need wording the rules cannot produce.
OVERRIDES = {
    "Login": "Sign in",
    "Login to Newshub": "Sign in to Briefdesk Portal",
    "Please contact Newsroom administrator to unlock your account": (
        "Please contact the Briefdesk Portal administrator to unlock your account"
    ),
    "Any agenda": "Any programme",
    "Cannot edit coverage watch when watching parent item": (
        "Cannot edit a deliverable follow while following the parent item"
    ),
    "Organize your Topic": "Organise your Watch",
    "You can create Topics by saving search terms and/or filters from the Wire section.": (
        "You can create Watches by saving search terms and filters in the Intelligence Feed."
    ),
    "Select some topics from the sidebar to add them here.": (
        "Select some watches from the sidebar to add them here."
    ),
    "A story has arrived that matches a subscribed topic": (
        "A report has arrived that matches a watch you subscribe to"
    ),
    "A story you downloaded has been updated": "A report you downloaded has been updated",
}

# Message ids that keep their newsroom-core wording.
#
# "Company" stays as it is. A client user reads their own organisation as their company; "Client" is
# how the operator refers to them, not how they refer to themselves, and renaming "Company Admin" to
# "Client Admin" makes the portal's own admin screen read as if it belonged to someone else.
KEEP = set()

_PLACEHOLDER = re.compile(r"(\{\{.*?\}\}|%\([^)]*\)[sdif]|%[sdif])")

# Applied in order. Longer and plural forms first so they are not eaten by the singular rule.
RULES = [
    (r"\bNewshub\b", "Briefdesk Portal"),
    (r"\bNewsroom\b", "Briefdesk Portal"),
    (r"\bCoverages\b", "Deliverables"),
    (r"\bcoverages\b", "deliverables"),
    (r"\bCoverage\b", "Deliverable"),
    (r"\bcoverage\b", "deliverable"),
    (r"\bTopics\b", "Watches"),
    (r"\btopics\b", "watches"),
    (r"\bTopic\b", "Watch"),
    (r"\btopic\b", "watch"),
    (r"\bSlugline\b", "Reference"),
    (r"\bslugline\b", "reference"),
    (r"\bHeadline\b", "Title"),
    (r"\bheadline\b", "title"),
    (r"\bWire\b", "Intelligence Feed"),
    (r"\bAgenda\b", "Risk Calendar"),
    (r"\bStories\b", "Reports"),
    (r"\bstories\b", "reports"),
    (r"\bStory\b", "Report"),
    (r"\bstory\b", "report"),
    (r"\bArticles\b", "Reports"),
    (r"\barticles\b", "reports"),
    (r"\bArticle\b", "Report"),
    (r"\barticle\b", "report"),
    (r"\bnews items\b", "reports"),
    (r"\bnews item\b", "report"),
]

COMPILED_RULES = [(re.compile(pattern), replacement) for pattern, replacement in RULES]


def translate(msgid):
    """Return the Briefdesk wording for ``msgid``, or None if it is unchanged."""

    if msgid in KEEP:
        return None
    if msgid in OVERRIDES:
        return OVERRIDES[msgid]

    # Placeholders such as ``{{ wire }}`` name a config value, not the English word, and must
    # survive the rewrite untouched.
    parts = _PLACEHOLDER.split(msgid)
    for index in range(0, len(parts), 2):
        for pattern, replacement in COMPILED_RULES:
            parts[index] = pattern.sub(replacement, parts[index])
    result = "".join(parts)

    return result if result != msgid else None


def read_pot(text):
    """Return the msgids of a PO/POT file, in file order, skipping the metadata entry."""

    msgids = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("msgid "):
            if current is not None:
                msgids.append(current)
            current = unquote(line[len("msgid "):])
        elif line.startswith('"') and current is not None:
            current += unquote(line)
        elif line.startswith("msgstr") or line.startswith("#") or not line:
            if current is not None:
                msgids.append(current)
                current = None
    if current is not None:
        msgids.append(current)
    return [msgid for msgid in msgids if msgid]


def unquote(value):
    value = value.strip()
    if not (value.startswith('"') and value.endswith('"')):
        raise ValueError(f"not a PO string: {value!r}")
    return (
        value[1:-1]
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def quote(value):
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\t", "\\t")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def load_pot(argv):
    if len(argv) > 1:
        return Path(argv[1]).read_text(encoding="utf-8")

    core = Path(os.environ.get("NEWSROOM_CORE", DEFAULT_CORE))
    if not core.exists():
        sys.exit(
            f"newsroom-core checkout not found at {core}. "
            "Pass the path to messages.pot as an argument or set NEWSROOM_CORE."
        )
    return subprocess.run(
        ["git", "-C", str(core), "show", "origin/develop:messages.pot"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def po_header():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M+0000")
    return [
        "Project-Id-Version: Briefdesk Portal",
        "Report-Msgid-Bugs-To: clientdesk@halden.example",
        f"POT-Creation-Date: {now}",
        f"PO-Revision-Date: {now}",
        "Language: en",
        "Language-Team: Briefdesk",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "Content-Transfer-Encoding: 8bit",
        "Plural-Forms: nplurals=2; plural=(n != 1);",
    ]


def write_po(path, entries, header_lines):
    lines = [
        "# Briefdesk Portal English label overrides.",
        "# Generated by build_en.py, do not edit by hand. Change the rules in that script instead.",
        "#",
        'msgid ""',
        'msgstr ""',
    ]
    lines.extend(quote(line + "\n") for line in header_lines)
    lines.append("")

    for msgid, msgstr in entries:
        lines.append(f"msgid {quote(msgid)}")
        lines.append(f"msgstr {quote(msgstr)}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_mo(path, entries, header):
    """Write a GNU .mo file. Same layout as the stdlib Tools/i18n/msgfmt.py generator."""

    catalog = [("", header)] + list(entries)
    catalog.sort(key=lambda pair: pair[0].encode("utf-8"))

    keys = b""
    values = b""
    key_offsets = []
    value_offsets = []
    for msgid, msgstr in catalog:
        raw_id = msgid.encode("utf-8")
        raw_str = msgstr.encode("utf-8")
        key_offsets.append((len(raw_id), len(keys)))
        value_offsets.append((len(raw_str), len(values)))
        keys += raw_id + b"\x00"
        values += raw_str + b"\x00"

    count = len(catalog)
    key_table_offset = 7 * 4
    value_table_offset = key_table_offset + count * 8
    keys_offset = value_table_offset + count * 8
    values_offset = keys_offset + len(keys)

    offsets = []
    for (id_length, id_offset), (str_length, str_offset) in zip(key_offsets, value_offsets):
        offsets.append(id_length)
        offsets.append(id_offset + keys_offset)
    for (id_length, id_offset), (str_length, str_offset) in zip(key_offsets, value_offsets):
        offsets.append(str_length)
        offsets.append(str_offset + values_offset)

    output = struct.pack(
        "Iiiiiii",
        0x950412DE,
        0,
        count,
        key_table_offset,
        value_table_offset,
        0,
        0,
    )
    output += array.array("i", offsets).tobytes()
    output += keys
    output += values

    path.write_bytes(output)


def main(argv):
    pot = load_pot(argv)
    msgids = read_pot(pot)

    entries = []
    for msgid in msgids:
        msgstr = translate(msgid)
        if msgstr:
            entries.append((msgid, msgstr))

    missing = sorted(set(OVERRIDES) - set(msgids))
    if missing:
        print("WARNING: these overrides do not match any msgid in the pot and do nothing:")
        for msgid in missing:
            print(f"  {msgid!r}")

    header_lines = po_header()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_po(OUT_DIR / "messages.po", entries, header_lines)
    write_mo(OUT_DIR / "messages.mo", entries, "".join(line + "\n" for line in header_lines))

    print(f"{len(msgids)} message ids read, {len(entries)} overridden")
    print(f"wrote {OUT_DIR / 'messages.po'}")
    print(f"wrote {OUT_DIR / 'messages.mo'}")


if __name__ == "__main__":
    main(sys.argv)
