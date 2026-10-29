# Problem Framing and Data Acquisition

## Problem statement.

Our ten stores need to decide how much stock to order before knowing how much customers will buy. At the moment, these decisions rely mostly on store managers' experience rather than a consistent way of forecasting demand. This makes it difficult to plan stock replenishment for each store and product category, leading to stockouts during busy periods, lost sales, excess inventory and waste, especially for perishable goods such as milk and bread.

To address this problem, we'll develop a regression-based forecasting model to predict sales revenue, units sold and transaction volumes for each store and product category, on a weekly and monthly basis. We will also test whether promotions, public holidays, month-end paydays and national inflation data improve forecast accuracy. The model will use two years of synthetic sales data, store and promotion records, and inflation data from the Kenya National Bureau of Statistics (KNBS). 
The goal is to provide better information for stock replenishment and inventory allocation, helping the business anticipate demand, plan for busy periods and make more informed decisions about stock levels.

## How success will be measured

**Model Success:** The model will aim for a Mean Absolute Percentage Error (MAPE) of 15% or less on unseen test data. Mean Absolute Error (MAE) will also be reported. Forecast accuracy will be compared with and without promotion and inflation data to assess whether these factors improve predictions.

**Business Outcomes:** The forecasts should help stores plan stock replenishment more accurately, anticipate demand during busy periods and promotions, and allocate inventory more effectively. The impact will be assessed by tracking changes in stockout rates, excess inventory, and stock wastage.

## Business Questions
1. **Sales Forecasting**  
How much will each store and category sell?  
_What will total revenue, units sold and number of receipts be for each store and product category over the next weeks and the next month?_
2. **Promotional Impact**   
How do promotions and discounts affect sales, and how does demand change after a promotion ends?  
_How much extra do promotions sell, does a deeper discount sell more, and do sales dip in the weeks after a promotion ends?  (This will examine how sales vary with promotional activity and discount levels, including any changes after promotions end.)_  

3. **Understanding the Effect of Inflation on Sales**  
Do inflation rates, public holidays, and month-end payday patterns help explain changes in sales across product categories?  
_Does knowing the national inflation rate, public holidays and month-end payday make the forecast more accurate? (This will explore the relationship between these factors and test whether including them improves forecast accuracy compared with a model that excludes them.)_

## Data inventory, sources and terms

All raw files are stored unedited in `Data/`. Column definitions are in `data_dictionary.md`.

| File(s) | Description and source | Licence / terms |
|---|---|---|
| `branches.csv`, `products.csv`, `customers.csv`, `promos.csv`, `transactions.csv`, `receipt-lines.csv` |  Branches, products, customers, promotions, receipts and receipt lines. **Source:** Synthetic data generated with Claude (Anthropic) | No real or personal data; no third-party dataset used. |
| `inflation_data_knbs.csv` | Monthly inflation rates. **Source:** KNBS, via the [Central Bank of Kenya inflation table](https://www.centralbank.go.ke/inflation-rates/). Retrieved 22 Oct 2026.  | No CPI-specific licence found. Cite KNBS; check its terms of use. |
| `kenya_public_holidays.csv` | **Contents:** Kenyan public holiday dates, Jan 2024 to Sep 2026 (32 holidays). **Source:** [Public Holidays Act (Cap. 110)](https://new.kenyalaw.org/akn/ke/act/1912/21); Kenya Gazette notices for varying and one-off holidays. | Official Kenyan legal sources; Cite the Act and the Gazette notices. |


