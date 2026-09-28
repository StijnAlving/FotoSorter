"""Resolve a photo's country: GPS EXIF (offline reverse-geocode) first, then
the user's manual date-range -> location mapping. GPS is a bonus path - the
current camera in this project has no GPS at all, so the manual mapping is
what actually does the work today."""
from datetime import datetime

from . import config

# ISO 3166-1 alpha-2 -> common English name, for labelling reverse_geocoder's
# country-code output. Falls back to the raw code for anything missing here.
_COUNTRY_NAMES = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan", "AG": "Antigua and Barbuda",
    "AI": "Anguilla", "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AR": "Argentina",
    "AT": "Austria", "AU": "Australia", "AW": "Aruba", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria",
    "BH": "Bahrain", "BI": "Burundi", "BJ": "Benin", "BN": "Brunei", "BO": "Bolivia", "BR": "Brazil",
    "BS": "Bahamas", "BT": "Bhutan", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize", "CA": "Canada",
    "CD": "DR Congo", "CF": "Central African Republic", "CG": "Congo", "CH": "Switzerland",
    "CI": "Ivory Coast", "CL": "Chile", "CM": "Cameroon", "CN": "China", "CO": "Colombia",
    "CR": "Costa Rica", "CU": "Cuba", "CV": "Cabo Verde", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica", "DO": "Dominican Republic",
    "DZ": "Algeria", "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "ER": "Eritrea", "ES": "Spain",
    "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FR": "France", "GA": "Gabon",
    "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia", "GH": "Ghana", "GL": "Greenland",
    "GM": "Gambia", "GN": "Guinea", "GQ": "Equatorial Guinea", "GR": "Greece", "GT": "Guatemala",
    "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong", "HN": "Honduras", "HR": "Croatia",
    "HT": "Haiti", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India",
    "IQ": "Iraq", "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JM": "Jamaica", "JO": "Jordan",
    "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati",
    "KM": "Comoros", "KN": "Saint Kitts and Nevis", "KP": "North Korea", "KR": "South Korea",
    "KW": "Kuwait", "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon", "LC": "Saint Lucia",
    "LI": "Liechtenstein", "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MC": "Monaco",
    "MD": "Moldova", "ME": "Montenegro", "MG": "Madagascar", "MH": "Marshall Islands",
    "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia", "MR": "Mauritania",
    "MT": "Malta", "MU": "Mauritius", "MV": "Maldives", "MW": "Malawi", "MX": "Mexico",
    "MY": "Malaysia", "MZ": "Mozambique", "NA": "Namibia", "NE": "Niger", "NG": "Nigeria",
    "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NZ": "New Zealand",
    "OM": "Oman", "PA": "Panama", "PE": "Peru", "PG": "Papua New Guinea", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", "PW": "Palau", "PY": "Paraguay",
    "QA": "Qatar", "RO": "Romania", "RS": "Serbia", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan",
    "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia", "SK": "Slovakia", "SL": "Sierra Leone",
    "SM": "San Marino", "SN": "Senegal", "SO": "Somalia", "SR": "Suriname", "SS": "South Sudan",
    "ST": "Sao Tome and Principe", "SV": "El Salvador", "SY": "Syria", "SZ": "Eswatini",
    "TD": "Chad", "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan", "TL": "Timor-Leste",
    "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey", "TT": "Trinidad and Tobago",
    "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "US": "USA", "UY": "Uruguay", "UZ": "Uzbekistan", "VA": "Vatican City",
    "VC": "Saint Vincent and the Grenadines", "VE": "Venezuela", "VN": "Vietnam", "VU": "Vanuatu",
    "WS": "Samoa", "YE": "Yemen", "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

_rg = None  # lazily imported: reverse_geocoder loads a multi-MB dataset on first use


def gps_to_country(lat: float, lon: float) -> str | None:
    global _rg
    try:
        if _rg is None:
            import reverse_geocoder as rg
            _rg = rg
        result = _rg.search([(lat, lon)])
        cc = result[0]["cc"]
        return _COUNTRY_NAMES.get(cc, cc)
    except Exception:
        return None  # offline dataset missing/corrupt etc. - fall back to manual rules


def resolve_country(gps_lat: float | None, gps_lon: float | None, taken: datetime, config_dir) -> str | None:
    if gps_lat is not None and gps_lon is not None:
        country = gps_to_country(gps_lat, gps_lon)
        if country:
            return country
    rules = config.load_location_rules(config_dir)
    return config.lookup_location(rules, taken.date() if isinstance(taken, datetime) else taken)
