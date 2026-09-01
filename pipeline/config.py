"""Configuration and constants for the OpenDataViz Pipeline."""

import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "dashboard" / "public" / "data"
DB_PATH = DATA_DIR / "warehouse.duckdb"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- World Bank API ---
WB_BASE_URL = "https://api.worldbank.org/v2"
WB_FORMAT = "json"
WB_DATE_RANGE = "2000:2024"
WB_PER_PAGE = 10000  # Max to avoid pagination

# --- Indicators ---
# Organized into 4 poles: Economy, Health, Education, Infrastructure (15 each = 60 total).
# The 10 original indicators are folded into the pole that fits them best
# (e.g. population/unemployment/fdi_inflows -> Economy, internet_users -> Infrastructure).
INDICATORS = {
    # ── Economy (15) ──────────────────────────────────────────────
    "NY.GDP.MKTP.CD": {"name": "GDP (current US$)", "category": "Economy", "unit": "US$", "short": "gdp"},
    "NY.GDP.MKTP.KD.ZG": {"name": "GDP Growth (annual %)", "category": "Economy", "unit": "%", "short": "gdp_growth"},
    "NY.GDP.PCAP.PP.CD": {"name": "GDP per Capita, PPP (current international $)", "category": "Economy", "unit": "Int'l $", "short": "gdp_per_capita_ppp"},
    "SP.POP.TOTL": {"name": "Population", "category": "Economy", "unit": "count", "short": "population"},
    "FP.CPI.TOTL.ZG": {"name": "Inflation (CPI, annual %)", "category": "Economy", "unit": "%", "short": "inflation"},
    "SL.UEM.TOTL.ZS": {"name": "Unemployment (% of labor force)", "category": "Economy", "unit": "%", "short": "unemployment"},
    "BX.KLT.DINV.WD.GD.ZS": {"name": "FDI Inflows (% of GDP)", "category": "Economy", "unit": "%", "short": "fdi_inflows"},
    "SI.POV.GINI": {"name": "GINI Index", "category": "Economy", "unit": "index", "short": "gini_index"},
    "NE.EXP.GNFS.ZS": {"name": "Exports of Goods and Services (% of GDP)", "category": "Economy", "unit": "%", "short": "exports_gdp"},
    "NE.IMP.GNFS.ZS": {"name": "Imports of Goods and Services (% of GDP)", "category": "Economy", "unit": "%", "short": "imports_gdp"},
    "DT.DOD.DECT.GN.ZS": {"name": "External Debt Stocks (% of GNI)", "category": "Economy", "unit": "%", "short": "external_debt"},
    "NY.GNS.ICTR.ZS": {"name": "Gross Savings (% of GDP)", "category": "Economy", "unit": "%", "short": "gross_savings"},
    "NE.GDI.FTOT.ZS": {"name": "Gross Fixed Capital Formation (% of GDP)", "category": "Economy", "unit": "%", "short": "capital_formation"},
    "PA.NUS.FCRF": {"name": "Official Exchange Rate (LCU per US$)", "category": "Economy", "unit": "LCU/US$", "short": "exchange_rate"},
    "GC.DOD.TOTL.GD.ZS": {"name": "Central Government Debt, Total (% of GDP)", "category": "Economy", "unit": "%", "short": "government_debt"},

    # ── Health (15) ───────────────────────────────────────────────
    "SP.DYN.LE00.IN": {"name": "Life Expectancy at Birth", "category": "Health", "unit": "years", "short": "life_expectancy"},
    "SH.XPD.CHEX.GD.ZS": {"name": "Current Health Expenditure (% of GDP)", "category": "Health", "unit": "%", "short": "health_expenditure_gdp"},
    "SH.MED.PHYS.ZS": {"name": "Physicians (per 1,000 people)", "category": "Health", "unit": "per 1,000", "short": "physicians_density"},
    "SP.DYN.IMRT.IN": {"name": "Infant Mortality Rate (per 1,000 live births)", "category": "Health", "unit": "per 1,000", "short": "infant_mortality"},
    "SH.DYN.AIDS.ZS": {"name": "HIV Prevalence (% ages 15-49)", "category": "Health", "unit": "%", "short": "hiv_prevalence"},
    "SH.IMM.IDPT": {"name": "Immunization, DPT (% of children ages 12-23 months)", "category": "Health", "unit": "%", "short": "immunization_dpt"},
    "SH.MED.BEDS.ZS": {"name": "Hospital Beds (per 1,000 people)", "category": "Health", "unit": "per 1,000", "short": "hospital_beds"},
    "SH.XPD.CHEX.PC.CD": {"name": "Health Expenditure per Capita (current US$)", "category": "Health", "unit": "US$", "short": "health_expenditure_capita"},
    "SH.DYN.MORT": {"name": "Under-5 Mortality Rate (per 1,000 live births)", "category": "Health", "unit": "per 1,000", "short": "under5_mortality"},
    "SH.STA.MMRT": {"name": "Maternal Mortality Ratio (per 100,000 live births)", "category": "Health", "unit": "per 100,000", "short": "maternal_mortality"},
    "SP.DYN.TFRT.IN": {"name": "Fertility Rate, Total (births per woman)", "category": "Health", "unit": "births/woman", "short": "fertility_rate"},
    "SH.IMM.MEAS": {"name": "Immunization, Measles (% of children ages 12-23 months)", "category": "Health", "unit": "%", "short": "immunization_measles"},
    "SH.TBS.INCD": {"name": "Incidence of Tuberculosis (per 100,000 people)", "category": "Health", "unit": "per 100,000", "short": "tuberculosis_incidence"},
    "SH.STA.STNT.ZS": {"name": "Prevalence of Stunting, Children Under 5 (%)", "category": "Health", "unit": "%", "short": "child_stunting"},
    "SN.ITK.DEFC.ZS": {"name": "Prevalence of Undernourishment (% of population)", "category": "Health", "unit": "%", "short": "undernourishment"},

    # ── Education (15) ────────────────────────────────────────────
    "SE.ADT.LITR.ZS": {"name": "Literacy Rate (adult %)", "category": "Education", "unit": "%", "short": "literacy_rate"},
    "SE.PRM.ENRR": {"name": "School Enrollment, Primary (% gross)", "category": "Education", "unit": "%", "short": "primary_enrollment"},
    "SE.SEC.ENRR": {"name": "School Enrollment, Secondary (% gross)", "category": "Education", "unit": "%", "short": "secondary_enrollment"},
    "SE.XPD.TOTL.GD.ZS": {"name": "Government Expenditure on Education (% of GDP)", "category": "Education", "unit": "%", "short": "education_expenditure_gdp"},
    "SE.PRM.ENRL.TC.ZS": {"name": "Pupil-Teacher Ratio, Primary", "category": "Education", "unit": "ratio", "short": "pupil_teacher_ratio"},
    "SE.XPD.PRIM.PC.ZS": {"name": "Expenditure per Student, Primary (% of GDP per capita)", "category": "Education", "unit": "%", "short": "education_expenditure_per_student"},
    "SE.TER.ENRR": {"name": "School Enrollment, Tertiary (% gross)", "category": "Education", "unit": "%", "short": "tertiary_enrollment"},
    "SE.PRM.CMPT.ZS": {"name": "Primary Completion Rate (%)", "category": "Education", "unit": "%", "short": "primary_completion"},
    "SE.SEC.CMPT.LO.ZS": {"name": "Lower Secondary Completion Rate (%)", "category": "Education", "unit": "%", "short": "lower_secondary_completion"},
    "SE.ADT.1524.LT.ZS": {"name": "Youth Literacy Rate (% ages 15-24)", "category": "Education", "unit": "%", "short": "youth_literacy_rate"},
    "SE.PRM.NENR": {"name": "School Enrollment, Primary (% net)", "category": "Education", "unit": "%", "short": "primary_enrollment_net"},
    "SE.ENR.PRSC.FM.ZS": {"name": "Gender Parity Index, Primary and Secondary Enrollment", "category": "Education", "unit": "index", "short": "gender_parity_index"},
    "SE.PRE.ENRR": {"name": "School Enrollment, Pre-Primary (% gross)", "category": "Education", "unit": "%", "short": "preprimary_enrollment"},
    "SE.COM.DURS": {"name": "Compulsory Education, Duration (years)", "category": "Education", "unit": "years", "short": "compulsory_education_years"},
    "SE.SEC.PROG.ZS": {"name": "Progression to Secondary School (%)", "category": "Education", "unit": "%", "short": "secondary_progression"},

    # ── Infrastructure (15) ──────────────────────────────────────────
    "IT.NET.USER.ZS": {"name": "Internet Users (% of population)", "category": "Infrastructure", "unit": "%", "short": "internet_users"},
    "EG.ELC.ACCS.ZS": {"name": "Access to Electricity (%)", "category": "Infrastructure", "unit": "%", "short": "electricity_access"},
    "SH.H2O.BASW.ZS": {"name": "Basic Drinking Water Services (% of population)", "category": "Infrastructure", "unit": "%", "short": "basic_water_access"},
    "SH.STA.BASS.ZS": {"name": "Basic Sanitation Services (% of population)", "category": "Infrastructure", "unit": "%", "short": "basic_sanitation_access"},
    "IT.MLT.MAIN.P2": {"name": "Fixed Telephone Subscriptions (per 100 people)", "category": "Infrastructure", "unit": "per 100", "short": "fixed_telephone"},
    "IS.ROD.PAVE.ZS": {"name": "Paved Roads (% of total roads)", "category": "Infrastructure", "unit": "%", "short": "paved_roads"},
    "EG.USE.ELEC.KH.PC": {"name": "Electric Power Consumption (kWh per capita)", "category": "Infrastructure", "unit": "kWh", "short": "electricity_consumption"},
    "IT.CEL.SETS.P2": {"name": "Mobile Cellular Subscriptions (per 100 people)", "category": "Infrastructure", "unit": "per 100", "short": "mobile_subscriptions"},
    "IT.NET.BBND.P2": {"name": "Fixed Broadband Subscriptions (per 100 people)", "category": "Infrastructure", "unit": "per 100", "short": "broadband_subscriptions"},
    "EG.ELC.ACCS.RU.ZS": {"name": "Access to Electricity, Rural (%)", "category": "Infrastructure", "unit": "%", "short": "electricity_access_rural"},
    "EG.ELC.ACCS.UR.ZS": {"name": "Access to Electricity, Urban (%)", "category": "Infrastructure", "unit": "%", "short": "electricity_access_urban"},
    "EG.FEC.RNEW.ZS": {"name": "Renewable Energy Consumption (% of total final energy)", "category": "Infrastructure", "unit": "%", "short": "renewable_energy"},
    "IS.VEH.NVEH.P3": {"name": "Motor Vehicles (per 1,000 people)", "category": "Infrastructure", "unit": "per 1,000", "short": "motor_vehicles"},
    "IS.AIR.PSGR": {"name": "Air Transport, Passengers Carried", "category": "Infrastructure", "unit": "count", "short": "air_passengers"},
    "SH.H2O.SMDW.ZS": {"name": "Safely Managed Drinking Water Services (% of population)", "category": "Infrastructure", "unit": "%", "short": "safe_water_access"},
}

# Pole grouping — used to render pole-specific dashboard pages (economy.html, health.html, ...)
POLES = ["Economy", "Health", "Education", "Infrastructure"]

# Short code → indicator code mapping
SHORT_TO_CODE = {v["short"]: k for k, v in INDICATORS.items()}

# --- African Countries ---
# Sub-Saharan Africa (SSF) + North Africa
# We fetch by region SSF plus individual North African countries
NORTH_AFRICA_CODES = ["DZA", "EGY", "LBY", "MAR", "MRT", "TUN"]

# All 54 African countries (ISO3 codes)
AFRICAN_COUNTRIES = {
    "DZA": {"name": "Algeria", "region": "North Africa", "iso2": "DZ"},
    "AGO": {"name": "Angola", "region": "Central Africa", "iso2": "AO"},
    "BEN": {"name": "Benin", "region": "West Africa", "iso2": "BJ"},
    "BWA": {"name": "Botswana", "region": "Southern Africa", "iso2": "BW"},
    "BFA": {"name": "Burkina Faso", "region": "West Africa", "iso2": "BF"},
    "BDI": {"name": "Burundi", "region": "East Africa", "iso2": "BI"},
    "CPV": {"name": "Cabo Verde", "region": "West Africa", "iso2": "CV"},
    "CMR": {"name": "Cameroon", "region": "Central Africa", "iso2": "CM"},
    "CAF": {"name": "Central African Republic", "region": "Central Africa", "iso2": "CF"},
    "TCD": {"name": "Chad", "region": "Central Africa", "iso2": "TD"},
    "COM": {"name": "Comoros", "region": "East Africa", "iso2": "KM"},
    "COG": {"name": "Congo, Rep.", "region": "Central Africa", "iso2": "CG"},
    "COD": {"name": "Congo, Dem. Rep.", "region": "Central Africa", "iso2": "CD"},
    "CIV": {"name": "Côte d'Ivoire", "region": "West Africa", "iso2": "CI"},
    "DJI": {"name": "Djibouti", "region": "East Africa", "iso2": "DJ"},
    "EGY": {"name": "Egypt", "region": "North Africa", "iso2": "EG"},
    "GNQ": {"name": "Equatorial Guinea", "region": "Central Africa", "iso2": "GQ"},
    "ERI": {"name": "Eritrea", "region": "East Africa", "iso2": "ER"},
    "SWZ": {"name": "Eswatini", "region": "Southern Africa", "iso2": "SZ"},
    "ETH": {"name": "Ethiopia", "region": "East Africa", "iso2": "ET"},
    "GAB": {"name": "Gabon", "region": "Central Africa", "iso2": "GA"},
    "GMB": {"name": "Gambia", "region": "West Africa", "iso2": "GM"},
    "GHA": {"name": "Ghana", "region": "West Africa", "iso2": "GH"},
    "GIN": {"name": "Guinea", "region": "West Africa", "iso2": "GN"},
    "GNB": {"name": "Guinea-Bissau", "region": "West Africa", "iso2": "GW"},
    "KEN": {"name": "Kenya", "region": "East Africa", "iso2": "KE"},
    "LSO": {"name": "Lesotho", "region": "Southern Africa", "iso2": "LS"},
    "LBR": {"name": "Liberia", "region": "West Africa", "iso2": "LR"},
    "LBY": {"name": "Libya", "region": "North Africa", "iso2": "LY"},
    "MDG": {"name": "Madagascar", "region": "East Africa", "iso2": "MG"},
    "MWI": {"name": "Malawi", "region": "East Africa", "iso2": "MW"},
    "MLI": {"name": "Mali", "region": "West Africa", "iso2": "ML"},
    "MRT": {"name": "Mauritania", "region": "West Africa", "iso2": "MR"},
    "MUS": {"name": "Mauritius", "region": "East Africa", "iso2": "MU"},
    "MAR": {"name": "Morocco", "region": "North Africa", "iso2": "MA"},
    "MOZ": {"name": "Mozambique", "region": "East Africa", "iso2": "MZ"},
    "NAM": {"name": "Namibia", "region": "Southern Africa", "iso2": "NA"},
    "NER": {"name": "Niger", "region": "West Africa", "iso2": "NE"},
    "NGA": {"name": "Nigeria", "region": "West Africa", "iso2": "NG"},
    "RWA": {"name": "Rwanda", "region": "East Africa", "iso2": "RW"},
    "STP": {"name": "São Tomé and Príncipe", "region": "Central Africa", "iso2": "ST"},
    "SEN": {"name": "Senegal", "region": "West Africa", "iso2": "SN"},
    "SYC": {"name": "Seychelles", "region": "East Africa", "iso2": "SC"},
    "SLE": {"name": "Sierra Leone", "region": "West Africa", "iso2": "SL"},
    "SOM": {"name": "Somalia", "region": "East Africa", "iso2": "SO"},
    "ZAF": {"name": "South Africa", "region": "Southern Africa", "iso2": "ZA"},
    "SSD": {"name": "South Sudan", "region": "East Africa", "iso2": "SS"},
    "SDN": {"name": "Sudan", "region": "East Africa", "iso2": "SD"},
    "TZA": {"name": "Tanzania", "region": "East Africa", "iso2": "TZ"},
    "TGO": {"name": "Togo", "region": "West Africa", "iso2": "TG"},
    "TUN": {"name": "Tunisia", "region": "North Africa", "iso2": "TN"},
    "UGA": {"name": "Uganda", "region": "East Africa", "iso2": "UG"},
    "ZMB": {"name": "Zambia", "region": "East Africa", "iso2": "ZM"},
    "ZWE": {"name": "Zimbabwe", "region": "East Africa", "iso2": "ZW"},
}

# --- Data Quality Thresholds ---
DQ_THRESHOLDS = {
    # Economy
    "NY.GDP.MKTP.CD": {"min": 1e6, "max": 1e13},
    "NY.GDP.MKTP.KD.ZG": {"min": -50, "max": 100},
    "NY.GDP.PCAP.PP.CD": {"min": 200, "max": 200000},
    "SP.POP.TOTL": {"min": 10000, "max": 3e9},
    "FP.CPI.TOTL.ZG": {"min": -30, "max": 10000},
    "SL.UEM.TOTL.ZS": {"min": 0, "max": 80},
    "BX.KLT.DINV.WD.GD.ZS": {"min": -100, "max": 500},
    "SI.POV.GINI": {"min": 20, "max": 75},
    "NE.EXP.GNFS.ZS": {"min": 0, "max": 150},
    "NE.IMP.GNFS.ZS": {"min": 0, "max": 150},
    "DT.DOD.DECT.GN.ZS": {"min": 0, "max": 300},
    "NY.GNS.ICTR.ZS": {"min": -50, "max": 80},
    "NE.GDI.FTOT.ZS": {"min": 0, "max": 80},
    "PA.NUS.FCRF": {"min": 0, "max": 1e7},
    "GC.DOD.TOTL.GD.ZS": {"min": 0, "max": 300},

    # Health
    "SP.DYN.LE00.IN": {"min": 25, "max": 95},
    "SH.XPD.CHEX.GD.ZS": {"min": 0, "max": 30},
    "SH.MED.PHYS.ZS": {"min": 0, "max": 20},
    "SP.DYN.IMRT.IN": {"min": 0, "max": 200},
    "SH.DYN.AIDS.ZS": {"min": 0, "max": 40},
    "SH.IMM.IDPT": {"min": 0, "max": 100},
    "SH.MED.BEDS.ZS": {"min": 0, "max": 20},
    "SH.XPD.CHEX.PC.CD": {"min": 0, "max": 20000},
    "SH.DYN.MORT": {"min": 0, "max": 300},
    "SH.STA.MMRT": {"min": 0, "max": 3000},
    "SP.DYN.TFRT.IN": {"min": 0.5, "max": 10},
    "SH.IMM.MEAS": {"min": 0, "max": 100},
    "SH.TBS.INCD": {"min": 0, "max": 1500},
    "SH.STA.STNT.ZS": {"min": 0, "max": 80},
    "SN.ITK.DEFC.ZS": {"min": 0, "max": 80},

    # Education
    "SE.ADT.LITR.ZS": {"min": 0, "max": 100},
    "SE.PRM.ENRR": {"min": 0, "max": 200},
    "SE.SEC.ENRR": {"min": 0, "max": 200},
    "SE.XPD.TOTL.GD.ZS": {"min": 0, "max": 20},
    "SE.PRM.ENRL.TC.ZS": {"min": 5, "max": 150},
    "SE.XPD.PRIM.PC.ZS": {"min": 0, "max": 200},
    "SE.TER.ENRR": {"min": 0, "max": 150},
    "SE.PRM.CMPT.ZS": {"min": 0, "max": 150},
    "SE.SEC.CMPT.LO.ZS": {"min": 0, "max": 150},
    "SE.ADT.1524.LT.ZS": {"min": 0, "max": 100},
    "SE.PRM.NENR": {"min": 0, "max": 100},
    "SE.ENR.PRSC.FM.ZS": {"min": 0, "max": 2},
    "SE.PRE.ENRR": {"min": 0, "max": 150},
    "SE.COM.DURS": {"min": 0, "max": 15},
    "SE.SEC.PROG.ZS": {"min": 0, "max": 100},

    # Infrastructure
    "IT.NET.USER.ZS": {"min": 0, "max": 100},
    "EG.ELC.ACCS.ZS": {"min": 0, "max": 100},
    "SH.H2O.BASW.ZS": {"min": 0, "max": 100},
    "SH.STA.BASS.ZS": {"min": 0, "max": 100},
    "IT.MLT.MAIN.P2": {"min": 0, "max": 80},
    "IS.ROD.PAVE.ZS": {"min": 0, "max": 100},
    "EG.USE.ELEC.KH.PC": {"min": 0, "max": 20000},
    "IT.CEL.SETS.P2": {"min": 0, "max": 250},
    "IT.NET.BBND.P2": {"min": 0, "max": 60},
    "EG.ELC.ACCS.RU.ZS": {"min": 0, "max": 100},
    "EG.ELC.ACCS.UR.ZS": {"min": 0, "max": 100},
    "EG.FEC.RNEW.ZS": {"min": 0, "max": 100},
    "IS.VEH.NVEH.P3": {"min": 0, "max": 1000},
    "IS.AIR.PSGR": {"min": 0, "max": 1e9},
    "SH.H2O.SMDW.ZS": {"min": 0, "max": 100},
}
