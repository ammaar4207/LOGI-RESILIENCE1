"""Canonical maritime graph seed — 30 major global ports and 50 strategic shipping lanes.

Covers all major trade corridors:
  - Trans-Pacific (Asia → Americas)
  - Asia-Europe (via Suez Canal)
  - Intra-Asia
  - Transatlantic
  - Cape of Good Hope bypass
  - Mediterranean circuits
  - Gulf & Indian Ocean lanes
"""

PORTS = [
    # ─── East Asia ──────────────────────────────────────────────────────────────
    {"id": "SGSIN", "name": "Singapore",       "lat":  1.264,  "lon": 103.820, "capacity_teu": 37000000},
    {"id": "CNSHA", "name": "Shanghai",         "lat": 31.230,  "lon": 121.470, "capacity_teu": 47000000},
    {"id": "KRPUS", "name": "Busan",            "lat": 35.100,  "lon": 129.040, "capacity_teu": 22000000},
    {"id": "CNHKG", "name": "Hong Kong",        "lat": 22.310,  "lon": 114.170, "capacity_teu": 18000000},
    {"id": "CNNBO", "name": "Ningbo-Zhoushan",  "lat": 29.870,  "lon": 121.550, "capacity_teu": 33000000},
    {"id": "CNQIN", "name": "Qingdao",          "lat": 36.060,  "lon": 120.390, "capacity_teu": 22000000},
    {"id": "TWKHH", "name": "Kaohsiung",        "lat": 22.620,  "lon": 120.270, "capacity_teu": 10000000},
    {"id": "JPTYO", "name": "Tokyo (Yokohama)", "lat": 35.450,  "lon": 139.640, "capacity_teu":  4300000},

    # ─── Southeast Asia ─────────────────────────────────────────────────────────
    {"id": "MYPKG", "name": "Port Klang (KL)",  "lat":  3.000,  "lon": 101.400, "capacity_teu": 13000000},
    {"id": "PHMNI", "name": "Manila",           "lat": 14.590,  "lon": 120.980, "capacity_teu":  4900000},
    {"id": "LKCMB", "name": "Colombo",          "lat":  6.930,  "lon": 79.850,  "capacity_teu":  7200000},
    {"id": "VNCPH", "name": "Ho Chi Minh City", "lat": 10.800,  "lon": 106.710, "capacity_teu":  8000000},

    # ─── South Asia & Middle East ────────────────────────────────────────────────
    {"id": "INMUN", "name": "Mumbai (JNPT)",    "lat": 18.950,  "lon": 72.950,  "capacity_teu":  6000000},
    {"id": "AEJEA", "name": "Jebel Ali (Dubai)","lat": 25.000,  "lon": 55.060,  "capacity_teu": 14000000},
    {"id": "OMSLL", "name": "Salalah (Oman)",   "lat": 17.010,  "lon": 54.090,  "capacity_teu":  4600000},
    {"id": "SADMM", "name": "Dammam (Saudi)",   "lat": 26.430,  "lon": 50.100,  "capacity_teu":  2300000},

    # ─── Choke Points ────────────────────────────────────────────────────────────
    {"id": "EGSUZ", "name": "Suez Canal Zone",  "lat": 30.460,  "lon": 32.350,  "capacity_teu":       0},
    {"id": "SGSTR", "name": "Strait of Malacca","lat":  2.500,  "lon": 101.000, "capacity_teu":       0},

    # ─── Europe ─────────────────────────────────────────────────────────────────
    {"id": "NLRTM", "name": "Rotterdam",        "lat": 51.950,  "lon":   4.140, "capacity_teu": 14500000},
    {"id": "DEHAM", "name": "Hamburg",          "lat": 53.550,  "lon":   9.990, "capacity_teu":  8700000},
    {"id": "BEANT", "name": "Antwerp",          "lat": 51.230,  "lon":   4.410, "capacity_teu": 11500000},
    {"id": "ESVLC", "name": "Valencia",         "lat": 39.470,  "lon":  -0.330, "capacity_teu":  5400000},
    {"id": "GRPIR", "name": "Piraeus (Athens)", "lat": 37.940,  "lon":  23.640, "capacity_teu":  5700000},
    {"id": "ITGOA", "name": "Genoa",            "lat": 44.410,  "lon":   8.930, "capacity_teu":  2400000},

    # ─── Americas ────────────────────────────────────────────────────────────────
    {"id": "USLAX", "name": "Los Angeles",      "lat": 33.740,  "lon":-118.270, "capacity_teu": 10000000},
    {"id": "USNYC", "name": "New York (Newark)","lat": 40.690,  "lon": -74.150, "capacity_teu":  7400000},
    {"id": "USHOH", "name": "Houston",          "lat": 29.760,  "lon": -95.370, "capacity_teu":  2800000},
    {"id": "BRSSZ", "name": "Santos (Brazil)",  "lat":-23.930,  "lon": -46.320, "capacity_teu":  4900000},

    # ─── Africa ──────────────────────────────────────────────────────────────────
    {"id": "ZADUR", "name": "Durban",           "lat":-29.870,  "lon":  31.030, "capacity_teu":  2900000},
    {"id": "NGLOS", "name": "Lagos (Apapa)",    "lat":  6.450,  "lon":   3.380, "capacity_teu":  1500000},
]

# (source, target, distance_km, co2_per_teu, base_risk, essential_priority 0–1)
LANES = [
    # ─── Trans-Pacific ───────────────────────────────────────────────────────────
    ("CNSHA", "USLAX",  10200, 215, 0.36, 0.70),
    ("KRPUS", "USLAX",   9800, 210, 0.35, 0.70),
    ("JPTYO", "USLAX",   8800, 205, 0.32, 0.65),
    ("TWKHH", "USLAX",   9600, 212, 0.34, 0.68),
    ("CNHKG", "USLAX",  10400, 218, 0.37, 0.68),

    # ─── Intra-Asia ──────────────────────────────────────────────────────────────
    ("SGSIN", "CNSHA",   3800, 120, 0.25, 0.90),
    ("CNSHA", "KRPUS",    850,  95, 0.30, 0.85),
    ("KRPUS", "SGSIN",   4700, 140, 0.28, 0.80),
    ("SGSIN", "MYPKG",    320,  35, 0.15, 0.92),
    ("MYPKG", "SGSTR",    120,  20, 0.18, 0.95),
    ("SGSTR", "SGSIN",    100,  18, 0.20, 0.95),
    ("CNSHA", "CNNBO",    200,  30, 0.12, 0.88),
    ("CNSHA", "CNQIN",    600,  55, 0.18, 0.85),
    ("CNHKG", "CNSHA",    600,  55, 0.20, 0.82),
    ("TWKHH", "CNHKG",    800,  75, 0.22, 0.80),
    ("SGSIN", "VNCPH",   1100,  80, 0.24, 0.78),
    ("SGSIN", "PHMNI",   2200, 100, 0.28, 0.75),
    ("JPTYO", "KRPUS",    700,  75, 0.22, 0.80),

    # ─── Asia-Indian Ocean ──────────────────────────────────────────────────────
    ("SGSIN", "LKCMB",   2100, 115, 0.30, 0.85),
    ("SGSIN", "INMUN",   4200, 160, 0.32, 0.88),
    ("LKCMB", "INMUN",   1000,  80, 0.28, 0.87),
    ("INMUN", "AEJEA",   1900, 110, 0.35, 0.90),
    ("LKCMB", "OMSLL",   1800, 105, 0.32, 0.85),

    # ─── Gulf & Red Sea ─────────────────────────────────────────────────────────
    ("AEJEA", "OMSLL",    900,  70, 0.30, 0.88),
    ("AEJEA", "SADMM",    450,  50, 0.22, 0.85),
    ("AEJEA", "EGSUZ",   2200, 130, 0.45, 0.95),
    ("OMSLL", "EGSUZ",   2400, 135, 0.42, 0.92),

    # ─── Suez → Europe ──────────────────────────────────────────────────────────
    ("EGSUZ", "GRPIR",   1600,  90, 0.40, 0.92),
    ("EGSUZ", "ESVLC",   3000, 140, 0.45, 0.90),
    ("EGSUZ", "NLRTM",   3200, 150, 0.50, 0.95),
    ("EGSUZ", "BEANT",   3100, 145, 0.48, 0.93),

    # ─── Intra-Europe ───────────────────────────────────────────────────────────
    ("NLRTM", "DEHAM",    450,  45, 0.20, 0.80),
    ("NLRTM", "BEANT",    100,  20, 0.12, 0.85),
    ("BEANT", "DEHAM",    550,  50, 0.18, 0.82),
    ("ESVLC", "GRPIR",   2200, 110, 0.30, 0.75),
    ("GRPIR", "ITGOA",   1300,  75, 0.28, 0.72),
    ("ITGOA", "ESVLC",   1400,  80, 0.25, 0.70),

    # ─── Europe → Americas ──────────────────────────────────────────────────────
    ("NLRTM", "USNYC",   5800, 165, 0.32, 0.72),
    ("DEHAM", "USNYC",   5900, 168, 0.33, 0.70),
    ("DEHAM", "USLAX",   9200, 200, 0.38, 0.65),

    # ─── Trans-Atlantic ─────────────────────────────────────────────────────────
    ("USNYC", "BRSSZ",   7800, 185, 0.36, 0.68),
    ("USHOH", "BRSSZ",   7200, 178, 0.34, 0.65),

    # ─── Cape of Good Hope bypass (alternative to Suez) ─────────────────────────
    ("SGSIN", "ZADUR",   9400, 210, 0.42, 0.60),
    ("ZADUR", "NLRTM",   9800, 220, 0.42, 0.60),
    ("ZADUR", "NGLOS",   3200, 130, 0.45, 0.55),
    ("USLAX", "ZADUR",  16800, 280, 0.48, 0.55),
    ("BRSSZ", "ZADUR",   6200, 155, 0.40, 0.58),

    # ─── West Africa ─────────────────────────────────────────────────────────────
    ("NGLOS", "NLRTM",  10500, 230, 0.50, 0.58),
    ("NGLOS", "BEANT",  10200, 225, 0.48, 0.56),

    # ─── Americas Coastal ───────────────────────────────────────────────────────
    ("USLAX", "USHOH",   3200, 115, 0.28, 0.72),
    ("USNYC", "USHOH",   2800, 105, 0.26, 0.70),
]
