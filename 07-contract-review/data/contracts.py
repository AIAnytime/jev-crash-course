"""Two sample agreements. Neither is legal advice and neither is a real contract;
they exist so the demo has something with teeth in it to chew on."""

ONE_SIDED = """\
MASTER SERVICES AGREEMENT

1. Term. This Agreement begins on the Effective Date and continues for an initial term of thirty-six (36) months. It renews automatically for successive twelve (12) month terms unless Customer gives written notice of non-renewal at least ninety (90) days before the end of the then-current term.

2. Fees. Customer shall pay the fees set out in the Order Form annually in advance. Supplier may increase fees for any renewal term by providing notice at any time before renewal. Invoices are payable within fifteen (15) days. Late amounts accrue interest at 2.5% per month.

3. Limitation of Liability. Supplier's total liability arising out of this Agreement shall not exceed the lesser of (a) the fees paid in the three (3) months preceding the claim, or (b) five thousand dollars ($5,000). Customer's liability under this Agreement is unlimited.

4. Indemnity. Customer shall indemnify, defend and hold harmless Supplier against any and all claims arising from Customer's use of the Services, including claims caused in whole or in part by Supplier's own negligence.

5. Service Levels. Supplier will use commercially reasonable efforts to make the Services available. Supplier provides no uptime commitment and no service credits.

6. Data. Supplier may access, process and analyse Customer Data for the purpose of improving its products and services, including training machine learning models, and may retain such data after termination.

7. Termination. Supplier may terminate this Agreement at any time for convenience upon thirty (30) days notice. Customer may terminate only for Supplier's material breach that remains uncured after sixty (60) days written notice. No refunds are payable in any circumstance.

8. Governing Law. This Agreement is governed by the laws of the State of Delaware. The parties submit to the exclusive jurisdiction of the courts of Wilmington, Delaware, and waive any right to a jury trial.

9. Assignment. Customer may not assign this Agreement, including in connection with a merger or sale of substantially all assets, without Supplier's prior written consent, which may be withheld in Supplier's sole discretion.

10. Publicity. Supplier may identify Customer by name and logo in its marketing materials, case studies and website without further approval.
"""

BALANCED = """\
SOFTWARE SUBSCRIPTION AGREEMENT

1. Term. This Agreement begins on the Effective Date and continues for twelve (12) months. It renews for successive twelve (12) month terms unless either party gives thirty (30) days written notice before the end of the current term.

2. Fees. Fees are as set out in the Order Form and are payable within thirty (30) days of invoice. Supplier may increase fees at renewal by no more than the greater of five percent (5%) or the change in the consumer price index, on sixty (60) days notice.

3. Limitation of Liability. Neither party's aggregate liability under this Agreement shall exceed the fees paid or payable in the twelve (12) months preceding the claim. Neither party is liable for indirect or consequential loss. Nothing limits liability for death, personal injury, or wilful misconduct.

4. Indemnity. Each party shall indemnify the other against third party claims arising from its own breach of this Agreement. Supplier shall indemnify Customer against claims that the Services infringe third party intellectual property rights.

5. Service Levels. Supplier will make the Services available 99.9% of the time each calendar month, excluding scheduled maintenance notified in advance. Failure to meet this commitment entitles Customer to service credits as set out in Schedule 2.

6. Data. Customer retains all rights in Customer Data. Supplier processes Customer Data only to provide the Services and in accordance with the Data Processing Addendum. Supplier will delete or return Customer Data within thirty (30) days of termination on request.

7. Termination. Either party may terminate for material breach that remains uncured thirty (30) days after written notice. On termination for Supplier's breach, Customer receives a pro-rata refund of prepaid fees.

8. Governing Law. This Agreement is governed by the laws of England and Wales, and the parties submit to the non-exclusive jurisdiction of the courts of England and Wales.

9. Assignment. Either party may assign this Agreement to a successor in connection with a merger or sale of substantially all of its assets on written notice to the other party.

10. Confidentiality. Each party shall keep the other's confidential information in confidence for the term and for three (3) years afterwards, and shall use it only for the purposes of this Agreement.
"""

SAMPLES = {
    "A one-sided services agreement": ONE_SIDED,
    "A more balanced subscription agreement": BALANCED,
}
