from __future__ import annotations
import pycountry
import re

"""
    Parsing raw PubMed-Affiliation strings

     Steps for Parsing the Strings:
     1st. parting the String into separate affiliations
     2nd. Delete Noise (E-Mails, postal adresses, …)
     3rd. extract the last geographical field
"""

# ============================================
#   step 1 splitting the Affiliation Strings
# ============================================

# initially as numbered blocks -> splits them up into multiple strings

_NUMBERED_SPLIT = re.compile(r"(?<=[.!?])\s+(?=\d+\s+[A-Z])")

def splitAffiliations(raw: str) -> list[str]:
    """
    returns a list of single Affiliations

    supported formats:
    split with "|"
        "inst A, Berlin, Germany | inst B, Paris, France"

    split with ";"
        "inst A, Berlin, Germany; inst B, Paris, France"

    Single Affiliations (no splitting sign)
        "Charité Berlin, Berlin, Germany"
    """

    #split with "|"
    if "|" in raw:
        return [s.strip() for s in raw.split("|") if s.strip()]

    #Numbered
    parts = _NUMBERED_SPLIT .split(raw)
    if len(parts) > 1:
        cleaned = []
        for part in parts:
            # delete leading number and space ("1 Inst A" -> "Inst A")
            part = re.sub(r"^\d+\s", "", part).strip()
            if part:
                cleaned.append(part)
        return cleaned

    # Single Affiliation
    return [raw.strip()]

# ============================
#     step 2 delete Noise
# ============================

_NOISE_PATTERNS: list [re.Pattern] = [
    # E-Mails
    re.compile(r"[Ee]lectronic\s+[Aa]ddress\s*:?\s*\S+@\S+"),
    re.compile(r"[Ee]-?[Mm]ail\s*:?\s*\S+@\S+"),
    re.compile(r"[Cc]orrespond\w*\s*(?:[Aa]uthor)?\s*:?\s*\S+@\S+"),
    # "Electronic address:" ohne E-Mail dahinter (Label allein)
    re.compile(r"[Ee]lectronic\s+[Aa]ddress\s*:?\s*$"),
    # raw E-Mail-Patter
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b"),
    # Mailbox
    re.compile(r"P\.?\s*O\.?\s*[Bb]ox\s+[\w-]+", re.I),
    re.compile(r"[Pp]ostf(?:ach)?\s*\d+"),
    # brackets only containing Contact information
    re.compile(r"\([^)]*@[^)]*\)"),
    re.compile(r"\((?:[Cc]ontact|[Cc]orrespond)[^)]*\)"),
    # "Electronic address" (last sentence)
    re.compile(r"\.\s*[Ee]lectronic\s+[Aa]ddress.*$"),
    # Trailing-punctuation
    re.compile(r"[.,;]\s*$"),
]
def removeNoise(text: str) -> str:
    """
        removes e-mail adresses, mailboxes & other non-geo-information
        out of a single Affiliation string
    """
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub("", text)
        # removing:
        # Empty brackets "( ,"->","
        text = re.sub(r"\(\s*,", ",", text)
        text = re.sub(r"\(\s*,+", ",", text)
        # double/ hanging commas
        text = re.sub(r" ,\s*,+", ",", text)
        # multiple spaces
        text = re.sub(r"  +", " ", text)
        # space before comma
        text = re.sub(r"\s+,", ",", text)
        #trailling "."
        text = text.strip(".")
        # building nr. like "Geb. 50.41"
        text = re.sub(r"[Gg]eb\.\s*[\d.]+", "", text)
        # zip-code + city blocks "76131 Karlsruhe"
        text = re.sub(r"\b\d{4,5}\s+[A-ZÄÖÜ][a-zäöüß]+", "", text)

    return text.strip().strip(",").strip()

# =============================================
#   step 3 extract last geographical field
# =============================================

    # things that are no Country name, event if they're in the last spot
_NON_GEO = re.compile(
    r"^\s*("
    r"[Dd]ept(?:artment)?\.?\s*(?:of\s+)?.*|"   # Dept. / Department of …
    r"[Dd]ivision\s*(?:of\s+)?.*|"
    r"[Ll]aborator(?:y|ies).*|"
    r"[Ff]acult(?:y|ies)\s*(?:of\s+)?.*|"
    r"[Ss]chool\s+of\s+.*|"
    r"[Ii]nstitute\s*(?:of\s+)?.*|"
    r"[Cc]ent(?:er|re)\s*(?:for\s+)?.*|"
    r"[Ss]ection\s*(?:of\s+)?.*|"
    r"[Ww]ard\s+\w+.*|"
    r"\d{4,6}\s*|"                               # Postal codes "02115"
    r"[A-Z]{2}\s+\d{4,6}\s*"                    # State + ZIP "MA 02115"
    r")\s*$",
    re.DOTALL,
)

def extractGeoField(affiliation: str) -> str:
    """
    returns the last field that could be geographical.
    Skips department names and fields containing only postal codes.
    """
    parts = [p.strip() for p in affiliation.split(",")]
    parts = [p for p in parts if len(p) > 1]

    # from last: first field that fits no Non-Geo-Pattern
    for part in reversed(parts):
        if not _NON_GEO.match(part):
            return part
        # Fallback: last field
    return parts[-1]

# ===================================
#   Open API - combine all 3 steps
# ===================================

def parseAffiliation(raw: str) -> list[str]:
    """
    takes a raw PubMed-Affiliation string.
    returns list of cleaned Geo-Candidates
    (one per affiliation)

    Example:
    -------------
    >>> parseAffiliation("charité Berlin, Berlin, Germany, Email: x@charté.de")
    ['Germany']
    >>> parseAffiliation("Inst A, Berlin, Germany, Inst B, Paris, France")
    ['Germany', 'France']
    """
    candidates: list[str] = []

    for single in splitAffiliations(raw):       # step 1
        clean = removeNoise(single)             # step 2
        if not clean:
            continue
        field = extractGeoField(clean)          # step 3
        if field:
            candidates.append(field)
    return candidates