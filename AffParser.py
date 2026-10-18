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
_AFFILIATION_SEPARATORS = re.compile(
    r"\s*\|\s*"
    r"|(?<=\.)\s+&\s+(?=[A-ZÄÖÜ])"
    r"|;\s+(?=[A-ZÄÖÜ])"
)

def splitAffiliations(raw: str) -> list[str]:
    """Trennt eigenständige Affiliations an |, '. &' und Semikolon."""
    return [
        part.strip()
        for part in _AFFILIATION_SEPARATORS.split(raw)
        if part.strip()
    ]
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
        # zip-code infront of Country name "550000 China" -> "China"
        text = re.sub(r"\b\d{4,6}\s+(?=[A-Z])", "", text)
        #author initials in the end: "(Y.N.)" or "(S.K.)"
        text = re.sub(r"\s*\([A-Z]\.[A-Z A-Z\.]*\)\s*$", "", text)
        text = re.sub(r"\s*[A-Z]\.[A-Z\.]+\)\s*§", "", text)
        #trailing special characters after country name: "Italy -" -> "Italy"
        text = re.sub(r"\s*[-\(\)]+s*$", "", text)


    return text.strip().strip(",").strip()

# =============================================
#   step 3 extract last geographical field
# =============================================

    # things that are no Country name, event if they're in the last spot
_NON_GEO = re.compile(
    r"^\s*("
     r"[Dd]ep(?:artment|t)\.?\s*(?:of\s+)?.*|"  # Dept. / Department of …
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

    if not parts:
        return ""

    # from last: first field that fits no Non-Geo-Pattern
    for part in reversed(parts):
        if not _NON_GEO.match(part):
            return part
        # Fallback: last field
    return parts[-1]