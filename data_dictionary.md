# Data dictionary

## customers.csv

| Column | Description |
|---|---|
| customer_id | Customer code, uniquely identifies each customer |
| registration_date | Date the customer record was created |
| registration_store_id | Branch where the customer was first recorded |
| county | County of residence (may differ from the branch's county) |
| age_band | 18-24, 25-34, 35-44, 45-54 or 55+ |
| gender | Female or Male |

## products.csv

| Column | Description |
|---|---|
| product_id | Product code, such as SKU0042 |
| product_name | Name of the product. |
| category | One of nine product categories |
| tier | Economy, Standard or Premium version of the product |
| list_price_kes | Shelf/Selling price per unit |
| unit_cost_kes | What the retailer pays its supplier per unit |

Selling price minus cost is the gross margin. 

## branches.csv

| Column | Description |
|---|---|
| store_id | Branch code|
| store_name | Branch name |
| county | County the branch is in |
| town | Town the branch is in |
| format | Indicates the store type: Hypermarket, Supermarket, or Express. |
| store_positioning | The shoppers the branch targets: Value, Mid-market or Upmarket |
| opening_date | Date the branch officially started trading |
| floor_area_sqm | Shop floor area in square metres |

## promos.csv

| Column | Description |
|---|---|
| promo_id | Promotion code|
| promo_name | Name of the promotion, for example Payday Deals|
| promo_type | Type of promotion (percentage off) |
| start_date | First day of the promotion |
| end_date | Last day of the promotion |
| scope_type | Indicates whether the promotion applies to an entire product category or an individual product (SKU).|
| category | The category on promotion (blank for product promotions) |
| product_id | The product on promotion (blank for category promotions) |
| store_scope | Indicates which stores the promotion applies to: all stores (ALL) or specific stores listed by branch code, separated by semicolons. |
| discount_pct | Discount as a percentage |

## transactions.csv

| Column | Description |
|---|---|
| transaction_id | Unique receipt number combining the branch code, date (YYYYMMDD), and daily running number. |
| transaction_date | Date of the receipt |
| transaction_time | Time of the receipt |
| store_id | Branch where the sale happened |
| customer_id | Customer who made the purchase |
| basket_total_kes | Receipt total recorded by the till |
| payment_method | Cash, M-Pesa or Card |
| payment_reference | M-Pesa confirmation code (M-Pesa payments only) |
| original_transaction_id | Only for a return receipt, the receipt number of the earlier sale being refunded.|
## receipt-lines.csv

| Column | Description |
|---|---|
| line_id | Unique number for the line |
| transaction_id | The receipt this line belongs to |
| product_id | The product sold |
| quantity | Units sold. A negative number is an item returned |
| unit_price_kes | Shelf price charged per unit, before discount |
| discount_pct | Discount applied to the line, as a percentage (0 if none) |
| promo_id | The promotion that caused the discount (blank if none) |
> A return item has a negative basket_total_kes and negative quantities on its receipt line.

## inflation_data_knbs.csv

| Column | Description |
|---|---|
| month | First day of the month |
| inflation_12m_pct | Year-on-year inflation: how much higher prices are than in the same month a year earlier |


## kenya_public_holidays.csv

| Column | Description |
|---|---|
| date | Date of the holiday |
| holiday_name | Name of the holiday |


