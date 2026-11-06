#!/usr/bin/env python3
"""
Synthetic retail dataset generator
==================================

Builds a reproducible, multi-store retail dataset (Kenyan supermarket chain,
1 Oct 2024 - 30 Sep 2026) as six CSV tables:

    branches.csv       10 stores
    customers.csv      loyalty-card customers
    products.csv       product catalogue (tiers, list prices, unit costs)
    promotions.csv     promotion calendar
    transactions.csv   receipts (sales and returns)
    receipt_lines.csv  receipt line items

Usage
-----
    python generate_data.py --seed 42 --out data/

Requirements: Python 3.9+, numpy, pandas.  The same seed always produces the
same files.  All behaviour is controlled by the CONFIG section below.

Design overview
---------------
1.  Calendar     : daily demand multipliers (month, weekday, month-end payday
                   ramp, start-of-month bump, Christmas/New Year/Easter).
2.  Promotions   : weekly SKU offers + seasonal category campaigns.
3.  Customers    : registration, demographics, behaviour segment
                   (one-time / lapsed / active), visit rate, spend level.
4.  Visits       : each customer's visit dates and stores are simulated first;
                   anonymous walk-in receipts then fill each store-day up to
                   its simulated traffic.
5.  Baskets      : products drawn by store/tier/category preferences, customer
                   affluence, promo uplift and seasonal surges; quantities,
                   prices (weekly price paths) and promo discounts follow.
6.  Returns      : a small share of sales are partly or fully returned.
7.  Payments     : method mix by store; M-Pesa receipts carry a unique reference.
8.  Messiness    : a few realistic data-quality problems are injected on
                   purpose (text-formatted prices, placeholder values) so the
                   dataset can be used to practise cleaning.
"""
import argparse
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

# =====================================================================
# CONFIG
# =====================================================================
SEED = 42
START, END = date(2024, 10, 1), date(2026, 9, 30)          # transaction window
REG_START, REG_END = date(2021, 10, 1), date(2026, 8, 31)  # customer registration window

# ---- stores ---------------------------------------------------------
# id, name, county, town, format, positioning, opening date, floor area (sqm)
BRANCHES = [
    ("S01", "Kilimani Supermarket",      "Nairobi",  "Kilimani",      "Supermarket", "Upmarket",   date(2017, 6, 1),   2300),
    ("S02", "Eastleigh Supermarket",     "Nairobi",  "Eastleigh",     "Supermarket", "Value",      date(2018, 10, 10), 2200),
    ("S03", "Embakasi Hypermarket",      "Nairobi",  "Embakasi",      "Hypermarket", "Value",      date(2019, 3, 15),  3900),
    ("S04", "Karen Express",             "Nairobi",  "Karen",         "Express",     "Upmarket",   date(2021, 5, 20),  700),
    ("S05", "Ruiru Supermarket",         "Kiambu",   "Ruiru",         "Supermarket", "Mid-market", date(2020, 2, 1),   2000),
    ("S06", "Kikuyu Express",            "Kiambu",   "Kikuyu",        "Express",     "Mid-market", date(2022, 9, 12),  650),
    ("S07", "Thika Supermarket",         "Kiambu",   "Thika",         "Supermarket", "Value",      date(2019, 7, 1),   2000),
    ("S08", "Athi River Supermarket",    "Machakos", "Athi River",    "Supermarket", "Value",      date(2021, 11, 5),  2000),
    ("S09", "Ongata Rongai Supermarket", "Kajiado",  "Ongata Rongai", "Supermarket", "Mid-market", date(2023, 3, 18),  1900),
    ("S10", "Naivasha Express",          "Nakuru",   "Naivasha",      "Express",     "Mid-market", date(2025, 3, 3),   650),
]
STORES = [b[0] for b in BRANCHES]
STORE_FORMAT = {b[0]: b[4] for b in BRANCHES}
STORE_CLASS = {b[0]: b[5] for b in BRANCHES}
STORE_OPEN = {b[0]: b[6] for b in BRANCHES}

# average receipts per open day (sales only)
STORE_DAILY_TXNS = {"S01": 76.2, "S02": 86.7, "S03": 149.5, "S04": 29.0, "S05": 58.0,
                    "S06": 20.3, "S07": 56.6, "S08": 55.1, "S09": 49.6, "S10": 15.8}

# ---- calendar effects (multipliers on daily traffic) -----------------
ANNUAL_GROWTH = 0.20                                   # log-growth per year
MONTH_EFFECT = {1: 1.020, 2: 0.990, 3: 1.019, 4: 1.028, 5: 1.023, 6: 1.046,
                7: 1.028, 8: 1.074, 9: 1.005, 10: 1.064, 11: 1.099, 12: 1.208}
DOW_EFFECT = {0: 1.000, 1: 1.042, 2: 1.029, 3: 1.109, 4: 1.306, 5: 1.472, 6: 1.280}  # Mon=0
# month-end payday ramp, keyed by days left in the month (0 = last day)
PAYDAY_TRAFFIC = {5: 1.09, 4: 1.38, 3: 1.475, 2: 1.70, 1: 1.667, 0: 1.78}
START_OF_MONTH_TRAFFIC = {1: 1.48, 2: 1.46, 3: 1.10}   # day-of-month -> multiplier
PAYDAY_BASKET = {5: 1.11, 4: 1.13, 3: 1.17, 2: 1.19, 1: 1.205, 0: 1.21}   # basket-size multiplier
START_OF_MONTH_BASKET = {1: 1.16, 2: 1.12, 3: 1.05}
FIXED_DAY_EFFECT = {(12, 24): 1.33, (12, 25): 0.40, (12, 26): 0.83, (1, 1): 0.58}
EASTER_EFFECT = {-3: 1.50, -2: 1.00, -1: 1.63, 0: 0.85, 1: 0.90}   # offsets from Easter Sunday
BLACK_FRIDAY_TRAFFIC = 1.09
COMMON_DAY_SHOCK_SD = 0.10          # city-wide day-to-day noise
STORE_DAY_NOISE_SD = 0.10           # extra store-level noise on top of Poisson
NEW_STORE_RAMP = {"S10": (0.35, 1.30, 150.0)}   # start level, mature level, ramp days
# full-day closures (store, first day, last day); part of the closed store's traffic
# is picked up by other stores in the same county
STORE_CLOSURES = [("S07", date(2024, 12, 17), date(2024, 12, 17)),
                  ("S02", date(2025, 1, 28), date(2025, 1, 29)),
                  ("S03", date(2025, 6, 2), date(2025, 6, 15)),
                  ("S05", date(2026, 5, 14), date(2026, 5, 15))]
CLOSURE_DISPLACED_SHARE = 0.50

OPENING_HOURS = list(range(7, 21))                  # 07:00 - 20:59
HOUR_WEIGHTS = np.array([0.020, 0.030, 0.049, 0.061, 0.070, 0.080, 0.080,
                         0.060, 0.050, 0.060, 0.111, 0.139, 0.120, 0.070])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

# ---- customers ------------------------------------------------------
CUSTOMERS_PER_STORE = {"S01": 1044, "S02": 1131, "S03": 2030, "S04": 377, "S05": 812,
                       "S06": 290, "S07": 783, "S08": 754, "S09": 725, "S10": 276}
NEW_STORE_REG_BURST = (1.2, 200.0)       # extra registrations after opening: size, decay (days)
AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55+"]
AGE_PROBS = [0.120, 0.306, 0.248, 0.185, 0.141]
GENDER_PROBS = {"Female": 0.583, "Male": 0.417}
AGE_VISIT_RATE = {"18-24": 0.80, "25-34": 0.97, "35-44": 1.07, "45-54": 1.00, "55+": 0.92}   # relative visit frequency
AGE_SPEND = {"18-24": 0.94, "25-34": 1.00, "35-44": 1.08, "45-54": 1.04, "55+": 0.98}
GENDER_SPEND = {"Male": 1.04, "Female": 1.00}
FEMALE_45_54_SPEND = 1.12                # small interaction effect
CATCHMENT = {   # county mix of customers by registration store
    "S01": {"Nairobi": .865, "Kiambu": .045, "Machakos": .045, "Kajiado": .045},
    "S02": {"Nairobi": .865, "Kiambu": .045, "Machakos": .045, "Kajiado": .045},
    "S03": {"Nairobi": .865, "Kiambu": .036, "Machakos": .050, "Kajiado": .049},
    "S04": {"Nairobi": .865, "Kiambu": .045, "Machakos": .045, "Kajiado": .045},
    "S05": {"Kiambu": .866, "Nairobi": .134},
    "S06": {"Kiambu": .900, "Nairobi": .100},
    "S07": {"Kiambu": .897, "Nairobi": .103},
    "S08": {"Machakos": .886, "Nairobi": .067, "Kajiado": .047},
    "S09": {"Kajiado": .860, "Nairobi": .064, "Machakos": .076},
    "S10": {"Nakuru": .862, "Baringo": .090, "Nyandarua": .048},
}
# share of values replaced by a placeholder token, and the token mix
PLACEHOLDER_RATE = {"county": 0.0287, "age_band": 0.1073, "gender": 0.0748}
PLACEHOLDER_TOKENS = ["", "unknown", "N/A", "-"]
PLACEHOLDER_MIX = {"county": [69, 68, 50, 49], "age_band": [258, 278, 168, 178], "gender": [193, 186, 106, 130]}

# behaviour segments
P_ONE_TIME_NEW = 0.32        # registered inside the window: buys once, then never again
P_ONE_TIME_EXISTING = 0.26   # registered before the window
NEVER_PURCHASED_SHARE = 0.0020   # registered but never bought
P_LAPSED = 0.27              # stops buying part-way through the window
LAPSE_SHAPE = (2.5, 1.5)     # Beta shape of how far through their window a lapsed customer gets
VISIT_RATE_MEDIAN = 2.0      # visits per month while active
VISIT_RATE_SIGMA = 0.65
FIRST_VISIT_LAG_NEW = 9.0    # mean days from registration to first purchase
FIRST_VISIT_LAG_EXISTING = 13.0
HOME_STORE_SHARE = 0.876
TARGET_MEMBER_SHARE = 0.505  # share of receipts carrying a customer id
BASKET_SIZE_SD = 0.18        # persistent customer-level basket-size spread
AFFLUENCE_TIER_TILT = {"E": -0.5, "S": 0.0, "P": 0.8}

# ---- baskets ---------------------------------------------------------
LINES_BASE = {"Supermarket": 4.51, "Hypermarket": 5.29, "Express": 3.23}   # mean lines, mid-month
LINES_DISPERSION = 1.45             # negative-binomial shape for extra lines
BASE_CATEGORY_SHARE = {"Baby Care": .018, "Beverages": .125, "Dairy": .123, "Farm Produce": .124,
                       "Food Staples": .325, "Household & Cleaning": .090, "Personal Care": .085,
                       "School & Stationery": .0175, "Snacks & Confectionery": .088}
EXPRESS_CATEGORY_ADJ = {"Baby Care": 0.2}
TIER_SHARE = {  # share of lines by tier (Economy, Standard, Premium) at each store
    "S01": (.036, .678, .286), "S02": (.351, .631, .018), "S03": (.340, .638, .022),
    "S04": (.029, .702, .269), "S05": (.202, .704, .094), "S06": (.226, .714, .060),
    "S07": (.344, .645, .011), "S08": (.341, .644, .014), "S09": (.213, .679, .108),
    "S10": (.212, .736, .052),
}
POPULARITY_SIGMA = 0.55             # product popularity spread (log-normal)
POPULARITY_PRICE_ELASTICITY = -0.50
EXPRESS_PRICE_ELASTICITY = -0.18     # express stores skew further towards cheaper items  # cheaper products sell more often
QTY_CATEGORY_MEAN = {"Baby Care": 1.25, "Beverages": 2.05, "Dairy": 1.64, "Farm Produce": 1.92,
                     "Food Staples": 1.99, "Household & Cleaning": 1.62, "Personal Care": 1.42,
                     "School & Stationery": 3.15, "Snacks & Confectionery": 1.75}
# quantity multipliers by store class and price band (value stores buy cheap items in bulk)
QTY_STORE_PRICE = {
    "value":      {"cheap": 1.28, "mid": 1.05, "dear": 1.00},
    "hyper":      {"cheap": 1.42, "mid": 1.05, "dear": 1.00},
    "upmarket":   {"cheap": 0.80, "mid": 1.00, "dear": 1.12},
    "mid-market": {"cheap": 0.93, "mid": 0.95, "dear": 0.95},
}
QTY_BASE_SCALE = 0.72                # shrinks the category extra-units figure above
BULK_PROB = 0.0030                  # share of lines that are case/carton purchases
BULK_PACKS, BULK_PACK_P = [6, 12, 24], [0.30, 0.45, 0.25]
BULK_MULT, BULK_MULT_P = [1, 2, 3, 4, 5, 8], [0.45, 0.25, 0.12, 0.08, 0.05, 0.05]
QTY_FORMAT_FACTOR = {"Express": 0.85}   # small-basket formats buy fewer units per line
PROMO_QTY_BUMP = 0.55               # extra units (Poisson mean) on discounted lines

# ---- promotions ------------------------------------------------------
SKU_OFFERS_PER_MONTH, SKU_OFFERS_TOTAL = (8, 12), 240
SKU_OFFER_DURATIONS, SKU_OFFER_DUR_P = [7, 14], [0.52, 0.48]
SKU_OFFER_DISCOUNTS, SKU_OFFER_DISC_P = [5, 10, 20, 30, 40], [39, 54, 76, 40, 31]
SKU_OFFER_ALL_STORES_P = 0.567
SKU_OFFER_SUBSET_SIZES, SKU_OFFER_SUBSET_P = [3, 4, 5, 6], [24, 21, 30, 29]
SKU_OFFER_CATEGORY_FACTOR = {"Baby Care": .16, "Beverages": 1.15, "Dairy": 1.58, "Farm Produce": 2.02,
                             "Food Staples": 1.05, "Household & Cleaning": .71, "Personal Care": .75,
                             "School & Stationery": .65, "Snacks & Confectionery": .67}
SKU_OFFER_TIER_FACTOR = {"E": 0.80, "S": 1.00, "P": 0.60}
PAYDAY_CATEGORIES = ["Beverages", "Household & Cleaning", "Personal Care", "Snacks & Confectionery", "Food Staples"]
PAYDAY_DISCOUNTS = [5, 10, 15]
PROMO_FIRST_START = date(2024, 10, 4)
# demand response
SKU_PROMO_UPLIFT = (1.5, 0.017)      # uplift = a + b * discount_pct on the promoted product
POST_PROMO_DIP, POST_PROMO_DAYS = 0.92, 14
CATEGORY_PROMO_UPLIFT = {"Payday Deals": 1.43, "Festive Season": 1.60, "Easter Offers": 1.55, "Black Friday": 1.00}
BACK_TO_SCHOOL_SURGE = {"jan": (15.5, 0, 1.0), "other": (9.0, 10, 3.0)}   # in-window mult, tail days, tail mult

# ---- returns ---------------------------------------------------------
RETURN_RATE = 0.0123
RETURN_LAG_P = 0.26                 # geometric lag in days (max 21)
RETURN_FULL_QTY_P = 0.937
RETURN_PARTIAL_FRACTIONS, RETURN_PARTIAL_P = [0.5, 1 / 3, 2 / 3, 0.25], [204, 40, 34, 14]
RETURN_OTHER_METHOD_P = 0.0023

# ---- payments --------------------------------------------------------
PAYMENT_MIX = {  # M-Pesa, Cash, Card
    "S01": (.468, .268, .264), "S02": (.548, .312, .140), "S03": (.532, .300, .169),
    "S04": (.450, .273, .277), "S05": (.531, .269, .200), "S06": (.502, .315, .184),
    "S07": (.543, .302, .154), "S08": (.537, .293, .170), "S09": (.522, .282, .196),
    "S10": (.486, .329, .185),
}
PAYMENT_PLACEHOLDER_RATE = {s: 0.00078 for s in STORES}
PAYMENT_PLACEHOLDER_RATE["S05"] = 0.0100
PAYMENT_PLACEHOLDER_TOKENS, PAYMENT_PLACEHOLDER_P = ["", "N/A", "-", "unknown"], [344, 140, 130, 120]

# ---- prices ----------------------------------------------------------
PRICE_WEEKS = 106
# category: (mean weeks between repricing, annual drift, step sd)
PRICE_BEHAVIOUR = {
    "Food Staples": (8, 0.07, 0.050), "Dairy": (10, 0.05, 0.045), "Beverages": (12, 0.04, 0.045),
    "Household & Cleaning": (13, 0.04, 0.045), "Personal Care": (14, 0.03, 0.040),
    "Snacks & Confectionery": (12, 0.04, 0.045), "Baby Care": (14, 0.04, 0.035),
    "School & Stationery": (16, 0.03, 0.035), "Farm Produce": (3, 0.00, 0.000),
}
PRICE_BIG_MOVE_P, PRICE_BIG_MOVE_RANGE = 0.06, (0.06, 0.14)
PRICE_DRIFT_SCALE = 0.45
PRICE_CATEGORY_SHOCK_SD = 0.004
STORE_PRICE_INDEX = {"S01": 1.03, "S02": 0.98, "S03": 0.97, "S04": 1.05, "S05": 1.00,
                     "S06": 1.02, "S07": 0.98, "S08": 0.98, "S09": 1.00, "S10": 1.02}
STORE_PRODUCT_PRICE_NOISE = 0.015
PRICE_STYLE_P = {"charm9": 0.50, "round5": 0.30, "round10": 0.20}
MIN_MARGIN_OVER_COST = 1.03
TEXT_PRICE_SHARE = 0.0537            # share of lines whose price is stored as text, e.g. "KES 1,089"

# ---- product catalogue -----------------------------------------------
# (category, name, tier code E/S/P, list price in KES), in product-id order
CATALOGUE = [
    ("Food Staples", "Maize Flour 2kg", "E", 129),
    ("Food Staples", "Maize Flour 2kg", "S", 149),
    ("Food Staples", "Maize Flour 2kg", "P", 189),
    ("Food Staples", "Pishori Rice 2kg", "E", 309),
    ("Food Staples", "Pishori Rice 2kg", "S", 359),
    ("Food Staples", "Pishori Rice 2kg", "P", 469),
    ("Food Staples", "Wheat Flour 2kg", "E", 169),
    ("Food Staples", "Wheat Flour 2kg", "S", 199),
    ("Food Staples", "Wheat Flour 2kg", "P", 259),
    ("Food Staples", "Sugar 1kg", "S", 199),
    ("Food Staples", "Cooking Oil 1L", "E", 269),
    ("Food Staples", "Cooking Oil 1L", "S", 309),
    ("Food Staples", "Cooking Oil 1L", "P", 399),
    ("Food Staples", "Salt 500g", "S", 39),
    ("Food Staples", "Salt 500g", "P", 49),
    ("Food Staples", "Loose Tea Leaves 250g", "E", 109),
    ("Food Staples", "Loose Tea Leaves 250g", "S", 129),
    ("Food Staples", "Loose Tea Leaves 250g", "P", 169),
    ("Food Staples", "Sliced White Bread 400g", "S", 69),
    ("Food Staples", "Sliced White Bread 400g", "P", 89),
    ("Food Staples", "Maize Flour 1kg", "S", 79),
    ("Food Staples", "Cooking Oil 3L", "E", 749),
    ("Food Staples", "Cooking Oil 3L", "S", 879),
    ("Food Staples", "Cooking Oil 3L", "P", 1149),
    ("Food Staples", "Spaghetti 500g", "E", 109),
    ("Food Staples", "Spaghetti 500g", "S", 129),
    ("Food Staples", "Dry Beans 1kg", "S", 189),
    ("Food Staples", "Green Grams 1kg", "S", 219),
    ("Food Staples", "Brown Bread 400g", "S", 69),
    ("Food Staples", "Macaroni 500g", "E", 99),
    ("Food Staples", "Macaroni 500g", "S", 119),
    ("Food Staples", "Tomato Paste 200g", "E", 79),
    ("Food Staples", "Tomato Paste 200g", "S", 89),
    ("Food Staples", "Baking Flour 2kg", "E", 169),
    ("Food Staples", "Baking Flour 2kg", "S", 199),
    ("Food Staples", "Oats 500g", "E", 149),
    ("Food Staples", "Oats 500g", "S", 179),
    ("Food Staples", "Oats 500g", "P", 229),
    ("Food Staples", "Olive Oil 500ml", "E", 919),
    ("Food Staples", "Olive Oil 500ml", "S", 1089),
    ("Food Staples", "Olive Oil 500ml", "P", 1409),
    ("Food Staples", "Pasta Sauce 400g", "S", 279),
    ("Food Staples", "Pasta Sauce 400g", "P", 369),
    ("Food Staples", "Quinoa 500g", "S", 569),
    ("Food Staples", "Muesli 500g", "E", 409),
    ("Food Staples", "Muesli 500g", "S", 479),
    ("Food Staples", "Muesli 500g", "P", 619),
    ("Dairy", "Fresh Milk 500ml", "E", 49),
    ("Dairy", "Fresh Milk 500ml", "S", 69),
    ("Dairy", "Fresh Milk 1L", "S", 119),
    ("Dairy", "Fresh Milk 1L", "P", 159),
    ("Dairy", "Eggs Tray of 30", "E", 409),
    ("Dairy", "Eggs Tray of 30", "S", 479),
    ("Dairy", "Yoghurt 500ml", "E", 89),
    ("Dairy", "Yoghurt 500ml", "S", 109),
    ("Dairy", "Margarine 500g", "S", 249),
    ("Dairy", "Margarine 500g", "P", 319),
    ("Dairy", "Long Life Milk 1L", "S", 129),
    ("Dairy", "Long Life Milk 1L", "P", 169),
    ("Dairy", "Butter 250g", "E", 259),
    ("Dairy", "Butter 250g", "S", 309),
    ("Dairy", "Cheddar Cheese 250g", "S", 429),
    ("Dairy", "Eggs Tray of 12", "S", 189),
    ("Dairy", "Greek Yoghurt 500g", "S", 249),
    ("Dairy", "Mozzarella 200g", "S", 379),
    ("Farm Produce", "Tomatoes 1kg", "S", 109),
    ("Farm Produce", "Onions 1kg", "S", 109),
    ("Farm Produce", "Potatoes 2kg", "S", 149),
    ("Farm Produce", "Kale Bunch", "S", 29),
    ("Farm Produce", "Bananas 1kg", "S", 99),
    ("Farm Produce", "Carrots 1kg", "S", 89),
    ("Farm Produce", "Avocados 4 Pack", "S", 129),
    ("Farm Produce", "Mangoes 1kg", "S", 139),
    ("Farm Produce", "Spinach Bunch", "S", 29),
    ("Farm Produce", "Cooking Bananas 1kg", "S", 79),
    ("Farm Produce", "Oranges 1kg", "S", 119),
    ("Farm Produce", "Garlic 250g", "S", 99),
    ("Beverages", "Soda 500ml", "E", 59),
    ("Beverages", "Soda 500ml", "S", 69),
    ("Beverages", "Soda 500ml", "P", 89),
    ("Beverages", "Bottled Water 1.5L", "S", 89),
    ("Beverages", "Fruit Juice 1L", "E", 189),
    ("Beverages", "Fruit Juice 1L", "S", 229),
    ("Beverages", "Fruit Juice 1L", "P", 289),
    ("Beverages", "Tea Bags 100s", "S", 269),
    ("Beverages", "Tea Bags 100s", "P", 349),
    ("Beverages", "Soda 2L", "S", 189),
    ("Beverages", "Instant Coffee 100g", "S", 339),
    ("Beverages", "Energy Drink 500ml", "E", 129),
    ("Beverages", "Energy Drink 500ml", "S", 149),
    ("Beverages", "Bottled Water 500ml", "S", 49),
    ("Beverages", "Bottled Water 500ml", "P", 69),
    ("Beverages", "Drinking Chocolate 400g", "S", 379),
    ("Beverages", "Sparkling Water 500ml", "S", 109),
    ("Beverages", "Iced Tea 500ml", "S", 119),
    ("Snacks & Confectionery", "Biscuits Pack", "E", 89),
    ("Snacks & Confectionery", "Biscuits Pack", "S", 109),
    ("Snacks & Confectionery", "Biscuits Pack", "P", 139),
    ("Snacks & Confectionery", "Potato Crisps", "E", 49),
    ("Snacks & Confectionery", "Potato Crisps", "S", 59),
    ("Snacks & Confectionery", "Potato Crisps", "P", 79),
    ("Snacks & Confectionery", "Chocolate Bar", "E", 69),
    ("Snacks & Confectionery", "Chocolate Bar", "S", 89),
    ("Snacks & Confectionery", "Chocolate Bar", "P", 119),
    ("Snacks & Confectionery", "Sweets Pack", "S", 49),
    ("Snacks & Confectionery", "Breakfast Cereal 500g", "S", 409),
    ("Snacks & Confectionery", "Breakfast Cereal 500g", "P", 529),
    ("Snacks & Confectionery", "Peanut Butter 400g", "S", 359),
    ("Snacks & Confectionery", "Peanut Butter 400g", "P", 469),
    ("Snacks & Confectionery", "Jam 400g", "E", 179),
    ("Snacks & Confectionery", "Jam 400g", "S", 209),
    ("Snacks & Confectionery", "Jam 400g", "P", 279),
    ("Snacks & Confectionery", "Cereal Bars 6 Pack", "S", 239),
    ("Household & Cleaning", "Laundry Detergent 1kg", "E", 289),
    ("Household & Cleaning", "Laundry Detergent 1kg", "S", 349),
    ("Household & Cleaning", "Laundry Detergent 1kg", "P", 449),
    ("Household & Cleaning", "Toilet Paper 10 Pack", "E", 399),
    ("Household & Cleaning", "Toilet Paper 10 Pack", "S", 469),
    ("Household & Cleaning", "Dishwashing Liquid 750ml", "E", 159),
    ("Household & Cleaning", "Dishwashing Liquid 750ml", "S", 189),
    ("Household & Cleaning", "Matchbox", "S", 16),
    ("Household & Cleaning", "Bleach 750ml", "S", 149),
    ("Household & Cleaning", "Bleach 750ml", "P", 199),
    ("Household & Cleaning", "Floor Cleaner 1L", "S", 269),
    ("Household & Cleaning", "Floor Cleaner 1L", "P", 349),
    ("Household & Cleaning", "Garbage Bags 20s", "S", 189),
    ("Household & Cleaning", "Air Freshener", "E", 189),
    ("Household & Cleaning", "Air Freshener", "S", 219),
    ("Household & Cleaning", "Insecticide Spray", "E", 329),
    ("Household & Cleaning", "Insecticide Spray", "S", 379),
    ("Personal Care", "Toothpaste 100ml", "E", 159),
    ("Personal Care", "Toothpaste 100ml", "S", 189),
    ("Personal Care", "Toothpaste 100ml", "P", 249),
    ("Personal Care", "Bathing Soap Bar", "E", 69),
    ("Personal Care", "Bathing Soap Bar", "S", 79),
    ("Personal Care", "Bathing Soap Bar", "P", 109),
    ("Personal Care", "Sanitary Pads 10s", "E", 119),
    ("Personal Care", "Sanitary Pads 10s", "S", 139),
    ("Personal Care", "Sanitary Pads 10s", "P", 179),
    ("Personal Care", "Body Lotion 400ml", "E", 299),
    ("Personal Care", "Body Lotion 400ml", "S", 349),
    ("Personal Care", "Body Lotion 400ml", "P", 459),
    ("Personal Care", "Deodorant Roll-on", "S", 309),
    ("Personal Care", "Shampoo 400ml", "E", 319),
    ("Personal Care", "Shampoo 400ml", "S", 369),
    ("Personal Care", "Shampoo 400ml", "P", 479),
    ("Personal Care", "Petroleum Jelly 250ml", "E", 139),
    ("Personal Care", "Petroleum Jelly 250ml", "S", 169),
    ("Personal Care", "Petroleum Jelly 250ml", "P", 219),
    ("Personal Care", "Hair Oil 250ml", "S", 309),
    ("Personal Care", "Hair Oil 250ml", "P", 399),
    ("Baby Care", "Diapers Jumbo Pack", "E", 769),
    ("Baby Care", "Diapers Jumbo Pack", "S", 909),
    ("Baby Care", "Diapers Jumbo Pack", "P", 1179),
    ("Baby Care", "Baby Wipes 80s", "S", 279),
    ("Baby Care", "Baby Lotion 300ml", "E", 289),
    ("Baby Care", "Baby Lotion 300ml", "S", 339),
    ("Baby Care", "Infant Formula 400g", "E", 889),
    ("Baby Care", "Infant Formula 400g", "S", 1049),
    ("Baby Care", "Baby Soap", "S", 149),
    ("School & Stationery", "Exercise Book 96pg", "S", 49),
    ("School & Stationery", "Exercise Book 96pg", "P", 59),
    ("School & Stationery", "Exercise Book 200pg", "S", 89),
    ("School & Stationery", "Ball Pens Box of 12", "S", 239),
    ("School & Stationery", "Geometry Set", "S", 199),
    ("School & Stationery", "School Bag", "E", 989),
    ("School & Stationery", "School Bag", "S", 1169),
    ("School & Stationery", "Crayons 12 Colours", "S", 179),
    ("School & Stationery", "Notebook A4", "E", 159),
    ("School & Stationery", "Notebook A4", "S", 189),
    ("School & Stationery", "Notebook A4", "P", 239),
]
TIER_NAME = {"E": "Economy", "S": "Standard", "P": "Premium"}
COST_RATIO_MEAN = {"Baby Care": .802, "Beverages": .816, "Dairy": .826, "Farm Produce": .712,
                   "Food Staples": .876, "Household & Cleaning": .781, "Personal Care": .728,
                   "School & Stationery": .657, "Snacks & Confectionery": .742}
COST_RATIO_SD = 0.021
PRODUCTS_WITHOUT_COST = 6

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# =====================================================================
# HELPERS
# =====================================================================
def easter_sunday(year):
    """Gregorian Easter Sunday (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def month_end(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def months_between(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fmt_date(d, sep_abbr="Sep", year4=True):
    mon = sep_abbr if d.month == 9 else MONTH_ABBR[d.month - 1]
    return f"{d.day:02d}-{mon}-{d.year if year4 else str(d.year)[2:]}"


def make_rngs(seed):
    ss = np.random.SeedSequence(seed)
    names = ["catalogue", "promo", "customers", "visits", "traffic", "baskets", "returns", "payments", "prices", "noise"]
    return dict(zip(names, [np.random.default_rng(s) for s in ss.spawn(len(names))]))


# =====================================================================
# 1. TABLES: BRANCHES, PRODUCTS
# =====================================================================
def build_branches():
    return pd.DataFrame([{
        "store_id": b[0], "store_name": b[1], "county": b[2], "town": b[3], "format": b[4],
        "store_positioning": b[5], "opening_date": fmt_date(b[6]), "floor_area_sqm": b[7]} for b in BRANCHES])


def build_products(rng):
    rows = []
    for i, (cat, name, tier, price) in enumerate(CATALOGUE, start=1):
        ratio = float(np.clip(rng.normal(COST_RATIO_MEAN[cat], COST_RATIO_SD), 0.55, 0.93))
        rows.append({"product_id": f"SKU{i:04d}", "product_name": name, "category": cat,
                     "tier": TIER_NAME[tier], "list_price_kes": price, "unit_cost_kes": round(price * ratio, 2)})
    df = pd.DataFrame(rows)
    missing = rng.choice(len(df), size=PRODUCTS_WITHOUT_COST, replace=False)
    df.loc[missing, "unit_cost_kes"] = np.nan
    return df


# =====================================================================
# 2. PROMOTIONS
# =====================================================================
def build_promos(rng, products):
    rows = []

    def add(name, start, end, scope, cat, pid, stores, disc):
        rows.append({"promo_name": name, "promo_type": "Percentage off", "start_date": start, "end_date": end,
                     "scope_type": scope, "category": cat, "product_id": pid, "store_scope": stores,
                     "discount_pct": int(disc)})

    # weekly SKU offers
    w = (products["category"].map(SKU_OFFER_CATEGORY_FACTOR) * products["tier"].str[0].map(SKU_OFFER_TIER_FACTOR)).values
    w = w / w.sum()
    months = list(months_between(START, END))
    while True:                                    # monthly offer counts that add up to the total
        counts = rng.integers(SKU_OFFERS_PER_MONTH[0], SKU_OFFERS_PER_MONTH[1] + 1, len(months))
        if counts.sum() == SKU_OFFERS_TOTAL:
            break
    for (y, m), n in zip(months, counts):
        for _ in range(n):
            dur = int(rng.choice(SKU_OFFER_DURATIONS, p=SKU_OFFER_DUR_P))
            lo = max(date(y, m, 1), PROMO_FIRST_START)
            hi = min(month_end(y, m), END - timedelta(days=dur - 1))
            if hi < lo:
                continue
            start = lo + timedelta(days=int(rng.integers(0, (hi - lo).days + 1)))
            end = start + timedelta(days=dur - 1)
            pid = products["product_id"].iloc[int(rng.choice(len(products), p=w))]
            disc = rng.choice(SKU_OFFER_DISCOUNTS, p=np.array(SKU_OFFER_DISC_P) / sum(SKU_OFFER_DISC_P))
            if rng.random() < SKU_OFFER_ALL_STORES_P:
                scope = "ALL"
            else:
                k = int(rng.choice(SKU_OFFER_SUBSET_SIZES, p=np.array(SKU_OFFER_SUBSET_P) / sum(SKU_OFFER_SUBSET_P)))
                scope = ";".join(sorted(rng.choice(STORES, size=k, replace=False)))
            add("Weekly SKU Offer", start, end, "SKU", None, pid, scope, disc)

    # payday deals: last five days of each month, two categories
    for y, m in months_between(START, END):
        last = month_end(y, m)
        for cat in rng.choice(PAYDAY_CATEGORIES, size=2, replace=False):
            add("Payday Deals", last - timedelta(days=4), last, "Category", cat, None, "ALL",
                rng.choice(PAYDAY_DISCOUNTS))

    cats_all = list(BASE_CATEGORY_SHARE)
    for y in range(START.year, END.year + 1):
        # Black Friday: Friday after US Thanksgiving, four days
        nov1 = date(y, 11, 1)
        thanksgiving = nov1 + timedelta(days=(3 - nov1.weekday()) % 7 + 21)
        bf = thanksgiving + timedelta(days=1)
        if bf >= START and bf + timedelta(days=3) <= END:
            for c in cats_all:
                add("Black Friday", bf, bf + timedelta(days=3), "Category", c, None, "ALL", 25)
        # Festive season
        if date(y, 12, 10) >= START and date(y, 12, 24) <= END:
            for c in ["Beverages", "Snacks & Confectionery"]:
                add("Festive Season", date(y, 12, 10), date(y, 12, 24), "Category", c, None, "ALL", 15)
        # Back to school
        for (s, e, disc) in [(date(y, 1, 2), date(y, 1, 20), 20), (date(y, 4, 22), date(y, 5, 6), 12),
                             (date(y, 8, 22), date(y, 9, 5), 12)]:
            if s >= START and e <= END:
                add("Back to School", s, e, "Category", "School & Stationery", None, "ALL", disc)
        # Easter
        es = easter_sunday(y)
        if es - timedelta(days=4) >= START and es + timedelta(days=1) <= END:
            for c in ["Dairy", "Farm Produce", "Snacks & Confectionery"]:
                add("Easter Offers", es - timedelta(days=4), es + timedelta(days=1), "Category", c, None, "ALL", 10)

    df = pd.DataFrame(rows).sort_values("start_date", kind="stable").reset_index(drop=True)
    df.insert(0, "promo_id", [f"PR{i:04d}" for i in range(1, len(df) + 1)])
    return df


# =====================================================================
# 3. CALENDAR
# =====================================================================
def build_calendar(promos):
    days = pd.date_range(START, END)
    D = len(days)
    cal = pd.DataFrame({"date": days.date})
    easter = {y: easter_sunday(y) for y in range(START.year, END.year + 1)}
    traffic = np.ones(D)
    pay_basket = np.ones(D)
    bf_windows = promos[promos.promo_name == "Black Friday"][["start_date", "end_date"]].drop_duplicates()
    for i, d in enumerate(cal["date"]):
        dim = month_end(d.year, d.month).day
        to_end = dim - d.day
        t = MONTH_EFFECT[d.month] * DOW_EFFECT[d.weekday()]
        if to_end in PAYDAY_TRAFFIC:
            t *= PAYDAY_TRAFFIC[to_end]
            pay_basket[i] = PAYDAY_BASKET[to_end]
        elif d.day in START_OF_MONTH_TRAFFIC:
            t *= START_OF_MONTH_TRAFFIC[d.day]
            pay_basket[i] = START_OF_MONTH_BASKET[d.day]
        t *= FIXED_DAY_EFFECT.get((d.month, d.day), 1.0)
        off = (d - easter[d.year]).days
        t *= EASTER_EFFECT.get(off, 1.0)
        for s, e in zip(bf_windows.start_date, bf_windows.end_date):
            if s <= d <= e:
                t *= BLACK_FRIDAY_TRAFFIC
        traffic[i] = t
    cal["traffic"] = traffic          # seasonal shape of demand (no growth, no store size)
    cal["pay_basket"] = pay_basket
    cal["week"] = np.minimum(np.arange(D) // 7, PRICE_WEEKS - 1)
    cal["t_years"] = np.arange(D) / 365.0
    return cal


# =====================================================================
# 4. PRICES, DISCOUNTS AND DEMAND MULTIPLIERS
# =====================================================================
def build_price_tensor(rng, products):
    """price[store, week, product] in whole KES."""
    P = len(products)
    cats = list(PRICE_BEHAVIOUR)
    cat_shock = {c: np.cumsum(rng.normal(0, PRICE_CATEGORY_SHOCK_SD, PRICE_WEEKS)) for c in cats}
    level = np.ones((P, PRICE_WEEKS))
    for i, row in enumerate(products.itertuples()):
        mean_wk, drift, sd = PRICE_BEHAVIOUR[row.category]
        if row.category == "Farm Produce":                   # seasonal, mean-reverting
            phase, lv, nxt = rng.uniform(0, 52), 0.0, 0
            for w in range(PRICE_WEEKS):
                if w >= nxt:
                    season = 0.10 * np.sin(2 * np.pi * (w + phase) / 52) - 0.10 * np.sin(2 * np.pi * phase / 52)
                    lv = 0.55 * lv + 0.45 * season + rng.normal(0, 0.07)
                    nxt = w + max(1, int(rng.geometric(1 / mean_wk)))
                level[i, w] = np.exp(lv)
        else:                                                # step repricing with drift
            lv, nxt = 0.0, int(rng.geometric(1 / mean_wk))
            for w in range(PRICE_WEEKS):
                if w >= nxt:
                    gap = max(1, int(rng.geometric(1 / mean_wk)))
                    step = PRICE_DRIFT_SCALE * drift * gap / 52 + rng.normal(0, sd)
                    if rng.random() < PRICE_BIG_MOVE_P:
                        step += rng.choice([-1, 1]) * rng.uniform(*PRICE_BIG_MOVE_RANGE)
                    lv += step
                    nxt = w + gap
                level[i, w] = np.exp(lv + cat_shock[row.category][w])
    level = np.clip(level, 0.78, 1.65)
    S = len(STORES)
    store_idx = np.array([STORE_PRICE_INDEX[s] for s in STORES])
    noise = np.exp(rng.normal(0, STORE_PRODUCT_PRICE_NOISE, (S, P)))
    lst = products["list_price_kes"].values.astype(float)
    ratio = (products["unit_cost_kes"] / products["list_price_kes"]).groupby(products["category"]).transform("median")
    cost = products["unit_cost_kes"].fillna(ratio * products["list_price_kes"]).values
    style = rng.choice(list(PRICE_STYLE_P), size=P, p=list(PRICE_STYLE_P.values()))

    raw = lst[None, None, :] * level.T[None, :, :] * store_idx[:, None, None] * noise[:, None, :]
    raw = np.maximum(raw, (cost * MIN_MARGIN_OVER_COST)[None, None, :])
    st = style[None, None, :]
    out = np.round(raw)
    out = np.where((st == "charm9") & (raw >= 30), 10 * np.round((raw - 9) / 10) + 9, out)
    out = np.where((st == "round5") & (raw >= 30), 5 * np.round(raw / 5), out)
    out = np.where((st == "round10") & (raw >= 60), 10 * np.round(raw / 10), out)
    out = np.where((st == "round10") & (raw >= 30) & (raw < 60), 5 * np.round(raw / 5), out)
    out = np.maximum(out, 1)
    step = np.where(st == "round5", 5, np.where(raw < 30, 1, 10))
    out = np.where(out < cost[None, None, :], out + step * np.ceil((cost[None, None, :] - out) / step), out)
    return out.astype(np.int32)


def build_promo_tensors(promos, products, n_days):
    """Best discount, its promo index and the demand multiplier for every store/day/product."""
    S, P = len(STORES), len(products)
    disc = np.zeros((S, n_days, P), dtype=np.int16)
    pidx = np.full((S, n_days, P), -1, dtype=np.int16)
    uplift = np.ones((S, n_days, P), dtype=np.float32)
    dip = np.ones((S, n_days, P), dtype=np.float32)
    prod_pos = {p: i for i, p in enumerate(products["product_id"])}
    cat_members = {c: np.where(products["category"].values == c)[0] for c in products["category"].unique()}
    day0 = START

    def sl(a, b):
        return max((a - day0).days, 0), min((b - day0).days, n_days - 1)

    for k, r in enumerate(promos.itertuples()):               # ascending promo id: ties keep the lowest id
        d0, d1 = sl(r.start_date, r.end_date)
        if d1 < d0:
            continue
        sidx = list(range(S)) if r.store_scope == "ALL" else [STORES.index(s) for s in r.store_scope.split(";")]
        prods = np.array([prod_pos[r.product_id]]) if r.scope_type == "SKU" else cat_members[r.category]
        for s in sidx:
            cur = disc[s, d0:d1 + 1][:, prods]
            better = r.discount_pct > cur
            disc[s, d0:d1 + 1][:, prods] = np.where(better, r.discount_pct, cur)
            cp = pidx[s, d0:d1 + 1][:, prods]
            pidx[s, d0:d1 + 1][:, prods] = np.where(better, k, cp)
        # demand response
        if r.scope_type == "SKU":
            up = SKU_PROMO_UPLIFT[0] + SKU_PROMO_UPLIFT[1] * r.discount_pct
        elif r.promo_name == "Back to School":
            key = "jan" if r.start_date.month == 1 else "other"
            up, tail_days, tail_mult = BACK_TO_SCHOOL_SURGE[key]
            if tail_days:
                t0, t1 = sl(r.end_date + timedelta(days=1), r.end_date + timedelta(days=tail_days))
                if t1 >= t0:
                    for s in sidx:
                        blk = uplift[s, t0:t1 + 1][:, prods]
                        uplift[s, t0:t1 + 1][:, prods] = np.maximum(blk, tail_mult)
        else:
            up = CATEGORY_PROMO_UPLIFT[r.promo_name]
        for s in sidx:
            blk = uplift[s, d0:d1 + 1][:, prods]
            uplift[s, d0:d1 + 1][:, prods] = np.maximum(blk, up)
        if r.scope_type == "SKU":                              # pantry-loading dip after a SKU offer
            q0, q1 = sl(r.end_date + timedelta(days=1), r.end_date + timedelta(days=POST_PROMO_DAYS))
            if q1 >= q0:
                for s in sidx:
                    dip[s, q0:q1 + 1][:, prods] = POST_PROMO_DIP
    uplift = np.where(uplift > 1.0, uplift, dip)
    return disc, pidx, uplift.astype(np.float32)


# =====================================================================
# 5. STORE PRODUCT WEIGHTS (category and tier targets via iterative scaling)
# =====================================================================
Z_GRID = np.array([-1.28, -0.52, 0.0, 0.52, 1.28])     # affluence levels used for basket draws


def affluence_log_tilt(products):
    """log tier tilt per affluence level: shape (5, n_products)."""
    beta = np.array([AFFLUENCE_TIER_TILT[t] for t in products["tier"].str[0].values])
    return np.stack([beta * z - 0.5 * beta ** 2 for z in Z_GRID])


def build_store_weights(rng, products):
    P = len(products)
    price = products["list_price_kes"].values.astype(float)
    pop = np.exp(rng.normal(0, POPULARITY_SIGMA, P)) * (price / 150.0) ** POPULARITY_PRICE_ELASTICITY
    cats = products["category"].values
    tiers = products["tier"].str[0].values
    W = np.zeros((len(STORES), P))
    for si, s in enumerate(STORES):
        tgt_cat = dict(BASE_CATEGORY_SHARE)
        pop_s = pop * ((price / 150.0) ** EXPRESS_PRICE_ELASTICITY if STORE_FORMAT[s] == "Express" else 1.0)
        if STORE_FORMAT[s] == "Express":
            for c, f in EXPRESS_CATEGORY_ADJ.items():
                tgt_cat[c] *= f
        tot = sum(tgt_cat.values())
        tgt_cat = {c: v / tot for c, v in tgt_cat.items()}
        want_tier = dict(zip("ESP", TIER_SHARE[s]))
        tgt_tier = dict(want_tier)
        lt = np.exp(affluence_log_tilt(products))
        for _outer in range(12):               # outer loop: allow for the customer affluence tilt
            w = pop_s.copy()
            for _ in range(60):
                for c, t in tgt_cat.items():
                    m = cats == c
                    w[m] *= t / (w[m].sum() / w.sum())
                for t_code, t in tgt_tier.items():
                    m = tiers == t_code
                    w[m] *= t / (w[m].sum() / w.sum())
            mixed = np.zeros(3)
            for b in range(5):
                v = w * lt[b]
                v = v / v.sum()
                mixed += np.array([v[tiers == k].sum() for k in "ESP"]) / 5
            for j, k in enumerate("ESP"):
                tgt_tier[k] *= want_tier[k] / mixed[j]
            norm = sum(tgt_tier.values())
            tgt_tier = {k: v / norm for k, v in tgt_tier.items()}
        W[si] = w / w.sum()
    return W


# =====================================================================
# 6. CUSTOMERS
# =====================================================================
def draw_placeholders(rng, values, field):
    out = np.array(values, dtype=object)
    hit = rng.random(len(out)) < PLACEHOLDER_RATE[field]
    mix = np.array(PLACEHOLDER_MIX[field], dtype=float)
    out[hit] = rng.choice(PLACEHOLDER_TOKENS, size=hit.sum(), p=mix / mix.sum())
    return out


def build_customers(rng):
    rows = []
    reg_days_all = pd.date_range(REG_START, REG_END).date
    for s in STORES:
        n = CUSTOMERS_PER_STORE[s]
        lo = max(STORE_OPEN[s], REG_START)
        days = [d for d in reg_days_all if d >= lo]
        dens = np.ones(len(days))
        if STORE_OPEN[s] >= REG_START:                     # newly opened stores attract a registration burst
            age = np.array([(d - STORE_OPEN[s]).days for d in days])
            dens = 1 + NEW_STORE_REG_BURST[0] * np.exp(-age / NEW_STORE_REG_BURST[1])
        pick = rng.choice(len(days), size=n, p=dens / dens.sum())
        reg = [days[i] for i in pick]
        rng.shuffle(reg)
        cmix = CATCHMENT[s]
        county = rng.choice(list(cmix), size=n, p=np.array(list(cmix.values())) / sum(cmix.values()))
        age = rng.choice(AGE_BANDS, size=n, p=AGE_PROBS)
        gender = rng.choice(list(GENDER_PROBS), size=n, p=list(GENDER_PROBS.values()))
        for i in range(n):
            rows.append((s, reg[i], county[i], age[i], gender[i]))
    df = pd.DataFrame(rows, columns=["registration_store_id", "registration_date", "county", "age_band", "gender"])
    df.insert(0, "customer_id", [f"C{i:06d}" for i in range(1, len(df) + 1)])
    return df


def assign_customer_traits(rng, cust):
    n = len(cust)
    new = np.array([d >= START for d in cust.registration_date])
    z = rng.normal(0, 1, n)                                         # affluence
    bucket = np.digitize(z, [-0.84, -0.25, 0.25, 0.84])
    spend = np.exp(rng.normal(0, BASKET_SIZE_SD, n))
    spend *= cust.age_band.map(AGE_SPEND).values * cust.gender.map(GENDER_SPEND).values
    fem4554 = ((cust.gender == "Female") & (cust.age_band == "45-54")).values
    spend[fem4554] = spend[fem4554] / GENDER_SPEND["Female"] * FEMALE_45_54_SPEND * 1.0
    seg = np.empty(n, dtype=object)
    u = rng.random(n)
    p_one = np.where(new, P_ONE_TIME_NEW, P_ONE_TIME_EXISTING)
    seg[u < p_one] = "one_time"
    rest = u >= p_one
    lapse = rng.random(n) < P_LAPSED
    seg[rest & lapse] = "lapsed"
    seg[rest & ~lapse] = "active"
    seg[rng.random(n) < NEVER_PURCHASED_SHARE] = "never"
    rate = np.exp(rng.normal(np.log(VISIT_RATE_MEDIAN), VISIT_RATE_SIGMA, n)) * cust.age_band.map(AGE_VISIT_RATE).fillna(1.0).values
    rate = np.clip(rate, 0.3, 12.0)
    return dict(new=new, affluence=z, bucket=bucket, spend=spend, segment=seg, rate=rate)


# =====================================================================
# 7. MEMBER VISITS (simulated before any receipts exist)
# =====================================================================
def plan_visits(rng, cust, traits, cal, expected_total_receipts):
    D = len(cal)
    day_w = cal["traffic"].values
    n = len(cust)
    home = np.array([STORES.index(s) for s in cust.registration_store_id])
    reg = np.array(cust.registration_date)
    new = traits["new"]
    open_idx = np.array([max((STORE_OPEN[s] - START).days, 0) for s in STORES])
    store_traffic = np.array([STORE_DAILY_TXNS[s] for s in STORES], dtype=float)
    closed = closure_mask(cal)
    county_of = np.array([b[2] for b in BRANCHES])

    # first purchase date
    lag = np.where(new, rng.exponential(FIRST_VISIT_LAG_NEW, n), rng.exponential(FIRST_VISIT_LAG_EXISTING, n))
    lag = np.minimum(np.floor(lag), 180).astype(int)
    reg_idx = np.array([(r - START).days for r in reg])
    first = np.where(new, reg_idx + lag, lag)
    seg = traits["segment"]

    # lapsed customers stop partway through their window
    last = np.full(n, D - 1)
    lapsed = seg == "lapsed"
    frac = rng.beta(LAPSE_SHAPE[0], LAPSE_SHAPE[1], n)
    last[lapsed] = (first[lapsed] + frac[lapsed] * (D - 1 - first[lapsed])).astype(int)

    # scale visit rates so that members make roughly TARGET_MEMBER_SHARE of receipts
    span_m = np.maximum(last - first, 0) / 30.4
    mean_visits = np.maximum(2, traits["rate"] * span_m)
    multi = ~np.isin(seg, ["one_time", "never"]) & (first < D)
    one = (seg == "one_time") & (first < D)
    target = TARGET_MEMBER_SHARE * expected_total_receipts
    k = (target - one.sum()) / mean_visits[multi].sum()

    vc, vd, vs = [], [], []
    for c in range(n):
        f = first[c]
        if f >= D or seg[c] == "never":
            continue
        if seg[c] == "one_time":
            d = f if new[c] else int(rng.choice(D, p=day_w / day_w.sum()))
            dates = np.array([d])
        else:
            m = int(max(2, rng.poisson(mean_visits[c] * k)))
            pool = np.arange(f + 1, last[c] + 1)
            m_extra = min(m - 1, len(pool))
            if m_extra > 0:
                w = day_w[pool]
                extra = rng.choice(pool, size=m_extra, replace=False, p=w / w.sum())
            else:
                extra = np.array([], dtype=int)
            dates = np.concatenate([[f], extra]).astype(int)
        # stores: always home on the first visit, then home with prob HOME_STORE_SHARE
        st = np.full(len(dates), home[c])
        away = rng.random(len(dates)) > HOME_STORE_SHARE
        away[0] = False
        if away.any():
            wst = store_traffic.copy()
            wst[home[c]] = 0
            st[away] = rng.choice(len(STORES), size=away.sum(), p=wst / wst.sum())
        # a store cannot be visited before it opens or on a closure day
        bad = (dates < open_idx[st]) | closed[st, dates]
        for j in np.flatnonzero(bad):
            ok = ~closed[:, dates[j]] & (dates[j] >= open_idx)
            wst = store_traffic * ok * np.where(county_of == county_of[home[c]], 3.0, 1.0)
            st[j] = rng.choice(len(STORES), p=wst / wst.sum())
        vc.append(np.full(len(dates), c))
        vd.append(dates)
        vs.append(st)
    return np.concatenate(vc), np.concatenate(vd), np.concatenate(vs)


# =====================================================================
# 8. SALES RECEIPTS AND LINES
# =====================================================================
def closure_mask(cal):
    """Boolean (store, day) array: True on days a store is closed."""
    closed = np.zeros((len(STORES), len(cal)), dtype=bool)
    for s, a, b in STORE_CLOSURES:
        i0, i1 = (a - START).days, (b - START).days
        closed[STORES.index(s), i0:i1 + 1] = True
    return closed


def store_mean_traffic(cal):
    """Expected receipts per day for each store (store size x growth x ramp-up x seasonal shape)."""
    D = len(cal)
    out = np.zeros((len(STORES), D))
    for si, s in enumerate(STORES):
        shape = cal["traffic"].values * np.exp(ANNUAL_GROWTH * cal["t_years"].values)
        open_day = max((STORE_OPEN[s] - START).days, 0)
        ramp = np.ones(D)
        if s in NEW_STORE_RAMP:
            r0, r1, tau = NEW_STORE_RAMP[s]
            since = np.maximum(np.arange(D) - open_day, 0)
            ramp = r0 + (r1 - r0) * (1 - np.exp(-since / tau))
        mu = shape * ramp
        mu[:open_day] = 0
        scale = STORE_DAILY_TXNS[s] / mu[open_day:].mean() / np.exp(COMMON_DAY_SHOCK_SD ** 2 / 2 + STORE_DAY_NOISE_SD ** 2 / 2)
        out[si] = mu * scale
    county = np.array([b[2] for b in BRANCHES])
    for s, a, b in STORE_CLOSURES:                       # closed store's traffic partly moves to its neighbours
        si, i0, i1 = STORES.index(s), (a - START).days, (b - START).days
        lost = out[si, i0:i1 + 1].copy()
        out[si, i0:i1 + 1] = 0
        near = [j for j in range(len(STORES)) if j != si and county[j] == county[si]]
        if near:
            share = np.array([STORE_DAILY_TXNS[STORES[j]] for j in near], dtype=float)
            share /= share.sum()
            for j, f in zip(near, share):
                out[j, i0:i1 + 1] += lost * CLOSURE_DISPLACED_SHARE * f
    return out


def qty_factor_table(products):
    price = products["list_price_kes"].values
    band = np.where(price <= 150, "cheap", np.where(price >= 200, "dear", "mid"))
    out = np.ones((len(STORES), len(products)))
    for si, s in enumerate(STORES):
        cls = "hyper" if STORE_FORMAT[s] == "Hypermarket" else STORE_CLASS[s].lower()
        for b in ("cheap", "mid", "dear"):
            out[si, band == b] = QTY_STORE_PRICE[cls][b]
    return out


def generate_sales(rngs, products, cust, traits, cal, W, price_t, disc_t, pidx_t, uplift_t, visits):
    rng = rngs["baskets"]
    D, P = len(cal), len(products)
    mu = store_mean_traffic(cal)
    closed = closure_mask(cal)
    shock = np.exp(rngs["traffic"].normal(0, COMMON_DAY_SHOCK_SD, D))
    vc, vd, vs = visits
    key = vs * D + vd
    order = np.argsort(key, kind="stable")
    vc, vd, vs, key = vc[order], vd[order], vs[order], key[order]

    cat_codes = products["category"].values
    qty_mean = np.array([QTY_CATEGORY_MEAN[c] for c in cat_codes])
    qfac = qty_factor_table(products)
    for si, s in enumerate(STORES):
        qfac[si] *= QTY_FORMAT_FACTOR.get(STORE_FORMAT[s], 1.0)
    log_tilt = affluence_log_tilt(products)                    # (5, P)

    t_store, t_day, t_seq, t_min, t_cust, t_nl = [], [], [], [], [], []
    l_txn, l_prod, l_qty, l_price, l_disc, l_pid = [], [], [], [], [], []
    txn_offset = 0
    for si, s in enumerate(STORES):
        open_day = max((STORE_OPEN[s] - START).days, 0)
        lo = np.searchsorted(key, si * D)
        hi = np.searchsorted(key, (si + 1) * D)
        sk, sc = key[lo:hi] - si * D, vc[lo:hi]
        bounds = np.searchsorted(sk, np.arange(D + 1))
        for d in range(open_day, D):
            if closed[si, d]:
                continue
            members = sc[bounds[d]:bounds[d + 1]]
            m = len(members)
            total = max(m, int(rng.poisson(mu[si, d] * shock[d] * np.exp(rng.normal(0, STORE_DAY_NOISE_SD)))))
            if total == 0:
                continue
            cust_ids = np.concatenate([members, -np.ones(total - m, dtype=int)])
            rng.shuffle(cust_ids)
            minutes = np.sort(rng.choice(OPENING_HOURS, size=total, p=HOUR_WEIGHTS) * 60 + rng.integers(0, 60, total))
            is_m = cust_ids >= 0
            spend = np.where(is_m, traits["spend"][np.maximum(cust_ids, 0)], np.exp(rng.normal(0, BASKET_SIZE_SD, total)))
            bucket = np.where(is_m, traits["bucket"][np.maximum(cust_ids, 0)], rng.integers(0, 5, total))
            mean_lines = LINES_BASE[STORE_FORMAT[s]] * cal["pay_basket"].values[d] * spend
            extra_mean = np.maximum(mean_lines - 1.0, 0.2)
            nl = 1 + rng.negative_binomial(LINES_DISPERSION, LINES_DISPERSION / (LINES_DISPERSION + extra_mean))
            nl = np.minimum(nl, 45)

            wdyn = W[si] * uplift_t[si, d]
            logw = np.log(wdyn)[None, :] + log_tilt[bucket]
            keys = logw - np.log(-np.log(rng.random((total, P))))      # Gumbel top-k: weighted draw without replacement
            top = np.argsort(-keys, axis=1)[:, :nl.max()]
            mask = np.arange(top.shape[1])[None, :] < nl[:, None]
            prod = top[mask]
            tix = np.repeat(np.arange(total), nl)
            shuffle_key = rng.random(len(prod))                         # random line order within a receipt
            o = np.lexsort((shuffle_key, tix))
            prod, tix = prod[o], tix[o]

            ex = np.maximum((qty_mean[prod] - 1.0) * QTY_BASE_SCALE, 0.05) * qfac[si, prod]
            q = rng.geometric(1.0 / (1.0 + ex))
            dsc = disc_t[si, d, prod]
            q = q + np.where(dsc > 0, rng.poisson(PROMO_QTY_BUMP, len(q)), 0)
            bulk = rng.random(len(q)) < BULK_PROB
            if bulk.any():
                q[bulk] = (rng.choice(BULK_PACKS, size=bulk.sum(), p=BULK_PACK_P) *
                           rng.choice(BULK_MULT, size=bulk.sum(), p=BULK_MULT_P))
            price = price_t[si, cal["week"].values[d], prod]

            t_store.append(np.full(total, si)); t_day.append(np.full(total, d))
            t_seq.append(np.arange(1, total + 1)); t_min.append(minutes)
            t_cust.append(cust_ids); t_nl.append(nl)
            l_txn.append(tix + txn_offset); l_prod.append(prod); l_qty.append(q.astype(np.int32))
            l_price.append(price); l_disc.append(dsc); l_pid.append(pidx_t[si, d, prod])
            txn_offset += total
    cat = np.concatenate
    txn = dict(store=cat(t_store), day=cat(t_day), seq=cat(t_seq), minute=cat(t_min), cust=cat(t_cust), nl=cat(t_nl))
    lines = dict(txn=cat(l_txn), prod=cat(l_prod), qty=cat(l_qty), price=cat(l_price), disc=cat(l_disc), pidx=cat(l_pid))
    return txn, lines


# =====================================================================
# 9. RETURNS
# =====================================================================
def generate_returns(rng, txn, lines, n_days):
    n = len(txn["store"])
    line_start = np.concatenate([[0], np.cumsum(txn["nl"])])[:-1]
    hit = np.where(rng.random(n) < RETURN_RATE)[0]
    lag = np.minimum(rng.geometric(RETURN_LAG_P, len(hit)), 21)
    rday = txn["day"][hit] + lag
    keep = rday < n_days
    hit, rday = hit[keep], rday[keep]
    pick = line_start[hit] + np.floor(rng.random(len(hit)) * txn["nl"][hit]).astype(int)
    oq = lines["qty"][pick]
    frac = rng.choice(RETURN_PARTIAL_FRACTIONS, size=len(hit), p=np.array(RETURN_PARTIAL_P) / sum(RETURN_PARTIAL_P))
    partial = (rng.random(len(hit)) > RETURN_FULL_QTY_P) & (oq >= 2)
    rq = np.where(partial, np.maximum(1, np.round(oq * frac)).astype(int), oq)
    minutes = rng.choice(OPENING_HOURS, size=len(hit), p=HOUR_WEIGHTS) * 60 + rng.integers(0, 60, len(hit))
    ret = dict(orig=hit, store=txn["store"][hit], day=rday, minute=minutes, cust=txn["cust"][hit])
    # sequence numbers per store/day, starting at 70001
    order = np.lexsort((np.arange(len(hit)), ret["day"], ret["store"]))
    seq = np.zeros(len(hit), dtype=int)
    k = ret["store"][order] * (n_days + 1) + ret["day"][order]
    first = np.concatenate([[True], k[1:] != k[:-1]])
    grp = np.cumsum(first) - 1
    seq[order] = 70001 + (np.arange(len(order)) - np.flatnonzero(first)[grp])
    ret["seq"] = seq
    rl = dict(prod=lines["prod"][pick], qty=-rq, price=lines["price"][pick], disc=lines["disc"][pick], pidx=lines["pidx"][pick])
    return ret, rl


# =====================================================================
# 10. PAYMENTS, IDS AND OUTPUT TABLES
# =====================================================================
_ALPHABET = np.array(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))


def unique_references(rng, n, used=None):
    used = set() if used is None else used
    out = []
    while len(out) < n:
        need = n - len(out)
        cand = ["".join(r) for r in _ALPHABET[rng.integers(0, 36, (need, 10))]]
        for c in cand:
            if c not in used:
                used.add(c)
                out.append(c)
    return out, used


def draw_methods(rng, stores):
    out = np.empty(len(stores), dtype=object)
    for si, s in enumerate(STORES):
        m = stores == si
        out[m] = rng.choice(["M-Pesa", "Cash", "Card"], size=m.sum(), p=np.array(PAYMENT_MIX[s]) / sum(PAYMENT_MIX[s]))
    return out


def build_transaction_tables(rngs, products, cust, cal, txn, lines, ret, rl):
    rng = rngs["payments"]
    n_days = len(cal)
    day_str = np.array([fmt_date(d) for d in cal["date"]])
    day_key = np.array([d.strftime("%Y%m%d") for d in cal["date"]])
    time_str = np.array([f"{(m // 60) % 12 or 12:02d}:{m % 60:02d} {'AM' if m < 720 else 'PM'}" for m in range(1440)])
    store_arr = np.array(STORES)

    # ---- sales
    n_s = len(txn["store"])
    method = draw_methods(rng, txn["store"])
    ref = np.full(n_s, "", dtype=object)
    m_idx = np.where(method == "M-Pesa")[0]
    refs, used = unique_references(rng, len(m_idx))
    ref[m_idx] = refs
    ph_rate = np.array([PAYMENT_PLACEHOLDER_RATE[s] for s in STORES])[txn["store"]]
    ph = rng.random(n_s) < ph_rate
    p_tok = np.array(PAYMENT_PLACEHOLDER_P, dtype=float)
    method_out = method.copy()
    method_out[ph] = rng.choice(PAYMENT_PLACEHOLDER_TOKENS, size=ph.sum(), p=p_tok / p_tok.sum())

    net = lines["qty"] * lines["price"] * (1 - lines["disc"] / 100.0)
    basket = np.round(np.bincount(lines["txn"], weights=net, minlength=n_s), 2)
    cust_ids = cust["customer_id"].values
    sales = pd.DataFrame({
        "transaction_id": [f"{store_arr[a]}-{day_key[b]}-{c:05d}" for a, b, c in zip(txn["store"], txn["day"], txn["seq"])],
        "transaction_date": day_str[txn["day"]],
        "transaction_time": time_str[txn["minute"]],
        "store_id": store_arr[txn["store"]],
        "customer_id": np.where(txn["cust"] >= 0, cust_ids[np.maximum(txn["cust"], 0)], ""),
        "basket_total_kes": basket,
        "payment_method": method_out,
        "payment_reference": ref,
        "original_transaction_id": "",
    })
    sales["_key"] = (txn["store"] * (n_days + 1) + txn["day"]) * 100000 + txn["seq"]

    # ---- returns
    n_r = len(ret["store"])
    r_method = method[ret["orig"]].copy()
    flip = rng.random(n_r) < RETURN_OTHER_METHOD_P
    r_method[flip] = rng.choice(["M-Pesa", "Cash", "Card"], size=flip.sum())
    r_ref = np.full(n_r, "", dtype=object)
    r_m = np.where(r_method == "M-Pesa")[0]
    new_refs, used = unique_references(rng, len(r_m), used)
    r_ref[r_m] = new_refs
    r_net = rl["qty"] * rl["price"] * (1 - rl["disc"] / 100.0)
    returns = pd.DataFrame({
        "transaction_id": [f"{store_arr[a]}-{day_key[b]}-{c:05d}" for a, b, c in zip(ret["store"], ret["day"], ret["seq"])],
        "transaction_date": day_str[ret["day"]],
        "transaction_time": time_str[ret["minute"]],
        "store_id": store_arr[ret["store"]],
        "customer_id": np.where(ret["cust"] >= 0, cust_ids[np.maximum(ret["cust"], 0)], ""),
        "basket_total_kes": np.round(r_net, 2),
        "payment_method": r_method,
        "payment_reference": r_ref,
        "original_transaction_id": sales["transaction_id"].values[ret["orig"]],
    })
    returns["_key"] = (ret["store"] * (n_days + 1) + ret["day"]) * 100000 + ret["seq"]

    # ---- lines
    pid_codes = products["product_id"].values
    promo_ids = np.append(cal.attrs["promo_ids"], "")
    def line_frame(l, txn_key):
        return pd.DataFrame({
            "_key": txn_key,
            "product_id": pid_codes[l["prod"]],
            "quantity": l["qty"],
            "price": l["price"],
            "discount_pct": l["disc"].astype(int),
            "promo_id": np.where(l["pidx"] >= 0, promo_ids[l["pidx"]], ""),
        })
    sale_lines = line_frame(lines, sales["_key"].values[lines["txn"]])
    ret_lines = line_frame(rl, returns["_key"].values)

    all_txn = pd.concat([sales, returns], ignore_index=True)
    all_lines = pd.concat([sale_lines, ret_lines], ignore_index=True)
    all_txn = all_txn.sort_values("_key", kind="stable").reset_index(drop=True)
    all_lines = all_lines.sort_values("_key", kind="stable").reset_index(drop=True)
    # text-formatted prices, e.g. "KES 1,089"
    as_text = rng.random(len(all_lines)) < TEXT_PRICE_SHARE
    price_str = all_lines["price"].astype(int).astype(str).values.astype(object)
    price_str[as_text] = [f"KES {p:,}" for p in all_lines["price"].values[as_text]]
    all_lines["unit_price_kes"] = price_str
    txn_id_by_key = dict(zip(all_txn["_key"], all_txn["transaction_id"]))
    all_lines["transaction_id"] = all_lines["_key"].map(txn_id_by_key)
    all_lines.insert(0, "line_id", np.arange(1, len(all_lines) + 1))
    all_lines = all_lines[["line_id", "transaction_id", "product_id", "quantity", "unit_price_kes", "discount_pct", "promo_id"]]
    all_txn = all_txn.drop(columns="_key")
    return all_txn, all_lines


def format_customers(rng, cust):
    out = cust.copy()
    out["registration_date"] = [fmt_date(d, sep_abbr="Sept", year4=False) for d in out["registration_date"]]
    out["county"] = draw_placeholders(rng, out["county"].values, "county")
    out["age_band"] = draw_placeholders(rng, out["age_band"].values, "age_band")
    out["gender"] = draw_placeholders(rng, out["gender"].values, "gender")
    return out[["customer_id", "registration_date", "registration_store_id", "county", "age_band", "gender"]]


def format_promos(promos):
    out = promos.copy()
    out["start_date"] = [fmt_date(d) for d in out["start_date"]]
    out["end_date"] = [fmt_date(d) for d in out["end_date"]]
    return out[["promo_id", "promo_name", "promo_type", "start_date", "end_date", "scope_type",
                "category", "product_id", "store_scope", "discount_pct"]]


# =====================================================================
# MAIN
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=SEED, help="random seed (default %(default)s)")
    ap.add_argument("--out", default="data", help="output folder (default %(default)s)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rngs = make_rngs(args.seed)

    print("building reference tables ...")
    branches = build_branches()
    products = build_products(rngs["catalogue"])
    promos = build_promos(rngs["promo"], products)
    cal = build_calendar(promos)
    cal.attrs["promo_ids"] = promos["promo_id"].values
    n_days = len(cal)

    print("building prices, promotions and demand multipliers ...")
    price_t = build_price_tensor(rngs["prices"], products)
    disc_t, pidx_t, uplift_t = build_promo_tensors(promos, products, n_days)
    W = build_store_weights(rngs["catalogue"], products)

    print("building customers and planning visits ...")
    cust = build_customers(rngs["customers"])
    traits = assign_customer_traits(rngs["customers"], cust)
    expected = store_mean_traffic(cal).sum()
    visits = plan_visits(rngs["visits"], cust, traits, cal, expected)

    print("generating receipts and lines ...")
    txn, lines = generate_sales(rngs, products, cust, traits, cal, W, price_t, disc_t, pidx_t, uplift_t, visits)
    print("generating returns ...")
    ret, rl = generate_returns(rngs["returns"], txn, lines, n_days)
    print("assembling tables ...")
    transactions, receipt_lines = build_transaction_tables(rngs, products, cust, cal, txn, lines, ret, rl)
    customers = format_customers(rngs["noise"], cust)

    out = {
        "branches.csv": branches, "customers.csv": customers, "products.csv": products,
        "promotions.csv": format_promos(promos), "transactions.csv": transactions,
        "receipt_lines.csv": receipt_lines,
    }
    for name, df in out.items():
        df.to_csv(os.path.join(args.out, name), index=False)
        print(f"  {name:<20s} {len(df):>10,d} rows")
    print("done.")


if __name__ == "__main__":
    main()
