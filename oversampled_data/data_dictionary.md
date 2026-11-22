# Data dictionary - oversampled files

Files in `oversampled_data/refresh1_2026-01` (January 2026) and `refresh2_2026-02` (February 2026). Same columns as the original source files; the loader accepts `.xlsx` and `.csv`. "Inherited" = value comes from a real historical sales row (pharmacy, lot, batch, medicine combination) that was sampled.


## 01_master_data
63 medicines; 4 re-priced per refresh

| Column | Type | Description | How generated |
|---|---|---|---|
| MedicineID | VARCHAR | Business key of the medicine | Copied from master |
| InternalSKU | VARCHAR | Internal stock-keeping unit code | Copied |
| GTIN14 | VARCHAR | GS1 14-digit trade item number (text, keeps leading zeros) | Copied |
| GenericName | VARCHAR | Generic (INN) name | Copied |
| FictionalBrandName | VARCHAR | Fictional brand name | Copied |
| DiseaseCategory | VARCHAR | Disease area the medicine treats | Copied |
| ICD10Category | VARCHAR | ICD-10 category code | Copied |
| ATCCode | VARCHAR | WHO ATC classification code | Copied |
| TherapeuticClass | VARCHAR | Therapeutic class | Copied |
| DosageForm | VARCHAR | Tablet, injection, etc. | Copied |
| Strength | VARCHAR | Dose strength | Copied |
| RouteOfAdministration | VARCHAR | Oral, intravenous, etc. | Copied |
| PackSize | INTEGER | Units per pack | Copied |
| BaseUnitOfMeasure | VARCHAR | Unit of measure of a pack | Copied |
| PrescriptionClass | VARCHAR | Prescription / OTC class | Copied |
| ControlledMedicineFlag | VARCHAR | Y/N controlled substance | Copied |
| ColdChainFlag | VARCHAR | Y/N needs cold-chain storage | Copied |
| StorageMinTempC | DOUBLE | Minimum storage temperature (C) | Copied |
| StorageMaxTempC | DOUBLE | Maximum storage temperature (C) | Copied |
| MaxHumidityPct | DOUBLE | Maximum allowed humidity (%) | Copied |
| ShelfLifeMonths | INTEGER | Shelf life in months | Copied |
| MinimumRemainingShelfLifeDays | INTEGER | Minimum shelf life left when shipped to a customer | Copied |
| PrimarySupplierID | VARCHAR | Main supplier | Copied |
| PrimaryPlantID | VARCHAR | Main manufacturing plant | Copied |
| ManufacturingLeadTimeDays | INTEGER | Production lead time | Copied |
| StandardBatchSizePacks | INTEGER | Standard production batch size (packs) | Copied |
| SafetyStockDays | INTEGER | Safety stock in days of demand | Copied |
| ReorderReviewCycleDays | INTEGER | Days between replenishment reviews | Copied |
| UnitManufacturingCostUSD | DOUBLE | Manufacturing cost per pack (USD) | Copied; for the 4 re-priced medicines +2% to +5% |
| WholesalePriceUSD | DOUBLE | Wholesale price per pack (USD) | Copied; for the 4 re-priced medicines +4% to +10% (creates SCD2 history) |
| RecommendedRetailPriceUSD | DOUBLE | Recommended retail price per pack (USD) | Copied; re-priced medicines follow the wholesale change |
| ProductStatus | VARCHAR | Active / Discontinued | Copied |
| EffectiveFromDate | DATE | Date this version of the record is valid from | First day of the refresh month for re-priced medicines |
| SourceSystem | VARCHAR | Originating system | Constant |

## 05_pharmacy_sales_data
Grain: one sales transaction; 16,677 rows (Jan), 15,064 rows (Feb)

| Column | Type | Description | How generated |
|---|---|---|---|
| SalesTransactionID | VARCHAR | Unique sales transaction id (primary key) | Sequence continuing SALE-000500001 |
| SalesDate | DATE | Date of sale | Uniform random day inside the refresh month; monthly volume = projected annual rows / 365 x days in month |
| SalesTimestampUTC | TIMESTAMP | Exact UTC time of sale | Date = SalesDate; time of day inherited from the sampled row |
| SalesChannel | VARCHAR | Physical Pharmacy or E-commerce | Inherited from the sampled historical row |
| PharmacyID | VARCHAR | Pharmacy identifier | Inherited from the sampled combination |
| PharmacyGLN | VARCHAR | Pharmacy GS1 location number | Inherited |
| PharmacyName | VARCHAR | Pharmacy name | Inherited |
| PharmacyType | VARCHAR | Chain / Independent / Hospital Pharmacy | Inherited |
| HospitalID | VARCHAR | Hospital served (hospital pharmacies only) | Inherited |
| PharmacyCity | VARCHAR | City | Inherited |
| PharmacyState | VARCHAR | State | Inherited |
| CountryCode | VARCHAR | Country code | Inherited |
| PharmacyOrderID | VARCHAR | Replenishment order that supplied the stock | Inherited |
| PharmacyDeliveryID | VARCHAR | Replenishment delivery id | Inherited |
| PharmacyDeliveryDate | DATE | Date stock was delivered to the pharmacy | Inherited |
| DeliveryQuantityPacks | INTEGER | Quantity of the delivery (repeats on many sales) | Inherited |
| DeliveryOTIFFlag | VARCHAR | Delivery on time in full (Y/N) | Inherited |
| WarehouseLotID | VARCHAR | Warehouse lot the stock came from | Inherited from sampled combination (real lot) |
| SourceWarehouseID | VARCHAR | Warehouse that supplied the lot | Inherited |
| ProductionBatchID | VARCHAR | Production batch of the medicine | Inherited from sampled combination |
| MedicineID | VARCHAR | Business key of the medicine | Copied from master |
| GTIN14 | VARCHAR | GS1 14-digit trade item number (text, keeps leading zeros) | Copied |
| DiseaseCategory | VARCHAR | Disease area the medicine treats | Copied |
| GenericName | VARCHAR | Generic (INN) name | Copied |
| BatchExpiryDate | DATE | Expiry date of the batch | Inherited; only batches expiring at least 30 days after the month start are sampled |
| DaysToExpiryAtSale | INTEGER | Days between sale and batch expiry | BatchExpiryDate - SalesDate |
| QuantitySoldPacks | INTEGER | Packs sold in the transaction | Inherited from the sampled row |
| UnitRetailPriceUSD | DOUBLE | Price per pack at sale (USD) | Current recommended retail price from the master (includes the refresh price changes) |
| GrossSalesAmountUSD | DOUBLE | Quantity x unit price | Formula |
| DiscountAmountUSD | DOUBLE | Discount given | Gross x median discount % of that promotion code in the sampling pool (last 180 days) |
| NetSalesAmountUSD | DOUBLE | Gross - discount | Formula |
| SalesTaxUSD | DOUBLE | Sales tax | Net x median tax rate observed in the sampling pool (0.06) |
| CostOfGoodsSoldUSD | DOUBLE | Cost of goods sold | Quantity x wholesale price (observed in history) |
| GrossMarginUSD | DOUBLE | Net sales - COGS | Formula |
| PromotionCode | VARCHAR | Promotion applied (blank = none) | Inherited share of promoted sales |
| PrescriptionRequiredFlag | VARCHAR | Y/N prescription needed | Inherited |
| PrescriptionID | VARCHAR | Prescription reference | RX- sequence matching SalesTransactionID when a prescription is required |
| CustomerSegment | VARCHAR | Customer segment | Inherited |
| PayerType | VARCHAR | Who pays (government, private, self-pay...) | Inherited |
| PaymentMethod | VARCHAR | Card, cash, insurance... | Inherited |
| EcommerceDeliveryStatus | VARCHAR | Delivery status for online orders | Inherited |
| ReturnFlag | VARCHAR | Y/N sale was returned | Inherited from the sampled row (keeps the historical return rate) |
| ReturnedQuantityPacks | INTEGER | Packs returned | Inherited |
| SaleStatus | VARCHAR | Completed / Returned etc. | Inherited |
| SourceSystem | VARCHAR | Originating system | Constant |

## 06_hospital_demand_data
Grain: hospital x medicine x month; 756 rows per month

| Column | Type | Description | How generated |
|---|---|---|---|
| HospitalDemandRecordID | VARCHAR | Unique hospital-medicine-month id (primary key) | Sequence continuing HDEM-00027217 |
| DemandMonth | DATE | First day of the demand month | Refresh month |
| HospitalID | VARCHAR | Hospital served (hospital pharmacies only) | Inherited |
| HospitalGLN | VARCHAR | Hospital GS1 location number | Copied |
| HospitalName | VARCHAR | Hospital name | Copied |
| HospitalType | VARCHAR | Hospital type | Copied |
| HospitalPharmacyID | VARCHAR | Hospital pharmacy id (link to sales) | Copied |
| City | VARCHAR | Hospital city | Copied |
| State | VARCHAR | Hospital state | Copied |
| CountryCode | VARCHAR | Country code | Inherited |
| LicensedBeds | INTEGER | Licensed beds | Copied |
| ICUBeds | INTEGER | ICU beds | Copied |
| AverageOccupancyRatePct | DOUBLE | Average bed occupancy (%) | Copied from the same hospital last year |
| TraumaLevel | VARCHAR | Trauma centre level | Copied |
| CatchmentPopulation | BIGINT | Population served | Copied |
| MedicineID | VARCHAR | Business key of the medicine | Copied from master |
| GTIN14 | VARCHAR | GS1 14-digit trade item number (text, keeps leading zeros) | Copied |
| GenericName | VARCHAR | Generic (INN) name | Copied |
| DiseaseCategory | VARCHAR | Disease area the medicine treats | Copied |
| ICD10Category | VARCHAR | ICD-10 category code | Copied |
| EstimatedDiseaseCases | INTEGER | Estimated disease cases in the catchment | Same month last year x one growth factor per hospital and disease (about 1.02) |
| DiseaseRelatedAdmissions | INTEGER | Admissions related to the disease | Same month last year x the same hospital-disease factor |
| OutpatientEncounters | INTEGER | Outpatient visits | Same month last year x the same hospital-disease factor |
| ForecastDemandPacks | INTEGER | Forecast demand (packs) | Same month last year x growth (last year / year before, clipped 0.95-1.12) x noise 3% |
| RequestedQuantityPacks | INTEGER | Quantity requested by the hospital | Forecast x last year request/forecast ratio; never below forecast |
| ApprovedQuantityPacks | INTEGER | Quantity approved | Requested x last year approval ratio; capped at requested |
| ReceivedQuantityPacks | INTEGER | Quantity received | Approved x last year receipt ratio; capped at approved |
| EmergencyRequestQuantityPacks | INTEGER | Emergency requests | Last year value x noise 20% |
| OpeningStockPacks | INTEGER | Stock at month start | Previous month closing stock (chained) |
| DispensedQuantityPacks | INTEGER | Packs dispensed to patients | Consumed x last year dispensed/consumed ratio, minus any shortfall |
| ConsumedQuantityPacks | INTEGER | Packs consumed | Forecast x last year consumed/forecast ratio x noise 3% |
| WastageQuantityPacks | INTEGER | Packs wasted (expiry, damage) | 1% of rows receive 1-3 packs, otherwise 0 |
| ClosingStockPacks | INTEGER | Stock at month end | Opening + received - dispensed - wastage (identity found in the history) |
| UnfulfilledDemandPacks | INTEGER | Demand that could not be met | Shortfall = max(0, dispensed + wastage - (opening + received)) |
| StockoutDays | INTEGER | Days with stock-out | Derived from the shortfall (max 10) |
| ServiceLevelPct | DOUBLE | Share of demand fulfilled (%) | 100 x (1 - unfulfilled / requested) |
| MedicationRequestStatus | VARCHAR | Request status | Partially fulfilled when unfulfilled > 0, else Completed |
| FormularyStatus | VARCHAR | Formulary status | Copied from the same hospital-medicine last year |
| AverageLeadTimeDays | INTEGER | Average replenishment lead time (days) | Last year value +/- 1 day |
| DemandTrendIndex | DOUBLE | Demand index vs baseline | Last year value x noise 1% |
| SourceSystem | VARCHAR | Originating system | Constant |
