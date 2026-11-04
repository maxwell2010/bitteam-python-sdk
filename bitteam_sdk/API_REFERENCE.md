# BitTeam API reference - 2026-11-03

Use `client.api.<method>(path_arguments, params={...}, data={...})`.
Responses preserve the original JSON shape. Server callbacks and dev operations are listed but not callable.
All client routes have named methods; this catalog does not imply successful live verification of private routes.

| Method | HTTP endpoint | Access | Body contract | Live public check |
|---|---|---|---|---|
| `get_asset` | `GET /asset` | public | Swagger | OK |
| `get_currencies` | `GET /currencies` | public | Swagger | OK |
| `get_discount` | `GET /discount` | private | Swagger | not run |
| `get_discounts` | `GET /discounts` | private | Swagger | not run |
| `get_forgot_2fa` | `GET /forgot-2fa` | private | Swagger | not run |
| `get_get_options` | `GET /get-options` | private | Swagger | not run |
| `get_get_session_status` | `GET /get-session-status` | private | Swagger | not run |
| `get_get_user_data` | `GET /get-user-data` | private | Swagger | not run |
| `get_login_confirmation` | `GET /login-confirmation` | public | Swagger | not run |
| `get_orders` | `GET /orders` | public | Swagger | OK |
| `get_orders_by_user` | `GET /ordersByUser` | private | Swagger | not run |
| `get_pairs` | `GET /pairs` | public | Swagger | OK |
| `get_rate_wallbtc` | `GET /rate-wallbtc` | private | Swagger | not run |
| `get_rates` | `GET /rates` | public | Swagger | OK |
| `get_stats` | `GET /stats` | public | Swagger | HTTP 500 |
| `get_trades` | `GET /trades` | public | Swagger | OK |
| `get_trades_by_user` | `GET /tradesByUser` | private | Swagger | not run |
| `get_transactions_by_user` | `GET /transactionsByUser` | private | Swagger | not run |
| `get_transactions_of_user` | `GET /transactionsOfUser` | private | Swagger | not run |
| `get_address_wallets` | `GET /address/wallets` | private | Swagger | not run |
| `get_altyn_banks` | `GET /altyn/banks` | private | Swagger | HTTP 401 |
| `get_ccxt_balance` | `GET /ccxt/balance` | private | Swagger | not run |
| `get_ccxt_orders_of_user` | `GET /ccxt/ordersOfUser` | private | Swagger | not run |
| `get_ccxt_pairs` | `GET /ccxt/pairs` | public | Swagger | OK |
| `get_ccxt_trades_of_user` | `GET /ccxt/tradesOfUser` | private | Swagger | not run |
| `get_cmc_assets` | `GET /cmc/assets` | public | Swagger | OK |
| `get_cmc_summary` | `GET /cmc/summary` | public | Swagger | OK |
| `get_cmc_ticker` | `GET /cmc/ticker` | public | Swagger | OK |
| `get_markdown_menu` | `GET /markdown/menu` | public | Swagger | HTTP 500 |
| `get_orderbooks_by_symbol` | `GET /orderbooks/{symbol}` | public | Swagger | OK |
| `get_pair_by_name` | `GET /pair/{name}` | public | Swagger | OK |
| `get_pairs_precisions` | `GET /pairs/precisions` | public | Swagger | OK |
| `get_phone_check_validation` | `GET /phone/checkValidation` | private | Swagger | not run |
| `get_stock_balance` | `GET /stock/balance` | private | Swagger | not run |
| `get_sumsub_create` | `GET /sumsub/create` | private | Swagger | not run |
| `get_sumsub_data` | `GET /sumsub/data` | private | Swagger | not run |
| `get_sumsub_obtain` | `GET /sumsub/obtain` | private | Swagger | not run |
| `get_sumsub_status` | `GET /sumsub/status` | private | Swagger | not run |
| `get_trade_by_id` | `GET /trade/{id}` | public | Swagger | not run |
| `get_transaction_by_id` | `GET /transaction/{id}` | public | Swagger | not run |
| `get_user_api_keys` | `GET /user/api-keys` | private | Swagger | not run |
| `get_user_stats` | `GET /user/stats` | private | Swagger | not run |
| `get_address_by_currency_id_create` | `GET /address/{currencyId}/create` | private | Swagger | not run |
| `get_altyn_client` | `GET /altyn/client/` | private | Swagger | HTTP 401 |
| `get_altyn_payment_by_transaction_id` | `GET /altyn/payment/{transactionID}` | public | Swagger | not run |
| `get_ccxt_order_by_id` | `GET /ccxt/order/{id}` | private | Swagger | not run |
| `get_cmc_orderbook_by_pair` | `GET /cmc/orderbook/{pair}` | public | Swagger | OK |
| `get_cmc_trades_by_pair` | `GET /cmc/trades/{pair}` | public | Swagger | OK |
| `get_markdown_content_by_slug` | `GET /markdown/content/{slug}` | public | Swagger | not run |
| `get_user_stats_all` | `GET /user/stats/all` | private | Swagger | not run |
| `get_user_stats_ref` | `GET /user/stats/ref` | private | Swagger | not run |
| `get_user_volume_by_symbol` | `GET /user/volume/{symbol}` | private | Swagger | not run |
| `get_withdraw_by_currency_id_check` | `GET /withdraw/{currencyId}/check` | private | Swagger | not run |
| `get_altyn_payment_qr_page_by_payment_token` | `GET /altyn/payment/qr-page/{paymentToken}` | public | Swagger | not run |
| `get_user_stats_ref_table` | `GET /user/stats/ref/table` | private | Swagger | not run |
| `post_access_check` | `POST /access-check` | private | incomplete | not run |
| `post_before_transaction_email` | `POST /before-transaction-email` | private | Swagger | not run |
| `post_confirm_email` | `POST /confirm-email` | private | Swagger | not run |
| `post_disable_2fa` | `POST /disable-2fa` | private | Swagger | not run |
| `post_enable_2fa` | `POST /enable-2fa` | private | Swagger | not run |
| `post_login_auth` | `POST /login-auth` | public | incomplete | not run |
| `post_logout` | `POST /logout` | private | incomplete | not run |
| `post_password_change` | `POST /password-change` | private | incomplete | not run |
| `post_pay_build` | `POST /pay-build` | private | Swagger | not run |
| `post_refresh_logout` | `POST /refresh-logout` | private | incomplete | not run |
| `post_refresh_token` | `POST /refresh-token` | private | incomplete | not run |
| `post_register_wallbtc` | `POST /register-wallbtc` | private | incomplete | not run |
| `post_reset_password` | `POST /reset-password` | public | Swagger | not run |
| `post_send_email` | `POST /send-email` | private | incomplete | not run |
| `post_set_2fa` | `POST /set-2fa` | private | Swagger | not run |
| `post_set_options` | `POST /set-options` | private | Swagger | not run |
| `post_all_orders_cancel` | `POST /all-orders/cancel` | private | Swagger | not run |
| `post_altyn_client` | `POST /altyn/client` | public | Swagger | not run |
| `post_ccxt_cancel_all_order` | `POST /ccxt/cancel-all-order` | private | Swagger | not run |
| `post_ccxt_cancelorder` | `POST /ccxt/cancelorder` | private | Swagger | not run |
| `post_ccxt_ordercreate` | `POST /ccxt/ordercreate` | private | Swagger | not run |
| `post_ccxt_withdraw` | `POST /ccxt/withdraw` | private | Swagger | not run |
| `post_order_cancel` | `POST /order/cancel` | private | Swagger | not run |
| `post_order_create` | `POST /order/create` | private | Swagger | not run |
| `post_p2p_create_transaction` | `POST /p2p/create-transaction` | private | Swagger | not run |
| `post_p2p_create_transaction_for_p2p` | `POST /p2p/create-transaction-for-p2p` | private | Swagger | not run |
| `post_p2p_create_withdraw` | `POST /p2p/create-withdraw` | private | Swagger | not run |
| `post_p2p_get_balance` | `POST /p2p/get-balance` | private | Swagger | not run |
| `post_p2p_set_p2p_token` | `POST /p2p/set-p2p-token` | private | Swagger | not run |
| `post_p2p_set_token` | `POST /p2p/set-token` | private | Swagger | not run |
| `post_phone_add` | `POST /phone/add` | private | Swagger | not run |
| `post_stock_deposit` | `POST /stock/deposit` | private | incomplete | not run |
| `post_stock_withdraw` | `POST /stock/withdraw` | private | incomplete | not run |
| `post_user_pay_fee_btt` | `POST /user/pay-fee-btt` | private | Swagger | not run |
| `post_webhook_deposit` | `POST /webhook/deposit` | server-only | Swagger | not run |
| `post_withdraw_confirm` | `POST /withdraw/confirm` | private | Swagger | not run |
| `post_withdraw_create` | `POST /withdraw/create` | private | Swagger | not run |
| `post_altyn_payment_sbp` | `POST /altyn/payment/sbp` | public | Swagger | not run |
| `post_deposit_fiat_request` | `POST /deposit/fiat/request` | private | Swagger | not run |
| `post_login_confirmation_code_resend` | `POST /login-confirmation/code/resend` | private | Swagger | not run |
| `post_order_conditional_create` | `POST /order/conditional/create` | private | Swagger | not run |
| `post_user_api_keys_redeem` | `POST /user/api-keys/redeem` | private | Swagger | not run |
| `post_user_api_keys_reset` | `POST /user/api-keys/reset` | private | Swagger | not run |
| `post_user_api_keys_update` | `POST /user/api-keys/update` | private | Swagger | not run |
| `post_user_favourite_add_pair` | `POST /user/favourite/add-pair` | private | Swagger | not run |
| `post_user_favourite_remove_pair` | `POST /user/favourite/remove-pair` | private | Swagger | not run |
| `post_user_verification_documents` | `POST /user/verification/documents` | private | Swagger | not run |
| `post_user_verification_phone` | `POST /user/verification/phone` | private | Swagger | not run |
| `post_user_verification_sms` | `POST /user/verification/sms` | private | incomplete | not run |
| `post_withdraw_confirmation_email` | `POST /withdraw/confirmation/email` | private | Swagger | not run |
| `post_withdraw_confirmation_phone` | `POST /withdraw/confirmation/phone` | private | Swagger | not run |
| `post_user_verification_phone_confirm` | `POST /user/verification/phone/confirm` | private | Swagger | not run |
| `post_deposit_fiat_webhook_by_user_id_by_order_id` | `POST /deposit/fiat/webhook/{userId}/{orderId}` | server-only | incomplete | not run |
| `post_withdraw_fiat_webhook_by_user_id_by_order_id` | `POST /withdraw/fiat/webhook/{userId}/{orderId}` | server-only | incomplete | not run |
| `delete_dev_all_orders_cancel` | `DELETE /dev/all-orders/cancel` | server-only | Swagger | not run |
