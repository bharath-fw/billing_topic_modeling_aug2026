# Comprehensive Brightspeed Billing Taxonomy

Canonical tags are stable machine output labels. Categories remain macro. Subcategories represent specific customer billing asks.

## Bill Understanding and Balance

- BILL_GENERAL_BILLING_QUESTION: General billing question
  - General help understanding billing when no more specific issue is stated
  - Evidence: Observed
- BILL_CURRENT_ACCOUNT_BALANCE: Current account balance
  - Customer wants the current amount owed on the account
  - Evidence: Observed
- BILL_PAYMENT_DUE_DATE: Payment due date
  - Customer wants to know when payment is due
  - Evidence: Observed
- BILL_BILL_AMOUNT_LINE_ITEM_EXPLANATION: Bill amount or line item explanation
  - Customer wants an explanation of an amount, line item, or calculation without clearly alleging an error
  - Evidence: Observed
- BILL_FIRST_BILL_EXPLANATION: First bill explanation
  - Customer needs help understanding the first bill after new service or activation
  - Evidence: Coverage Expansion
- BILL_PRORATED_BILL_EXPLANATION: Prorated bill explanation
  - Customer asks about partial month, prorated, or midcycle billing
  - Evidence: Coverage Expansion
- BILL_BILLING_CYCLE_STATEMENT_DATE: Billing cycle or statement date
  - Customer asks when the billing period starts, ends, or when the statement generates
  - Evidence: Coverage Expansion
- BILL_UPCOMING_ESTIMATED_BILL_AMOUNT: Upcoming or estimated bill amount
  - Customer asks what a future or next bill is expected to be
  - Evidence: Coverage Expansion

## Rates Discounts and Recurring Charges

- RATE_BILL_HIGHER_THAN_EXPECTED: Bill higher than expected
  - Customer reports a higher total bill but has not isolated one specific erroneous charge
  - Evidence: Observed
- RATE_PRICE_RATE_INCREASE: Price or rate increase
  - Customer asks about an increase in recurring service price or plan rate
  - Evidence: Observed
- RATE_PROMOTIONAL_RATE_EXPIRED: Promotional rate expired
  - Customer says a promotional or introductory rate ended and the bill increased
  - Evidence: Coverage Expansion
- RATE_MISSING_INCORRECT_DISCOUNT: Missing or incorrect discount
  - Customer expects a recurring discount that is absent or wrong
  - Evidence: Coverage Expansion
- RATE_LOWER_PRICE_DISCOUNT_REQUEST: Lower price or discount request
  - Customer wants a lower monthly price, discount, or more affordable plan
  - Evidence: Observed
- RATE_PLAN_PACKAGE_PRICE_INQUIRY: Plan or package price inquiry
  - Customer asks what a plan, package, or service tier costs
  - Evidence: Observed
- RATE_RECURRING_CHARGE_INQUIRY: Recurring charge inquiry
  - Customer asks about a recurring monthly charge without clearly disputing it
  - Evidence: Observed
- RATE_ADD_FEATURE_RECURRING_CHARGE: Add on or feature recurring charge
  - Customer asks about a recurring charge for an added feature, service, or optional product
  - Evidence: Coverage Expansion

## Billing Errors Fees and Taxes

- ERR_INCORRECT_UNEXPECTED_CHARGE: Incorrect or unexpected charge
  - Customer states that a billed charge is wrong or should not be present
  - Evidence: Observed
- ERR_DUPLICATE_CHARGE: Duplicate charge
  - Customer says the same charge appears more than once
  - Evidence: Coverage Expansion
- ERR_UNAUTHORIZED_BILLING_CHARGE: Unauthorized billing charge
  - Customer says a charge was not authorized or was not requested
  - Evidence: Coverage Expansion
- ERR_BILLING_AFTER_CANCELLATION_DISCONNECT: Billing after cancellation or disconnect
  - Customer disputes charges continuing after cancellation, disconnect, closure, or removal
  - Evidence: Observed
- ERR_LATE_FEE_DISPUTE: Late fee dispute
  - Customer says a late fee was assessed incorrectly
  - Evidence: Observed
- ERR_LATE_FEE_WAIVER_AVOIDANCE: Late fee waiver or avoidance
  - Customer asks to waive, remove, or avoid a plausible late fee
  - Evidence: Observed
- ERR_RETURNED_PAYMENT_INSUFFICIENT_FUNDS_FEE: Returned payment or insufficient funds fee
  - Customer asks about a fee caused by a returned or insufficient funds payment
  - Evidence: Coverage Expansion
- ERR_RECONNECTION_RESTORATION_FEE: Reconnection or restoration fee
  - Customer asks about a fee charged to reconnect or restore service
  - Evidence: Coverage Expansion
- ERR_TAX_REGULATORY_FEE_INQUIRY: Tax or regulatory fee inquiry
  - Customer asks about taxes, government fees, or regulatory charges
  - Evidence: Observed
- ERR_TAX_RECOVERY_SURCHARGE: Tax recovery surcharge
  - Customer specifically asks about or disputes the tax recovery surcharge
  - Evidence: Observed
- ERR_INCORRECT_TAX_FEE_AMOUNT: Incorrect tax or fee amount
  - Customer believes a tax, surcharge, or mandatory fee amount is wrong
  - Evidence: Coverage Expansion

## Payments and Payment Posting

- PAY_MAKE_ONE_TIME_PAYMENT: Make a one time payment
  - Customer wants to make a single payment outside AutoPay
  - Evidence: Observed
- PAY_GENERAL_PAYMENT_QUESTION: General payment question
  - Customer has a payment question without a more specific payment issue
  - Evidence: Observed
- PAY_ONLINE_APP_PAYMENT_ISSUE: Online or app payment issue
  - Customer cannot complete a payment through the website, portal, or app
  - Evidence: Observed
- PAY_PAYMENT_DECLINED_FAILED: Payment declined or failed
  - A non AutoPay payment attempt was declined or failed
  - Evidence: Coverage Expansion
- PAY_PAYMENT_NOT_POSTED: Payment not posted
  - Customer says a completed payment is missing from the account or balance
  - Evidence: Observed
- PAY_PAYMENT_APPLIED_WRONG_ACCOUNT: Payment applied to wrong account
  - Customer says a completed payment was credited to the wrong account
  - Evidence: Observed
- PAY_PAYMENT_CONFIRMATION_RECEIPT: Payment confirmation or receipt
  - Customer wants confirmation that a payment was received or a receipt or confirmation number
  - Evidence: Observed
- PAY_PAYMENT_REVERSED_RETURNED: Payment reversed or returned
  - Customer asks why a previously completed payment was reversed, returned, or removed
  - Evidence: Coverage Expansion
- PAY_DUPLICATE_PAYMENT: Duplicate payment
  - Customer reports that the same payment was made or withdrawn more than once
  - Evidence: Coverage Expansion
- PAY_PARTIAL_PAYMENT: Partial payment
  - Customer asks whether or how to make a payment for less than the total amount due
  - Evidence: Coverage Expansion
- PAY_CHECK_MAILED_PAYMENT_STATUS: Check or mailed payment status
  - Customer asks about a check, money order, or mailed payment that is pending or missing
  - Evidence: Observed
- PAY_PAYMENT_HISTORY_TRANSACTION_DETAILS: Payment history or transaction details
  - Customer wants details about prior payments, dates, amounts, or methods
  - Evidence: Observed

## AutoPay and Payment Methods

- AUTO_AUTOPAY_GENERAL_INQUIRY: AutoPay general inquiry
  - Customer asks a general question about automatic payments
  - Evidence: Observed
- AUTO_ENROLL_IN_AUTOPAY: Enroll in AutoPay
  - Customer wants to start automatic payments
  - Evidence: Observed
- AUTO_CONFIRM_AUTOPAY_ENROLLMENT: Confirm AutoPay enrollment
  - Customer wants to verify whether AutoPay is active
  - Evidence: Observed
- AUTO_REMOVE_AUTOPAY: Remove AutoPay
  - Customer wants to stop or disable automatic payments
  - Evidence: Observed
- AUTO_AUTOPAY_PAYMENT_FAILURE: AutoPay payment failure
  - An expected automatic payment did not process
  - Evidence: Observed
- AUTO_AUTOPAY_CHARGED_WRONG_AMOUNT: AutoPay charged wrong amount
  - Customer says AutoPay withdrew an incorrect amount
  - Evidence: Coverage Expansion
- AUTO_DUPLICATE_AUTOPAY_WITHDRAWAL: Duplicate AutoPay withdrawal
  - Customer says AutoPay withdrew more than once for the same bill
  - Evidence: Coverage Expansion
- AUTO_CHANGE_AUTOPAY_PAYMENT_DATE: Change AutoPay payment date
  - Customer wants to change when an automatic payment is withdrawn
  - Evidence: Coverage Expansion
- AUTO_UPDATE_REPLACE_PAYMENT_METHOD: Update or replace payment method
  - Customer wants to add, change, or replace a card or bank account
  - Evidence: Observed
- AUTO_UPDATE_AUTOPAY_PAYMENT_METHOD: Update AutoPay payment method
  - Customer specifically wants to change the card or bank account used for AutoPay
  - Evidence: Observed
- AUTO_COMPROMISED_CARD_BANK_ACCOUNT: Compromised card or bank account
  - Customer needs to replace a payment method because it is compromised or closed
  - Evidence: Observed

## Payment Assistance Past Due and Collections

- DUE_PAYMENT_ARRANGEMENT_GENERAL_INQUIRY: Payment arrangement general inquiry
  - Customer asks about payment plans or arrangements
  - Evidence: Observed
- DUE_SET_UP_PAYMENT_ARRANGEMENT: Set up payment arrangement
  - Customer wants to establish a payment arrangement
  - Evidence: Observed
- DUE_EXTEND_DUE_DATE_REQUEST_MORE_TIME: Extend due date or request more time
  - Customer asks for additional time to pay or a due date extension
  - Evidence: Observed
- DUE_PAYMENT_ARRANGEMENT_SYSTEM_ELIGIBILITY_ISSUE: Payment arrangement system or eligibility issue
  - Customer cannot create or manage an arrangement because of a system or eligibility problem
  - Evidence: Observed
- DUE_MISSED_BROKEN_PAYMENT_ARRANGEMENT: Missed or broken payment arrangement
  - Customer has missed a promised payment or an existing arrangement is no longer valid
  - Evidence: Coverage Expansion
- DUE_FINANCIAL_HARDSHIP_PAYMENT_ASSISTANCE: Financial hardship or payment assistance
  - Customer requests hardship support or billing assistance because they cannot afford the bill
  - Evidence: Coverage Expansion
- DUE_PAST_DUE_BALANCE_NONPAYMENT: Past due balance or nonpayment
  - Customer is calling about an overdue or delinquent balance
  - Evidence: Observed
- DUE_SERVICE_SUSPENDED_DISCONNECTED_NONPAYMENT: Service suspended or disconnected for nonpayment
  - Customer reports service suspension or disconnect caused by unpaid billing
  - Evidence: Observed
- DUE_RESTORE_SERVICE_AFTER_PAYMENT: Restore service after payment
  - Customer has paid or plans to pay and wants service restored
  - Evidence: Observed
- DUE_COLLECTIONS_NOTICE_AGENCY_INQUIRY: Collections notice or agency inquiry
  - Customer asks about debt collection activity or a collection agency
  - Evidence: Observed
- DUE_CREDIT_REPORTING_CREDIT_SCORE_CONCERN: Credit reporting or credit score concern
  - Customer is concerned that billing or collections affected credit reporting
  - Evidence: Observed
- DUE_PAID_DEBT_STILL_IN_COLLECTIONS: Paid debt still in collections
  - Customer says a debt was paid but collections or credit reporting still shows it outstanding
  - Evidence: Coverage Expansion

## Credits Refunds and Adjustments

- CRD_GENERAL_CREDIT_REQUEST: General credit request
  - Customer asks for a bill or account credit without a more specific reason
  - Evidence: Observed
- CRD_GENERAL_REFUND_REQUEST: General refund request
  - Customer asks for money to be returned without a more specific refund issue
  - Evidence: Observed
- CRD_OUTAGE_CREDIT_BILL_ADJUSTMENT: Outage credit or bill adjustment
  - Customer requests a credit because service was unavailable or impaired
  - Evidence: Observed
- CRD_SERVICE_QUALITY_CREDIT: Service quality credit
  - Customer requests a credit for poor, slow, or unreliable service rather than a total outage
  - Evidence: Coverage Expansion
- CRD_MISSING_CREDIT_ADJUSTMENT: Missing credit or adjustment
  - Customer was promised or expects a credit that is not reflected on the account
  - Evidence: Coverage Expansion
- CRD_REFUND_NOT_RECEIVED_REFUND_STATUS: Refund not received or refund status
  - Customer expects a refund and wants its status because it has not arrived or posted
  - Evidence: Observed
- CRD_REFUND_METHOD_TIMING_INQUIRY: Refund method or timing inquiry
  - Customer asks how or when a refund will be issued
  - Evidence: Coverage Expansion
- CRD_OVERPAYMENT_REFUND: Overpayment refund
  - Customer wants a refund of money paid above the amount owed
  - Evidence: Coverage Expansion
- CRD_DEPOSIT_REFUND: Deposit refund
  - Customer asks about return of a security or service deposit
  - Evidence: Coverage Expansion

## Billing Delivery Account and Preferences

- ACCT_BILL_COPY_STATEMENT_REQUEST: Bill copy or statement request
  - Customer needs a copy of a bill or statement
  - Evidence: Observed
- ACCT_BILL_NOT_RECEIVED: Bill not received
  - Customer says an expected bill or statement was not received
  - Evidence: Coverage Expansion
- ACCT_PAPERLESS_BILLING_GENERAL_INQUIRY: Paperless billing general inquiry
  - Customer asks about electronic or paperless billing
  - Evidence: Observed
- ACCT_ENROLL_IN_PAPERLESS_BILLING: Enroll in paperless billing
  - Customer wants to stop paper statements and receive bills electronically
  - Evidence: Observed
- ACCT_SWITCH_PAPER_BILLING: Switch to paper billing
  - Customer wants printed statements instead of paperless billing
  - Evidence: Observed
- ACCT_BILLING_EMAIL_NOTIFICATION_ISSUE: Billing email or notification issue
  - Customer is not receiving billing emails or payment notifications
  - Evidence: Coverage Expansion
- ACCT_ONLINE_ACCOUNT_ACCESS_VERIFICATION: Online account access or verification
  - Customer cannot access or verify the online account needed for billing
  - Evidence: Observed
- ACCT_UPDATE_BILLING_ADDRESS: Update billing address
  - Customer wants to change the billing or mailing address
  - Evidence: Observed
- ACCT_UPDATE_BILLING_CONTACT_INFORMATION: Update billing contact information
  - Customer wants to change billing email, phone, or contact information
  - Evidence: Coverage Expansion

## Promotions Rewards and Gift Cards

- PROMO_GENERAL_REWARD_INQUIRY: General reward inquiry
  - Customer asks a general question about a reward or incentive
  - Evidence: Observed
- PROMO_PROMOTIONAL_GIFT_CARD_NOT_RECEIVED: Promotional gift card not received
  - Customer was promised a promotional gift card but has not received it
  - Evidence: Observed
- PROMO_PROMOTIONAL_GIFT_CARD_STATUS: Promotional gift card status
  - Customer asks for the status of a promotional gift card
  - Evidence: Observed
- PROMO_GIFT_CARD_AMOUNT_VALUE_INQUIRY: Gift card amount or value inquiry
  - Customer asks how much a reward or promotional gift card should be worth
  - Evidence: Coverage Expansion
- PROMO_PROMOTION_REWARD_ELIGIBILITY: Promotion or reward eligibility
  - Customer asks whether they qualify for a billing promotion, reward, or incentive
  - Evidence: Coverage Expansion
- PROMO_PROMOTION_TERMS_FULFILLMENT_TIMING: Promotion terms or fulfillment timing
  - Customer asks about requirements or timing for receiving a promotion or reward
  - Evidence: Coverage Expansion

## Service Changes Equipment and Final Billing

- SVC_FINAL_BILL_AFTER_CANCELLATION: Final bill after cancellation
  - Customer asks about an expected closing or final bill after service ends
  - Evidence: Observed
- SVC_CANCEL_DISCONNECT_SERVICE_WITH_BILLING_IMPACT: Cancel or disconnect service with billing impact
  - Customer wants to cancel or disconnect and is asking about charges, balance, or final billing
  - Evidence: Observed
- SVC_REMOVE_SERVICE_CHARGE: Remove service or charge
  - Customer wants a billed service, feature, or associated recurring charge removed
  - Evidence: Observed
- SVC_VACATION_HOLD_BILLING: Vacation hold billing
  - Customer asks what they will be charged during a temporary vacation or seasonal service hold, or disputes billing during that hold
  - Evidence: Observed Rare
- SVC_RESUME_SERVICE_AFTER_VACATION_HOLD_BILLING: Resume service after vacation hold billing
  - Customer asks about billing when resuming service after a temporary hold
  - Evidence: Coverage Expansion
- SVC_MOVE_TRANSFER_SERVICE_BILLING: Move or transfer service billing
  - Customer asks how moving service to another address affects billing, credits, deposits, or final and first bills
  - Evidence: Coverage Expansion
- SVC_UPGRADE_DOWNGRADE_BILLING_IMPACT: Upgrade or downgrade billing impact
  - Customer asks how changing speed, technology, or plan affects the bill
  - Evidence: Observed
- SVC_ADD_SERVICE_FEATURE_BILLING_IMPACT: Add service or feature billing impact
  - Customer asks what adding another service or feature will do to the bill
  - Evidence: Coverage Expansion
- SVC_CHANGE_EFFECTIVE_DATE_PRORATION: Change effective date or proration
  - Customer asks how the effective date of a service change affects prorated charges
  - Evidence: Coverage Expansion
- SVC_CLOSED_ACCOUNT_BALANCE_FINAL_PAYMENT: Closed account balance or final payment
  - Customer asks what remains owed or refundable after the account is closed
  - Evidence: Coverage Expansion
- SVC_MODEM_ROUTER_RENTAL_FEE: Modem or router rental fee
  - Customer asks about recurring rental charges for a modem, router, gateway, or similar equipment
  - Evidence: Observed
- SVC_EQUIPMENT_PURCHASE_OWNERSHIP_CHARGE: Equipment purchase or ownership charge
  - Customer asks about buying equipment, ownership, or a one time equipment charge
  - Evidence: Observed
- SVC_EQUIPMENT_RETURN_NONRETURN_CHARGE: Equipment return or nonreturn charge
  - Customer asks about a charge related to returning or failing to return equipment
  - Evidence: Coverage Expansion
- SVC_INSTALLATION_ACTIVATION_CHARGE: Installation or activation charge
  - Customer asks about installation, activation, or setup charges
  - Evidence: Coverage Expansion
- SVC_TECHNICIAN_VISIT_SERVICE_CALL_CHARGE: Technician visit or service call charge
  - Customer asks about a billed technician visit or service call fee
  - Evidence: Coverage Expansion
- SVC_EQUIPMENT_SHIPPING_HANDLING_CHARGE: Equipment shipping or handling charge
  - Customer asks about shipping or handling fees for equipment
  - Evidence: Coverage Expansion
- SVC_REPLACEMENT_EQUIPMENT_CHARGE: Replacement equipment charge
  - Customer asks about a charge for replacement equipment
  - Evidence: Coverage Expansion

## Other Category

- OTHER_MISC_OTHER_BILLING: Misc or Other billing
  - The call is billing related but no defined subcategory fits adequately
  - Evidence: Fallback
