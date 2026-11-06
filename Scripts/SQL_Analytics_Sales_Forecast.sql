 /*RETAIL SALES ANALYSIS
==========================================================================================================================
CREATING TABLES
===========================================================================================================================*/               
create schema retail_forecasting;
set search_path to retail_forecasting;
-- Preparing the tables
-- 1. Branches
create table branches (
    store_id varchar(20) primary key,
    store_name varchar(150),
    county varchar(100),
    town varchar(100),
    format varchar(100),
    store_positioning varchar(100),
    opening_date date,
    floor_area_sqm numeric(10,2));

-- 2. Products
create table products (
    product_id varchar(30) primary key,
    product_name varchar(150),
    category varchar(100),
    tier varchar(50),
    list_price_kes numeric(12,2),
    unit_cost_kes numeric(12,2));

-- 3. Customers
create table customers (
    customer_id varchar(30) primary key,
    registration_date date,
    registration_store_id varchar(20),
    county varchar(100),
    age_band varchar(30),
    gender varchar(30),
    foreign key (registration_store_id)
        references branches(store_id));

-- 4. Promotions
create table promotions (
    promo_id varchar(30) primary key,
    promo_name varchar(150),
    promo_type varchar(100),
    start_date date,
    end_date date,
    scope_type varchar(50),
    category varchar(100),
    product_id varchar(30),
    store_scope varchar(100),
    discount_pct numeric(8,2),
    foreign key (product_id) references products(product_id));

-- 5. Transactions
create table transactions (
    transaction_id varchar(30) primary key,
    transaction_date date,
    transaction_time TIME,
    store_id varchar(20),
    customer_id varchar(30),
    basket_total_kes numeric(14,2),
    payment_method varchar(50),
    payment_reference varchar(100),
    original_transaction_id varchar(30),
    year integer,
    month integer,
    week integer,
    day_name varchar(20),
    end_month BOOLEAN,
    foreign key (store_id) references branches(store_id),
    foreign key (customer_id) references customers(customer_id));

-- 6. Receipt Lines
create table receipt_lines (
    line_id varchar(30) primary key,
    transaction_id varchar(30),
    product_id varchar(30),
    quantity numeric(12,2),
    unit_price_kes numeric(12,2),
    discount_pct numeric(8,2),
    promo_id varchar(30),
    foreign key (transaction_id) references transactions(transaction_id),
    foreign key (product_id) references products(product_id),
    foreign key (promo_id) references promotions(promo_id));

-- 7. Inflation
create table inflation (
    month date primary key,
    inflation_12m_pct numeric(8,2),
    annual_avg_inflation_pct numeric(8,2));

-- 8. Holidays
create table holidays (
    date date primary key,
    holiday_name varchar(150));

-- 9. Sales (aggregated sales-line dataset)
create table sales (
    line_id varchar(30) primary key,
    transaction_id varchar(30),
    product_id varchar(30),
    quantity numeric(12,2),
    unit_price_kes numeric(12,2),
    discount_pct numeric(8,2),
    promo_id varchar(30),
    transaction_date date,
    year integer,
    month integer,
    week integer,
    day_name varchar(20),
    end_month BOOLEAN,
    store_id varchar(20),
    category varchar(100),
    revenue_kes numeric(14,2),
    week_start date,
    promo_indicator integer,
    is_holiday integer,
    month_start date,
    discount_level varchar(50),
    foreign key (transaction_id) references transactions(transaction_id),
    foreign key (product_id) references products(product_id),
    foreign key (promo_id) references promotions(promo_id),
    foreign key (store_id) references branches(store_id));

-- Import the cleaned CSV files into their respective PostgreSQL tables.
-- Files are located in Data/processed_data/.
/*=================================================================================================================================
DATA CHECKS
===================================================================================================================================*/
--Schema check: Tables and column with its data type

select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'retail_forecasting'
order by table_name, ordinal_position;

-- Confirming  data loaded fully:
select 'sales' as table_name, count(*) as row_count from sales
union all select 'receipt_lines',count(*) from receipt_lines
union all select 'transactions', count(*) from transactions
union all select 'branches', count(*) from branches
union all select 'products', count(*) from products
union all select 'customers', count(*) from customers
union all select 'inflation', count(*) from inflation
union all select 'holidays', count(*) from holidays;

/*================================================================================================================================
BUSINESS QUESTIONS
===================================================================================================================================
   Q1. How do revenue, units sold and receipt volumes vary across stores and product categories?
      
   Q2. How are promotions and discount levels associated with sales, and what happens to sales after promotions end? 
      (inflation, public holidays and month-end patterns are also covered here)
       
   Q3. What do customer purchasing patterns, cohorts and RFM segments reveal about customer activity and value?
       
 ================================================================================================================================
  1. STORE AND PRODUCT PERFORMANCE
  ================================================================================================================================*/

--1.1. Sales performance by store (Revenue, Units and Transactions)
select b.store_id, b.store_name, b.store_positioning, b.opening_date,
	sum(s.revenue_kes) as total_revenue,
   	sum(s.quantity) as total_units_sold, 
   	count(distinct s.transaction_id) as transaction_count
from sales s
join branches b
on s.store_id = b.store_id
where s.quantity > 0
group by b.store_id, b.store_name, b.store_positioning, b.opening_date
order by total_revenue desc;

-- 1.2. Revenue generated by product tier across stores
select b.store_name, b.store_positioning,
    sum(case when p.tier = 'Economy' then rl.quantity * rl.unit_price_kes *
        (1 - coalesce(rl.discount_pct, 0) / 100) else 0 end) as Economy_Revenue,
    sum(case when p.tier = 'Standard' then rl.quantity * rl.unit_price_kes *
        (1 - coalesce(rl.discount_pct, 0) / 100) else 0 end) as Standard_Revenue,
    sum(case when p.tier = 'Premium' then rl.quantity * rl.unit_price_kes *
        (1 - coalesce(rl.discount_pct, 0) / 100) else 0 end) as Premium_Revenue
from receipt_lines rl
join transactions t
    on rl.transaction_id = t.transaction_id
join branches b
    on t.store_id = b.store_id
join products p
    on rl.product_id = p.product_id
where rl.quantity > 0
group by b.store_positioning,  b.store_name 
order by b.store_positioning;

-- Finding: Standard products generate the highest revenue in all stores. Economy and Premium contributions vary by store.

--1.3). Average selling price by product tier and store
select b.store_name, b.store_positioning,
    round(sum(case when p.tier = 'Economy' then rl.quantity * rl.unit_price_kes * (1 - coalesce(rl.discount_pct, 0) / 100) else 0 end) /
        nullif(sum(case when p.tier = 'Economy' then rl.quantity else 0 end), 0), 2) as Economy_Avg_Price,
    round(sum(case when p.tier = 'Standard' then rl.quantity * rl.unit_price_kes * (1 - coalesce(rl.discount_pct, 0) / 100) else 0 end) /
        nullif(sum(case when p.tier = 'Standard' then rl.quantity else 0 end), 0), 2) as Standard_Avg_Price,
    round(sum(case when p.tier = 'Premium' then rl.quantity * rl.unit_price_kes *(1 - coalesce(rl.discount_pct, 0) / 100) else 0 end) /
        nullif(sum(case when p.tier = 'Premium' then rl.quantity else 0 end), 0), 2 ) as Premium_Avg_Price
from receipt_lines rl
join transactions t
    on rl.transaction_id = t.transaction_id
join branches b
    on t.store_id = b.store_id
join products p
    on rl.product_id = p.product_id
where rl.quantity > 0
group by b.store_name, b.store_positioning
order by b.store_positioning;

--1.4)Month over Month Revenue change per store
with monthly_sales as (
    select store_id, date_trunc('month', transaction_date)::date as month, sum(revenue_kes) as revenue
    from sales
    where quantity > 0
    group by store_id,date_trunc('month', transaction_date)),
revenue_changes as (
    select store_id, month, revenue, lag(revenue) over ( partition by store_id order by month) as previous_month_revenue
    from monthly_sales)       
    select b.store_name, r.month,
	   round(r.revenue, 2) as monthly_revenue,
	   round(r.previous_month_revenue, 2) as previous_month_revenue,
	   round((r.revenue - r.previous_month_revenue) /nullif(r.previous_month_revenue, 0) * 100, 2) as revenue_change_pct
    from revenue_changes r
join branches b
    on r.store_id = b.store_id
order by b.store_name, r.month;

-- 1.5.) Store contribution to sales within its store positioning
with store_sales as (
    select b.store_id, b.store_name,b.store_positioning,
        sum(s.revenue_kes) as total_revenue,
        sum(s.quantity) as total_units_sold,
        count(distinct s.transaction_id) as transaction_count
   from sales s
   join branches b    
   on s.store_id = b.store_id     
   where s.quantity > 0     
   group by b.store_id, b.store_name, b.store_positioning)
   select store_id, store_name, store_positioning,
    round(total_revenue / sum(total_revenue) over (partition by store_positioning) * 100, 2) as revenue_share_pct,
    round(total_units_sold / sum(total_units_sold) over ( partition by store_positioning ) * 100, 2) as units_share_pct,
    round(transaction_count * 100.0 / sum(transaction_count) over (partition by store_positioning ),2) as receipt_share_pct
    from store_sales    
    order by store_positioning, revenue_share_pct desc;   

--1.6. Revenue, units and receipts by product category
select p.category,sum(s.revenue_kes) as total_revenue,
       sum(s.quantity) as total_units_sold,
       count(distinct s.transaction_id) as transaction_count,
       round(100.0 * sum(s.revenue_kes) / sum(sum(s.revenue_kes)) over (), 2) as revenue_share_pct
from sales s
join products p 
on s.product_id = p.product_id
where s.quantity > 0
group by p.category
order by total_revenue desc;

--1.7. Returned products ranked by their value
select p.product_name, p.category,
    sum(abs(rl.quantity)) as units_returned,
    round(sum(abs(rl.quantity * rl.unit_price_kes * (1 - coalesce(rl.discount_pct, 0) / 100))), 2) as returned_value     
from receipt_lines rl
join products p
    on rl.product_id = p.product_id
where rl.quantity < 0
group by p.product_name, p.category
order by returned_value desc;

--1.8 Top 5 and bottom 5 products per store by revenue
with product_sales as (
    select  b.store_name,p.product_name, p.category,
	      sum(s.quantity) as units_sold,
	      sum(s.revenue_kes) as total_revenue
     from sales s    
    join branches b 
    on s.store_id = b.store_id
    join products p 
    on s.product_id = p.product_id
    where s.quantity > 0
    group by b.store_name, p.product_name, p.category),
ranked as (
    select *,row_number() over ( partition by store_name order by total_revenue desc, product_name) as top_rank,
        	row_number() over (partition by store_name order by total_revenue, product_name) as bottom_rank
    from product_sales)           
select store_name, product_name,category, total_revenue,
		case when top_rank <= 5 then 'Top 5' else 'Bottom 5' end as performance_group          
from ranked
where top_rank <= 5 or bottom_rank <= 5
order by store_name, total_revenue asc;

-- 1.9 Top 5 and bottom 5 products per store by units_sold(same logic as 1.8, but ranked on units_sold)
with product_sales as (
    select  b.store_name,p.product_name, p.category,
      sum(s.quantity) as units_sold,
      sum(s.revenue_kes) as total_revenue
     from sales s    
    join branches b 
    on s.store_id = b.store_id
    join products p 
    on s.product_id = p.product_id
    where s.quantity > 0
    group by b.store_name, p.product_name, p.category),
ranked as (
    select *,row_number() over ( partition by store_name order by units_sold desc, product_name) as top_rank,
        row_number() over (partition by store_name order by units_sold, product_name) as bottom_rank
    from product_sales)           
select store_name, product_name,category,units_sold,
		case when top_rank <= 5 then 'Top 5' else 'Bottom 5' end as performance_group             
from ranked
where top_rank <= 5 or bottom_rank <= 5
order by store_name, units_sold asc;

  /*==============================================================================================================================
  2. PROMOTIONS, INFLATION AND CALENDAR EFFECTS
  ================================================================================================================================*/
--2.1. Sales by discount level
select discount_level,
       count(distinct transaction_id) as transaction_count,
       sum(quantity) as units_sold,
       round(sum(revenue_kes), 2) as total_revenue,
       round(avg(revenue_kes), 2) as avg_line_revenue
from sales
where quantity > 0
group by discount_level
order by discount_level;

--2.2.  Promotional revenue share and month-on-month revenue change
with monthly_sales as (
    select
        date_trunc('month', transaction_date)::date as month,
        sum(revenue_kes) as total_revenue,
        sum(revenue_kes) filter (where discount_pct > 0) as promo_revenue
    from sales
    where quantity > 0
    group by 1)
select month, round(total_revenue, 2) as total_revenue, 
    round(100.0 * promo_revenue / nullif(total_revenue, 0), 2) as promo_revenue_share_pct,
    round(100.0 * (total_revenue - lag(total_revenue) over (order by month))
        / nullif(lag(total_revenue) over (order by month), 0), 2) as revenue_change_pct
    from monthly_sales
	order by month;    

--2.3. Inflation and monthly sales
select i.month, i.inflation_12m_pct,
 	count(distinct s.transaction_id) as transaction_count,
	sum(s.quantity) as units_sold,
	round(sum(s.revenue_kes), 2) as total_revenue,
	round(sum(s.revenue_kes) / count(distinct s.transaction_id), 2) as avg_revenue_per_receipt
from inflation i   
join sales s
on date_trunc('month', s.transaction_date) = i.month
where s.quantity > 0
group by i.month, i.inflation_12m_pct
order by i.month;

--2.4. Calendar effects: Public holidays and month-end
select case
	        when h.date is not null then 'Public Holiday'
	        when extract(day from s.transaction_date) >= extract(day from (date_trunc('month', s.transaction_date)
	             + interval '1 month' - interval '1 day')) - 4   then 'Month-End'
 			else 'Ordinary Day'
       end as calendar_period,
    count(distinct s.transaction_id) as transaction_count,
    sum(s.quantity) as units_sold,
    round(sum(s.revenue_kes), 2) as total_revenue,
    round(sum(s.revenue_kes) / count(distinct s.transaction_id), 2) as avg_revenue_per_receipt
from sales s
left join holidays h
on s.transaction_date::date = h.date
where s.quantity > 0
group by calendar_period
order by calendar_period;

 /*==============================================================================================================================
  3. CUSTOMERS
  ================================================================================================================================*/
-- 3.1. Customer distribution and sales contribution by county
select c.county,
    count(distinct c.customer_id) as registered_customers,
    count(distinct t.customer_id) as active_customers,
    count(distinct t.transaction_id) as transaction_count,
    round(coalesce(sum(t.basket_total_kes), 0), 2) as total_revenue
from customers c
left join transactions t
    on c.customer_id = t.customer_id
group by c.county
order by total_revenue desc;

--3.2. Customers and sales by registration store
select b.store_name, b.store_positioning,
    count(distinct c.customer_id) as registered_customers,
    count(distinct t.customer_id) as active_customers,
    count(distinct t.transaction_id) as transaction_count,
    round(coalesce(sum(t.basket_total_kes), 0), 2) as total_revenue
from customers c
join branches b
    on c.registration_store_id = b.store_id
left join transactions t
    on c.customer_id = t.customer_id
group by b.store_name, b.store_positioning
order by total_revenue desc;

 /*==============================================================================================================================
  RFM ANALYSIS
   R = Recency   (days since last purchase. The lower the better)
   F = Frequency (number of transactions)
   M = Monetary  (total spend)
   Each is scored 1-5 with NTILE(5).
  ================================================================================================================================*/
-- 3.3. RFM Values per customer
 select customer_id,
  (select max(transaction_date)::date from transactions) - max(transaction_date)::date as recency_days,
      count(transaction_id) as frequency,
      round(sum(basket_total_kes), 2) as monetary_value
from transactions
where customer_id is not null
group by customer_id
order by monetary_value desc;

--3.4. RFM Scores
with customer_rfm as (
    select customer_id,
       	(select max(transaction_date) from transactions) - max(transaction_date) as recency_days,
        count(transaction_id) as frequency,
       	sum(basket_total_kes) as monetary_value  
	from transactions
    where customer_id is not null
    group by customer_id)
select customer_id, recency_days, frequency,
    round(monetary_value, 2) as monetary_value,
    ntile(5) over (order by recency_days desc) as r_score,
    ntile(5) over (order by frequency) as f_score,
    ntile(5) over (order by monetary_value) as m_score
from customer_rfm;

--3.5. Customer segments and their value
with customer_rfm as (
    select customer_id,
        (select max(transaction_date) from transactions) - max(transaction_date) as recency_days,
		count(transaction_id) as frequency,sum(basket_total_kes) as monetary_value
    from transactions       
    where customer_id is not null
 	group by customer_id),
rfm_scores as (
    select customer_id, recency_days, frequency, monetary_value,
        ntile(5) over (order by recency_days desc) as r_score,
        ntile(5) over (order by frequency) as f_score,
        ntile(5) over (order by monetary_value) as m_score
    from customer_rfm),
customer_segments as (
    select customer_id, monetary_value,
        case
            when r_score >= 4 and f_score >= 4 and m_score >= 4 then 'Premium Customers'
			when f_score >= 4 then 'Loyal Customers'
            when m_score = 5 then 'Big Spenders'
			when r_score <= 2 then 'At Risk'
            else 'Other Customers' 
		end as customer_segment
     from rfm_scores)        
    select
   customer_segment,count(*) as customer_count,
    round(sum(monetary_value), 2) as total_revenue,
    round(avg(monetary_value), 2) as avg_customer_spend
from customer_segments
group by customer_segment
order by total_revenue desc;

-- 3.6. Customer cohorts by first purchase month. Cohort (the month a customer first bought). 
select
    date_trunc('month', first_purchase)::date as cohort_month,
    count(*) as new_customers,
    count(*) filter (where transaction_count > 1) as repeat_customers
from (
    select customer_id,min(transaction_date) as first_purchase,count(*) as transaction_count
  	from transactions
    where customer_id is not null
    group by customer_id) customers
group by cohort_month
order by cohort_month;

--3.7. Month to Month Customer Retention
--  retention share = customers active this month AND last month / customers active last month
with monthly_customers as (
    select distinct date_trunc('month', transaction_date)::date as month,customer_id  
    from transactions
    where customer_id is not null)
select c.month,
    count(distinct c.customer_id) as active_customers,
    count(distinct p.customer_id) as returning_customers,
   round(count(distinct p.customer_id) * 100.0 /
    nullif( (select count(*) from monthly_customers m where m.month = c.month - interval '1 month'), 0 ), 2) as retention_pct
from monthly_customers c
left join monthly_customers p
    on c.customer_id = p.customer_id
    and p.month = c.month - interval '1 month'
group by c.month
order by c.month;

--====================================================================VIEWS=========================================================================
-- 1. RFM scores and segments  |  from section 3 (RFM analysis)
create or replace view v_customer_rfm as
with customer_rfm as (
    select customer_id,
           (select max(transaction_date)::date from transactions) - max(transaction_date)::date as recency_days,          
           count(transaction_id) as frequency,
           sum(basket_total_kes) as monetary_value
    from transactions
    where customer_id is not null
    group by customer_id),
scored as (
    select customer_id, recency_days, frequency, monetary_value,
           ntile(5) over (order by recency_days desc) as r_score,
           ntile(5) over (order by frequency) as f_score,
           ntile(5) over (order by monetary_value) as m_score
    from customer_rfm)
select s.customer_id,c.county,c.registration_store_id, s.recency_days, s.frequency, s.monetary_value,
       s.r_score, s.f_score, s.m_score,
       case
           when s.r_score >= 4 and s.f_score >= 4 and s.m_score >= 4 then 'Premium_customers'
           when s.f_score >= 4 then 'Loyal Customers'
           when s.m_score = 5 then 'Big Spenders'
           when s.r_score <= 2 then 'At Risk'
           else 'Other Customers'
       end as customer_segment      
from scored s
left join customers c on c.customer_id = s.customer_id;

-- 2. Cohort retention from section 3 (customer cohorts)
create or replace view v_cohort_retention as
with first_purchase as (
    select customer_id,date_trunc('month', min(transaction_date))::date as cohort_month       
    from transactions
    where customer_id is not null
    group by customer_id),
cohort_sizes as (
    select cohort_month, count(*) as cohort_size
    from first_purchase
    group by cohort_month),
activity as (
    select distinct customer_id,date_trunc('month', transaction_date)::date as active_month         
    from transactions
    where customer_id is not null)
select f.cohort_month,
       (extract(year  from age(a.active_month, f.cohort_month)) * 12
      + extract(month from age(a.active_month, f.cohort_month)))::int as months_since_first,
       count(distinct a.customer_id) as active_customers,
       cs.cohort_size
from first_purchase f
join activity a  
on a.customer_id = f.customer_id
join cohort_sizes cs 
on cs.cohort_month = f.cohort_month
group by f.cohort_month, 2, cs.cohort_size;


-- 3. Month-to-month retention from customer retention
create or replace view v_monthly_retention as
with monthly_customers as (
    select distinct date_trunc('month', transaction_date)::date as month, customer_id        
    from transactions
    where customer_id is not null),
active as (
    select month, count(*) as active_customers
    from monthly_customers
    group by month),
returning_c as (
    select c.month, count(*) as returning_customers
    from monthly_customers c
    join monthly_customers p
      on p.customer_id = c.customer_id
     and p.month = (c.month - interval '1 month')::date
    group by c.month)
select a.month,
       a.active_customers,
       coalesce(r.returning_customers, 0) as returning_customers,
       lag(a.active_customers) over (order by a.month) as previous_month_active,
       100.0 * r.returning_customers/ nullif(lag(a.active_customers) over (order by a.month), 0) as retention_pct          
from active a
left join returning_c r 
on r.month = a.month;

--Querying to confirm views have been created successfully
select table_name from information_schema.views where table_schema = 'retail_forecasting';


































