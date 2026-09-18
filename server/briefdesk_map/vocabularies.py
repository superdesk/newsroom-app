"""Labels and colours for the Briefdesk taxonomies used by the map mock.

These mirror the Superdesk custom vocabularies (`severity`, `threat_type`,
`region`, `sector`, `country`). They are duplicated here because the mock does
not read anything from the database.
"""

SEVERITIES = [
    {"code": "critical", "name": "Critical", "color": "#B42318", "rank": 5, "radius": 11},
    {"code": "high", "name": "High", "color": "#D9480F", "rank": 4, "radius": 9},
    {"code": "medium", "name": "Medium", "color": "#E8A317", "rank": 3, "radius": 8},
    {"code": "low", "name": "Low", "color": "#2E7D5B", "rank": 2, "radius": 7},
    {"code": "info", "name": "Informational", "color": "#5B7083", "rank": 1, "radius": 6},
]

THREAT_TYPES = [
    {"code": "civil_unrest", "name": "Civil unrest"},
    {"code": "terrorism", "name": "Terrorism"},
    {"code": "crime", "name": "Crime"},
    {"code": "natural_hazard", "name": "Natural hazard"},
    {"code": "transport", "name": "Transport disruption"},
    {"code": "industrial_action", "name": "Industrial action"},
    {"code": "cyber", "name": "Cyber"},
    {"code": "health", "name": "Health"},
    {"code": "political", "name": "Political"},
    {"code": "conflict", "name": "Armed conflict"},
]

REGIONS = {
    "europe": "Europe",
    "mena": "Middle East and North Africa",
    "americas": "Americas",
    "apac": "Asia-Pacific",
    "ssa": "Sub-Saharan Africa",
}

SECTORS = {
    "logistics": "Logistics",
    "pharma": "Pharmaceuticals",
    "energy": "Energy",
    "finance": "Finance",
    "retail": "Retail",
    "technology": "Technology",
}

COUNTRIES = {
    "pl": "Poland",
    "de": "Germany",
    "cz": "Czechia",
    "fr": "France",
    "es": "Spain",
    "it": "Italy",
    "nl": "Netherlands",
    "gb": "United Kingdom",
    "tr": "Türkiye",
    "eg": "Egypt",
    "ae": "United Arab Emirates",
    "sa": "Saudi Arabia",
    "mx": "Mexico",
    "br": "Brazil",
    "us": "United States",
}

DEFAULT_SEVERITY = {"code": "info", "name": "Informational", "color": "#5B7083", "rank": 1, "radius": 6}

SEVERITY_BY_CODE = {item["code"]: item for item in SEVERITIES}
THREAT_TYPE_BY_CODE = {item["code"]: item for item in THREAT_TYPES}
