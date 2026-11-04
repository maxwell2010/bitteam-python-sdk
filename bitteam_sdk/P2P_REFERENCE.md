# P2P/API-v2 catalog - 2026-11-03

This is the official website client contract, not a validated production schema for all private operations.
Use client.p2p.<operation>(path={}, params={}, data={}); no automatic retries or arbitrary URLs.
Private requests use the general access_token cookie. P2P IDs differ from spot IDs.
Read-only typed snapshots are available through client.get_p2p_accounts() and
client.inspect_p2p_withdrawal(identifier); see docs/P2P_READ_WORKFLOWS.md for
provenance and limitations. General renewal is not established; HTTP401 does
not trigger cookie blacklist/clear, spot refresh or mutation replay; the same
cookie may be used by a subsequent independent call. HTTP401 is not proof of
global expiry. Calls are bound to auth identity
and lifecycle through queue, dispatch and response; logout cancels private
in-flight transport work.

| Operation | Method / path | Private | GET mutation |
|---|---|---|---|
| `create_new_withdraw` | `POST /account/create-withdraw` | True | False |
| `confirm_new_withdraw` | `GET /account/verification-withdraw/{code}` | True | True |
| `create_new_wallet_for_account` | `GET /account/create-wallet/{currency_id}` | True | True |
| `get_active_operations` | `GET /operations/active` | True | False |
| `get_archive_operations` | `GET /operations/archive` | True | False |
| `get_archived_adverts` | `GET /anunt/my-advert` | True | False |
| `get_archive_payment_system` | `GET /user/get-payment-detail` | True | False |
| `send_messages_operation` | `POST /operations/send-message` | True | False |
| `create_operation` | `POST /operations/create` | True | False |
| `get_my_advert` | `GET /anunt/my-advert` | True | False |
| `change_status_all` | `GET /user/change-status-all` | True | True |
| `change_status_advert` | `POST /anunt/change-status-advert` | True | False |
| `get_operation` | `GET /operations/get-operation` | True | False |
| `accept_operation` | `GET /operations/accept-operation` | True | True |
| `pay_operation` | `GET /operations/pay-operation` | True | True |
| `send_coin_operation` | `GET /operations/send-coin-operation` | True | True |
| `cancel_operation` | `GET /operations/cancel-operation` | True | True |
| `dispute_operation` | `POST /operations/dispute-operation` | True | False |
| `save_review_to_user` | `POST /operations/review-operation` | True | False |
| `get_messages_operation` | `GET /operations/get-messages` | True | False |
| `get_messages_support` | `GET /support/ticket/{ticket_id}/messages` | True | False |
| `get_ticket_subjects` | `GET /support/list-subjects` | True | False |
| `get_tickets` | `GET /support/list-tickets` | True | False |
| `send_messages_support` | `POST /support/send-messages` | True | False |
| `create_ticket` | `POST /support/ticket/create` | True | False |
| `get_auth_google` | `GET /user/auth-google-first` | True | True |
| `get_auth_google_active` | `GET /user/auth-google-active` | True | True |
| `get_auth_google_confirm` | `GET /user/auth-google-confirm` | True | True |
| `get_user_payments` | `GET /user/get-payment-detail` | True | False |
| `get_payments_systems_list` | `GET /user/get-payment-systems` | True | False |
| `add_payment_system` | `POST /user/add-payment-systems` | True | False |
| `del_payment_system` | `GET /user/del-payment-systems/{payment_id}` | True | True |
| `get_source_price` | `GET /anunt/get-price-source` | True | False |
| `create_new_advert` | `POST /anunt/create-new-advert` | True | False |
| `get_advert_edit` | `GET /anunt/get-edit-advert/{advert_id}` | True | False |
| `get_subjects` | `GET /chatbot/process` | False | False |
| `get_questions` | `GET /chatbot/process` | False | False |
| `save_advert_edit` | `POST /anunt/save-edit-advert/{advert_id}` | True | False |
| `delete_advert_user` | `GET /anunt/delete-advert/{advert_id}` | True | True |
| `load_user_statistic` | `GET /user/get-user-statistic` | True | False |
| `load_user_review` | `GET /user/get-user-review` | True | False |
| `upload_verification` | `POST /user/verification-user` | True | False |
| `remove_ticket` | `POST /support/ticket/{ticket_id}/close` | True | False |
| `get_answers` | `GET /chatbot/process` | False | False |
| `get_commission_btt` | `GET /commission/list` | False | False |
| `set_language` | `GET /user/set-language` | True | True |
| `update_login` | `POST /user/update-login` | True | False |
| `resend_operation_email` | `GET /account/resend-email/{operation_id}` | True | True |
| `add_advert_to_favorites` | `POST /user/deal-favorites/add` | True | False |
| `delete_advert_from_favorites` | `POST /user/deal-favorites/delete` | True | False |
| `get_favorites_adverts` | `GET /user/deal-favorites/list` | True | False |
| `delete_advert_from_archive` | `GET /anunt/restore-advert/{advert_id}` | True | True |
| `cancel_withdraw` | `GET /account/cancel-withdraw/{withdraw_id}` | True | True |
| `get_user_avatars` | `GET /avatar/index-by-auth-user` | True | False |
| `set_user_avatar` | `POST /avatar/set-active-avatar` | True | False |
| `send_telegram_permission_code` | `POST /telegram/send-telegram-permission-code` | True | False |
| `check_telegram_permission_code` | `POST /telegram/check-telegram-permission-code` | True | False |
| `send_test_message_api` | `POST /telegram/send-message` | True | False |
| `remove_app_token_api` | `POST /user/remove-app-token` | True | False |
| `remove_all_app_token_api` | `POST /user/remove-all-app-token` | True | False |
| `get_cities_list` | `GET /city/get` | False | False |
| `get_accounts` | `GET /auth/user` | True | False |
| `get_withdrawal` | `GET /transactions/get-withdraw-by-id/{withdraw_id}` | True | False |
