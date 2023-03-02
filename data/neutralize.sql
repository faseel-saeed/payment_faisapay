-- disable faisapay payment provider
UPDATE payment_provider
   SET faisapay_merchant_id = NULL,
       faisapay_passcode = NULL,
       faisapay_acquirer_id = NULL;
