import pytz

# From spacetime-informal: https://github.com/spencermountain/spacetime-informal/blob/778770b2c0523324551e9bdb8ef810ac95a128ab/data/06-abbreviations.js#L9-L15
abbreviations = {
    "America/Halifax": ["ast", "adt", "atlantic"],
    "America/New_York": ["est", "edt", "eastern"],
    "America/Chicago": ["cst", "cdt", "central"],
    "America/Denver": ["mst", "mdt", "mountain"],
    "America/Los_Angeles": ["pst", "pdt", "pacific"],
    "America/Anchorage": ["ahst", "ahdt", "akst", "akdt", "alaska"],
    "America/St_Johns": ["nst", "ndt", "nt", "newfoundland", "nddt"],
}

data = {abbr: iana for iana, abbrs in abbreviations.items() for abbr in abbrs}


def timezone(zone: str) -> pytz.BaseTzInfo:
    zone_lower = zone.lower()
    if zone_lower in data:
        return pytz.timezone(data[zone_lower])
    return pytz.timezone(zone)
