# Sales Demand Forecasting and Customer Intelligence for a Kenyan Supermarket Chain

An end-to-end data analytics project on a multi-store supermarket dataset: data generation and cleaning, EDA, SQL analytics, statistical tests, a weekly and monthly demand forecasting model, and a five-page Power BI dashboard.

> **Data note:** all data is AI-generated. The raw tables were first generated through conversations with Claude (Anthropic). `Scripts/generate_data.py` was written afterwards, working back from those files, so that anyone can regenerate a *statistically equivalent* dataset, so a regenerated dataset gives similar results (see [Reproducing the results](#reproducing-the-results)). The inflation and public holiday files are real public data (see [Data sources](#data-sources)).

## The problem

A supermarket chain needs to stock enough of each product without waste (perishables) or empty shelves (stock-outs). The core questions, set in `problem_framing.md`, are:

1. **Sales forecasting:** how much revenue, how many units and how many receipts will each store and product sell over the next weeks and the next month?
2. **Promotional impact:** how much extra do promotions sell, does a deeper discount sell more, and do sales dip after a promotion ends?
3. **Inflation, holidays and payday:** do they make the forecast more accurate?

Supporting questions added for the SQL analysis and dashboard: which stores, categories and products drive sales and when they peak; who the valuable and at-risk customers are; and whether customers come back.

## The data at a glance

| Table | Rows | Notes |
|---|---|---|
| branches | 10 | ten stores |
| products | 171 | catalogue with tiers and prices |
| customers | 8,222 | registered customers; 8,196 made at least one purchase |
| promos | 322 | promotion calendar |
| transactions | 435,951 | receipts including returns; about 431K sales transactions after returns are excluded |
| receipt lines | 2,175,508 | items on each receipt |
| inflation | 24 | one row per month (real KNBS data) |
| holidays | 27 | Kenyan public holidays (real) |

Period covered: 1 October 2024 to 30 September 2026.

## How success was measured

The target was a **WAPE of 15% or less** on unseen test data, with MAE also reported, and every model compared with a "same as the previous period" baseline. WAPE replaced the MAPE named in the original plan, because MAPE divides each row's error by its actual sales, so rows with zero sales make it undefined or extremely large. WAPE adds up all the errors and divides once by total sales.

**Target versus result** (weekly and monthly, store × product level, final model Gradient Boosting):

- **Met:** monthly transactions (13.6%).
- **Not met:** weekly forecasts (22.9% to 30.4%) and monthly revenue and units (18.2% to 20.3%).
- **Beaten:** the baseline, by a clear margin, in every case.
- Weekly sales of one product in one store are small, random numbers, so some error cannot be removed whatever the model.

## Key results

| Forecast | Target | Baseline (last period) | Gradient Boosting | Random Forest |
|---|---|---|---|---|
| Weekly | Revenue | 47.1% | **30.4%** | 31.3% |
| Weekly | Units sold | 44.0% | **27.6%** | 27.9% |
| Weekly | Transactions | 37.9% | **22.9%** | 23.3% |
| Monthly | Revenue | 24.9% | 20.3% | **19.1%** |
| Monthly | Units sold | 25.1% | 18.2% | **17.9%** |
| Monthly | Transactions | 17.6% | **13.6%** | 14.0% |

Error is WAPE on the held-out test set (16 weeks, 4 months); lower is better. **Gradient Boosting is the final model:** it is more accurate weekly, within about a point of the Random Forest monthly, and much faster to train.

## Answers to the business questions

| Question | Where it is answered | Answer |
|---|---|---|
| 1. Sales forecasting | `preprocessing_and_model_training`, dashboard page 5 | Gradient Boosting beats the baseline by 15-17 points weekly and 4-7 points monthly (table above).|
| 2. Promotional impact | `exploratory_analysis_and_statistical_tests`, dashboard page 3 | About 21% of revenue comes from discounted lines, mostly at 1-20% discounts (discounts above 30% are about 0.5% of revenue). Removing the planned discount makes weekly forecasts 2-4 points worse, so promotions measurably change sales. The EDA agrees: promoted lines sell higher quantities, and weekly store-product sales have a median of 19 units in promotional periods against 12 otherwise (Mann-Whitney p < 0.001). The effect is small (rank-biserial +0.19).|
| 3. Inflation, holidays, payday | `preprocessing_and_model_training` (features removed one at a time), `exploratory_analysis_and_statistical_tests` | Payday timing improves weekly accuracy by about 3.5-4 points and planned promotions by 2-4 points. Public holidays and inflation add nothing measurable. Month-end days average about 1.9 times the daily revenue of an ordinary day. The EDA confirms the month-end effect is very large and statistically significant (p < 0.001, rank-biserial +0.91 for both revenue and units sold). Monthly sales and inflation are strongly correlated, but both trended upward over the same period, so this does not show a direct effect of inflation.|
| Customers and retention | `retail_analysis.sql`, dashboard page 4 | Of 8,196 customers who bought, 28% are Premium and bring about 68% of spend; the 30% classed as Lost bring about 2%. 793 customers (9.7%) are At Risk, mostly in Nairobi and Kiambu. About 79% of one month's customers buy again the next month, but customers who signed up in 2025-26 return at about 40% after one month, against 75% for the 2024 group. |

The forecast runs low for some categories (for example School & Stationery) and for the largest month-end peaks; see the limitations below.

## Changes made to the original plan

The original plan was to measure accuracy with a MAPE of 15% or less. This was changed to a WAPE of 15% or less, reported alongside MAE, because MAPE divides each error by that row's actual sales. A row with zero sales cannot be calculated, and rows with very small sales produce extremely large percentages. WAPE divides the total error by total sales, so zero-sales rows do not break it, and MAE shows the average error in units.

## Repository structure

```
.
├── README.md
├── data_dictionary.md
├── problem_framing.md
├── requirements.txt           # pip 
├── Scripts/
│   └── generate_data.py       # regenerates an equivalent synthetic raw dataset             # real public data used
├── Data/  
│   ├── inflation_data_knbs.csv
│   └── holidays_kenya.csv                
│   ├── *.csv                  # raw tables from generate_data.py
│   └── processed_data/        # cleaned tables, sales table, weekly/monthly tables, predictions
├── Notebooks/
│   ├── data_cleaning.ipynb
│   ├── exploratory_analysis_and_statistical_tests.ipynb   
│   └── preprocessing_and_model_training.ipynb
├── sql/
│   └── retail_analysis.sql    # tables, business questions, RFM, views
├── Dashboard/
│   └── screenshots/           
└── Reports/
    └── findings_and_recommendations.pptx
```

## How to run everything

**1. Set up the environment** (Python 3.12 recommended)

```bash
python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

**2. Create the raw data**

```bash
python Scripts/generate_data.py --seed 42 --out Data/
```

This writes `branches.csv`, `customers.csv`, `products.csv`, `promos.csv`, `transactions.csv` and `receipt-lines.csv`. The seed makes the output identical on every run.

**3. Run the notebooks in order** (Jupyter or VS Code; "Run all")

| Step | Notebook | What it does | Output |
|---|---|---|---|
| 1 | `data_cleaning` | Cleans each table, fixes dates and placeholders, builds the `sales` table | `Data/processed_data/*_cleaned.csv`, `sales.csv`|
| 2 | `exploratory_analysis_and_statistical_tests` | Explores sales, products, stores and customers, then statistical tests | figures, findings, test results |
| 3 | `preprocessing_and_model_training` | Builds the weekly and monthly forecast tables, trains and compares the models and exports predictions | `Data/processed_data/ weekly_data.csv`, `monthly_data.csv`, `weekly_predictions.csv`, `monthly_predictions.csv` |

**4. SQL analytics** (PostgreSQL)

1. Create a database and run the table definitions at the top of `sql/retail_analysis.sql` (schema `retail_forecasting`).
2. Import the cleaned CSVs from `Data/processed_data/` into the matching tables.
3. Run the queries (store and product performance, promotions and calendar effects, customers and RFM) and create the three views: `v_customer_rfm`, `v_cohort_retention`, `v_monthly_retention`.

**5. Dashboard** (Power BI)

[Sales Forecast Dashboard](https://app.powerbi.com/view?r=eyJrIjoiYjQ5YjA2ZGYtYWFiMy00ZGI1LWE0Y2UtZDRhODcwNDRkYjc1IiwidCI6IjFlZWU4YjJlLTRhN2YtNDdiYy05YzUzLTY5YTFiZTI2ZDZkYSJ9). The interactive dashboard is shared through Power BI's "Publish to web", and a screenshot of every page is in `dashboard/screenshots/`. To rebuild it, load the SQL views and tables and the two predictions files, link them on store, product and date, and add the measures.

### Reproducing the results

The reported results come from the original generated files. Running the steps above on data regenerated with `generate_data.py` produces the same structure and the same patterns, with numbers that differ slightly, by a few points.

## Method summary

- **Cleaning:** type and date fixes, placeholder handling, validity checks; returns excluded from sales.
- **Forecast table:** one row per store, product and week (or month), for complete periods only
- **Validation:** chronological split, 70% train / 15% validation / 15% test: 71 / 15 / 16 weeks and 16 / 3 / 4 months. Models and features were chosen on the validation set; the test set was used only for the final scores.
- **Models:** `HistGradientBoostingRegressor` and `RandomForestRegressor`, one per target, compared with a previous-period baseline.
- **Metrics:** WAPE, MAE and R².
- **Transactions:** at product level this is the number of receipts containing the product.

## Limitations

- The data is synthetic and covers two years, so each seasonal pattern appears once or twice.
- The monthly validation and test sets are very short (a few months), so monthly results are rough.
- The models underpredict the largest month-end peaks and some categories (School & Stationery), and per-product forecasts are much looser than totals.
- Roughly half of the transactions carry no customer ID, so customer analysis covers registered customers only.
- The data has no stock or waste records, so the business benefit (fewer stockouts and less waste) cannot be measured.
- The forecasts shown in the dashboard are for the test period, not for future weeks.

## Data sources

| File(s) | Source | Terms |
|---|---|---|
| Branches, products, customers, promotions, receipts and receipt lines | Synthetic, generated with Claude (Anthropic); regenerable with `Scripts/generate_data.py` | No real or personal data |
| `inflation_data_knbs.csv` | KNBS, via the [Central Bank of Kenya inflation table](https://www.centralbank.go.ke/inflation-rates/); retrieved 22 Oct 2026 | No CPI-specific licence found; cite KNBS |
| `holidays_kenya.csv` | [Public Holidays Act (Cap. 110)](https://new.kenyalaw.org/akn/ke/act/1912/21) and Kenya Gazette notices | Official Kenyan legal sources; cite the Act and the Gazette |
