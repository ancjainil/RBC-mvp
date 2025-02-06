# Account Takeover (ATO) Fraud Patterns

## Overview
Account takeover occurs when a fraudster gains unauthorized access to a legitimate customer's banking or payment account and uses it to conduct fraudulent transactions. ATO is distinct from CNP fraud because the fraudster controls the entire account, not just the card credentials.

In Canada, ATO incidents increased **42% year-over-year in 2023**, driven by:
- Large-scale data breaches exposing username/password combinations
- SIM-swapping attacks bypassing SMS-based two-factor authentication
- Social engineering / vishing attacks targeting bank IVR systems
- Malware (RATs, keyloggers) targeting personal computers and mobile devices

## Behavioural Signatures of ATO

### Immediate Post-Compromise Indicators (0–4 hours)
- Password or security question change followed within minutes by a large transaction
- New payee added to bill pay / e-transfer list immediately followed by a transfer
- Contact information changed (email, phone number, mailing address) before transactions
- Multiple failed login attempts preceding a successful login from a new IP/device
- Login from a country or city never previously used by the account holder

### Spending Pattern Disruption
- **Complete category shift**: Customer who exclusively shops at Loblaws/Tim Hortons suddenly makes transactions at electronics stores and wire transfer services
- Transactions occurring during hours the customer has never previously transacted (e.g., 2:00–5:00 AM on weekdays)
- Simultaneous transactions in geographically distant locations (card cloning combined with ATO)
- Sudden high-value cash advances at ATMs the customer has never used
- Immediate spend-to-limit behavior: multiple transactions bringing the account to its credit limit within hours

### Channel and Device Anomalies
- Account accessed via a new device that has not been registered or seen before
- Mobile app login from an emulator or rooted/jailbroken device
- Browser fingerprint changes (different OS, browser, language settings) for online banking
- IP address associated with proxy services, VPNs, or residential proxy networks
- Multiple accounts accessed from the same device within a short window (credential stuffing at scale)

## SIM-Swap Indicators
SIM-swap attacks are particularly dangerous because they allow the fraudster to intercept SMS-based OTPs:
- Phone number recently ported to a different carrier
- Customer reports receiving no SMS messages for an extended period
- Multiple authentication attempts where the OTP was consumed but the customer denies initiating the login
- New SIM card issued within 24 hours of suspicious transactions

## Social Engineering / Vishing
- Customer called a number purporting to be the bank's fraud department
- Customer was instructed to provide one-time passwords to "verify their identity"
- Large e-transfer sent to an unknown payee shortly after a customer service call
- Customer added as a co-signer or authorized user of an account they do not recognize

## Canadian-Specific Context
- **Interac e-Transfer fraud**: Canada's near-universal use of Interac e-Transfer makes it a primary target. Fraudsters who gain account access immediately send e-Transfers to money mules. Key indicator: e-Transfer sent to a new, unrecognized email address within 30 minutes of first login from a new device.
- **CRA (Canada Revenue Agency) impersonation**: Fraudsters impersonate CRA agents, convincing victims to transfer funds or reveal credentials. Resulting transactions often involve e-Transfers or cryptocurrency purchases.
- **CERB/CRB fraud follow-on**: Some accounts compromised during pandemic benefit fraud remain dormant and are activated later for ATO attacks.

## Detection Framework
1. **Login anomaly scoring**: Device, IP, geolocation, time-of-day, and browser fingerprint compared against the account's session history
2. **First-session transaction risk**: Any transaction within 15 minutes of the first login from a new device warrants elevated scrutiny
3. **Payee velocity**: New payee + immediate transfer = high-risk signal
4. **Spending pattern ML baseline**: Autoencoder or isolation forest model trained on 90-day spending history; sharp reconstruction error = anomaly

## Recommended Response
- Immediately freeze outgoing transfers pending customer verification
- Require out-of-band authentication (phone call, not SMS) for high-value changes
- Flag account for manual review within 1 business day
- File Suspicious Transaction Report (STR) with FINTRAC if transaction > $10,000 or structuring suspected

## References
- RCMP Financial Crimes Division: Account Takeover Advisory 2023
- Canadian Anti-Fraud Centre (CAFC): Annual Report 2023
- FINTRAC Guideline 2: Suspicious Transaction Reporting
