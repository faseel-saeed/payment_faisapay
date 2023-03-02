# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hmac
import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request



_logger = logging.getLogger(__name__)


class FaisapayController(http.Controller):
    _return_url = '/payment/faisapay/return'
    _version = 3

    @http.route(
        _return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False,
        save_session=False
    )
    def faisapay_return_from_checkout(self, reference, **data):
        """ Process the notification data sent by Faisapay after redirection from checkout.

        :param str reference: The transaction reference embedded in the return URL.
        :param dict data: The notification data.
        """
        
        _logger.info("Handling redirection from Faisapay with data:\n%s", pprint.pformat(data))
        if all(f'{key}' in data for key in ('orderID', 'authCode', 'signature')):
            # Check the integrity of the notification.
            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'faisapay', {'orderID': reference}
            )              
            self._verify_notification_signature(data, data.get('signature'), tx_sudo)

            # Handle the notification data.
            tx_sudo._handle_notification_data('faisapay', data)

        elif all(f'{key}' in data for key in ('orderID', 'reasonCode', 'responseCode')):
            # Check the integrity of the notification.
            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'faisapay', {'orderID': reference}
            )
            data.update({'merchantCheck': True})

            # Handle the notification data.
            tx_sudo._handle_notification_data('faisapay', data)

        else:  # The customer cancelled the payment or the payment failed.
            pass  # Don't try to process this case because the payment id was not provided.

        # Redirect the user to the status page.
        return request.redirect('/payment/status')

    @staticmethod
    def _verify_notification_signature(
        notification_data, received_signature, tx_sudo, is_redirect=True
    ):
        """ Check that the received signature matches the expected one.

        :param dict|bytes notification_data: The notification data.
        :param str received_signature: The signature to compare with the expected signature.
        :param recordset tx_sudo: The sudoed transaction referenced by the notification data, as a
                                  `payment.transaction` record
        :param bool is_redirect: Whether the notification data should be treated as redirect data
                                 or as coming from a webhook notification.
        :return: None
        :raise :class:`werkzeug.exceptions.Forbidden`: If the signatures don't match.
        """
        # Check for the received signature.
        if not received_signature:
            _logger.warning("Received notification with missing signature.")
            raise Forbidden()

        # Compare the received signature with the expected signature.
        expected_signature = tx_sudo.provider_id._faisapay_calculate_signature(
            notification_data, is_redirect=is_redirect
        )
        if not hmac.compare_digest(received_signature, expected_signature):
            _logger.warning("Received notification with invalid signature.")
            raise Forbidden()
