# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import hmac
import logging
import pprint
import base64

import requests
from werkzeug.urls import url_join

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.payment_faisapay.const import SUPPORTED_CURRENCIES


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('faisapay', "Faisapay")], ondelete={'faisapay': 'set default'}
    )
    faisapay_merchant_id = fields.Char(
        string="Faisapay Merchant Id",
        help="The key solely used to identify the merchant with Faisapay.",
        required_if_provider='faisapay',
    )
    faisapay_acquirer_id = fields.Char(
        string="Faisapay Acquirer",
        help="The can be any 1-10 digit numeric string for your reference",
        required_if_provider='faisapay',
        groups='base.group_system',
    )
    faisapay_passcode = fields.Char(
        string="Faisapay Passcode",
        required_if_provider='faisapay',

    )

    

    #=== COMPUTE METHODS ===#

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'faisapay').update({
            'support_manual_capture': False,
            'support_refund': 'full_only',
        })

    # === BUSINESS METHODS ===#

    @api.model
    def _get_compatible_providers(self, *args, currency_id=None, **kwargs):
        """ Override of `payment` to filter out Faisapay providers for unsupported currencies. """
        providers = super()._get_compatible_providers(*args, currency_id=currency_id, **kwargs)

        currency = self.env['res.currency'].browse(currency_id).exists()
        
        _logger.info(
            "Get compatible currency: Faisapay: currency %s",
            currency.name
        )
        if currency and currency.name not in SUPPORTED_CURRENCIES:
            providers = providers.filtered(lambda p: p.code != 'faisapay')

        return providers
    
    def _faisapay_get_api_url(self):
        """ Return the URL of the API corresponding to the provider's state.

        :return: The API URL.
        :rtype: str
        """
        self.ensure_one()
        _logger.info(
            "GETTING API URL FOR STATE: %s",
            self.state
        )


        if self.state == 'enabled':
            return 'https://faisanet.mib.com.mv/pgv2/'
        else:  # 'test'
            return 'https://smarf.mib.com.mv/pgv2/'

    def _faisapay_make_request(self, endpoint, payload=None, method='POST'):
        """ Make a request to Faisapay API at the specified endpoint.
        Note:Faisapay authentication is done using a
             signature that is includes in the post request
        
        
        Note: self.ensure_one()

        :param str endpoint: The endpoint to be reached by the request.
        :param dict payload: The payload of the request.
        :param str method: The HTTP method of the request.
        :return The JSON-formatted content of the response.
        :rtype: dict
        :raise ValidationError: If an HTTP error occurs.
        """
        self.ensure_one()

        url = url_join(self._faisapay_get_api_url(), endpoint)
        
        
        try:
            if method == 'GET':
                response = requests.get(url, params=payload, timeout=10)
            else:
                response = requests.post(url, json=payload, timeout=10)
                
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                _logger.exception(
                    "Invalid API request at %s with data:\n%s", url, pprint.pformat(payload),
                )
                raise ValidationError("Faisapay: " + _(
                    "The communication with the API failed. Faisapay gave us the following "
                    "information: '%s'", response.json().get('error', {}).get('description')
                ))
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.exception("Unable to reach endpoint at %s", url)
            raise ValidationError(
                "Faisapay: " + _("Could not establish the connection to the API.")
            )
        return response.json()
    
    def _faisapay_calculate_pay_request_signature(self, data):
        """ Compute the signature for the request according to the Faisapay documentation.


        :param dict|bytes data: The data to sign.
        :return: The calculated signature.
        :rtype: str
        """ 

        merchant = self.faisapay_merchant_id    
        acquirer = self.faisapay_acquirer_id
        secret = self.faisapay_passcode  
            
        signing_string = f'{secret}{merchant}{acquirer}{data["orderID"]}{data["purchaseAmt"]}{data["purchaseCurrency"]}{data["purchaseCurrencyExponent"]}'
        return base64.b64encode(hashlib.sha256(signing_string.encode('utf-8')).digest()).decode('ASCII')
    
        
        
    def _faisapay_calculate_api_request_signature(self, data):
        """ Compute the signature for the api request according to the Faisapay documentation.
            This can be a status request or a reversal/refund request


        :param dict|bytes data: The data to sign.
        :return: The calculated signature.
        :rtype: str
        """

        merchant = self.faisapay_merchant_id
        acquirer = self.faisapay_acquirer_id
        secret = self.faisapay_passcode  
            
        signing_string = f'{secret}{merchant}{acquirer}{data["orderID"]}{data["requestType"]}'
        return base64.b64encode(hashlib.sha256(signing_string.encode('utf-8')).digest()).decode('ASCII')
   
    
    def _faisapay_calculate_signature(self, data, is_redirect=True):
        """ Compute the signature for the request's data according to the Faisapay documentation.


        :param dict|bytes data: The data to sign.
        :param bool is_redirect: Whether the data should be treated as redirect data
        :return: The calculated signature.
        :rtype: str
        """
        if is_redirect:
            merchant = self.faisapay_merchant_id
            aquirer = self.faisapay_acquirer_id
            secret = self.faisapay_passcode
            request_type = '0'; # request type 0 is payment
            
            signing_string = f'{request_type}{secret}{merchant}{aquirer}{data["orderID"]}{data["salt"]}'
            return base64.b64encode(hashlib.sha256(signing_string.encode('utf-8')).digest()).decode('ASCII')
        
        else:  # Notification data.
            merchant = self.faisapay_merchant_id
            acquirer = self.faisapay_acquirer_id
            secret = self.faisapay_passcode
            request_type = '0'; # request type 0 is payment
            
            signing_string = f'{request_type}{secret}{merchant}{acquirer}{data["orderID"]}{data["salt"]}'
            return base64.b64encode(hashlib.sha256(signing_string.encode('utf-8')).digest()).decode('ASCII')
