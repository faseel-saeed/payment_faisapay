# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from werkzeug.urls import url_encode, url_join

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_faisapay.const import CURRENCY_MAPPING
from odoo.addons.payment_faisapay.const import PAYMENT_STATUS_MAPPING
from odoo.addons.payment_faisapay.controllers.main import FaisapayController


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return faisapay-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the
                                       transaction.
        :return: The dict of provider-specific rendering values.
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'faisapay':
            return res

        # Faisapay requires amount to be sent without decimal places. We use 2 digit currency exponent 
        # & multiply the amount by 100 to remove the decimal place
        # Initiate the payment
        currency_exponent = 2
        converted_amount = int(self.amount * 100);  #remove the decimals from the amount
        version = FaisapayController._version
        
        
        
        
        _logger.info(
                    "Returning Payment Request Rendering values for(PROVIDER ID)%s:\n(values)%s",
                    self.provider_id, pprint.pformat(processing_values),
                )
        
       
        #convert currency to ISO 4217 numeric 3-digit code
        currency_code_numeric = CURRENCY_MAPPING[self.currency_id.name]
        
        base_url = self.provider_id.get_base_url()
        return_url_params = {'reference': self.reference}
        passcode = self.provider_id.faisapay_passcode
        

        rendering_values = {
            'api_url': self.provider_id._faisapay_get_api_url(),
            'version': version,
            'merID': self.provider_id.faisapay_merchant_id,
            'acqID': self.provider_id.faisapay_acquirer_id,
            'orderID': self.reference,
            'purchaseAmt': converted_amount,
            'purchaseCurrency': currency_code_numeric,
            'purchaseCurrencyExponent': currency_exponent,
            'signatureMethod': 'SHA256',
            'merRespURL': url_join(
                base_url, f'{FaisapayController._return_url}?{url_encode(return_url_params)}'
            ),
        }
        
        rendering_values.update({
            'signature': self.provider_id._faisapay_calculate_pay_request_signature(rendering_values)
        })
        
        return rendering_values



    def _send_refund_request(self, amount_to_refund=None):
        """ Override of `payment` to send a refund request to Faisapay.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'faisapay':
            return refund_tx

        # Make the refund request to Faisapay.

        version = FaisapayController._version
        requestType = 2

        payload = {
            'responseFormat': 'JSON',
            'version': version,
            'merID': self.provider_id.faisapay_merchant_id,
            'acqID': self.provider_id.faisapay_acquirer_id,
            'requestType': requestType,
            'orderID': self.provider_reference,
            'signatureMethod': 'SHA256'
        }

        payload.update({
            'signature': self.provider_id._faisapay_calculate_api_request_signature(payload)
        })


        _logger.info(
            "Payload of Faisapay 'reversalRequest' for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(payload)
        )

        response_content = refund_tx.provider_id._faisapay_make_request(
            'reversalRequest', payload=payload
        )

        _logger.info(
            "Response of Faisapay 'reversalRequest' for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(response_content)
        )

        response_content.update(entity_type='refund')
        response_content.update(operation='refund')
        refund_tx._handle_notification_data('faisapay', response_content) #NOT SURE WHERE THIS GOES YET

        return refund_tx
    

    def _send_capture_request(self):
        # Faisapay does not support capture request
        """ Override of `payment` to send a capture request to Faisapay.

        Note: self.ensure_one()

        :return: None
        """
        super()._send_capture_request()
        if self.provider_code != 'faisapay':
            return

        raise UserError(_("Transactions processed by Faisapay can't be captured manually"))


    def _send_void_request(self):
        #FaisaPay does not support transaction void requests as the payment is already deducted from the customers account
        #instead a refund request should be sent
        """ Override of `payment` to explain that it is impossible to void a Faisapay transaction.

        Note: self.ensure_one()

        :return: None
        """
        super()._send_void_request()
        if self.provider_code != 'faisapay':
            return

        raise UserError(_("Transactions processed by Faisapay can't be manually voided from Odoo."))

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of `payment` to find the transaction based on faisapay data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The normalized notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'faisapay' or len(tx) == 1:
            return tx

        _logger.info(
            "_get_tx_from_notification_data (notification_data)%s",
            notification_data
        )

        reference = notification_data.get('orderID')
        if not reference:
            raise ValidationError("Faisapay: " + _("Received data with missing reference."))

        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'faisapay')])

        if not tx:
            raise ValidationError(
                "Faisapay: " + _("No transaction found matching reference %s.", reference)
            )

        return tx


    def _process_notification_data(self, notification_data):
        """ Override of `payment` to process the transaction based on Faisapay data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'faisapay':
            return

        _logger.info(
            "_process_notification_data (PROVIDER ID)%s:\n(notification_data)%s",
            self.provider_id, pprint.pformat(notification_data),
        )

        provider_reference = notification_data.get('referenceNo')
        response_code = notification_data.get('responseCode')
        reason_code = notification_data.get('reasonCode')
        reason_text = notification_data.get('reasonText')
        merchant_check = notification_data.get('merchantCheck')

        if provider_reference:
            self.provider_reference = provider_reference

        if not response_code:
            raise ValidationError("Faisapay: " + _("Received data with missing response code."))

        if not reason_code:
            raise ValidationError("Faisapay: " + _("Received data with missing reason code."))

        if not merchant_check and response_code == '1' and reason_code in PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        elif not merchant_check and response_code == '1' and reason_code in PAYMENT_STATUS_MAPPING['reversed']:
            self._set_done()

            # Immediately post-process the transaction if it is a refund, as the post-processing
            # will not be triggered by a customer browsing the transaction from the portal.
            self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        elif not merchant_check and response_code == '2' and reason_code in PAYMENT_STATUS_MAPPING['cancelled']:
            self._set_canceled()
        else:
            _logger.warning(
                "Received data with error code (%s) for transaction with primary"
                "(response code %s) and (reason code %s).", response_code, reason_code, self.reference
            )
            self._set_error("Faisapay: " + _("An error occurred during the processing "
                                             "response code: %s,reason code %s, reason desc: %s ",
                                             response_code, reason_code, reason_text))
