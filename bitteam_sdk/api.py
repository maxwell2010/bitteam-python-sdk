"""Generated API methods. Regenerate with scripts_sdk/generate_api.py."""
from .endpoints import EndpointAPI


class BitTeamAPI(EndpointAPI):

    async def get_asset(self, *, params=None, data=None):
        """GET /asset. Retuns detailed info about specified currency"""
        return await self.call('get_asset', path={}, params=params, data=data)

    async def get_currencies(self, *, params=None, data=None):
        """GET /currencies. Get all currencies"""
        return await self.call('get_currencies', path={}, params=params, data=data)

    async def get_discount(self, *, params=None, data=None):
        """GET /discount. Returns discount, calculated for current user's BTT amount"""
        return await self.call('get_discount', path={}, params=params, data=data)

    async def get_discounts(self, *, params=None, data=None):
        """GET /discounts. Returns all discount levels, base on BTT amount"""
        return await self.call('get_discounts', path={}, params=params, data=data)

    async def get_forgot_2fa(self, *, params=None, data=None):
        """GET /forgot-2fa. Use this endpoint to display QRCode, generated from Secret2FA."""
        return await self.call('get_forgot_2fa', path={}, params=params, data=data)

    async def get_get_options(self, *, params=None, data=None):
        """GET /get-options. Use this endpoint to get new user's options"""
        return await self.call('get_get_options', path={}, params=params, data=data)

    async def get_get_session_status(self, *, params=None, data=None):
        """GET /get-session-status. Get session status"""
        return await self.call('get_get_session_status', path={}, params=params, data=data)

    async def get_get_user_data(self, *, params=None, data=None):
        """GET /get-user-data. Endpoint for fetching user's data"""
        return await self.call('get_get_user_data', path={}, params=params, data=data)

    async def get_login_confirmation(self, *, params=None, data=None):
        """GET /login-confirmation. User login confirmation"""
        return await self.call('get_login_confirmation', path={}, params=params, data=data)

    async def get_orders(self, *, params=None, data=None):
        """GET /orders. Get all orders"""
        return await self.call('get_orders', path={}, params=params, data=data)

    async def get_orders_by_user(self, *, params=None, data=None):
        """GET /ordersByUser. Get orders by user"""
        return await self.call('get_orders_by_user', path={}, params=params, data=data)

    async def get_pairs(self, *, params=None, data=None):
        """GET /pairs. Use this method to get information about all trading pairs"""
        return await self.call('get_pairs', path={}, params=params, data=data)

    async def get_rate_wallbtc(self, *, params=None, data=None):
        """GET /rate-wallbtc. Get rate and amount"""
        return await self.call('get_rate_wallbtc', path={}, params=params, data=data)

    async def get_rates(self, *, params=None, data=None):
        """GET /rates. Get all rates"""
        return await self.call('get_rates', path={}, params=params, data=data)

    async def get_stats(self, *, params=None, data=None):
        """GET /stats. Retuns detailed info about specified currency"""
        return await self.call('get_stats', path={}, params=params, data=data)

    async def get_trades(self, *, params=None, data=None):
        """GET /trades. Get all trades"""
        return await self.call('get_trades', path={}, params=params, data=data)

    async def get_trades_by_user(self, *, params=None, data=None):
        """GET /tradesByUser. Get trades by user"""
        return await self.call('get_trades_by_user', path={}, params=params, data=data)

    async def get_transactions_by_user(self, *, params=None, data=None):
        """GET /transactionsByUser. Get transactions by user"""
        return await self.call('get_transactions_by_user', path={}, params=params, data=data)

    async def get_transactions_of_user(self, *, params=None, data=None):
        """GET /transactionsOfUser. Get transactions by user"""
        return await self.call('get_transactions_of_user', path={}, params=params, data=data)

    async def get_address_wallets(self, *, params=None, data=None):
        """GET /address/wallets. User`s wallets"""
        return await self.call('get_address_wallets', path={}, params=params, data=data)

    async def get_altyn_banks(self, *, params=None, data=None):
        """GET /altyn/banks. Get list of available banks"""
        return await self.call('get_altyn_banks', path={}, params=params, data=data)

    async def get_ccxt_balance(self, *, params=None, data=None):
        """GET /ccxt/balance. User balance"""
        return await self.call('get_ccxt_balance', path={}, params=params, data=data)

    async def get_ccxt_orders_of_user(self, *, params=None, data=None):
        """GET /ccxt/ordersOfUser. Get orders by user"""
        return await self.call('get_ccxt_orders_of_user', path={}, params=params, data=data)

    async def get_ccxt_pairs(self, *, params=None, data=None):
        """GET /ccxt/pairs. Use this method to get information about all trading pairs"""
        return await self.call('get_ccxt_pairs', path={}, params=params, data=data)

    async def get_ccxt_trades_of_user(self, *, params=None, data=None):
        """GET /ccxt/tradesOfUser. Get trades by user"""
        return await self.call('get_ccxt_trades_of_user', path={}, params=params, data=data)

    async def get_cmc_assets(self, *, params=None, data=None):
        """GET /cmc/assets. In depth details on crypto currencies available on the exchange"""
        return await self.call('get_cmc_assets', path={}, params=params, data=data)

    async def get_cmc_summary(self, *, params=None, data=None):
        """GET /cmc/summary. Overview of market data for all tickers and all markets"""
        return await self.call('get_cmc_summary', path={}, params=params, data=data)

    async def get_cmc_ticker(self, *, params=None, data=None):
        """GET /cmc/ticker. 24-hour rolling window price change statistics for all markets"""
        return await self.call('get_cmc_ticker', path={}, params=params, data=data)

    async def get_markdown_menu(self, *, params=None, data=None):
        """GET /markdown/menu. """
        return await self.call('get_markdown_menu', path={}, params=params, data=data)

    async def get_orderbooks_by_symbol(self, symbol, *, params=None, data=None):
        """GET /orderbooks/{symbol}. Returns orderbooks by symbol"""
        return await self.call('get_orderbooks_by_symbol', path={'symbol': symbol}, params=params, data=data)

    async def get_pair_by_name(self, name, *, params=None, data=None):
        """GET /pair/{name}. Returns pair info"""
        return await self.call('get_pair_by_name', path={'name': name}, params=params, data=data)

    async def get_pairs_precisions(self, *, params=None, data=None):
        """GET /pairs/precisions. Get pair precisions"""
        return await self.call('get_pairs_precisions', path={}, params=params, data=data)

    async def get_phone_check_validation(self, *, params=None, data=None):
        """GET /phone/checkValidation. Use this endpoint to verify sent verification code with generated one"""
        return await self.call('get_phone_check_validation', path={}, params=params, data=data)

    async def get_stock_balance(self, *, params=None, data=None):
        """GET /stock/balance. Get user balance on stock"""
        return await self.call('get_stock_balance', path={}, params=params, data=data)

    async def get_sumsub_create(self, *, params=None, data=None):
        """GET /sumsub/create. Endpoint for creating a sumsub applicant"""
        return await self.call('get_sumsub_create', path={}, params=params, data=data)

    async def get_sumsub_data(self, *, params=None, data=None):
        """GET /sumsub/data. Endpoint for fetching applicant's data"""
        return await self.call('get_sumsub_data', path={}, params=params, data=data)

    async def get_sumsub_obtain(self, *, params=None, data=None):
        """GET /sumsub/obtain. Endpoint for fetching applicant access token"""
        return await self.call('get_sumsub_obtain', path={}, params=params, data=data)

    async def get_sumsub_status(self, *, params=None, data=None):
        """GET /sumsub/status. Endpoint for fetching applicant review status"""
        return await self.call('get_sumsub_status', path={}, params=params, data=data)

    async def get_trade_by_id(self, id, *, params=None, data=None):
        """GET /trade/{id}. Get trade by ID"""
        return await self.call('get_trade_by_id', path={'id': id}, params=params, data=data)

    async def get_transaction_by_id(self, id, *, params=None, data=None):
        """GET /transaction/{id}. Get transaction by ID"""
        return await self.call('get_transaction_by_id', path={'id': id}, params=params, data=data)

    async def get_user_api_keys(self, *, params=None, data=None):
        """GET /user/api-keys. Returns list of all user's api keys"""
        return await self.call('get_user_api_keys', path={}, params=params, data=data)

    async def get_user_stats(self, *, params=None, data=None):
        """GET /user/stats. Endpoint for fetching user's statistics"""
        return await self.call('get_user_stats', path={}, params=params, data=data)

    async def get_address_by_currency_id_create(self, currency_id, *, params=None, data=None):
        """GET /address/{currencyId}/create. Create address"""
        return await self.call('get_address_by_currency_id_create', path={'currencyId': currency_id}, params=params, data=data)

    async def get_altyn_client(self, *, params=None, data=None):
        """GET /altyn/client/. """
        return await self.call('get_altyn_client', path={}, params=params, data=data)

    async def get_altyn_payment_by_transaction_id(self, transaction_id, *, params=None, data=None):
        """GET /altyn/payment/{transactionID}. """
        return await self.call('get_altyn_payment_by_transaction_id', path={'transactionID': transaction_id}, params=params, data=data)

    async def get_ccxt_order_by_id(self, id, *, params=None, data=None):
        """GET /ccxt/order/{id}. Get order by ID"""
        return await self.call('get_ccxt_order_by_id', path={'id': id}, params=params, data=data)

    async def get_cmc_orderbook_by_pair(self, pair, *, params=None, data=None):
        """GET /cmc/orderbook/{pair}. Market depth of a trading pair"""
        return await self.call('get_cmc_orderbook_by_pair', path={'pair': pair}, params=params, data=data)

    async def get_cmc_trades_by_pair(self, pair, *, params=None, data=None):
        """GET /cmc/trades/{pair}. Recently completed trades for a given market"""
        return await self.call('get_cmc_trades_by_pair', path={'pair': pair}, params=params, data=data)

    async def get_markdown_content_by_slug(self, slug, *, params=None, data=None):
        """GET /markdown/content/{slug}. """
        return await self.call('get_markdown_content_by_slug', path={'slug': slug}, params=params, data=data)

    async def get_user_stats_all(self, *, params=None, data=None):
        """GET /user/stats/all. Endpoint for fetching all user's operations"""
        return await self.call('get_user_stats_all', path={}, params=params, data=data)

    async def get_user_stats_ref(self, *, params=None, data=None):
        """GET /user/stats/ref. Endpoint for fetching user's referral programme statistics"""
        return await self.call('get_user_stats_ref', path={}, params=params, data=data)

    async def get_user_volume_by_symbol(self, symbol, *, params=None, data=None):
        """GET /user/volume/{symbol}. Get user trading volume by currency symbol"""
        return await self.call('get_user_volume_by_symbol', path={'symbol': symbol}, params=params, data=data)

    async def get_withdraw_by_currency_id_check(self, currency_id, *, params=None, data=None):
        """GET /withdraw/{currencyId}/check. Route for permission to withdraw"""
        return await self.call('get_withdraw_by_currency_id_check', path={'currencyId': currency_id}, params=params, data=data)

    async def get_altyn_payment_qr_page_by_payment_token(self, payment_token, *, params=None, data=None):
        """GET /altyn/payment/qr-page/{paymentToken}. Get payment QR page data for page state recovery"""
        return await self.call('get_altyn_payment_qr_page_by_payment_token', path={'paymentToken': payment_token}, params=params, data=data)

    async def get_user_stats_ref_table(self, *, params=None, data=None):
        """GET /user/stats/ref/table. Endpoint for fetching all user's operations"""
        return await self.call('get_user_stats_ref_table', path={}, params=params, data=data)

    async def post_access_check(self, *, params=None, data=None):
        """POST /access-check. Checks access token"""
        return await self.call('post_access_check', path={}, params=params, data=data)

    async def post_before_transaction_email(self, *, params=None, data=None):
        """POST /before-transaction-email. Send email before funds transaction"""
        return await self.call('post_before_transaction_email', path={}, params=params, data=data)

    async def post_confirm_email(self, *, params=None, data=None):
        """POST /confirm-email. Use this endpoint to check email validation token and allow user to set new password"""
        return await self.call('post_confirm_email', path={}, params=params, data=data)

    async def post_disable_2fa(self, *, params=None, data=None):
        """POST /disable-2fa. Use this endpoint to disable user's 2fa"""
        return await self.call('post_disable_2fa', path={}, params=params, data=data)

    async def post_enable_2fa(self, *, params=None, data=None):
        """POST /enable-2fa. Use this endpoint to enable new user's 2fa"""
        return await self.call('post_enable_2fa', path={}, params=params, data=data)

    async def post_login_auth(self, *, params=None, data=None):
        """POST /login-auth. Login with P2P tokens"""
        return await self.call('post_login_auth', path={}, params=params, data=data)

    async def post_logout(self, *, params=None, data=None):
        """POST /logout. Logout"""
        return await self.call('post_logout', path={}, params=params, data=data)

    async def post_password_change(self, *, params=None, data=None):
        """POST /password-change. Use this endpoint to send email-verification code, allowing password changing"""
        return await self.call('post_password_change', path={}, params=params, data=data)

    async def post_pay_build(self, *, params=None, data=None):
        """POST /pay-build. Create a payment token"""
        return await self.call('post_pay_build', path={}, params=params, data=data)

    async def post_refresh_logout(self, *, params=None, data=None):
        """POST /refresh-logout. Logout with refresh"""
        return await self.call('post_refresh_logout', path={}, params=params, data=data)

    async def post_refresh_token(self, *, params=None, data=None):
        """POST /refresh-token. Refresh access and refresh tokens"""
        return await self.call('post_refresh_token', path={}, params=params, data=data)

    async def post_register_wallbtc(self, *, params=None, data=None):
        """POST /register-wallbtc. Register on wall BTC"""
        return await self.call('post_register_wallbtc', path={}, params=params, data=data)

    async def post_reset_password(self, *, params=None, data=None):
        """POST /reset-password. Use this endpoint to send a 'Reset password' mail """
        return await self.call('post_reset_password', path={}, params=params, data=data)

    async def post_send_email(self, *, params=None, data=None):
        """POST /send-email. Send email following link Send"""
        return await self.call('post_send_email', path={}, params=params, data=data)

    async def post_set_2fa(self, *, params=None, data=None):
        """POST /set-2fa. Use this endpoint to set new user's 2fa"""
        return await self.call('post_set_2fa', path={}, params=params, data=data)

    async def post_set_options(self, *, params=None, data=None):
        """POST /set-options. Use this endpoint to set new user's options"""
        return await self.call('post_set_options', path={}, params=params, data=data)

    async def post_all_orders_cancel(self, *, params=None, data=None):
        """POST /all-orders/cancel. Cancel all orders"""
        return await self.call('post_all_orders_cancel', path={}, params=params, data=data)

    async def post_altyn_client(self, *, params=None, data=None):
        """POST /altyn/client. """
        return await self.call('post_altyn_client', path={}, params=params, data=data)

    async def post_ccxt_cancel_all_order(self, *, params=None, data=None):
        """POST /ccxt/cancel-all-order. Cancel all orders"""
        return await self.call('post_ccxt_cancel_all_order', path={}, params=params, data=data)

    async def post_ccxt_cancelorder(self, *, params=None, data=None):
        """POST /ccxt/cancelorder. Cancel order"""
        return await self.call('post_ccxt_cancelorder', path={}, params=params, data=data)

    async def post_ccxt_ordercreate(self, *, params=None, data=None):
        """POST /ccxt/ordercreate. create user order"""
        return await self.call('post_ccxt_ordercreate', path={}, params=params, data=data)

    async def post_ccxt_withdraw(self, *, params=None, data=None):
        """POST /ccxt/withdraw. Withdraw funds by API key"""
        return await self.call('post_ccxt_withdraw', path={}, params=params, data=data)

    async def post_order_cancel(self, *, params=None, data=None):
        """POST /order/cancel. Cancel order"""
        return await self.call('post_order_cancel', path={}, params=params, data=data)

    async def post_order_create(self, *, params=None, data=None):
        """POST /order/create. Use this method to create a new order, you can create either limit or market order."""
        return await self.call('post_order_create', path={}, params=params, data=data)

    async def post_p2p_create_transaction(self, *, params=None, data=None):
        """POST /p2p/create-transaction. Create transaction"""
        return await self.call('post_p2p_create_transaction', path={}, params=params, data=data)

    async def post_p2p_create_transaction_for_p2p(self, *, params=None, data=None):
        """POST /p2p/create-transaction-for-p2p. Create transaction for p2p"""
        return await self.call('post_p2p_create_transaction_for_p2p', path={}, params=params, data=data)

    async def post_p2p_create_withdraw(self, *, params=None, data=None):
        """POST /p2p/create-withdraw. Create Withdraw"""
        return await self.call('post_p2p_create_withdraw', path={}, params=params, data=data)

    async def post_p2p_get_balance(self, *, params=None, data=None):
        """POST /p2p/get-balance. Get balance from p2p"""
        return await self.call('post_p2p_get_balance', path={}, params=params, data=data)

    async def post_p2p_set_p2p_token(self, *, params=None, data=None):
        """POST /p2p/set-p2p-token. Set p2p_access_token"""
        return await self.call('post_p2p_set_p2p_token', path={}, params=params, data=data)

    async def post_p2p_set_token(self, *, params=None, data=None):
        """POST /p2p/set-token. Set access token"""
        return await self.call('post_p2p_set_token', path={}, params=params, data=data)

    async def post_phone_add(self, *, params=None, data=None):
        """POST /phone/add. Use this endpoint to set new user's phone and send verification code"""
        return await self.call('post_phone_add', path={}, params=params, data=data)

    async def post_stock_deposit(self, *, params=None, data=None):
        """POST /stock/deposit. Deposit funds from p2p to stock"""
        return await self.call('post_stock_deposit', path={}, params=params, data=data)

    async def post_stock_withdraw(self, *, params=None, data=None):
        """POST /stock/withdraw. Withdraw funds from stock to p2p"""
        return await self.call('post_stock_withdraw', path={}, params=params, data=data)

    async def post_user_pay_fee_btt(self, *, params=None, data=None):
        """POST /user/pay-fee-btt. Use this method to change user's 'pay fee with BTT' option"""
        return await self.call('post_user_pay_fee_btt', path={}, params=params, data=data)

    async def post_webhook_deposit(self, *, params=None, data=None):
        """POST /webhook/deposit. Webhook for register deposit"""
        return await self.call('post_webhook_deposit', path={}, params=params, data=data)

    async def post_withdraw_confirm(self, *, params=None, data=None):
        """POST /withdraw/confirm. Withdrawal, lock funds"""
        return await self.call('post_withdraw_confirm', path={}, params=params, data=data)

    async def post_withdraw_create(self, *, params=None, data=None):
        """POST /withdraw/create. Create withdraw transaction"""
        return await self.call('post_withdraw_create', path={}, params=params, data=data)

    async def post_altyn_payment_sbp(self, *, params=None, data=None):
        """POST /altyn/payment/sbp. """
        return await self.call('post_altyn_payment_sbp', path={}, params=params, data=data)

    async def post_deposit_fiat_request(self, *, params=None, data=None):
        """POST /deposit/fiat/request. Request fiat deposit transaction"""
        return await self.call('post_deposit_fiat_request', path={}, params=params, data=data)

    async def post_login_confirmation_code_resend(self, *, params=None, data=None):
        """POST /login-confirmation/code/resend. Resend code to email for confirmation device"""
        return await self.call('post_login_confirmation_code_resend', path={}, params=params, data=data)

    async def post_order_conditional_create(self, *, params=None, data=None):
        """POST /order/conditional/create. Create Conditional order"""
        return await self.call('post_order_conditional_create', path={}, params=params, data=data)

    async def post_user_api_keys_redeem(self, *, params=None, data=None):
        """POST /user/api-keys/redeem. Creates new api key and returns it's data"""
        return await self.call('post_user_api_keys_redeem', path={}, params=params, data=data)

    async def post_user_api_keys_reset(self, *, params=None, data=None):
        """POST /user/api-keys/reset. Removes specified api key from your account"""
        return await self.call('post_user_api_keys_reset', path={}, params=params, data=data)

    async def post_user_api_keys_update(self, *, params=None, data=None):
        """POST /user/api-keys/update. Updated specified api key's name"""
        return await self.call('post_user_api_keys_update', path={}, params=params, data=data)

    async def post_user_favourite_add_pair(self, *, params=None, data=None):
        """POST /user/favourite/add-pair. Add pair in favourite"""
        return await self.call('post_user_favourite_add_pair', path={}, params=params, data=data)

    async def post_user_favourite_remove_pair(self, *, params=None, data=None):
        """POST /user/favourite/remove-pair. Remove pair fron favourite"""
        return await self.call('post_user_favourite_remove_pair', path={}, params=params, data=data)

    async def post_user_verification_documents(self, *, params=None, data=None):
        """POST /user/verification/documents. Uploading documents"""
        return await self.call('post_user_verification_documents', path={}, params=params, data=data)

    async def post_user_verification_phone(self, *, params=None, data=None):
        """POST /user/verification/phone. Initiating a phone call"""
        return await self.call('post_user_verification_phone', path={}, params=params, data=data)

    async def post_user_verification_sms(self, *, params=None, data=None):
        """POST /user/verification/sms. Sending SMS if there was no call"""
        return await self.call('post_user_verification_sms', path={}, params=params, data=data)

    async def post_withdraw_confirmation_email(self, *, params=None, data=None):
        """POST /withdraw/confirmation/email. Send confirmation email code before withdraw of funds"""
        return await self.call('post_withdraw_confirmation_email', path={}, params=params, data=data)

    async def post_withdraw_confirmation_phone(self, *, params=None, data=None):
        """POST /withdraw/confirmation/phone. Call phone for confirmation before withdraw of funds"""
        return await self.call('post_withdraw_confirmation_phone', path={}, params=params, data=data)

    async def post_user_verification_phone_confirm(self, *, params=None, data=None):
        """POST /user/verification/phone/confirm. Verify phone with a code"""
        return await self.call('post_user_verification_phone_confirm', path={}, params=params, data=data)

    async def post_deposit_fiat_webhook_by_user_id_by_order_id(self, user_id, order_id, *, params=None, data=None):
        """POST /deposit/fiat/webhook/{userId}/{orderId}. Webhook fiat deposit callback"""
        return await self.call('post_deposit_fiat_webhook_by_user_id_by_order_id', path={'userId': user_id, 'orderId': order_id}, params=params, data=data)

    async def post_withdraw_fiat_webhook_by_user_id_by_order_id(self, user_id, order_id, *, params=None, data=None):
        """POST /withdraw/fiat/webhook/{userId}/{orderId}. Webhook fiat withdraw callback"""
        return await self.call('post_withdraw_fiat_webhook_by_user_id_by_order_id', path={'userId': user_id, 'orderId': order_id}, params=params, data=data)

    async def delete_dev_all_orders_cancel(self, *, params=None, data=None):
        """DELETE /dev/all-orders/cancel. Cancel all orders for all users (develop only)"""
        return await self.call('delete_dev_all_orders_cancel', path={}, params=params, data=data)
