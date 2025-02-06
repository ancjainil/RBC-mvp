# Geographic Velocity Anomaly Patterns

## Overview
Geographic velocity anomalies occur when a card or account is used at two geographically distant locations within a time window that makes physical travel between them impossible or highly improbable.

This pattern is one of the oldest and most reliable fraud signals in the industry. It indicates either:
1. A second fraudulent card (counterfeit or stolen) being used simultaneously with the legitimate card
2. Card-not-present fraud where the physical card remains with the legitimate holder but credentials are used remotely
3. A compromised account being accessed from a different location than the cardholder

## Distance-Time Thresholds for Canada

| Time Window | Maximum Legitimate Distance |
|---|---|
| < 15 minutes | 25 km (same metropolitan area) |
| 15–30 minutes | 50 km (adjacent cities) |
| 30–60 minutes | 120 km (highway driving) |
| 1–2 hours | 300 km (driving to adjacent city) |
| 2–4 hours | 800 km (domestic flight + transit) |
| > 4 hours | Any (international travel possible) |

**Critical threshold**: Any implied travel speed exceeding **900 km/h** between two point-of-sale transactions is physically impossible without commercial aviation. Speeds > 300 km/h are highly suspicious for POS transactions.

## Common Canadian City-Pair Scenarios

High-risk impossible-travel pairs (< 1 hour separation):
- **Toronto ↔ Vancouver**: 4,400 km — minimum 5h flight
- **Toronto ↔ Calgary**: 3,400 km — minimum 4h flight
- **Montreal ↔ Edmonton**: 3,600 km — minimum 4.5h flight
- **Toronto ↔ Halifax**: 1,800 km — minimum 2.5h flight
- **Vancouver ↔ Winnipeg**: 2,400 km — minimum 3h flight

## Risk Escalation Rules

### Immediate CRITICAL Risk
- Two POS transactions in different Canadian cities separated by < 30 minutes
- Any international POS transaction while a domestic POS transaction was processed within 60 minutes, with implied speed > 900 km/h
- Toronto POS + Vancouver POS within 2 hours

### High Risk (investigate within 1 hour)
- Implied speed 300–900 km/h between POS transactions
- Online transaction from an IP geolocation > 500 km from the customer's registered address, combined with a same-day POS transaction at the registered address
- International IP combined with a domestic POS within 4 hours

### Medium Risk (monitor)
- First transaction in a city > 200 km from the customer's home city with no prior travel history
- IP geolocation inconsistency with billing address by > 100 km for online transactions

## Handling International Travel
Customers who have pre-notified the bank of travel should have their geo-velocity thresholds adjusted. Key considerations:
- Check for travel notification records before flagging
- Consider airport locations — YYZ (Toronto Pearson) is in Mississauga, 30km from downtown; a POS at the airport + downtown Toronto within 45 minutes is normal
- Connecting flights create legitimate multi-city patterns: the full travel duration should be considered, not just the gap between transactions

## Card-Present vs Card-Not-Present
- **Two POS transactions** in distant cities: Almost certainly card cloning or use of a stolen physical card
- **POS + CNP from distant IP**: More ambiguous — customer could be shopping online while traveling
- **Two CNP transactions from different IPs**: Less decisive; VPN use could explain geolocation discrepancy

## Investigation Steps
1. Attempt to contact the cardholder on file immediately
2. Check travel notification records
3. Identify which transaction is more likely legitimate (typically the one closer to the home address)
4. Temporarily suspend the card and request re-issuance if travel velocity confirmed
5. File fraud report and initiate chargeback process for the fraudulent transaction
6. Review all transactions from the suspected fraudulent location

## References
- Visa Fraud Monitoring Program guidelines
- Mastercard International Security Rules and Procedures
- Payments Canada: Card Fraud Detection Best Practices 2023
