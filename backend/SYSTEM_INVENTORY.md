# CLONNECT BACKEND — SYSTEM INVENTORY

> Generated: 2026-02-25 | Purpose: E2E Testing Planning
> 844 .py files | 422 endpoints | 50 DB tables | 203 modules | 3,372 tests

---

## 1. ENDPOINTS (422 total)

### Summary

| Metric | Count |
|--------|-------|
| Total endpoints | 422 |
| Router files | 56 |
| GET | 218 (51.7%) |
| POST | 154 (36.5%) |
| DELETE | 26 (6.2%) |
| PUT | 14 (3.3%) |
| PATCH | 3 (0.7%) |

### Auth Distribution

| Auth Type | Count | % |
|-----------|-------|---|
| None (public) | 263 | 62.3% |
| require_creator_access | 80 | 19.0% |
| require_admin | 54 | 12.8% |
| get_db | 22 | 5.2% |
| get_current_user | 3 | 0.7% |

### Admin Endpoints (89 endpoints, 14 files)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /demo-status | get_demo_status | admin/creators.py | require_admin |
| GET | /creators | admin_list_creators | admin/creators.py | require_admin |
| POST | /creators/{creator_id}/pause | admin_pause_creator | admin/creators.py | require_admin |
| POST | /creators/{creator_id}/resume | admin_resume_creator | admin/creators.py | require_admin |
| POST | /reset-rate-limiter/{creator_id} | admin_reset_rate_limiter | admin/creators.py | require_admin |
| GET | /rate-limiter-stats | admin_rate_limiter_stats | admin/creators.py | require_admin |
| DELETE | /cleanup-test-leads/{creator_id} | cleanup_test_leads | admin/dangerous_lead_ops.py | require_admin |
| DELETE | /delete-lead-by-platform-id/{creator_id}/{platform_user_id} | delete_lead_by_platform_id | admin/dangerous_lead_ops.py | require_admin |
| POST | /cleanup-orphan-leads | cleanup_orphan_leads | admin/dangerous_lead_ops.py | require_admin |
| POST | /reset-db | reset_all_data | admin/dangerous_system_ops.py | require_admin |
| POST | /nuclear-reset | nuclear_reset | admin/dangerous_system_ops.py | require_admin |
| DELETE | /sync-reset/{creator_id} | sync_reset | admin/dangerous_system_ops.py | require_admin |
| DELETE | /clear-messages/{creator_id} | clear_messages | admin/dangerous_system_ops.py | require_admin |
| POST | /reset-demo-data/{creator_id} | reset_demo_data | admin/dangerous_system_ops.py | require_admin |
| POST | /reset-creator/{creator_id} | reset_creator | admin/dangerous_user_ops.py | require_admin |
| DELETE | /creators/{creator_name} | delete_creator | admin/dangerous_user_ops.py | require_admin |
| DELETE | /force-delete-creator/{creator_name} | force_delete_creator | admin/dangerous_user_ops.py | require_admin |
| DELETE | /delete-user/{email} | delete_user_by_email | admin/dangerous_user_ops.py | require_admin |
| GET | /debug-raw-messages/{creator_id}/{username} | debug_raw_messages | admin/debug.py | require_admin |
| GET | /debug-instagram-api/{creator_id} | debug_instagram_api | admin/debug.py | require_admin |
| GET | /debug-sync-logic/{creator_id} | debug_sync_logic | admin/debug.py | require_admin |
| GET | /debug-orphaned-messages/{creator_id} | debug_orphaned_messages | admin/debug.py | require_admin |
| GET | /full-diagnostic/{creator_id} | full_diagnostic | admin/debug.py | require_admin |
| GET | /ingestion/status/{creator_id} | get_ingestion_status | admin/ingestion.py | require_admin |
| POST | /ingestion/refresh-ig-posts/{creator_id} | refresh_ig_posts | admin/ingestion.py | require_admin |
| POST | /ingestion/refresh-content/{creator_id} | refresh_content | admin/ingestion.py | require_admin |
| POST | /ingestion/full-refresh/{creator_id} | full_refresh | admin/ingestion.py | require_admin |
| POST | /content/refresh/{creator_id} | trigger_content_refresh | admin/ingestion.py | require_admin |
| GET | /content/refresh/status | get_content_refresh_status | admin/ingestion.py | require_admin |
| POST | /rescore-leads/{creator_id} | rescore_leads | admin/leads.py | require_admin |
| GET | /lead-categories | get_lead_categories | admin/leads.py | require_admin |
| GET | /ghost-stats/{creator_id} | get_ghost_stats | admin/leads.py | require_admin |
| POST | /ghost-reactivate/{creator_id} | reactivate_ghosts | admin/leads.py | require_admin |
| POST | /ghost-config | configure_ghost_reactivation | admin/leads.py | require_admin |
| GET | /ghost-config | get_ghost_config | admin/leads.py | require_admin |
| GET | /diagnose-duplicate-leads/{creator_id} | diagnose_duplicate_leads | admin/leads.py | require_admin |
| POST | /merge-duplicate-leads/{creator_id} | merge_duplicate_leads | admin/leads.py | require_admin |
| GET | /stats | admin_global_stats | admin/stats.py | require_admin |
| GET | /conversations | admin_all_conversations | admin/stats.py | require_admin |
| GET | /pending-messages | admin_pending_messages | admin/stats.py | require_admin |
| GET | /alerts | admin_recent_alerts | admin/stats.py | require_admin |
| GET | /feature-flags | admin_feature_flags | admin/stats.py | require_admin |
| POST | /fix-lead-timestamps/{creator_id} | fix_lead_timestamps | admin/sync_dm/fix_operations.py | require_admin |
| POST | /apply-unique-constraint | apply_unique_constraint | admin/sync_dm/fix_operations.py | require_admin |
| POST | /fix-instagram-page-id/{creator_id} | fix_instagram_page_id | admin/sync_dm/fix_operations.py | require_admin |
| POST | /add-instagram-id/{creator_id}/{instagram_id} | add_instagram_id | admin/sync_dm/fix_operations.py | require_admin |
| POST | /fix-lead-duplicates | fix_lead_duplicates | admin/sync_dm/fix_operations.py | require_admin |
| POST | /generate-thumbnails/{creator_id} | generate_thumbnails | admin/sync_dm/media_operations.py | require_admin |
| POST | /update-profile-pics/{creator_id} | update_profile_pics | admin/sync_dm/media_operations.py | require_admin |
| POST | /generate-link-previews/{creator_id} | generate_link_previews | admin/sync_dm/media_operations.py | require_admin |
| POST | /run-migration/email-capture | run_email_capture_migration | admin/sync_dm/migration_operations.py | require_admin |
| POST | /test-ingestion-v2/{creator_id} | test_ingestion_v2 | admin/sync_dm/migration_operations.py | require_admin |
| POST | /backup | admin_create_backup | admin/sync_dm/migration_operations.py | require_admin |
| GET | /backups | admin_list_backups | admin/sync_dm/migration_operations.py | require_admin |
| POST | /clean-and-sync/{creator_id} | clean_and_sync | admin/sync_dm/sync_operations.py | require_admin |
| POST | /simple-dm-sync/{creator_id} | simple_dm_sync | admin/sync_dm/sync_operations.py | require_admin |
| POST | /start-sync/{creator_id} | start_sync | admin/sync_dm/sync_operations.py | require_admin |
| GET | /sync-status/{creator_id} | sync_status | admin/sync_dm/sync_operations.py | require_admin |
| POST | /sync-continue/{creator_id} | sync_continue | admin/sync_dm/sync_operations.py | require_admin |
| POST | /sync-leads/{creator_id} | sync_leads_from_conversations | admin/sync_dm/sync_operations.py | require_admin |
| POST | /test-full-sync/{creator_id}/{username} | test_full_sync_conversation | admin/sync_dm/test_operations.py | require_admin |
| POST | /test-shared-post/{creator_id}/{lead_id} | insert_test_shared_post | admin/sync_dm/test_operations.py | require_admin |
| GET | /oauth/status/{creator_id} | get_oauth_status | admin/tokens.py | require_admin |
| POST | /refresh-all-tokens | refresh_all_instagram_tokens | admin/tokens.py | require_admin |
| POST | /refresh-token/{creator_id} | refresh_creator_token | admin/tokens.py | require_admin |
| POST | /exchange-token/{creator_id} | exchange_short_lived_token | admin/tokens.py | require_admin |
| POST | /set-token/{creator_id} | set_creator_token | admin/tokens.py | require_admin |
| POST | /set-page-token/{creator_id} | set_page_access_token | admin/tokens.py | require_admin |
| POST | /fix-instagram-ids/{creator_id} | fix_instagram_ids | admin/tokens.py | require_admin |
| POST | /instagram/subscribe-feed | subscribe_to_feed_webhooks | admin/tokens.py | require_admin |

### Messaging & Webhooks (23 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /webhook/instagram | instagram_webhook_verify | messaging_webhooks/instagram_webhook.py | None |
| POST | /webhook/instagram | instagram_webhook_receive | messaging_webhooks/instagram_webhook.py | None |
| GET | /instagram/status | instagram_status | messaging_webhooks/instagram_webhook.py | None |
| POST | /webhook/instagram/comments | instagram_comments_webhook | messaging_webhooks/instagram_webhook.py | None |
| POST | /webhook/telegram | telegram_webhook | messaging_webhooks/telegram_webhook.py | None |
| POST | /telegram/webhook | telegram_webhook_legacy | messaging_webhooks/telegram_webhook.py | None |
| GET | /webhook/whatsapp | whatsapp_webhook_verify | messaging_webhooks/whatsapp_webhook.py | None |
| POST | /webhook/whatsapp | whatsapp_webhook_receive | messaging_webhooks/whatsapp_webhook.py | None |
| GET | /whatsapp/status | whatsapp_status | messaging_webhooks/whatsapp_webhook.py | None |
| POST | /admin/whatsapp/test-message | whatsapp_test_message | messaging_webhooks/whatsapp_webhook.py | None |
| POST | /webhook/whatsapp/evolution | evolution_webhook | messaging_webhooks/evolution_webhook.py | None |
| GET | /webhook (legacy) | instagram_webhook_verify | instagram/webhook.py | None |
| POST | /webhook (legacy) | instagram_webhook_receive | instagram/webhook.py | None |
| POST | /webhook/stories | instagram_stories_webhook | instagram/webhook.py | None |
| POST | /stripe | stripe_webhook | webhooks.py | None |
| POST | /hotmart | hotmart_webhook | webhooks.py | None |
| POST | /paypal | paypal_webhook | webhooks.py | None |
| POST | /calendly | calendly_webhook | webhooks.py | None |
| POST | /calcom | calcom_webhook | webhooks.py | None |

### Copilot (17 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /{creator_id}/pending | get_pending_responses | copilot/actions.py | require_creator_access |
| POST | /{creator_id}/approve/{message_id} | approve_response | copilot/actions.py | require_creator_access |
| POST | /{creator_id}/discard/{message_id} | discard_response | copilot/actions.py | require_creator_access |
| POST | /{creator_id}/discard-all | discard_all_pending | copilot/actions.py | require_creator_access |
| PUT | /{creator_id}/toggle | toggle_copilot_mode | copilot/actions.py | require_creator_access |
| POST | /{creator_id}/approve-all | approve_all_pending | copilot/actions.py | require_creator_access |
| POST | /{creator_id}/manual/{lead_id} | track_manual_response | copilot/actions.py | require_creator_access |
| POST | /{creator_id}/preference-pairs/mark-exported | mark_pairs_exported | copilot/actions.py | require_creator_access |
| GET | /{creator_id}/status | get_copilot_status | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/notifications | get_notifications | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/pending-for-lead/{lead_id} | get_pending_for_lead | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/stats | get_copilot_stats | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/learning-progress | get_learning_progress | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/comparisons | get_copilot_comparisons | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/history | get_copilot_history | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/historical-rates | get_historical_rates | copilot/analytics.py | require_creator_access |
| GET | /{creator_id}/preference-pairs | get_preference_pairs | copilot/analytics.py | require_creator_access |

### Leads (21 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /{creator_id} | get_leads | leads/crud.py | require_creator_access |
| GET | /{creator_id}/{lead_id} | get_lead | leads/crud.py | require_creator_access |
| POST | /{creator_id} | create_lead | leads/crud.py | require_creator_access |
| POST | /{creator_id}/manual | create_manual_lead | leads/crud.py | require_creator_access |
| PUT | /{creator_id}/{lead_id} | update_lead | leads/crud.py | require_creator_access |
| DELETE | /{creator_id}/{lead_id} | delete_lead | leads/crud.py | require_creator_access |
| PUT | /{creator_id}/{lead_id}/status | update_lead_status | leads/crud.py | require_creator_access |
| GET | /{creator_id}/{lead_id}/activities | get_lead_activities | leads/actions.py | require_creator_access |
| POST | /{creator_id}/{lead_id}/activities | create_lead_activity | leads/actions.py | require_creator_access |
| DELETE | /{creator_id}/{lead_id}/activities/{activity_id} | delete_lead_activity | leads/actions.py | require_creator_access |
| GET | /{creator_id}/{lead_id}/tasks | get_lead_tasks | leads/actions.py | require_creator_access |
| POST | /{creator_id}/{lead_id}/tasks | create_lead_task | leads/actions.py | require_creator_access |
| PUT | /{creator_id}/{lead_id}/tasks/{task_id} | update_lead_task | leads/actions.py | require_creator_access |
| DELETE | /{creator_id}/{lead_id}/tasks/{task_id} | delete_lead_task | leads/actions.py | require_creator_access |
| GET | /{creator_id}/{lead_id}/stats | get_lead_stats | leads/actions.py | require_creator_access |
| GET | /{creator_id}/escalations | get_escalation_alerts | leads/escalations.py | require_creator_access |
| PUT | /{creator_id}/escalations/{follower_id}/read | mark_escalation_read | leads/escalations.py | require_creator_access |
| DELETE | /{creator_id}/escalations | clear_escalations | leads/escalations.py | require_creator_access |
| GET | /{creator_id}/unified | list_unified_leads | unified_leads.py | None |
| GET | /{creator_id}/unified/{unified_id} | get_unified_lead | unified_leads.py | None |
| POST | /{creator_id}/merge | merge_leads | unified_leads.py | None |

### OAuth (16 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /instagram/start | instagram_oauth_start | oauth/instagram.py | None |
| GET | /instagram/callback | instagram_oauth_callback | oauth/instagram.py | None |
| GET | /debug | oauth_debug | oauth/instagram.py | None |
| GET | /google/start | google_oauth_start | oauth/google.py | None |
| GET | /google/callback | google_oauth_callback | oauth/google.py | None |
| POST | /refresh/google/{creator_id} | force_refresh_google | oauth/google.py | None |
| GET | /stripe/start | stripe_oauth_start | oauth/stripe.py | None |
| GET | /stripe/callback | stripe_oauth_callback | oauth/stripe.py | None |
| GET | /stripe/refresh | stripe_oauth_refresh | oauth/stripe.py | None |
| GET | /paypal/start | paypal_oauth_start | oauth/paypal.py | None |
| GET | /paypal/callback | paypal_oauth_callback | oauth/paypal.py | None |
| GET | /whatsapp/start | whatsapp_oauth_start | oauth/whatsapp.py | None |
| GET | /whatsapp/callback | whatsapp_oauth_callback | oauth/whatsapp.py | None |
| GET | /whatsapp/config | whatsapp_get_config | oauth/whatsapp.py | None |
| POST | /whatsapp/embedded-signup | whatsapp_embedded_signup | oauth/whatsapp.py | None |
| GET | /status/{creator_id} | get_oauth_status | oauth/status.py | None |

### Onboarding (24 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| POST | /magic-slice/quick | quick_onboard | onboarding/pipeline.py | None |
| POST | /magic-slice/creator | full_onboard | onboarding/pipeline.py | None |
| GET | /magic-slice/{creator_id}/status | get_magic_slice_status | onboarding/pipeline.py | None |
| DELETE | /magic-slice/{creator_id}/reset | reset_magic_slice_data | onboarding/pipeline.py | require_admin |
| POST | /whatsapp/trigger/{creator_id}/{instance_name} | trigger_whatsapp_onboarding | onboarding/pipeline.py | None |
| POST | /whatsapp/retrigger-phase/{creator_id} | retrigger_whatsapp_phase | onboarding/pipeline.py | None |
| GET | /whatsapp/status/{creator_id} | whatsapp_onboarding_status | onboarding/pipeline.py | None |
| POST | /full-setup/{creator_id} | start_full_setup | onboarding/pipeline.py | None |
| GET | /full-setup/{creator_id}/progress | get_full_setup_progress | onboarding/pipeline.py | None |
| POST | /complete | complete_wizard_onboarding | onboarding/clone.py | None |
| POST | /start-clone | start_clone_creation | onboarding/clone.py | None |
| GET | /progress/{creator_id} | get_clone_progress | onboarding/clone.py | None |
| POST | /sync-instagram-dms | sync_instagram_dms | onboarding/dm_sync.py | None |
| POST | /sync-instagram-dms-background | sync_instagram_dms_background | onboarding/dm_sync.py | None |
| GET | /sync-instagram-dms-status/{job_id} | get_dm_sync_status | onboarding/dm_sync.py | None |
| GET | /sync-instagram-dms-jobs/{creator_id} | list_dm_sync_jobs | onboarding/dm_sync.py | None |
| POST | /extraction/{creator_id}/start | start_extraction | onboarding/extraction.py | None |
| GET | /extraction/{creator_id}/progress | get_extraction_progress | onboarding/extraction.py | None |
| POST | /extraction/{creator_id}/run | run_extraction_sync | onboarding/extraction.py | None |
| GET | /{creator_id}/status | get_onboarding_status | onboarding/progress.py | None |
| GET | /{creator_id}/visual-status | get_visual_onboarding_status | onboarding/progress.py | None |
| POST | /{creator_id}/complete | complete_visual_onboarding | onboarding/progress.py | None |
| DELETE | /full-reset/{creator_id} | full_reset_creator | onboarding/setup.py | require_admin |
| GET | /verification/{creator_id} | verify_onboarding | onboarding/verification.py | require_creator_access |

### DM & Conversations (17 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| POST | /process | process_dm | dm/processing.py | None |
| POST | /send/{creator_id} | send_manual_message | dm/processing.py | None |
| POST | /send-media/{creator_id} | send_media_message | dm/processing.py | None |
| GET | /conversations/{creator_id} | get_conversations | dm/conversations.py | None |
| POST | /conversations/{creator_id}/{follower_id}/mark-read | mark_conversation_read | dm/conversations.py | None |
| POST | /conversations/{creator_id}/{conversation_id}/archive | archive_conversation_endpoint | dm/conversations.py | None |
| POST | /conversations/{creator_id}/{conversation_id}/spam | mark_conversation_spam_endpoint | dm/conversations.py | None |
| DELETE | /conversations/{creator_id}/{conversation_id} | delete_conversation_endpoint | dm/conversations.py | None |
| GET | /conversations/{creator_id}/archived | get_archived_conversations | dm/conversations.py | None |
| POST | /conversations/{creator_id}/{conversation_id}/restore | restore_conversation | dm/conversations.py | None |
| POST | /conversations/{creator_id}/reset | reset_conversations | dm/conversations.py | None |
| POST | /conversations/{creator_id}/sync-messages | sync_messages_from_json_endpoint | dm/conversations.py | None |
| POST | /conversations/{creator_id}/sync-timestamps | sync_last_contact_timestamps | dm/conversations.py | None |
| GET | /follower/{creator_id}/{follower_id} | get_follower_detail | dm/followers.py | None |
| PUT | /follower/{creator_id}/{follower_id}/status | update_follower_status | dm/followers.py | None |
| GET | /debug/{creator_id} | debug_messages | dm/debug.py | None |
| GET | /metrics/{creator_id} | get_dm_metrics | dm/debug.py | None |

### Content & Knowledge (21 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| POST | /add | add_content | content.py | None |
| GET | /search | search_content | content.py | None |
| POST | /reload | content_reload_post | content.py | None |
| GET | /stats | content_stats | content.py | None |
| POST | /setup-pgvector | setup_pgvector_endpoint | content.py | None |
| POST | /generate-embeddings | generate_embeddings_for_existing | content.py | None |
| DELETE | /{creator_id}/clear | clear_content | content.py | None |
| POST | /bulk-load | bulk_load_content | content.py | None |
| GET | /{creator_id}/knowledge | get_knowledge | knowledge.py | None |
| GET | /{creator_id}/knowledge/faqs | get_faqs | knowledge.py | None |
| POST | /{creator_id}/knowledge/faqs | add_faq | knowledge.py | None |
| PUT | /{creator_id}/knowledge/faqs/{item_id} | update_faq | knowledge.py | None |
| DELETE | /{creator_id}/knowledge/faqs/{item_id} | delete_faq | knowledge.py | None |
| GET | /{creator_id}/knowledge/about | get_about | knowledge.py | None |
| PUT | /{creator_id}/knowledge/about | update_about | knowledge.py | None |
| POST | /index | index_posts | citations.py | None |
| GET | /{creator_id}/stats | get_index_stats | citations.py | None |
| POST | /search | search_content | citations.py | None |
| POST | /instagram | ingest_instagram_v2_endpoint | ingestion_v2/instagram_ingest.py | None |
| POST | /website | ingest_website_v2 | ingestion_v2/website.py | get_db |
| POST | /youtube | ingest_youtube_v2_endpoint | ingestion_v2/youtube.py | None |

### Calendar & Booking (22 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /{creator_id}/bookings | get_bookings | calendar.py | require_creator_access |
| GET | /{creator_id}/stats | get_calendar_stats | calendar.py | require_creator_access |
| GET | /{creator_id}/links | get_booking_links | calendar.py | require_creator_access |
| POST | /{creator_id}/links | create_booking_link | calendar.py | require_creator_access |
| PUT | /{creator_id}/links/{link_id} | update_booking_link | calendar.py | require_creator_access |
| DELETE | /{creator_id}/links/{link_id} | delete_booking_link | calendar.py | require_creator_access |
| DELETE | /{creator_id}/bookings/reset | reset_bookings | calendar.py | require_creator_access |
| POST | /{creator_id}/bookings/{booking_id}/complete | mark_booking_completed | calendar.py | require_creator_access |
| POST | /{creator_id}/bookings/{booking_id}/no-show | mark_booking_no_show | calendar.py | require_creator_access |
| GET | /availability/{creator_id} | get_availability | booking.py | get_db |
| POST | /availability/{creator_id} | set_availability | booking.py | get_db |
| GET | /{creator_id}/slots | get_available_slots | booking.py | get_db |
| POST | /{creator_id}/reserve | reserve_slot | booking.py | get_db |
| POST | /{creator_id}/cancel/{booking_id} | cancel_booking | booking.py | get_db |

### Nurturing (15 endpoints)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /{creator_id}/followups | get_nurturing_followups | nurturing/followups.py | require_creator_access |
| GET | /{creator_id}/stats | get_nurturing_stats | nurturing/followups.py | require_creator_access |
| POST | /{creator_id}/run | run_nurturing_followups | nurturing/followups.py | require_creator_access |
| GET | /{creator_id}/sequences | get_nurturing_sequences | nurturing/sequences.py | require_creator_access |
| POST | /{creator_id}/sequences/{sequence_type}/toggle | toggle_nurturing_sequence | nurturing/sequences.py | require_creator_access |
| PUT | /{creator_id}/sequences/{sequence_type} | update_nurturing_sequence | nurturing/sequences.py | require_creator_access |
| GET | /{creator_id}/sequences/{sequence_type}/enrolled | get_enrolled_followers | nurturing/sequences.py | require_creator_access |
| DELETE | /{creator_id}/cancel/{follower_id} | cancel_nurturing | nurturing/sequences.py | require_creator_access |
| GET | /scheduler/status | get_scheduler_status | nurturing/scheduler.py | require_admin |
| POST | /scheduler/run-now | run_scheduler_now | nurturing/scheduler.py | require_admin |
| GET | /reconciliation/status | get_reconciliation_status | nurturing/scheduler.py | require_admin |
| GET | /reconciliation/health | check_reconciliation_health | nurturing/scheduler.py | require_admin |
| POST | /reconciliation/run-now | run_reconciliation_now | nurturing/scheduler.py | require_admin |

### Remaining Endpoints (products, payments, config, health, etc.)

| Method | Path | Function | File | Auth |
|--------|------|----------|------|------|
| GET | /{creator_id}/products | get_products | products.py | require_creator_access |
| POST | /{creator_id}/products | create_product | products.py | require_creator_access |
| PUT | /{creator_id}/products/{product_id} | update_product | products.py | require_creator_access |
| DELETE | /{creator_id}/products/{product_id} | delete_product | products.py | require_creator_access |
| GET | /{creator_id}/revenue | get_revenue_stats | payments.py | None |
| GET | /{creator_id}/purchases | get_purchases | payments.py | None |
| POST | /{creator_id}/purchases | record_purchase | payments.py | None |
| POST | /{creator_id}/attribute | attribute_sale | payments.py | None |
| GET | /{creator_id} | get_creator_config | config.py | require_creator_access |
| PUT | /{creator_id} | update_creator_config | config.py | require_creator_access |
| GET | /{creator_id}/email-capture | get_email_capture_config | config.py | require_creator_access |
| POST | /{creator_id}/email-capture | update_email_capture_config | config.py | require_creator_access |
| GET | /health | health | health.py | None |
| GET | /health/live | health_live | health.py | None |
| GET | /health/ready | health_ready | health.py | None |
| GET | /health/llm | health_llm | health.py | None |
| GET | /health/cache | health_cache | health.py | None |
| GET | /health/tasks | task_health | health.py | None |
| GET | /{creator_id}/overview | dashboard_overview | dashboard.py | None |
| PUT | /{creator_id}/toggle | toggle_clone | dashboard.py | None |
| GET | /{creator_id}/{lead_id} | get_lead_memories | memory.py | require_creator_access |
| DELETE | /{creator_id}/{lead_id} | forget_lead_memories | memory.py | require_creator_access |
| POST | /{creator_id}/consolidate | consolidate_memories | memory.py | require_creator_access |
| GET | /{creator_id}/export/{follower_id} | gdpr_export_data | gdpr.py | None |
| DELETE | /{creator_id}/delete/{follower_id} | gdpr_delete_data | gdpr.py | None |
| POST | /{creator_id}/anonymize/{follower_id} | gdpr_anonymize_data | gdpr.py | None |
| GET | /{creator_id} | event_stream | events.py | None |
| POST | /generate-rules | generate_ai_rules | ai.py | get_current_user |
| POST | /generate-knowledge | generate_ai_knowledge | ai.py | get_current_user |
| POST | /transcribe | transcribe_audio | audio.py | None |
| GET | /{creator_id}/today | get_today_mission | insights.py | get_db |
| GET | /{creator_id}/weekly | get_weekly_insights | insights.py | get_db |
| GET | /{creator_id}/dashboard | get_intelligent_dashboard | intelligence.py | get_db |
| GET | /{creator_id}/predictions | get_predictions | intelligence.py | get_db |
| GET | /{creator_id}/recommendations | get_recommendations | intelligence.py | get_db |
| GET | /dashboard/{creator_id} | get_metrics_dashboard | metrics.py | None |
| GET | /{creator_id} | get_latest_score | clone_score.py | require_creator_access |
| POST | /{creator_id}/evaluate | trigger_evaluation | clone_score.py | require_creator_access |

---

## 2. CORE SERVICES

### Summary

| Category | Classes | Public Methods | Module Functions | Total |
|----------|---------|---------------|-----------------|-------|
| core/ | 152 | ~800 | 306 | ~1,106 |
| services/ | 119 | ~450 | 148 | ~598 |
| **Total** | **271** | **~1,250** | **454** | **~1,704** |

### Key Core Classes

| Class | File | Public Methods |
|-------|------|----------------|
| DMResponderAgentV2 | core/dm/agent.py | add_knowledge, add_knowledge_batch, clear_knowledge, get_stats, health_check |
| InstagramHandler | core/instagram_handler.py | verify_webhook, get_status, get_recent_messages, get_recent_responses |
| CreatorConfigManager | core/creator_config.py | create_config, get_config, update_config, delete_config, list_creators, generate_system_prompt |
| CreatorData | core/creator_data_loader.py | get_known_prices, get_known_links, get_product_by_name, get_featured_product, to_dict |
| OnboardingService | core/onboarding_service.py | onboard_creator, get_onboarding_status, get_onboarding_progress |
| CopilotService | core/copilot/service.py | is_copilot_enabled, auto_discard_pending_for_lead, invalidate_copilot_cache |
| NurturingManager | core/nurturing/manager.py | schedule_followup, get_pending_followups, mark_as_sent, cancel_followups, get_stats |
| PaymentManager | core/payments/manager.py | verify_stripe_signature, get_customer_purchases, attribute_sale_to_bot, get_revenue_stats |
| CalendarManager | core/calendar/manager.py | get_booking_link, create_booking_link, get_bookings, get_booking_stats |
| GDPRManager | core/gdpr/manager.py | record_consent, export_user_data, delete_user_data, anonymize_user_data |
| SemanticRAG | core/rag/semantic.py | add_document, search, delete_document, load_from_db |
| BM25Retriever | core/rag/bm25.py | add_document, search, remove_document, get_stats |
| FrustrationDetector | core/frustration_detector.py | analyze_message, get_frustration_context |
| IntentClassifier | core/intent_classifier.py | classify_intent_simple |
| ProductManager | core/products.py | add_product, get_products, search_products, recommend_product |
| NotificationService | core/notifications.py | send_escalation, send_slack, send_email, send_telegram |
| SalesTracker | core/sales_tracker.py | record_click, record_sale, get_stats, get_follower_journey |
| TelegramAdapter | core/telegram_adapter.py | get_status, get_recent_messages, get_recent_responses |
| WhatsAppHandler | core/whatsapp/handler.py | verify_webhook, get_status, get_recent_messages |
| TaskScheduler | core/task_scheduler.py | register, health_report |

### Key Services Classes

| Class | File | Public Methods |
|-------|------|----------------|
| LLMService | services/llm_service.py | get_available_models, get_stats, switch_provider, complete |
| ResponseVariatorV2 | services/response_variator_v2.py | try_pool_response, try_multi_bubble, get_pools_for_creator |
| RelationshipDNAService | services/relationship_dna_service.py | get_dna_for_lead, get_prompt_instructions, analyze_and_update_dna |
| RelationshipAdapter | services/relationship_adapter.py | get_relational_context, get_profile_for_status |
| EdgeCaseHandler | services/edge_case_handler.py | detect, should_admit_unknown, process_with_context |
| MessageSplitter | services/message_splitter.py | should_split, split, get_total_delay |
| ConversationMemoryService | services/memory_service.py | detect_past_reference, extract_facts, get_memory_context_for_prompt |
| LeadService | services/lead_service.py | calculate_score, determine_stage, get_full_score |
| PromptBuilder | services/prompt_service.py | build_system_prompt, build_user_context, build_complete_prompt |
| TimingService | services/timing_service.py | calculate_delay, is_active_hours, should_delay_response |
| CloudinaryService | services/cloudinary_service.py | upload_from_url, upload_from_file, delete |
| CommitmentTrackerService | services/commitment_tracker.py | detect_and_store, get_pending_for_lead, mark_fulfilled |
| BotOrchestrator | services/bot_orchestrator.py | orchestrate |
| MetaRetryQueue | services/meta_retry_queue.py | get_stats, get_pending |
| CloneScoreEngine | services/clone_score_engine.py | score_response |

---

## 3. DATABASE MODELS (50 tables)

### Summary by Domain

| Domain | Tables | Key Tables |
|--------|--------|------------|
| Auth | 2 | users, user_creators |
| Creator | 6 | creators, tone_profiles, style_profiles, personality_docs, creator_availability, relationship_dna |
| Lead | 8 | leads, unified_leads, lead_activities, lead_tasks, lead_intelligence, lead_memories, dismissed_leads, unmatched_webhooks |
| Message | 6 | messages, conversation_states, conversation_summaries, conversation_embeddings, commitments, pending_messages |
| Product | 2 | products, product_analytics |
| Content | 6 | content_chunks, instagram_posts, post_contexts, content_performance, rag_documents, knowledge_base |
| Analytics | 6 | creator_metrics_daily, predictions, recommendations, detected_topics, weekly_reports, csat_ratings |
| Booking | 3 | booking_links, calendar_bookings, booking_slots |
| Learning | 7 | copilot_evaluations, learning_rules, gold_examples, pattern_analysis_runs, preference_pairs, clone_score_evaluations, clone_score_test_sets |
| Nurturing | 2 | nurturing_sequences, email_ask_tracking |
| Profile | 4 | unified_profiles, platform_identities, follower_memories, user_profiles |
| Sync | 2 | sync_queue, sync_state |

### All Tables with Key Columns

#### Auth
| Table | Key Columns |
|-------|-------------|
| `users` | id (UUID), email (unique), password_hash, name, is_active, is_admin |
| `user_creators` | id (UUID), user_id (FK users), creator_id (FK creators), role |

#### Creator
| Table | Key Columns |
|-------|-------------|
| `creators` | id (UUID), email, name (indexed), api_key (unique), bot_active, instagram_token, instagram_page_id (indexed), instagram_user_id (indexed), whatsapp_phone_id (indexed), copilot_mode, clone_status, clone_progress (JSON) |
| `tone_profiles` | id (UUID), creator_id (unique), profile_data (JSON), confidence_score |
| `style_profiles` | id (UUID), creator_id (FK creators), profile_data (JSONB), version, confidence |
| `personality_docs` | id (UUID), creator_id, doc_type, content (Text) |
| `creator_availability` | id (UUID), creator_id, day_of_week, start_time, end_time, is_active |
| `relationship_dna` | id (UUID), creator_id, follower_id, relationship_type, trust_score, vocabulary_uses (JSON), bot_instructions (Text), golden_examples (JSON) |

#### Lead
| Table | Key Columns |
|-------|-------------|
| `leads` | id (UUID), creator_id (FK, indexed), unified_lead_id (FK), platform, platform_user_id (indexed), username, status, score, purchase_intent, relationship_type, email, deal_value |
| `unified_leads` | id (UUID), creator_id (FK), display_name, email, phone, unified_score, status, merge_history (JSON) |
| `lead_activities` | id (UUID), lead_id (FK, indexed), activity_type, description, old_value, new_value |
| `lead_tasks` | id (UUID), lead_id (FK, indexed), title, task_type, priority, status, due_date |
| `lead_intelligence` | id (PK), creator_id, lead_id, engagement_score, intent_score, conversion_probability, churn_risk, recommended_action |
| `lead_memories` | id (UUID), creator_id (FK), lead_id (FK), fact_type, fact_text, confidence, is_active |
| `dismissed_leads` | id (UUID), creator_id (FK), platform_user_id, username, reason |
| `unmatched_webhooks` | id (UUID), instagram_ids (JSONB), payload_summary (JSONB), resolved |

#### Message
| Table | Key Columns |
|-------|-------------|
| `messages` | id (UUID), lead_id (FK, indexed), role, content (Text), intent, status, suggested_response, copilot_action, confidence_score, platform_message_id (indexed) |
| `conversation_states` | id (UUID), creator_id (indexed), follower_id (indexed), phase, message_count, context (JSON) |
| `conversation_summaries` | id (UUID), creator_id (FK), lead_id (FK), summary_text, key_topics (JSONB), commitments_made (JSONB) |
| `conversation_embeddings` | id (PK), creator_id (indexed), follower_id (indexed), content, msg_metadata (JSON) |
| `commitments` | id (UUID), creator_id, lead_id, commitment_text, commitment_type, due_date, status |
| `pending_messages` | id (UUID), creator_id (FK, indexed), content, lead_id (FK), attempt_count, status |

#### Product
| Table | Key Columns |
|-------|-------------|
| `products` | id (UUID), creator_id (FK, indexed), name, description, price, currency, payment_link, is_active, confidence |
| `product_analytics` | id (PK), product_id, creator_id (indexed), date, mentions, conversions, revenue |

#### Content
| Table | Key Columns |
|-------|-------------|
| `content_chunks` | id (UUID), creator_id (indexed), chunk_id, content, source_type, source_url |
| `instagram_posts` | id (UUID), creator_id (indexed), post_id, caption, permalink, media_type, likes_count |
| `rag_documents` | id (UUID), creator_id (FK, indexed), doc_id (indexed), content, source_type, embedding_model |
| `knowledge_base` | id (UUID), creator_id (FK, indexed), question, answer |
| `content_performance` | id (PK), creator_id (indexed), content_id, engagement_rate, dms_generated_24h, leads_generated |
| `post_contexts` | id (UUID), creator_id, active_promotion, promotion_deadline, recent_topics (JSON) |

#### Analytics
| Table | Key Columns |
|-------|-------------|
| `creator_metrics_daily` | id (PK), creator_id (indexed), date, total_conversations, total_messages, unique_users, conversions, revenue |
| `predictions` | id (PK), creator_id (indexed), prediction_type, predicted_value, confidence, actual_value |
| `recommendations` | id (PK), creator_id (indexed), category, priority, title, expected_impact (JSON) |
| `detected_topics` | id (PK), creator_id (indexed), topic_label, message_count, growth_rate |
| `weekly_reports` | id (PK), creator_id (indexed), week_start, metrics_summary (JSON), executive_summary |
| `csat_ratings` | id (UUID), lead_id (FK, unique), creator_id (FK), rating, feedback |

#### Booking
| Table | Key Columns |
|-------|-------------|
| `booking_links` | id (UUID), creator_id (indexed), meeting_type, title, duration_minutes, platform, url, price |
| `calendar_bookings` | id (UUID), creator_id (indexed), follower_id, status, scheduled_at, guest_email, meeting_url |
| `booking_slots` | id (UUID), creator_id (indexed), service_id (FK), date, start_time, end_time, status |

#### Learning
| Table | Key Columns |
|-------|-------------|
| `learning_rules` | id (UUID), creator_id (FK), rule_text, pattern, example_bad, example_good, confidence, is_active |
| `gold_examples` | id (UUID), creator_id (FK), user_message, creator_response, intent, quality_score |
| `preference_pairs` | id (UUID), creator_id (FK), chosen, rejected, user_message, intent, action_type |
| `copilot_evaluations` | id (UUID), creator_id (FK), eval_type, metrics (JSON), patterns (JSON) |
| `pattern_analysis_runs` | id (UUID), creator_id (FK), status, pairs_analyzed, rules_created |
| `clone_score_evaluations` | id (UUID), creator_id (FK), overall_score, dimension_scores (JSONB) |
| `clone_score_test_sets` | id (UUID), creator_id (FK), name, test_pairs (JSONB), is_active |

#### Nurturing, Profile, Sync
| Table | Key Columns |
|-------|-------------|
| `nurturing_sequences` | id (UUID), creator_id (FK, indexed), type, name, is_active, steps (JSON) |
| `email_ask_tracking` | id (UUID), creator_id (FK, indexed), platform_user_id (indexed), ask_level, captured_email |
| `unified_profiles` | id (UUID), email (unique, indexed), name, phone |
| `platform_identities` | id (UUID), unified_profile_id (FK), creator_id (FK), platform, platform_user_id |
| `follower_memories` | id (UUID), creator_id (indexed), follower_id (indexed), interests (JSON), products_discussed (JSON), purchase_intent_score |
| `user_profiles` | id (UUID), creator_id (indexed), user_id (indexed), preferences (JSON), interests (JSON) |
| `sync_queue` | id (PK), creator_id (indexed), conversation_id, status, attempts |
| `sync_state` | creator_id (PK), status, conversations_synced, conversations_total, messages_saved |

---

## 4. FLUJOS E2E CRITICOS

### Flow 1: Instagram Webhook (DM Reception & Processing)

**Entry:** `POST /webhook/instagram` -- `api/routers/messaging_webhooks/instagram_webhook.py`

```
1. instagram_webhook_receive()  →  messaging_webhooks/instagram_webhook.py
2. extract_all_instagram_ids()  →  core/webhook_routing.py
3. find_creator_for_webhook()   →  core/webhook_routing.py
4. update_creator_webhook_stats()  →  core/webhook_routing.py
5. get_handler_for_creator()    →  api/routers/instagram/__init__.py
6. InstagramHandler.handle_webhook()  →  core/instagram_handler.py
7. handle_webhook_impl()        →  core/instagram_modules/webhook.py
8. _extract_messages()          →  core/instagram_modules/webhook.py
9. handler.process_message()    →  core/instagram_modules/media.py
10. DMResponderAgentV2.process() →  core/dm_agent_v2.py
    (5-phase pipeline: detection → context → prompt → generation → postprocessing)
11. dispatch_response()          →  core/instagram_modules/dispatch.py
    - Copilot: copilot.create_pending_response()  →  core/copilot/lifecycle.py
    - Autopilot: handler.send_response()  →  core/instagram_modules/message_sender.py
12. _save_messages_to_db()       →  core/instagram_modules/message_store.py
13. _enrich_new_lead()           →  core/instagram_modules/message_store.py
14. update_follower_memory()     →  core/dm/post_response.py
```

**DB:** creators, leads, messages, conversations
**External:** Meta Graph API, OpenAI API, PostgreSQL + pgvector

---

### Flow 2: OAuth Flow (Instagram Connection)

**Entry:** `GET /oauth/instagram/login` + `GET /oauth/instagram/callback` -- `api/routers/oauth/instagram.py`

```
1. instagram_oauth_start()       →  redirect to Meta auth
2. instagram_oauth_callback()    →  exchange code for access_token
3. Fetch user info via GET /me
4. Create/update Creator record in DB
5. _auto_onboard_after_instagram_oauth() (background)
6. scrape_creator_posts()        →  fetch recent media from Meta API
7. OnboardingService.onboard_creator()  →  core/onboarding_service.py
8. ToneAnalyzer.analyze_posts()  →  ingestion/tone_analyzer.py
9. save_tone_profile()           →  core/tone_service.py
10. _index_content()              →  core/citation_service.py
11. auto_configure_bot()  →  PersonalityExtractor.run()  →  core/personality_extraction/extractor.py
```

**DB:** creators, tone_profiles, knowledge_documents
**External:** Meta Graph API (OAuth + media), OpenAI API

---

### Flow 3: Creator Onboarding

**Entry:** `POST /onboarding/magic-slice/creator` -- `api/routers/onboarding/pipeline.py`

```
1. full_onboard()                →  onboarding/pipeline.py
2. OnboardingService.onboard_creator()  →  core/onboarding_service.py
3. Phase 1 - Posts: _scrape_instagram() or _parse_manual_posts()
4. Phase 2 - Tone: ToneAnalyzer.analyze_posts()  →  ingestion/tone_analyzer.py
5. Phase 3 - Index: _index_content()  →  embeddings via core/embeddings.py  →  pgvector
6. Phase 4 - Personality: PersonalityExtractor.run()
   a) extract_conversations()     →  data_cleaner.py
   b) format_all_conversations()  →  conversation_formatter.py (Doc A)
   c) analyze_all_leads()         →  lead_analyzer.py (Doc B)
   d) compute_creator_dictionary() + compute_writing_style()  →  personality_profiler.py (Doc C)
   e) generate_bot_configuration()  →  bot_configurator.py (Doc D)
   f) generate_copilot_rules()    →  copilot_rules.py (Doc E)
7. Save BotConfiguration, cache via core/creator_config.py
8. DM Sync: sync_instagram_dms()  →  onboarding/dm_sync.py
```

**DB:** creators, tone_profiles, knowledge_documents, leads, messages
**External:** Meta Graph API, OpenAI API

---

### Flow 4: Lead Lifecycle

**Entry:** Leads created via webhook (Flow 1), DM sync (Flow 3), or API

```
1. Creation: _enrich_new_lead()       →  core/instagram_modules/message_store.py
2. Scoring: extract_signals()         →  services/lead_scoring.py
3. Classification: classify_lead()    →  services/lead_scoring.py
   Categories: cliente > caliente STRONG > colaborador > amigo > frio > caliente SOFT > nuevo
4. Score: calculate_score()           →  0-100 range by status
5. Per-message updates: _save_messages_to_db()  →  update last_contact_at, purchase_intent, status
6. Nurturing: trigger_nurturing_sequence()  →  core/nurturing/manager.py
7. Escalation: check_and_notify_escalation()  →  core/dm/post_response.py
8. Dashboard: get_leads(), get_conversations_with_counts()  →  api/services/db/leads.py
```

**DB:** leads, messages, nurturing_sequences, notifications

---

### Flow 5: Copilot Flow

**Entry:** Triggered during webhook processing when `copilot_mode = true`

```
1. handler._is_copilot_enabled()        →  core/instagram_handler.py
2. _handle_copilot_mode()               →  core/instagram_modules/dispatch.py
3. Anti-zombie checks:
   - has_creator_responded_recently()   →  core/instagram_modules/echo.py
   - Check for existing pending suggestion
4. create_pending_response_impl()       →  core/copilot/lifecycle.py
5. Add to in-memory cache               →  core/copilot/service.py
6. Creator reviews: GET /copilot/{creator_id}/pending
7. Approve: approve_response_impl()    →  core/copilot/actions.py
   → send_message_impl()  →  core/copilot/messaging.py  →  message_sender.py
8. Discard: discard_response_impl()    →  core/copilot/actions.py
9. Auto-discard: auto_discard_pending_for_lead() (when creator replies manually)
```

**DB:** messages (status: pending_approval/sent/edited/discarded), leads

---

### Flow 6: Knowledge/RAG

**Entry:** `POST /knowledge/{creator_id}` or auto-ingestion during onboarding

```
Ingestion:
1. add_knowledge()              →  core/dm/knowledge.py
2. generate_embedding()         →  core/embeddings.py (text-embedding-3-small, 1536 dims)
3. store_embedding()            →  core/embeddings.py (pgvector with IVF index)
4. Batch: index_creator_posts() →  core/citation_service.py (chunking + batch embeddings)

Retrieval (during DM processing):
5. retrieve_rag_context()       →  core/dm/phases/context.py
6. SemanticRAG.search()         →  core/rag/semantic.py (pgvector cosine distance)
7. (Optional) BM25Retriever.search()  →  core/rag/bm25.py (hybrid: 70% semantic, 30% BM25)
8. (Optional) Reranker.rerank()       →  core/rag/reranker.py (cross-encoder)
9. Results cached 5 min
```

**DB:** knowledge_documents, rag_documents, content_chunks (with pgvector embedding)
**External:** OpenAI Embeddings API, PostgreSQL + pgvector

---

### Flow 7: Payments/Stripe

**Entry:** `POST /webhook/stripe` -- `api/routers/webhooks.py`

```
1. stripe_webhook()              →  api/routers/webhooks.py
2. process_stripe_webhook()      →  core/payments/manager.py (verify HMAC)
3. _handle_stripe_event():
   - checkout.session.completed → record_purchase() → update lead to "cliente"
   - customer.subscription.updated → update lead.subscription_status
   - charge.refunded → mark purchase as refunded, notify creator
4. record_sale()                 →  core/sales_tracker.py
5. Send confirmation emails
```

**DB:** leads, messages (purchase records), purchases
**External:** Stripe API, Hotmart API, PayPal API, Email Service

---

## 5. CODIGO MUERTO

### High-Confidence Dead Code

| File | Status | Reason |
|------|--------|--------|
| `services/audio_transcription_processor.py` | REMOVE | 0 imports, replaced by audio_intelligence.py |
| `core/migration_runner.py` | REMOVE | 0 imports, replaced by Alembic |
| `core/memory.py` | DEPRECATED | Emits DeprecationWarning, replaced by core.dm_agent; scheduled removal v3.0 |

### Duplicated Implementations

| v1 File | v2 File | Status |
|---------|---------|--------|
| `services/response_variator.py` | `services/response_variator_v2.py` | v1 used only by bot_orchestrator.py; v2 is primary |
| `core/lead_categorization.py` | `core/lead_categorizer.py` | Both coexist; legacy has `_legacy()` functions |
| `core/response_variation.py` | `services/response_variator_v2.py` | Only referenced in tests |

### Scripts (70 one-off utilities)

63 scripts in `/scripts/` have `if __name__ == "__main__"`. Candidates for cleanup:
- `scripts/lab_test_complete.py` (1,469 lines - largest file in repo)
- `scripts/functional_audit.py`
- `scripts/verify_*.py` (multiple variants)
- `scripts/test_*.py` (manual test scripts)
- `scripts/backup.py`, `scripts/backup_db.py`, `scripts/backup.sh`

### Recommendations

1. **Remove immediately:** `audio_transcription_processor.py`, `migration_runner.py`
2. **Schedule removal:** `core/memory.py` (v3.0.0)
3. **Consolidate:** `lead_categorization.py` + `lead_categorizer.py` → single source
4. **Choose one:** `response_variator.py` vs `response_variator_v2.py`

---

## 6. COVERAGE MAP

### Summary

| Category | Covered | Total | Coverage |
|----------|---------|-------|----------|
| Core modules | 55 | 142 | 38.7% |
| Services modules | 18 | 61 | 29.5% |
| **Total** | **73** | **203** | **35.9%** |
| Test functions | 3,372 | - | - |

### Top Covered Modules

| Module | Tests | Level |
|--------|-------|-------|
| core.context_detector | 271 | Excellent |
| core.intent_classifier | 260 | Excellent |
| core.creator_data_loader | 132 | Well covered |
| core.copilot_service | 93 | Good |
| core.output_validator | 76 | Good |
| core.prompt_builder | 71 | Good |
| services.length_controller | 67 | Good |
| core.response_fixes | 67 | Good |
| core.user_context_loader | 66 | Good |
| core.instagram | 60 | Good |
| services.edge_case_handler | 59 | Good |
| core.frustration_detector | 50 | Good |
| core.sensitive_detector | 47 | Good |
| services.response_variator | 43 | Basic |
| core.confidence_scorer | 39 | Basic |

### Critical Uncovered Areas (for E2E planning)

| Area | Uncovered Modules |
|------|-------------------|
| DM Pipeline | core.dm.agent, core.dm.phases.* (detection, context, generation, postprocessing), core.dm.strategy, core.dm.text_utils |
| Instagram Modules | core.instagram_modules.* (webhook, dispatch, message_sender, message_store, echo, media, lead_manager, comment_handler) |
| Copilot Internals | core.copilot.actions, core.copilot.lifecycle, core.copilot.messaging |
| Payments | core.payments.* (manager, stripe_handler, subscription_manager, webhook_handler) |
| RAG | core.rag.bm25, core.rag.semantic, core.rag.reranker |
| Personality Extraction | core.personality_extraction.* (all 9 submodules) |
| Analytics | core.analytics.*, core.intelligence.engine |
| Nurturing | core.nurturing.manager, core.nurturing.models, core.nurturing.utils |
| Services | services.lead_scoring, services.lead_service, services.llm_service, services.relationship_adapter, services.relationship_analyzer, services.whatsapp_onboarding_pipeline |

---

## 7. RESUMEN

### System Totals

| Metric | Value |
|--------|-------|
| Python files | 844 |
| API endpoints | 422 |
| Router files | 56 |
| DB tables | 50 |
| Core classes | 152 |
| Services classes | 119 |
| Module functions | 454 |
| Total public API surface | ~1,704 members |
| Test functions | 3,372 |
| Module test coverage | 35.9% (73/203) |
| Dead code files | 3 (high confidence) |
| Duplicated implementations | 3 pairs |

### E2E Testing Priority Matrix

| Priority | Flow | Risk | Coverage | Complexity |
|----------|------|------|----------|------------|
| P0 | Instagram Webhook (Flow 1) | Critical | 0% on DM pipeline | Very High (14 steps) |
| P0 | Copilot (Flow 5) | Critical | 0% on copilot internals | High (9 steps) |
| P1 | Creator Onboarding (Flow 3) | High | 0% on personality extraction | High (8 phases) |
| P1 | Lead Lifecycle (Flow 4) | High | Partial (lead_scoring covered) | Medium (8 steps) |
| P1 | Knowledge/RAG (Flow 6) | High | 0% on RAG modules | Medium (9 steps) |
| P2 | OAuth (Flow 2) | Medium | 0% | Medium (11 steps) |
| P2 | Payments (Flow 7) | Medium | 0% on payments | Low (5 steps) |

### Auth Security Gaps

- 263/422 endpoints (62.3%) have NO authentication
- Many CRUD operations on creator data lack auth (knowledge, tone, content, connections)
- All debug endpoints are unprotected
- GDPR endpoints (export, delete, anonymize) have no auth

### Architecture Notes

- **5-phase DM pipeline:** detection → memory/context → prompt → LLM generation → postprocessing (core/dm/phases/)
- **Multi-tenant:** Creator-based isolation, supports Instagram/Telegram/WhatsApp
- **LLM providers:** Gemini Flash-Lite (primary) → GPT-4o-mini (fallback)
- **Embeddings:** OpenAI text-embedding-3-small (1536 dims) stored in pgvector
- **Re-export hub:** core/dm_agent_v2.py (75 lines) re-exports all DM pipeline symbols
