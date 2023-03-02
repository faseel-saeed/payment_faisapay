# Part of Odoo. See LICENSE file for full copyright and licensing details.

CURRENCY_MAPPING = {
    'MVR': '462',
    'USD': '840',
}

# The currencies supported by MIB Faisapay, in ISO 4217 format. Last updated on Feb 01, 2023.

SUPPORTED_CURRENCIES = [
    'USD', 'MVR'
]

# Mapping of transaction states to Faisapay's payment statuses.
PAYMENT_STATUS_MAPPING = {
    'done': ('1'),
    'reversed': ('108','124'),  # refunded is included
    'cancelled': ('36'),
    'invalid_merchant' : ('10')
}

