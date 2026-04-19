# Graph Report - .  (2026-04-09)

## Corpus Check
- Large corpus: 1175 files · ~10,076,122 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 21159 nodes · 40556 edges · 624 communities detected
- Extraction: 66% EXTRACTED · 34% INFERRED · 0% AMBIGUOUS · INFERRED: 13858 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `BoundedTTLCache` - 364 edges
2. `Intent` - 325 edges
3. `CreatorData` - 221 edges
4. `IntentClassifier` - 212 edges
5. `DeterministicScraper` - 202 edges
6. `ProductInfo` - 193 edges
7. `CreatorProfile` - 181 edges
8. `UserContext` - 176 edges
9. `RelationshipAnalyzer` - 174 edges
10. `Business logic services for Clonnect. Extracted from dm_agent.py following TDD m` - 170 edges

## Surprising Connections (you probably didn't know these)
- `Clonnect Functional Inventory` --references--> `DM Agent 5-Phase Pipeline`  [INFERRED]
  docs/CLONNECT_FUNCTIONAL_INVENTORY.md → core/dm/agent.py
- `Event Loop Blocking (Sync DB in Async)` --conceptually_related_to--> `Phase 2-3: Memory and Context`  [EXTRACTED]
  docs/audit/fase2_4_carga_generacion.md → core/dm/phases/context.py
- `Metrics API Router Provides endpoints for the academic metrics dashboard` --uses--> `MetricsDashboard`  [INFERRED]
  api/routers/metrics.py → metrics/dashboard.py
- `Get metrics dashboard for creator.` --uses--> `MetricsDashboard`  [INFERRED]
  api/routers/metrics.py → metrics/dashboard.py
- `Get quick health score.` --uses--> `MetricsDashboard`  [INFERRED]
  api/routers/metrics.py → metrics/dashboard.py

## Hyperedges (group relationships)
- **CPE v2 Decision-Grade Metrics (L1+L2+L3 only)** — cpe_v2_l1_quantitative, cpe_v2_l2_bertscore, cpe_v2_l3_lexical, cpe_v2_ablation_protocol [EXTRACTED 1.00]
- **LLM Generation Provider Chain (Gemini → GPT-4o-mini fallback)** — pipeline_phase4_llm_generation, gemini_flash_lite_primary, gpt4o_mini_fallback, deepinfra_provider [EXTRACTED 1.00]
- **CCEE Ablation Phases (3 Subtractive + 4 Additive + 3 Learning)** — ccee_phase3_subtractive, ccee_phase4_additive, ccee_phase5_learning, ccee_test_set_v2, cpe_v2_l2_bertscore [EXTRACTED 1.00]
- **Full DM Pipeline (Webhook → Phase 0-6 → Response)** — evolution_webhook, instagram_webhook, pipeline_phase0_preprocessing, pipeline_phase1_detection, pipeline_phase23_memory_context, pipeline_phase4_llm_generation, pipeline_phase5_postprocessing, pipeline_phase6_background [EXTRACTED 1.00]
- **Learning Systems 7→3 Consolidation (FeedbackCapture + PersonaCompiler)** — learning_consolidation_spec, learning_arch_feedbackcapture, learning_arch_personacompiler, doc_d_personality_doc [EXTRACTED 1.00]
- **CPE Academic Reference Cluster (BERTScore, CharacterEval, PersonaGym, InCharacter)** — ref_bertscore_zhang2020, ref_charactereval_tu2024, ref_personagym_samuel2024, ref_incharacter_wang2024, ref_fu2025_llm_reliability, ref_xlmroberta_conneau2020 [EXTRACTED 1.00]
- **DM Agent 5-Phase Pipeline** — phase_detection, phase_context, phase_generation, phase_postprocessing, dm_agent_pipeline [EXTRACTED 1.00]
- **RAG Hybrid Search Pipeline** — semantic_rag, bm25_retriever, rag_reranker, concept_hybrid_rag [EXTRACTED 1.00]
- **Feedback Learning Loop** — preference_pairs_service, learning_rules_service, gold_examples_service, autolearning_analyzer, concept_feedback_three_services [EXTRACTED 1.00]
- **Config-Driven Provider Refactor (Steps 5-8)** — model_config_loader, gemini_provider, deepinfra_provider, together_provider, fireworks_provider, openrouter_provider, llm_models_config [EXTRACTED 1.00]
- **Memory Subsystems (Episodic + Engine + Hierarchical)** — semantic_memory_pgvector, memory_engine, hierarchical_memory, memory_store [EXTRACTED 1.00]
- **Relationship DNA Analysis Pipeline** — relationship_dna_service, relationship_type_detector, relationship_analyzer, vocabulary_extractor, bot_instructions_generator, dm_agent_context_integration [EXTRACTED 1.00]
- **Context Assembly Systems (Phase 2-3)** — phase_context, memory_engine, semantic_rag, relationship_dna_service, conversation_state, calibration_loader, relationship_adapter, semantic_memory_pgvector, hierarchical_memory [EXTRACTED 1.00]
- **Session Boundary Detection Integration** — conversation_boundary_detector, concept_session_boundary_detection, concept_time_gap_thresholds, phase_context [EXTRACTED 1.00]
- **Background Systems Audit Group (31,32,33,34,8,38,39,40)** — sys31_lead_score_update, sys32_lead_categorization, sys33_follower_memory, sys34_fact_tracking, sys8_dna_trigger, sys38_creator_profile_service, sys39_auto_provisioner, sys40_style_analyzer [EXTRACTED 1.00]
- **Detection Phase Systems (1-5)** — sys1_sensitive_detection, sys2_frustration_detection, sys3_context_signals, sys4_edge_case_media, sys5_pool_matching [EXTRACTED 1.00]
- **Backtest Evaluation Series for Stefano Bonanno** — backtest_finetuned, backtest_finetuned_v6, backtest_finetuned_v8, backtest_8b_ft, backtest_scout_ft_test, backtest_scout_base, backtest_scout_debug2, backtest_scout_verify, backtest_baseline_v6, backtest_v9, backtest_baseline_v14 [EXTRACTED 1.00]
- **Dual Profile Storage Conflict (creator_profiles vs style_profiles)** — creator_profiles_table, style_profiles_table, sys38_creator_profile_service, sys40_style_analyzer, sys39_auto_provisioner [EXTRACTED 1.00]
- **Dual Memory Storage Conflict (MemoryStore vs ConversationMemoryService)** — memory_store, conversation_memory_service, sys33_follower_memory [EXTRACTED 1.00]
- **Iris Bertran Doc D Components** — doc_d_iris_identity, doc_d_iris_language_rules, doc_d_iris_length_rules, doc_d_iris_blacklist, doc_d_iris_calibration_params [EXTRACTED 1.00]
- **32B LoRA Adapter Family (SFT + DPO)** — lora_sft_32b, lora_dpo_32b, base_qwen3_32b, peft_framework [INFERRED 0.90]
- **8B LoRA Adapter Family (SFT + DPO + MLX)** — lora_sft_8b, lora_dpo_8b, lora_dpo_8b_mlx_4bit, base_qwen3_8b [INFERRED 0.85]

## Communities

### Community 0 - "System Audit Documentation"
Cohesion: 0.0
Nodes (711): Audit: Frustration Detection (Sistema #2), Audit: Pool Matching (Sistema #5), Multilingual Gap: Italian Not Supported, Pool Matching Fast Path (Bypass LLM), BookingInfo, build_creator_context_prompt(), CreatorData, CreatorProfile (+703 more)

### Community 1 - "Frontend Bundle (JS)"
Cohesion: 0.0
Nodes (1062): $1(), _3(), _5(), _8(), $9(), _a(), a3(), a5() (+1054 more)

### Community 2 - "Core DM Systems Audit"
Cohesion: 0.01
Nodes (526): Audit: Conversation Boundary Detector (Sistema #13), Audit: DNA Engine (Sistema #8), Audit: Episodic Memory (Sistema #10), Audit: RAG Knowledge Engine (Sistema #11), Audit: User Context Builder (Sistema #7), BM25Document, BM25Retriever, get_bm25_retriever() (+518 more)

### Community 3 - "DM Responder Agent"
Cohesion: 0.01
Nodes (404): DMResponderAgentV2, get_dm_agent(), invalidate_dm_agent_cache(), DM Responder Agent V2 - Slim Orchestrator.  This is the refactored agent that de, Initialize the DM Agent with all services.          Args:             creator_id, Load creator personality, products, and style from database.          Returns:, ECHO Engine: Load data-driven StyleProfile to enrich style_prompt.          Merg, Initialize all required services. (+396 more)

### Community 4 - "Lead Abandonment Detection"
Cohesion: 0.0
Nodes (515): AbandonmentCollector, Abandonment Rate Collector Measures: % of conversations abandoned before resolut, Tracks conversation abandonment., Analyze if conversation was abandoned., Determine if conversation was abandoned and why., Get overall abandonment rate., compute_copilot_stats(), compute_learning_progress() (+507 more)

### Community 5 - "Bio & Profile Extraction"
Cohesion: 0.01
Nodes (390): BioExtractor, ExtractedBio, Bio Extractor - Intelligent extraction using LLM.  Extracts structured creator i, Extract bio from list of scraped pages using LLM.          Args:             pag, Find pages that are likely about/bio pages., Extract bio from a single page using LLM., Clean page content for LLM processing., Parse JSON from LLM response. (+382 more)

### Community 6 - "Clone Auto-Configuration"
Cohesion: 0.01
Nodes (389): auto_configure_clone(), AutoConfigResult, AutoConfigurator, Auto Configurator - Orquesta la creación automática de clones.  Combina: - Insta, Orquestador de auto-configuración de clones.      Pipeline:     1. Scrapear Inst, Ejecuta pipeline completo de auto-configuración.          Args:             crea, Resultado completo de auto-configuración., Scrapea posts de Instagram con V2 sanity checks.          Prioridad:         1. (+381 more)

### Community 7 - "Clone Setup & Onboarding"
Cohesion: 0.01
Nodes (431): complete_wizard_onboarding(), get_clone_progress(), Wizard onboarding and clone creation endpoints., Request to start clone creation process., Update clone progress in database. This persists across workers/restarts.      A, Profile data from wizard onboarding., Start the clone creation process.     This triggers background tasks to:     1., Product data from wizard onboarding. (+423 more)

### Community 8 - "Copilot Response Actions"
Cohesion: 0.01
Nodes (447): approve_all_pending(), approve_response(), approve_response_impl(), ApproveRequest, auto_discard_pending_for_lead_impl(), create_lead_activity(), create_lead_task(), delete_lead_activity() (+439 more)

### Community 9 - "Bot API & Middleware"
Cohesion: 0.01
Nodes (272): BaseHTTPMiddleware, get_bot_status(), pause_bot(), PauseBotRequest, Bot Router - Bot control endpoints (pause/resume/status) Extracted from main.py, Pausar el bot para un creador.     Los mensajes entrantes no seran respondidos., Reanudar el bot para un creador.     El bot volvera a responder mensajes., Obtener estado del bot para un creador.     Looks up from DB (authoritative) wit (+264 more)

### Community 10 - "Vocabulary & Batch Processing"
Cohesion: 0.01
Nodes (274): Audit: Vocabulary Extractor, _analyze_message_set(), analyze_writing_patterns(), build_conversation_windows(), categorize_leads(), collect_db_followers(), collect_json_followers(), extract_facts() (+266 more)

### Community 11 - "Bot Orchestrator"
Cohesion: 0.01
Nodes (264): BotOrchestrator, BotResponse, get_bot_orchestrator(), BotOrchestrator - Orchestrates all bot autopilot services.  Complete flow: 1. Ti, Build memory context string for LLM prompt., Send responses with calculated delays.          Args:             bot_response:, Get global BotOrchestrator instance., Response from the bot with metadata. (+256 more)

### Community 12 - "Best-of-N Response Selection"
Cohesion: 0.01
Nodes (232): BestOfNResult, BestOfNSelector, Candidate, generate_best_of_n(), _generate_single(), Best-of-N Candidate Generation for copilot mode.  Generates N candidates at diff, Serialize BestOfNResult for storage in msg_metadata., Synchronous wrapper for Best-of-N selection with confidence scoring. (+224 more)

### Community 13 - "System Prompt Configuration"
Cohesion: 0.02
Nodes (270): _build_sysprompt_context(), _collect_lead_names(), _contains_phone_number(), _detect_reconnect_messages(), _extract_copilot_phrases(), _extract_real_templates(), generate_bot_configuration(), generate_doc_d() (+262 more)

### Community 14 - "Pipeline Audit Reports"
Cohesion: 0.01
Nodes (273): Audit Part 1 — Message Input & Audio Pipeline (2026-03-19), Audit Part 2 — DM Agent Detection & Context Building (2026-03-19), Audit Part 3 — LLM Generation & Post-processing & Learning (2026-03-19), Backtest — 8B Fine-tuned (score 82.5, pool=0), Backtest — Baseline V14 (score 81.9, pool=0), Backtest — Baseline V6 (score 98.0), Backtest — Finetuned Model (initial, score 88.8), Backtest — Finetuned V6 (score 95.9) (+265 more)

### Community 15 - "Data Migration Scripts"
Cohesion: 0.01
Nodes (173): backfill_display_names(), main(), Fetch display names for leads that are missing full_name., backfill(), main(), Instagram DM Backfill — Import missing messages from the last N days.  Fetches c, get_instagram_handler(), InstagramHandler (+165 more)

### Community 16 - "Style Adaptation Profiler"
Cohesion: 0.02
Nodes (195): AdaptationProfiler, CCEE Script 3: Adaptation Profiler  Analyzes how the creator adapts their style, Fetch creator messages grouped by trust segment of the lead., Compute A1-A5 metrics for a segment of messages., Analyze if creator adapts style with trust level.          Checks if metrics tre, Profiles how a creator adapts style based on relationship trust level., Build adaptation profile for a creator.          Args:             creator_id: C, _trust_segment() (+187 more)

### Community 17 - "Analytics & Events"
Cohesion: 0.01
Nodes (137): AnalyticsEvent, AnalyticsManager, DailyStats, detect_platform(), EventType, from_dict(), FunnelStats, get_analytics_manager() (+129 more)

### Community 18 - "Personalized Ranking"
Cohesion: 0.01
Nodes (143): adapt_system_prompt(), personalize_results(), Personalized Ranking - Re-ranking de resultados según perfil del lead.  Adapta l, Re-rankea resultados según perfil del usuario.      Args:         results: Resul, Adapta system prompt según preferencias del usuario.      Args:         base_pro, clear_memory_cache(), ConversationMemory, get_conversation_memory() (+135 more)

### Community 19 - "Document Extraction"
Cohesion: 0.04
Nodes (143): get_pdf_extractor(), PDFDocument, PDFExtractor, PDFPage, PDF Extractor - Extrae texto de PDFs y ebooks.  Soporta: - PDFs locales y desde, Extractor de texto de documentos PDF.      Uso:         extractor = PDFExtractor, Inicializa el extractor., Extrae texto de un archivo PDF local.          Args:             file_path: Ruta (+135 more)

### Community 20 - "Subsystem 20"
Cohesion: 0.02
Nodes (96): Citation, CitationContext, clean_rag_ctas(), ContentCitationEngine, ContentType, extract_topics_from_query(), format_citation_for_response(), normalize_text() (+88 more)

### Community 21 - "Subsystem 21"
Cohesion: 0.02
Nodes (144): WhatsApp Business API Connector.  Handles sending/receiving messages via Meta's, Process webhook event and extract messages.          Args:             payload:, Send a text message.          Args:             recipient: Phone number (with co, Send a template message (for initiating conversations).          Args:, Send interactive message with buttons.          Args:             recipient: Pho, Connector for WhatsApp Cloud API.      Handles sending/receiving messages via Me, Mark a message as read.          Args:             message_id: WhatsApp message, Get URL to download media.          Args:             media_id: WhatsApp media I (+136 more)

### Community 22 - "Subsystem 22"
Cohesion: 0.02
Nodes (178): BookingLink, BookingSlot, CalendarBooking, get_availability(), get_available_dates(), get_available_slots(), get_public_service_info(), Booking models: BookingLink, CalendarBooking, BookingSlot. (+170 more)

### Community 23 - "Subsystem 23"
Cohesion: 0.01
Nodes (181): log(), log_verbose(), main(), print_result(), print_summary(), Print test result in formatted way, Print with optional color, Print only in verbose mode (+173 more)

### Community 24 - "Subsystem 24"
Cohesion: 0.02
Nodes (166): ABComparisonRunner, print_ab_report(), A/B Blind Comparison Test — Clone vs Real Creator.  Presents pairs (clone respon, Run A/B comparison on all test cases.          If pipeline is provided, generate, Call LLM judge and parse response., Print A/B comparison report., Runs blind A/B tests between clone and real creator responses., Run a single blind A/B comparison.          Randomizes order to avoid position b (+158 more)

### Community 25 - "Subsystem 25"
Cohesion: 0.02
Nodes (108): ConversationBoundaryDetector, Conversation Boundary Detection for continuous message streams.  Instagram/Whats, Detects conversation session boundaries in continuous message streams.      Usag, Check if message starts with a greeting pattern., Check if message contains a farewell pattern., Check if message starts with a discourse marker signaling topic shift., Extract and parse timestamp from message dict., Determine if curr_msg starts a new conversation session.          IMPORTANT: Bou (+100 more)

### Community 26 - "Subsystem 26"
Cohesion: 0.02
Nodes (103): ContentChunk, create_chunks_from_content(), _fixed_split_text(), generate_chunk_id(), Content Indexer - Indexa contenido del creador en RAG con chunking inteligente., Genera un ID unico para un chunk., Crea chunks indexables desde contenido raw.      Args:         creator_id: ID de, Representa un fragmento de contenido indexado. (+95 more)

### Community 27 - "Subsystem 27"
Cohesion: 0.02
Nodes (88): BotQuestionAnalyzer, get_bot_question_analyzer(), is_short_affirmation(), QuestionType, Bot Question Analyzer - Analiza el contexto de la última pregunta del bot.  Este, Analiza el mensaje del bot y retorna el tipo de pregunta.          Args:, Tipos de pregunta que puede hacer el bot., Analiza el mensaje y retorna tipo + confianza.          Args:             bot_me (+80 more)

### Community 28 - "Subsystem 28"
Cohesion: 0.06
Nodes (81): BookingInfo, CompetitionInsight, ContentInsight, InsightsEngine, InsightsEngine - Generates actionable insights for "Hoy" page  SPRINT3-T3.1: Dai, Get weekly metrics with deltas vs previous week.          Returns:             W, Get hot leads ready to close.          Query criteria:         - purchase_intent, Count conversations where last message is from user (awaiting response). (+73 more)

### Community 29 - "Subsystem 29"
Cohesion: 0.02
Nodes (88): APIKey, AuthManager, create_access_token(), create_api_key(), CreateAPIKeyRequest, decode_token(), from_dict(), generate_creator_id() (+80 more)

### Community 30 - "Subsystem 30"
Cohesion: 0.02
Nodes (90): archive_conversation(), delete_conversation(), get_archived_conversations(), get_conversations(), mark_conversation_read(), mark_conversation_spam(), _media_description(), Conversation status management (archive, spam, reset, delete). (+82 more)

### Community 31 - "Subsystem 31"
Cohesion: 0.03
Nodes (80): AudienceProfile, AudienceProfileBuilder, get_audience_profile_builder(), ProfileData, Audience Intelligence Module (SPRINT1-T1.2)  Provides intelligent audience profi, Intermediate data structure for segment detection rules., Builds intelligent audience profiles with context and recommendations.      Feat, Initialize the profile builder.          Args:             creator_id: Creator i (+72 more)

### Community 32 - "Subsystem 32"
Cohesion: 0.03
Nodes (74): get_intelligence_engine(), IntelligenceEngine, Intelligence Engine - Core analytics and prediction engine for Clonnect.  Analyz, Analyze conversation patterns., Analyze conversion patterns., Predict which leads are most likely to convert.          Uses a simple scoring m, Main intelligence engine for pattern analysis, predictions, and recommendations., Determine best action for a lead. (+66 more)

### Community 33 - "Subsystem 33"
Cohesion: 0.02
Nodes (56): M(), U(), cs(), ds(), hs(), ls(), ms(), ns() (+48 more)

### Community 34 - "Subsystem 34"
Cohesion: 0.04
Nodes (42): Ae(), Be(), C(), D(), de(), dt(), Ee(), F() (+34 more)

### Community 35 - "Subsystem 35"
Cohesion: 0.04
Nodes (62): Alert, alert_exception(), alert_llm_error(), AlertLevel, AlertManager, get_alert_manager(), Clonnect Creators - Alert System Sistema de alertas via Telegram para errores cr, Enviar alerta via Telegram.          Args:             message: Mensaje de la al (+54 more)

### Community 36 - "Subsystem 36"
Cohesion: 0.02
Nodes (40): Tests for core/context_detector (v2 — Universal/Multilingual).  Tests the contex, build_context_notes also populates alerts for backward compat., Tests that frustration detection stub returns empty results., Tests that sarcasm detection stub returns empty results., Tests for extract_user_name function., Tests for detect_b2b function., Tests for detect_interest_level function (delegates to intent)., Without intent parameter, returns 'none' (delegates to classifier). (+32 more)

### Community 37 - "Subsystem 37"
Cohesion: 0.04
Nodes (69): _background_dm_sync(), ConversationInsight, get_dm_sync_status(), InstagramDMSyncRequest, InstagramDMSyncResponse, list_dm_sync_jobs(), Instagram DM history sync endpoints., Request for syncing Instagram DM history (+61 more)

### Community 38 - "Subsystem 38"
Cohesion: 0.03
Nodes (62): apply_ppa(), build_refinement_prompt(), _build_refinement_system_prompt(), compute_alignment_score(), find_similar_examples(), _get_forbidden_patterns(), PPAResult, Post Persona Alignment (PPA) — refine LLM responses to match creator voice.  Bas (+54 more)

### Community 39 - "Subsystem 39"
Cohesion: 0.04
Nodes (58): DocumentChunk, RAGService, RAG (Retrieval-Augmented Generation) Service.  Extracted from dm_agent.py as par, Retrieve relevant documents for a query.          Args:             query: Searc, Compute similarity between two texts.          Args:             text1: First te, Represents a chunk of document for RAG indexing.      Attributes:         conten, Clear all documents from the index., Get index statistics.          Returns:             Dictionary with index stats (+50 more)

### Community 40 - "Subsystem 40"
Cohesion: 0.02
Nodes (52): Audit tests for core/copilot_service.py., Test 1: Initialization and imports., Test 3: Edge case - approval flow logic., Greeting intent gives low purchase score., Strong interest intent raises purchase score to 0.75., Objection intent decreases purchase score., Purchase intent never exceeds 1.0., CopilotService initializes with empty caches. (+44 more)

### Community 41 - "Subsystem 41"
Cohesion: 0.02
Nodes (18): Tests that health_check and get_stats return expected structure., Tests the full 5-phase pipeline with a real agent., Tests for module-level text utility functions., Tests for get_dm_agent / invalidate_dm_agent_cache., Tests that dataclasses instantiate correctly with defaults and custom values., Mutable default fields should not be shared across instances., Tests for _determine_response_strategy., First message with '?' but no help signal → BIENVENIDA + AYUDA. (+10 more)

### Community 42 - "Subsystem 42"
Cohesion: 0.04
Nodes (53): LeadScore, LeadService, LeadStage, Lead Management Service.  Extracted from dm_agent.py as part of REFACTOR-PHASE2., Determine lead stage based on score and activity.          Args:             sco, Calculate full lead score with stage.          Returns:             LeadScore wi, Get recommended actions for a lead stage.          Args:             stage: Curr, Calculate intent-based score (0.0-1.0 scale).          This method implements th (+45 more)

### Community 43 - "Subsystem 43"
Cohesion: 0.03
Nodes (29): make_lead(), make_unified(), Tests for core/identity_resolver.py  (Prioridad 1 — riesgo ALTO)  Identity resol, @gmail, @hotmail etc. should not be extracted as IG handles., Distance(a, b) == Distance(b, a)., Names like 'María' and 'Mario' should be close., WhatsApp leads embed phone in platform_user_id: 'wa_34612345678'., If WhatsApp platform_user_id is not pure digits after stripping 'wa_', skip. (+21 more)

### Community 44 - "Subsystem 44"
Cohesion: 0.04
Nodes (50): get_reflexion_improver(), Reflexion Module for Clonnect  Iteratively improves responses by self-critique a, Generate prompt for improving the response, Parse critique response.          Returns:             (critique_text, score, im, Improve a response through iterative self-critique.          Args:             r, Result of Reflexion improvement, Convenience method to personalize a template message.          Args:, Get singleton instance of ReflexionImprover.      Args:         llm_client: LLM (+42 more)

### Community 45 - "Subsystem 45"
Cohesion: 0.03
Nodes (44): Audit tests for core/response_fixes.py., FIX 2: Product deduplication by name., Products with same name (case-insensitive) are deduplicated., The first occurrence of a duplicate product is kept., Products with empty/missing name are not tracked or deduplicated., A single product list is returned unchanged., apply_product_fixes delegates to deduplicate_products., FIX 6: Hide technical errors and handle edge cases. (+36 more)

### Community 46 - "Subsystem 46"
Cohesion: 0.05
Nodes (68): DummyMetric, end_ingestion(), get_content_type(), get_health_score(), get_ingestion_summary(), get_metrics(), get_metrics_dashboard(), log_ingestion_complete() (+60 more)

### Community 47 - "Subsystem 47"
Cohesion: 0.03
Nodes (59): full_refresh(), get_content_refresh_status(), get_ingestion_status(), Re-ingestion endpoints for refreshing creator content.  POST /admin/ingestion/re, Re-scrape Instagram posts for a creator via Graph API.      Uses the creator's s, Re-scrape creator website, detect products, create RAG chunks.      Uses clean_b, Result of a refresh operation., Full re-ingestion: IG posts + website content in sequence.      SAFE: Never touc (+51 more)

### Community 48 - "Subsystem 48"
Cohesion: 0.04
Nodes (45): InstagramService, Instagram Service.  Extracted from dm_agent.py as part of REFACTOR-PHASE2. Provi, Check if service is currently rate limited.          Returns:             True i, Increment the API request counter., Parse incoming webhook message from Instagram.          Expected payload structu, Get service statistics., Parsed webhook message from Instagram.      Attributes:         message: The tex, Service for Instagram API integration.      Provides:     - Message formatting w (+37 more)

### Community 49 - "Subsystem 49"
Cohesion: 0.04
Nodes (48): Audit tests for core/unified_profile_service.py., Verify module can be imported and key symbols exist., DB-dependent functions must return safe defaults when DB is unavailable., When DB is not available the function returns None (not raises)., Cross-function integration: offer types, captured messages, and decision., Discount offer with incomplete config should NOT mention discount code., Test core extraction and message generation on valid inputs., Edge cases: empty strings, None, incomplete configs. (+40 more)

### Community 50 - "Subsystem 50"
Cohesion: 0.05
Nodes (37): detect_language(), get_i18n_manager(), get_system_message(), get_translated_message(), I18nManager, Language, LanguageDetector, Sistema de Internacionalizacion (i18n) para Clonnect Creators.  Permite: - Detec (+29 more)

### Community 51 - "Subsystem 51"
Cohesion: 0.05
Nodes (34): CloudinaryService, get_cloudinary_service(), MediaType, Cloudinary Service.  Provides permanent media storage for Instagram/WhatsApp att, Map media type to Cloudinary resource type.          Args:             media_typ, Upload media from a URL to Cloudinary.          Args:             url: Source UR, Supported media types for upload., Upload media from a local file to Cloudinary.          Args:             file_pa (+26 more)

### Community 52 - "Subsystem 52"
Cohesion: 0.04
Nodes (34): analyze_and_persist(), get_style_analyzer(), load_profile_from_db(), _percentile(), Style Analyzer — Extract quantitative and qualitative style profiles from creato, Load creator's outgoing messages from DB.          Only loads messages where rol, Extract numeric/statistical style metrics from messages.          Inspired by wh, Use LLM to extract qualitative style traits.          Sends a sample of messages (+26 more)

### Community 53 - "Subsystem 53"
Cohesion: 0.03
Nodes (27): Tests for vocabulary_extractor service (data-mined, TF-IDF).  Updated to test th, For 50+ messages, threshold should be raised to 3., Should extract commonly used words from messages., TF-IDF distinctiveness scoring tests., A word used only with lead A should score higher than a common word., With 1 lead, all words should score > 0., Integration test for the main entry point., Fallback: frequency-only when no global corpus. (+19 more)

### Community 54 - "Subsystem 54"
Cohesion: 0.04
Nodes (34): MockMessage, Tests para el sistema inteligente de señales y predicción de venta, Test detección de objeción por precio, Test detección de objeción por tiempo, Test detección de señal 'para_quien' (interés sobre público objetivo), Test probabilidad baja con solo saludo, Test probabilidad media con interés, Test probabilidad alta con múltiples señales de compra (+26 more)

### Community 55 - "Subsystem 55"
Cohesion: 0.04
Nodes (59): detect_url_in_metadata(), generate_link_preview(), generate_link_previews(), generate_thumbnails(), Media processing, thumbnails, link previews, and profile pic endpoints., Endpoint ligero para actualizar SOLO fotos de perfil de Instagram.      No hace, Generate preview for a URL and add to metadata.     For YouTube: uses official t, Generate link previews for existing messages that have URLs but no preview. (+51 more)

### Community 56 - "Subsystem 56"
Cohesion: 0.03
Nodes (35): apply_voseo function should be importable, quieres' should convert to 'querés, puedes' should convert to 'podés, tienes' should convert to 'tenés, necesitas' should convert to 'necesitás, get_tone_dialect should return valid value, Tests for tone profile loading and application, Tone profile should load for known creator (+27 more)

### Community 57 - "Subsystem 57"
Cohesion: 0.04
Nodes (34): gdpr_tmpdir(), Audit tests for core/gdpr.py., export_user_data with include_analytics=False omits analytics key., export_user_data creates an audit log entry., Test 3: Edge case - data deletion mock., Deleting a user with no data succeeds with empty deleted_items., Deletion creates an audit log entry with DATA_DELETE action., Deletion persists to the deletion log file. (+26 more)

### Community 58 - "Subsystem 58"
Cohesion: 0.04
Nodes (35): Tests for Ingestion Pipeline Metrics.  Verifies that: 1. Metrics are properly in, Verify record_posts_indexed works with count., Verify record_chunks_saved works with count and source type., Verify record_ingestion_error works with error type., Verify observe_scrape_duration records histogram value., Verify observe_extract_duration records histogram with phase label., Tests for start/end ingestion tracking., Verify start_ingestion and end_ingestion work together. (+27 more)

### Community 59 - "Subsystem 59"
Cohesion: 0.05
Nodes (41): Config, FollowerDetailResponse, get_aggregated(), get_aggregated_metrics(), get_profile(), get_profiles_by_segment(), get_segment_counts(), get_segment_users() (+33 more)

### Community 60 - "Subsystem 60"
Cohesion: 0.04
Nodes (31): Audit tests for core/whatsapp.py., Test 3: Edge case - webhook verification logic., verify_webhook returns challenge on valid subscribe + token match., verify_webhook returns None when mode is not 'subscribe'., verify_webhook returns None when token does not match., verify_webhook_signature returns True when no app_secret configured., Test 4: Error handling - empty and malformed payloads., Test 1: Initialization and imports. (+23 more)

### Community 61 - "Subsystem 61"
Cohesion: 0.04
Nodes (22): Tests for adaptive length controller based on 2,967 real Stefan messages., otro' has the most samples (2386) and represents baseline behavior., Median varies 5x+ from shortest (interes=10) to longest (objecion=53)., A 200-char response to an objection (hard_max=277) stays intact., Price responses up to 162 chars stay intact., Objection responses up to 277 chars stay intact., Even excessively long responses never get cut mid-word., Explicit context parameter overrides auto-detection. (+14 more)

### Community 62 - "Subsystem 62"
Cohesion: 0.04
Nodes (33): End-to-end tests for the Copilot + Autolearning pipeline.  Tests the complete fl, Extremely long responses get lower confidence., Test that response fixes clean up text before confidence scoring., Catchphrase is removed by response_fixes., Broken links are fixed by response_fixes., Fix 4 (identity rewrite) is disabled — response passes through unchanged., A clean, post-processed response should score well., Test that pattern detection works across realistic data. (+25 more)

### Community 63 - "Subsystem 63"
Cohesion: 0.06
Nodes (22): CreatorKnowledge, CreatorKnowledgeService, get_creator_knowledge_service(), Creator Knowledge Service - Base de conocimiento del creador., Obtiene contexto relevante para un mensaje., Obtiene instancia del servicio., Conocimiento sobre un creador., Obtiene información relevante para una consulta. (+14 more)

### Community 64 - "Subsystem 64"
Cohesion: 0.04
Nodes (29): Audit tests for core/message_reconciliation.py., Sticker attachment correctly identified., Animated GIF correctly identified., Legacy image_data format extracts URL correctly., Test 4: Error handling - empty conversations and missing data., Test 1: Initialization and module-level constants., Module configuration constants are set to expected defaults., Unknown attachment type returns fallback content_text. (+21 more)

### Community 65 - "Subsystem 65"
Cohesion: 0.06
Nodes (36): calcular_categoria(), categoria_a_status_legacy(), CategorizationResult, detectar_keywords(), get_categoria_config(), Lead Categorization Service - Sistema de Embudo Estándar  Categorías: - nuevo: A, Convierte categoría nueva a status legacy para compatibilidad.      nuevo -> new, Convierte status legacy a categoría nueva.      new -> nuevo     active -> inter (+28 more)

### Community 66 - "Subsystem 66"
Cohesion: 0.06
Nodes (47): adapt_lead_response(), adapt_leads_response(), create_lead(), create_manual_lead(), delete_lead(), _get_json_path(), get_lead(), get_leads() (+39 more)

### Community 67 - "Subsystem 67"
Cohesion: 0.07
Nodes (36): add_conversations_to_queue(), get_next_pending_job(), get_or_create_sync_state(), get_sync_status(), process_single_conversation(), RateLimitError, Sync Worker - Sistema de cola inteligente para sincronización con Instagram API., Configuración del sync worker. (+28 more)

### Community 68 - "Subsystem 68"
Cohesion: 0.05
Nodes (47): analyze_creator_action(), _apply_sections(), _call_judge(), _categorize_evidence(), _collect_signals(), compile_persona(), compile_persona_all(), _compile_section() (+39 more)

### Community 69 - "Subsystem 69"
Cohesion: 0.09
Nodes (43): _bleu4(), build_augmented_prompt(), build_user_context_block(), _chrf(), compute_l1(), compute_l2(), compute_l3_quick(), _count_sentences() (+35 more)

### Community 70 - "Subsystem 70"
Cohesion: 0.06
Nodes (22): attribute_sale(), get_customer_purchases(), get_revenue_stats(), PurchaseRecord, Payments and revenue endpoints, Get purchase history for a specific customer, Manually attribute a sale to the bot.      Use when a purchase wasn't automatica, Get revenue statistics combining payment manager and sales tracker (+14 more)

### Community 71 - "Subsystem 71"
Cohesion: 0.05
Nodes (27): Messaging webhooks router tests - Written BEFORE implementation (TDD). Run these, Test main app includes messaging webhooks router., Main app should have Instagram webhook endpoint., Router should be importable., Main app should have WhatsApp webhook endpoint., Main app should have Telegram webhook endpoint., Router should have Instagram webhook endpoints., Router should have WhatsApp webhook endpoints. (+19 more)

### Community 72 - "Subsystem 72"
Cohesion: 0.07
Nodes (8): base_signals(), CAPA 2 — Unit tests: Lead Scoring Tests classify_lead() and calculate_score() as, Inactive but zero messages → stays nuevo., Return a minimal signals dict with sensible defaults., Existing customer status preserved even with new purchase signals., TestCalculateScore, TestClassifyLead, TestKeywordLists

### Community 73 - "Subsystem 73"
Cohesion: 0.05
Nodes (24): Tests for core/confidence_scorer.py., Test blacklist pattern detection., Clean text with no blacklisted patterns gets 1.0., One blacklisted pattern drops to 0.5., Multiple blacklisted patterns drop to 0.1., Catchphrase 'qué te llamó la atención' is caught., Broken link pattern is caught., Test multi-factor confidence calculation. (+16 more)

### Community 74 - "Subsystem 74"
Cohesion: 0.08
Nodes (40): aggregate_runs(), cliff_magnitude(), cliffs_delta(), compare_to_baseline(), _compute_bertscore_batch(), _compute_bleu4(), _compute_chrf(), _compute_meteor() (+32 more)

### Community 75 - "Subsystem 75"
Cohesion: 0.07
Nodes (17): ABC, AnthropicClient, get_llm_client(), GroqClient, LLMClient, OpenAIClient, Cliente LLM simplificado para Clonnect Creators Soporta Groq (default), OpenAI y, Factory para obtener cliente LLM      Providers disponibles:     - groq (default (+9 more)

### Community 76 - "Subsystem 76"
Cohesion: 0.06
Nodes (19): get_telegram_registry(), Telegram Bot Registry - Manages multiple Telegram bots for different creators. E, List all registered bots (without exposing full tokens)., Register a new Telegram bot for a creator.          Args:             creator_id, Registry for managing multiple Telegram bots.     Maps bot_id -> creator_id and, Update the creator_id for an existing bot.          Args:             bot_id: Th, Unregister a Telegram bot.          Args:             bot_id: The bot ID to unre, Reload configuration from file. (+11 more)

### Community 77 - "Subsystem 77"
Cohesion: 0.08
Nodes (24): _clear_caches(), _emoji_rate(), Tests for core/dm/style_normalizer.py — Bug 2 fix.  Validates: - Emoji normaliza, High creator rate (90%) — most emojis kept.         Uses 200 samples (stddev ~2%, When _get_creator_emoji_rate returns None → fallback keep_prob=0.50., Normalizer never returns an empty string when input was non-empty., evaluation_profiles/{creator}_style.json emoji_rate wins over baseline., If eval_profile doesn't exist, use baseline emoji_rate_pct. (+16 more)

### Community 78 - "Subsystem 78"
Cohesion: 0.05
Nodes (13): Audit tests for services/dm_agent_context_integration.py., Test 1: init/import - Module imports and core functions exist., Test 3: edge case - Graceful handling of missing data., Empty dict is falsy so _format_dna_for_prompt returns None., Test 4: error handling - Errors in sources do not crash assembly., Vocabulary lists are capped at 8 (uses) and 5 (avoids)., Test 5: integration check - Multiple sources merge correctly., Test 2: happy path - Context is assembled correctly from sources. (+5 more)

### Community 79 - "Subsystem 79"
Cohesion: 0.05
Nodes (16): Tests for: 1. P1 scoring bug fixes (double-multiply eliminated) 2. FeedbackStore, Test the unified FeedbackStore service., Verify that context-scored retrieval does NOT square confidence/quality., Test auto-creation of derivative records from evaluator feedback., _auto_create_preference_pair creates a PreferencePair with action_type=evaluator, _auto_create_gold_example creates GoldExample in caller's session., Regression tests for feedback store bug fixes., Verify no hardcoded creator IDs. (+8 more)

### Community 80 - "Subsystem 80"
Cohesion: 0.05
Nodes (23): Test full pipeline flow logic, Every status should have a defined pipeline score, Pipeline scores should increase with status progression, Scores should have reasonable gaps (25 points each), Test lead conversion calculation, Test expected conversion data structure, Test mock lead creation structure, Test pipeline scoring logic (+15 more)

### Community 81 - "Subsystem 81"
Cohesion: 0.07
Nodes (22): analyze_creator_posts(), PostAnalyzer, Post Analyzer - LLM-powered analysis of Instagram posts.  Analyzes creator's rec, Format posts list into text for LLM prompt.          Args:             posts: Li, Build the analysis prompt.          Args:             posts_text: Formatted post, Call LLM to analyze posts.          Args:             prompt: Analysis prompt, Parse LLM response JSON.          Args:             response: Raw LLM response, Convenience function to analyze posts.      Args:         posts: List of post di (+14 more)

### Community 82 - "Subsystem 82"
Cohesion: 0.06
Nodes (33): cleanup_orphan_leads(), cleanup_test_leads(), delete_lead_by_platform_id(), Dangerous/destructive admin endpoints — Lead cleanup operations.  Endpoints: - c, Clean up orphan leads:     1. Delete duplicate with ig_ prefix and 0 messages, Eliminar leads de test y leads sin username.      Requires admin API key (X-API-, Delete a specific lead by platform_user_id, including all its messages.     Use, Dangerous/destructive admin endpoints.  All endpoints in this module require adm (+25 more)

### Community 83 - "Subsystem 83"
Cohesion: 0.12
Nodes (34): _bleu4(), build_augmented_prompt(), _chrf(), compute_l1(), compute_l2(), compute_l3_quick(), _count_sentences(), _distinct2() (+26 more)

### Community 84 - "Subsystem 84"
Cohesion: 0.08
Nodes (26): CategoryScore, ConversationTurn, IntelligenceTestRunner, main(), print_report(), Reporte final de tests., Ejecutor de tests de inteligencia conversacional., Inicializar el agente y LLM. (+18 more)

### Community 85 - "Subsystem 85"
Cohesion: 0.08
Nodes (23): _make_message(), Integration tests for Copilot Enhancement Deploy 1-2 features.  Tests: - Session, No messages returns empty list., Multiple session breaks in a long conversation., Create a mock message with named-tuple-like attributes., session_label should be a valid ISO timestamp., Output should be in chronological order (oldest first)., Test that context messages have correct fields. (+15 more)

### Community 86 - "Subsystem 86"
Cohesion: 0.12
Nodes (33): _bleu4(), _chrf(), compute_l1(), compute_l2(), compute_l3_quick(), _count_sentences(), _distinct2(), _extract_per_case_from_files() (+25 more)

### Community 87 - "Subsystem 87"
Cohesion: 0.07
Nodes (22): fetch_creator_posts(), get_session(), InstagramPostFetcher, Instagram Post Fetcher - Fetches recent posts from Instagram Graph API.  Retriev, Call Instagram Graph API to fetch media.          Args:             user_id: Ins, Format raw API response to standard post format.          Args:             post, Check if post is within date range.          Args:             post: Post dict w, Convenience function to fetch creator's posts.      Args:         creator_id: Cr (+14 more)

### Community 88 - "Subsystem 88"
Cohesion: 0.06
Nodes (21): FASE 10 — 10 functional tests for vocabulary_extractor.  Tests use synthetic dat, Test 6: Pure Spanish conversation., Test 7: Mixed ES/EN/CA conversation., Test 8: Re-extracting vocabulary produces same result., Test 1: Iris-like creator vocabulary extraction from real message patterns., Test 9: Old LLM-generated vocabulary words are NOT in tokenized output., Test 10: Technical tokens (URLs, platform names) must not be vocabulary., Test 2: Stefano-like creator — Spanish male vocabulary. (+13 more)

### Community 89 - "Subsystem 89"
Cohesion: 0.07
Nodes (20): Tests for core/autolearning_evaluator.py., High discard rate generates review recommendation., High edit rate generates tone adjustment recommendation., Very high approval rate suggests auto mode., Improving approval rate over the week is noted., Normal metrics don't generate unnecessary recommendations., Test daily evaluation function., Test weekly recalibration function. (+12 more)

### Community 90 - "Subsystem 90"
Cohesion: 0.11
Nodes (33): _bleu4(), _build_history_metadata(), _chrf(), cliffs_delta(), cliffs_magnitude(), compare_vs_baseline(), compute_l1(), compute_l2() (+25 more)

### Community 91 - "Subsystem 91"
Cohesion: 0.1
Nodes (34): _ab_assign(), filter_cases(), _format_history(), _generate_bot_responses(), _get_cache_path(), _get_progress_path(), _humanize_media(), _is_fake_or_error() (+26 more)

### Community 92 - "Subsystem 92"
Cohesion: 0.08
Nodes (23): ExtractedContent, ExtractedFAQ, ExtractedProduct, ExtractedTestimonial, get_structured_extractor(), Structured Content Extractor - Extract structured data using REGEX patterns.  NO, Convert price string to float., Detect currency from text. (+15 more)

### Community 93 - "Subsystem 93"
Cohesion: 0.06
Nodes (15): _fake_db_session(), _patch_get_db_session(), Audit tests for core/tone_profile_db.py., Load profile and verify caching., Context manager yielding a MagicMock that acts as a DB session., Functions return safe defaults when DB is unavailable., Verify cache is properly maintained across operations., Return a patch for api.database.get_db_session. (+7 more)

### Community 94 - "Subsystem 94"
Cohesion: 0.06
Nodes (20): Tests for PersonaCompiler (System B) — learning consolidation 7→3 phase 2.  10 t, Pairs with edit_diff categorize correctly., Parse [PERSONA_COMPILER:*] tags from Doc D text., Correctly replace existing sections without touching human content., Add new section at end without touching existing content., Newer evidence overrides conflicting old section., _snapshot_doc_d inserts into doc_d_versions., Mixed CA/ES evidence detected correctly. (+12 more)

### Community 95 - "Subsystem 95"
Cohesion: 0.12
Nodes (32): _build_direct_prompt(), _build_pairwise_prompt(), _call_deepinfra(), _call_gemini(), _call_judge(), _call_openai(), evaluate_all_params(), _get_openai_client() (+24 more)

### Community 96 - "Subsystem 96"
Cohesion: 0.13
Nodes (32): api_call(), generate_html_report(), main(), Set current scenario for grouping, Maria creates her fitness coaching business, Carlos goes from greeting to purchase through objections, Ana speaks English - bot should respond in English, Decorator/marker for story steps (+24 more)

### Community 97 - "Subsystem 97"
Cohesion: 0.1
Nodes (31): _check_fuzzy_name(), _create_unified(), extract_contact_signals(), _levenshtein(), _link_and_log(), manual_merge(), manual_unmerge(), _match_by_email() (+23 more)

### Community 98 - "Subsystem 98"
Cohesion: 0.07
Nodes (11): clear_profile_cache(), Tests for services/preference_profile_service.py  format_preference_profile_for_, Partial profiles (missing keys) should not raise., Build a mock session whose SQLAlchemy chain returns the given messages., DB error inside try block → except handler returns None., Minimum sample size is 10; fewer returns None., With >=10 valid messages, should return a structured profile., Second call with same creator_id returns cached result without hitting DB. (+3 more)

### Community 99 - "Subsystem 99"
Cohesion: 0.15
Nodes (31): _bleu4(), _chrf(), cliffs_delta(), cliffs_magnitude(), compute_l1(), compute_l2(), compute_l3_quick(), _count_sentences() (+23 more)

### Community 100 - "Subsystem 100"
Cohesion: 0.1
Nodes (31): _build_prometheus_rubric(), _call_gemini_fallback(), _call_hf_inference(), _filter_media_cases(), _format_history(), _get_platform_user_id(), _get_prometheus_judge(), _is_media_case() (+23 more)

### Community 101 - "Subsystem 101"
Cohesion: 0.09
Nodes (17): clear_examples_cache(), make_example(), _mock_session_returning(), Tests for services/gold_examples_service.py  Focus: scoring & ranking logic in g, Intent match (+3×quality) beats universal (+0.5×quality)., Example with no intent/stage/rel gets +0.5×quality as base score., Example whose intent doesn't match still appears (base score > 0) but ranks last, Stage match (+2) ranks higher than intent match alone (+3×0.5). (+9 more)

### Community 102 - "Subsystem 102"
Cohesion: 0.13
Nodes (17): main(), Verify follower memory data quality., Verify RelationshipDNA data quality., Verify leads data quality., Verify messages data quality., Result of a single test., Verify products data quality., Verifier for all Clonnect systems. (+9 more)

### Community 103 - "Subsystem 103"
Cohesion: 0.09
Nodes (21): AudioEntities, AudioIntelligence, AudioIntelligenceService, clean_transcription_regex(), get_audio_intelligence(), _language_name(), Audio Intelligence Pipeline — 4-Layer Processing.  Whisper → Clean → Extract → S, Complete processed output for an audio message. (+13 more)

### Community 104 - "Subsystem 104"
Cohesion: 0.08
Nodes (20): Audit: Sensitive Content Detection (Sistema #1), _check_patterns(), detect_sensitive_content(), get_crisis_resources(), get_sensitive_detector(), Detector de Contenido Sensible v2.0.0 para Clonnect.  Detecta contenido que requ, # NOTE: In Instagram/WhatsApp DMs, leads legitimately ask for contact info, Verifica si el mensaje contiene alguno de los patrones. (+12 more)

### Community 105 - "Subsystem 105"
Cohesion: 0.11
Nodes (19): _make_result(), Functional tests for System #10: Episodic Memory.  Tests the _episodic_search fu, T06: Long content is truncated at 250 chars, not 150., T07: UUID pair is tried before slug pair., T08: If DB resolution fails, falls back to slug pair., T09: Empty or None recent_history doesn't crash., T10: user → 'lead', assistant → 'tú'., Test BUG-EP-01 fix: post_response writes to conversation_embeddings. (+11 more)

### Community 106 - "Subsystem 106"
Cohesion: 0.06
Nodes (17): payment_manager(), Tests for PayPal integration.  Tests: - OAuth flow - Webhook signature verificat, Test PayPal webhook signature verification, Test PayPal is properly added to platform enum, PAYPAL should be in PaymentPlatform enum, Integration tests for PayPal with SalesTracker, Create payment manager with temp storage, Test PayPal OAuth flow (+9 more)

### Community 107 - "Subsystem 107"
Cohesion: 0.06
Nodes (12): Audit tests for core/link_preview.py., Only properly formed URLs should be extracted., Verify module imports and constants., Verify timeout and error handling in extract_link_preview., Integration: extract_previews_from_text processes multiple URLs., Test URL extraction from text and platform detection., Edge cases for URL handling., TestExtractPreviewsIntegration (+4 more)

### Community 108 - "Subsystem 108"
Cohesion: 0.06
Nodes (13): Audit tests for core/ghost_reactivation.py., Verify module imports and configuration structure., Test the reactivation scheduling flow with mocks., Verify configuration mutation and threshold boundaries., Returned dict should be a copy, not a reference to the config., Stats should return structured dict even with no DB., Test ghost identification with mocked DB., Verify that recent contacts and old contacts are excluded. (+5 more)

### Community 109 - "Subsystem 109"
Cohesion: 0.06
Nodes (11): Tests for Together AI provider., Config-driven path: model_id loads sampling/runtime/provider from JSON., Test call_together function., Reset circuit breaker state before each test., Test circuit breaker behavior., Reset circuit breaker state before each test., Live integration test — only runs when TOGETHER_API_KEY is set., TestCallTogether (+3 more)

### Community 110 - "Subsystem 110"
Cohesion: 0.1
Nodes (30): classify_topic(), compute_stats(), detect_language_style(), extract_conversations(), _generate_context_description(), generate_synthetic_test_set(), generate_test_pairs(), get_db_session() (+22 more)

### Community 111 - "Subsystem 111"
Cohesion: 0.07
Nodes (19): MetaWebhookVerification, Contrato para verificación de webhook, Payloads diferentes producen firmas diferentes, Mismo payload produce misma firma, Tests de estructura de payloads de Meta, Estructura de webhook de mensaje, Estructura de webhook de read receipt, Tests de verificación de webhook de Meta (+11 more)

### Community 112 - "Subsystem 112"
Cohesion: 0.08
Nodes (18): measure_time(), Sistema debe manejar queries concurrentes eficientemente, Procesamiento por lotes debe ser más eficiente que individual, Medir tiempo de ejecución en ms, Tests de uso de memoria del sistema RAG, Índice no debe usar memoria excesiva por documento, Cache hits deben ser significativamente más rápidos, Tests de rendimiento para procesamiento de señales (+10 more)

### Community 113 - "Subsystem 113"
Cohesion: 0.07
Nodes (18): Audit tests for api/routers/ingestion_v2.py., IngestV2Request should require a url field., Test the Instagram ingestion status endpoint., Verify that the ingestion_v2 router and its models can be imported., Router object and prefix should be correct., Validate that Pydantic models enforce correct types and defaults., IngestV2Response should accept all required fields., ProductV2Response should allow price=None when not found. (+10 more)

### Community 114 - "Subsystem 114"
Cohesion: 0.08
Nodes (16): Tests for resolved_externally feature — learning from creator direct replies.  T, Without creator_response, should keep old behavior (manual_override/discarded)., When no pending messages exist, should return 0., Test that resolved_externally uses 0.7 confidence in autolearning., Test that resolved_externally respects ENABLE_AUTOLEARNING flag., Test text similarity calculation., Identical strings should return 1.0., Different strings should return 0 < x < 1. (+8 more)

### Community 115 - "Subsystem 115"
Cohesion: 0.07
Nodes (11): clear_cache(), Tests for services/calibration_loader.py  Calibration loader reads per-creator J, None result is also cached, preventing repeated disk hits., After invalidation, next call re-reads from disk., invalidate_cache() with no args clears everything., Cache key is per creator_id, not global., Reset in-memory cache before and after every test., Second call returns cached result even if file is deleted. (+3 more)

### Community 116 - "Subsystem 116"
Cohesion: 0.07
Nodes (17): Tests for System A: FeedbackCapture (services/feedback_capture.py) 8 tests cover, capture(best_of_n) creates N-1 pairs from ranked candidates., capture(evaluator_score) routes to save_feedback and returns correct fields., capture(historical_mine) calls mine_historical_pairs with correct args., Duplicate source_message_id → updates existing record, no new row., All 8 signal types produce correct quality scores., lo_enviarias >= 4 + ideal_response → auto-creates gold example., from services.feedback_store import capture still works via re-export shim. (+9 more)

### Community 117 - "Subsystem 117"
Cohesion: 0.07
Nodes (13): CAPA 2 — Unit tests: Webhook routing & payload parsing Tests pure parsing logic, Validate a messaging entry has expected fields., Meta sets is_echo=True on messages the page itself sends., Simulate the echo-skipping logic in the handler., Instagram X-Hub-Signature-256 format: 'sha256=<hex>, save_unmatched_webhook should either return a value or raise — not hang., A valid Meta webhook must have 'object' and 'entry'., Missing 'object' key means the webhook is invalid. (+5 more)

### Community 118 - "Subsystem 118"
Cohesion: 0.07
Nodes (7): Tests for core.emoji_utils — universal emoji detection., is_emoji_char must handle all emoji-related Unicode characters., count_emojis must count visible emoji, not modifiers., is_emoji_only must detect ALL Unicode emoji, not just high codepoints., TestCountEmojis, TestIsEmojiChar, TestIsEmojiOnly

### Community 119 - "Subsystem 119"
Cohesion: 0.07
Nodes (7): Router import tests. Verifies all routers can be imported and have correct struc, Test that routers have expected endpoint structure., Test that main app imports correctly with all routers., Test that all routers can be imported., TestMainAppImport, TestRouterImports, TestRouterStructure

### Community 120 - "Subsystem 120"
Cohesion: 0.09
Nodes (27): Audit: Feedback Services (Sistema #11), Autolearning Analyzer, Bug: Double Quality Score Multiplication, Feedback Split Across Three Services, Re-export shim — all logic moved to services/style_retriever.py. Kept for backwa, create_rule(), deactivate_rule(), filter_contradictions() (+19 more)

### Community 121 - "Subsystem 121"
Cohesion: 0.11
Nodes (27): cliff_magnitude(), cliffs_delta(), compute_chrf(), compute_rouge_l(), compute_vocab_overlap(), evaluate_l1(), evaluate_l2_batch(), evaluate_l3() (+19 more)

### Community 122 - "Subsystem 122"
Cohesion: 0.09
Nodes (24): _patch_copilot_service(), Audit tests for api/routers/copilot.py., Test behavior when there are no pending responses., Return a context manager that patches the lazily-imported copilot service., Verify that endpoints pass creator_id correctly to the service., Test GET /copilot/{creator_id}/pending-for-lead/{lead_id}., Verify that the copilot router and its models can be imported., Router object, Pydantic models, and route prefix are correct. (+16 more)

### Community 123 - "Subsystem 123"
Cohesion: 0.11
Nodes (27): ensure_lead_in_postgres(), full_sync_creator(), _get_json_path(), _load_json(), Data Synchronization Service for CLONNECT Provides bidirectional sync between Po, Sync a JSON follower to PostgreSQL Lead.     Called when JSON exists but Postgre, Sync a message to the JSON last_messages array.     Called after saving a messag, Get the JSON file path for a follower (+19 more)

### Community 124 - "Subsystem 124"
Cohesion: 0.09
Nodes (27): _auto_create_gold_example(), _auto_create_preference_pair(), capture(), _compute_quality(), create_pairs_from_action(), curate_pairs(), _fetch_context_and_save_sync(), get_feedback() (+19 more)

### Community 125 - "Subsystem 125"
Cohesion: 0.1
Nodes (27): Audit: Compressed Doc D (Sistema #14), Audit: Fase 3 Prompt Assembly, _bfi_summary(), build_compressed_doc_d(), _get_catchphrases(), _get_creator_display_name(), _get_creator_products(), _get_length_divergence() (+19 more)

### Community 126 - "Subsystem 126"
Cohesion: 0.09
Nodes (26): check_reconciliation_health(), get_reconciliation_status(), get_scheduler_status(), _process_profile_retries(), Nurturing scheduler and reconciliation endpoints (admin-protected), Run reconciliation on server startup.     Recovers messages from the last 24 hou, Run a single scheduler cycle - process all due followups across all creators., # NOTE: Reconciliation, lead enrichment, and ghost reactivation have been (+18 more)

### Community 127 - "Subsystem 127"
Cohesion: 0.07
Nodes (17): Tests for System C: StyleRetriever (services/style_retriever.py) 8 tests coverin, retrieve() filters by language when specified., retrieve() uses embedding similarity when >= 3 embeddings exist., create_gold_example generates embedding on creation., ensure_embeddings() backfills embedding for examples without one., curate_examples() still works (logic unchanged from gold_examples_service)., from services.gold_examples_service import ... still works via re-export shim., retrieve() falls back to keyword scoring when < 3 embeddings exist. (+9 more)

### Community 128 - "Subsystem 128"
Cohesion: 0.07
Nodes (7): Tests for Fireworks AI provider., Config-driven path: model_id loads sampling/runtime/provider from JSON., Test call_fireworks function., TestCallFireworks, TestCallFireworksConfigDriven, TestCircuitBreaker, TestLiveIntegration

### Community 129 - "Subsystem 129"
Cohesion: 0.08
Nodes (18): Audit tests for api/routers/oauth.py., The router should have endpoints for Instagram, Google, Stripe, PayPal., Verify that the oauth router and its key symbols can be imported., GET /oauth/debug should list config for all platforms., The router object and key helpers should be importable., Internal async helpers should be importable., Test OAuth Instagram start endpoint returns correct URL structure., GET /oauth/instagram/start should return auth_url when app_id is set. (+10 more)

### Community 130 - "Subsystem 130"
Cohesion: 0.11
Nodes (16): DNAMigrator, main(), DNA Migration Script for existing leads.  Analyzes existing conversations and cr, Get all leads with their message counts.          Args:             creator_id:, Analyze a lead's conversation and create DNA.          Args:             lead: L, Get messages for a specific lead.          Args:             creator_id: Creator, Migrates existing leads to have RelationshipDNA records., Main entry point for CLI usage. (+8 more)

### Community 131 - "Subsystem 131"
Cohesion: 0.12
Nodes (25): create_gold_example(), curate_examples(), detect_language(), _embed_text(), ensure_embeddings(), get_matching_examples(), _invalidate_examples_cache(), _is_non_text() (+17 more)

### Community 132 - "Subsystem 132"
Cohesion: 0.11
Nodes (23): apply_all_response_fixes(), apply_blacklist_filter(), apply_product_fixes(), clean_raw_ctas(), deduplicate_products(), fix_broken_links(), fix_identity_claim(), fix_price_typo() (+15 more)

### Community 133 - "Subsystem 133"
Cohesion: 0.11
Nodes (22): check_data_dir_health(), check_disk_health(), check_llm_health(), check_memory_health(), determine_overall_status(), health(), health_cache(), health_live() (+14 more)

### Community 134 - "Subsystem 134"
Cohesion: 0.12
Nodes (23): _analyze_behavior(), analyze_conversation_signals(), _analyze_conversation_signals_internal(), _calculate_avg_response_time(), _calculate_behavior_metrics(), _empty_analysis(), _generate_cache_key(), _generate_next_step() (+15 more)

### Community 135 - "Subsystem 135"
Cohesion: 0.11
Nodes (23): apply_blacklist_replacement(), _cosine_similarity(), detect_message_language(), _filter_blacklisted_examples(), get_few_shot_section(), invalidate_cache(), load_calibration(), _load_creator_blacklist() (+15 more)

### Community 136 - "Subsystem 136"
Cohesion: 0.12
Nodes (23): classify_lead_context(), ContextLengthRule, detect_message_type(), enforce_length(), get_context_rule(), get_length_guidance_prompt(), get_short_replacement(), get_soft_max() (+15 more)

### Community 137 - "Subsystem 137"
Cohesion: 0.12
Nodes (14): ingest_youtube_v2(), YouTube Ingestion V2 - Transcripts + RAG Chunks  Soporta: 1. Obtener videos de u, Limpia datos anteriores de YouTube para el creator., Obtiene videos del canal., Obtiene transcript de un video., Crea content chunks para RAG desde transcripts.          Cada video se divide en, Resultado completo de ingestion de YouTube., Guarda content chunks en PostgreSQL. (+6 more)

### Community 138 - "Subsystem 138"
Cohesion: 0.12
Nodes (22): _bfi_detailed(), _bfi_one_line(), build_docd_a(), build_docd_b(), build_docd_c(), build_docd_d(), compute_metrics(), generate_responses() (+14 more)

### Community 139 - "Subsystem 139"
Cohesion: 0.09
Nodes (8): Audit tests for core/embeddings.py — OpenAI text-embedding-3-small., Verify module imports and constants., Cosine similarity edge cases., EMBEDDING_DIMENSIONS must be 1536 (OpenAI text-embedding-3-small)., OpenAI API embedding generation — mocked calls., TestCosineSimilarity, TestEmbeddingsImport, TestOpenAIEmbeddings

### Community 140 - "Subsystem 140"
Cohesion: 0.13
Nodes (22): _build_messages(), collect_prompts(), convert_existing_pairs(), create_dpo_pair(), generate_responses_deepinfra(), generate_responses_fireworks(), generate_responses_together(), generate_synthetic_prompts() (+14 more)

### Community 141 - "Subsystem 141"
Cohesion: 0.32
Nodes (22): cid(), get_conn(), main(), Record a test result., Return the correct creator_id value based on table type., set_category(), test(), test_conversation_states() (+14 more)

### Community 142 - "Subsystem 142"
Cohesion: 0.13
Nodes (22): clear_existing_data(), create_bookings(), create_creator(), create_followers(), create_knowledge_base(), create_leads_and_states(), create_messages(), create_products() (+14 more)

### Community 143 - "Subsystem 143"
Cohesion: 0.1
Nodes (10): get_query_expander(), QueryExpander, Expande query con sinónimos y variaciones.          Args:             query: Que, Expande query en conjunto de tokens únicos.          Args:             query: Qu, Añade sinónimos custom al diccionario, Añade acrónimo custom al diccionario, Get global query expander instance, Expande queries con sinónimos y variaciones para mejorar recall.      Técnicas: (+2 more)

### Community 144 - "Subsystem 144"
Cohesion: 0.17
Nodes (21): _call_judge(), _call_prometheus(), _estimate_tokens(), _parse_rating(), _rating_to_score(), LLM Judge — Reusable LLM-as-judge component for quality evaluation.  Uses GPT-4o, Call LLM judge: Prometheus (HF) → Gemini fallback., B2: Does the bot maintain the creator's personality consistently? (+13 more)

### Community 145 - "Subsystem 145"
Cohesion: 0.09
Nodes (12): Tests for Webhook Routing - Multi-creator isolation and ID extraction., Test edge cases in webhook payloads., Entry without messaging key should not crash., Should handle large payloads without issues., Test comment/reaction webhook format with changes., Extracted IDs should not contain duplicates., Test ID extraction from various webhook payload formats., Test that routing correctly isolates creators. (+4 more)

### Community 146 - "Subsystem 146"
Cohesion: 0.09
Nodes (6): Tests for question remover., TestContainsBannedQuestion, TestConvertQuestionToStatement, TestProcessQuestions, TestRemoveBannedQuestions, TestShouldAllowQuestion

### Community 147 - "Subsystem 147"
Cohesion: 0.09
Nodes (13): Audit tests for api/services/data_sync.py., Verify that the data_sync module and its key symbols can be imported., Verify graceful handling of missing or empty data., All public functions should be importable., sync_message_to_json should create a basic JSON if none exists., Verify that full_sync_creator tracks sync statistics correctly., Test that sync_lead_to_json writes correctly shaped JSON data., Test that sync only upgrades status, never downgrades. (+5 more)

### Community 148 - "Subsystem 148"
Cohesion: 0.14
Nodes (21): audit_shadow_data(), compute_all_lexical(), compute_bleu4(), compute_chrf(), compute_length_ratio(), compute_rouge_l(), compute_vocab_overlap(), _get_platform_user_id() (+13 more)

### Community 149 - "Subsystem 149"
Cohesion: 0.15
Nodes (21): _build_correlation_table(), _fmt_cell(), _load_auto_scores_from_summary(), _load_human_scores(), _load_json(), main(), _pearson(), _print_correlation_table() (+13 more)

### Community 150 - "Subsystem 150"
Cohesion: 0.09
Nodes (14): Extended calendar router tests - Written BEFORE implementation (TDD). Tests for, Calendar router should have GET /link/{meeting_type} endpoint., Calendar router should have POST /bookings/{booking_id}/complete endpoint., Calendar router should have POST /bookings/{booking_id}/no-show endpoint., Test main app includes all calendar endpoints via router., Main app should have /calendar/{creator_id}/link/{meeting_type} endpoint., Main app should have /calendar/{creator_id}/bookings/{booking_id}/complete endpo, Main app should have /calendar/{creator_id}/bookings/{booking_id}/no-show endpoi (+6 more)

### Community 151 - "Subsystem 151"
Cohesion: 0.2
Nodes (21): format_currency(), format_number(), format_percentage(), generate_daily_report(), generate_full_report(), generate_funnel_report(), generate_intent_report(), generate_platform_report() (+13 more)

### Community 152 - "Subsystem 152"
Cohesion: 0.16
Nodes (21): admin_headers(), DELETE(), e2e_flow_1_instagram_webhook(), e2e_flow_2_leads_crud(), e2e_flow_3_products(), e2e_flow_4_copilot(), e2e_flow_5_oauth_status(), GET() (+13 more)

### Community 153 - "Subsystem 153"
Cohesion: 0.12
Nodes (21): create_google_meet_event(), debug_google_config(), delete_google_calendar_event(), force_refresh_google(), get_google_freebusy(), get_valid_google_token(), google_oauth_callback(), google_oauth_start() (+13 more)

### Community 154 - "Subsystem 154"
Cohesion: 0.13
Nodes (21): _count_creator_messages(), ensure_profiles(), _generate_baseline(), _generate_calibration(), _generate_length_profile(), _generate_profiles_async(), _generate_profiles_sync(), _get_creator_messages() (+13 more)

### Community 155 - "Subsystem 155"
Cohesion: 0.14
Nodes (21): create_relationship_dna(), delete_relationship_dna(), _dna_to_dict(), _get_dna_from_json(), get_or_create_relationship_dna(), get_relationship_dna(), get_session(), _list_dnas_from_json() (+13 more)

### Community 156 - "Subsystem 156"
Cohesion: 0.13
Nodes (20): compare_vs_baseline(), compute_l3_bertscore(), compute_semsim(), generate_layer2_dna_run(), _get_platform_user_id(), load_dna_context_prompt(), load_dna_for_lead(), _load_lead_profile() (+12 more)

### Community 157 - "Subsystem 157"
Cohesion: 0.1
Nodes (12): Audit tests for api/services/db_service.py., Verify that the service module and its key symbols can be imported., Verify graceful failure when the DB session is unavailable., Core public functions are importable without side-effects., Verify that get_leads passes the limit parameter correctly., Test lead retrieval returns correctly-shaped results when DB is mocked., Edge cases where database returns no data., TestDbServiceImport (+4 more)

### Community 158 - "Subsystem 158"
Cohesion: 0.14
Nodes (20): _analyze_issues(), _find_strongest_dimension(), _find_weakest_dimension(), generate_dashboard_data(), generate_dashboard_from_test_cases(), _get_recommendation(), main(), print_dashboard_summary() (+12 more)

### Community 159 - "Subsystem 159"
Cohesion: 0.18
Nodes (20): build_multi_turn_cases(), build_single_turn_cases(), _classify_message(), _detect_language(), extract_conversations(), _get_conn(), get_language_distribution(), get_real_distribution() (+12 more)

### Community 160 - "Subsystem 160"
Cohesion: 0.17
Nodes (20): detect_interests(), detect_language(), detect_objections(), detect_product_interest(), get_connection(), load_all_data(), main(), phase2_user_profiles() (+12 more)

### Community 161 - "Subsystem 161"
Cohesion: 0.13
Nodes (13): _categorize(), get_relationship_scorer(), Relationship Scorer v2 — multi-signal, gradated, universal, USER-only.  Replaces, Score from memory engine facts. Max 0.35., Score from DB lead.status field. Max 0.30.          The lead.status field is man, Score from user message count. Max 0.15., Score from relationship duration. Max 0.15., Score from message format — audios and long messages. Max 0.10. (+5 more)

### Community 162 - "Subsystem 162"
Cohesion: 0.13
Nodes (18): CreatorDMStyle, Estilo de DM del creador basado en datos reales., CreatorDMStyleService, format_for_prompt(), get_creator_dm_style_for_prompt(), get_style(), Servicio para obtener y formatear el estilo de DM del creador.  Este servicio pr, Servicio para obtener el estilo de DM de un creador. (+10 more)

### Community 163 - "Subsystem 163"
Cohesion: 0.15
Nodes (19): detect_platform(), extract_and_save_preview(), extract_link_preview(), extract_previews_from_text(), extract_urls(), _fetch_og_metadata(), get_domain(), has_link_preview() (+11 more)

### Community 164 - "Subsystem 164"
Cohesion: 0.14
Nodes (19): _cleanup_expired_entries(), configure_reactivation(), get_ghost_leads_for_reactivation(), _get_reactivation_key(), get_reactivation_stats(), _mark_as_reactivated(), Ghost Reactivation Service - Reactiva automáticamente leads fantasma.  Un lead f, Reactiva leads fantasma para un creator.      Args:         creator_id: ID del c (+11 more)

### Community 165 - "Subsystem 165"
Cohesion: 0.19
Nodes (19): _cleanup(), _create_test_followups(), _get_creator_id(), _get_followups_path(), dry_run=false with force_due=true should process and update stats, Generate unique creator ID per test run, due_only=true should only process followups with scheduled_at <= now, limit parameter should cap processed followups (+11 more)

### Community 166 - "Subsystem 166"
Cohesion: 0.17
Nodes (19): aggregate_runs(), _bleu4(), _chrf(), compute_l1(), compute_l3(), _compute_text_metrics(), generate_naked_run(), main() (+11 more)

### Community 167 - "Subsystem 167"
Cohesion: 0.1
Nodes (12): Migration tests - Verify dm_agent_v2 works as drop-in replacement. Written BEFOR, V2 should be importable with DMResponderAgent alias., V2 should instantiate with same interface as V1., V2 should have all required public methods., V2 should have all required services initialized., Test V2 compatibility with expected V1 behavior., add_knowledge should return document ID., get_stats should return dictionary with expected keys. (+4 more)

### Community 168 - "Subsystem 168"
Cohesion: 0.13
Nodes (12): _mock_response(), Tests for DeepInfra provider, including config-driven mode and /no_think injecti, Pure function tests — kept after refactor for regression safety., Legacy path: model_id=None — current prod behavior must be preserved., test_caller_override_wins_over_config(), test_config_model_string_overrides_env_var(), test_empty_no_think_suffix_skips_injection(), test_legacy_qwen3_substring_injects_no_think() (+4 more)

### Community 169 - "Subsystem 169"
Cohesion: 0.1
Nodes (3): _clear_cache(), Unit tests for core.providers.model_config — shared model-config loader., Ensure each test starts with a fresh cache.

### Community 170 - "Subsystem 170"
Cohesion: 0.12
Nodes (11): _mock_response(), Tests for OpenRouter provider, including config-driven mode., Legacy path: model_id=None → existing behavior preserved., Config-driven path: model_id loads sampling/runtime/provider from JSON., test_caller_override_wins_over_config(), test_legacy_path_uses_env_and_arg_defaults(), test_loads_config_values(), test_unknown_model_id_falls_back_to_default() (+3 more)

### Community 171 - "Subsystem 171"
Cohesion: 0.14
Nodes (19): categorize_pool_responses(), compute_baseline(), compute_context_soft_max(), extract_context_response_pools(), extract_creator_vocabulary(), extract_few_shot(), extract_response_pools(), load_conversation_pairs() (+11 more)

### Community 172 - "Subsystem 172"
Cohesion: 0.13
Nodes (19): _build_expertise_chunks(), _build_faq_chunks_from_db(), _build_objection_chunks(), _build_policies_chunks(), build_proposition_chunks(), _build_values_chunks(), _get_context_prefix(), insert_chunks() (+11 more)

### Community 173 - "Subsystem 173"
Cohesion: 0.12
Nodes (19): _check_message_window(), _get_creator_info_by_name(), get_nurturing_followups(), get_nurturing_stats(), _guess_channel(), Nurturing followup management endpoints and helpers, Check if follower's last inbound message is within Meta's messaging window., Save sent nurturing message to messages table for inbox visibility. (+11 more)

### Community 174 - "Subsystem 174"
Cohesion: 0.15
Nodes (19): _context_to_model(), create_post_context(), delete_post_context(), get_expired_contexts(), get_or_create_post_context(), get_post_context(), get_session(), _model_to_dict() (+11 more)

### Community 175 - "Subsystem 175"
Cohesion: 0.16
Nodes (17): build_few_shot(), build_prompt(), build_user_prompt(), call_gemini(), call_model(), call_openai(), load_few_shot(), load_system_prompt() (+9 more)

### Community 176 - "Subsystem 176"
Cohesion: 0.11
Nodes (12): Step 4: Verify follower detail endpoint returns messages, Step 5: Test updating lead status via API, Step 6: Clean up test data, Test that nurturing scheduler status endpoint works, Test that health endpoint works (returns valid response), End-to-end flow tests - requires DATABASE_URL, Step 1: Create a lead via API, Step 2: Add messages to simulate a conversation (+4 more)

### Community 177 - "Subsystem 177"
Cohesion: 0.17
Nodes (18): build_level1(), build_level2(), build_level3(), _detect_topic(), _extractive_summary(), _fetch_conversations(), _get_db_session(), _get_persona_dir() (+10 more)

### Community 178 - "Subsystem 178"
Cohesion: 0.13
Nodes (10): Centralized background task scheduler with health monitoring., Sleep that can be interrupted by shutdown., Manages background tasks with health tracking and graceful shutdown., Register a task to run on a schedule., Start all registered tasks., Gracefully stop all tasks., Return health status of all tasks., Run a single task on its schedule. (+2 more)

### Community 179 - "Subsystem 179"
Cohesion: 0.16
Nodes (17): _get_creator_emoji_rate(), get_emoji_adaptation(), _has_emoji(), _load_baseline(), _load_bot_natural_rates(), _load_eval_profile_emoji_rate(), normalize_style(), Style normalizer — post-processing to match creator quantitative style.  Fixes t (+9 more)

### Community 180 - "Subsystem 180"
Cohesion: 0.2
Nodes (17): _parse_file(), E2E tests for the onboarding pipeline. Verifies that all components are wired co, Read a file relative to backend/., Parse a Python file and return AST., _read_file(), test_clone_creation_function_exists(), test_no_race_condition(), test_onboarding_endpoints_exist() (+9 more)

### Community 181 - "Subsystem 181"
Cohesion: 0.11
Nodes (11): Tests for sensitive content detection integration in dm_agent_v2.  Step 1 of cog, Verify sensitive_detector module exists and is importable., detect_sensitive_content function should exist., get_crisis_resources function should exist., detect_sensitive_content should return result with attributes or None., get_crisis_resources should return Spanish crisis resources., Verify integration points in dm_agent_v2., ENABLE_SENSITIVE_DETECTION flag should exist in dm_agent_v2. (+3 more)

### Community 182 - "Subsystem 182"
Cohesion: 0.11
Nodes (11): Tests for output validation integration in dm_agent_v2.  Step 2 of cognitive mod, Verify output_validator module exists and is importable., validate_prices function should exist., validate_links function should exist., validate_prices should return list of issues., validate_links should return tuple of (issues, corrected)., Verify integration points in dm_agent_v2., ENABLE_OUTPUT_VALIDATION flag should exist in dm_agent_v2. (+3 more)

### Community 183 - "Subsystem 183"
Cohesion: 0.24
Nodes (17): check_api_health(), check_data_directory(), check_env_vars(), check_imports(), check_required_files(), check_syntax(), fail(), main() (+9 more)

### Community 184 - "Subsystem 184"
Cohesion: 0.16
Nodes (17): ConversationScenario, main(), print_summary(), 50-Conversation Stress Test — validates DM pipeline under load.  Runs 50 synthet, Result of processing a single turn., Result of running a complete scenario., Final report for the stress test., Run a single conversation scenario through the DM pipeline. (+9 more)

### Community 185 - "Subsystem 185"
Cohesion: 0.15
Nodes (17): contains_banned_question(), convert_question_to_statement(), _load_creator_question_rate(), _load_creator_question_rate_std(), _normalize_for_filler(), process_questions(), Question Remover - Removes unnecessary questions from responses.  Loads creator', Load creator's question_rate standard deviation from profile.      Returns std a (+9 more)

### Community 186 - "Subsystem 186"
Cohesion: 0.12
Nodes (11): Alembic Environment Configuration for CLONNECT, Run migrations in 'offline' mode.      This configures the context with just a U, Run migrations in 'online' mode.      In this scenario we need to create an Engi, run_migrations_offline(), run_migrations_online(), get_logger(), Logging configuration for Clonnect API, Get a logger instance for a module.      Args:         name: Module name (typica (+3 more)

### Community 187 - "Subsystem 187"
Cohesion: 0.17
Nodes (16): cleanup_test_data(), Test updating sequence steps, Clean up test data files, Test getting nurturing stats, Test getting enrolled followers for a sequence, Test cancelling nurturing for a follower, Test the complete nurturing flow, Test that GET /sequences returns all default nurturing sequences (+8 more)

### Community 188 - "Subsystem 188"
Cohesion: 0.14
Nodes (15): build_system_prompt(), call_fireworks(), call_gemini(), call_openai(), call_together(), format_detailed_output(), format_markdown_table(), main() (+7 more)

### Community 189 - "Subsystem 189"
Cohesion: 0.13
Nodes (15): add_instagram_id_to_creator(), clear_routing_cache(), extract_all_instagram_ids(), find_creator_for_webhook(), get_creator_by_any_instagram_id(), Webhook Routing for Multi-Creator Support  This module provides robust routing o, Try to find a creator using any of the provided Instagram IDs.      Iterates thr, Save an unmatched webhook for later debugging and resolution.      Stores only n (+7 more)

### Community 190 - "Subsystem 190"
Cohesion: 0.12
Nodes (13): clear_cache(), get_provider_info(), get_runtime(), get_safety(), get_sampling(), load_model_config(), Shared model-config loader.  Loads per-model JSON configs from config/models/. U, Return safety block. Defaults to BLOCK_ONLY_HIGH for all categories. (+5 more)

### Community 191 - "Subsystem 191"
Cohesion: 0.17
Nodes (15): _get_conn(), CCEE Business Metrics (I1-I4)  Queries production DB for business impact metrics, I3: % of conversations where creator manually intervened after bot.      Lower e, I4: % of leads that progressed in status after bot interaction.      Checks if l, Get DB connection (same pattern as style_profile_builder)., Compute all business metrics (I1-I4) for a creator.      Returns aggregate score, Resolve creator slug (e.g. 'iris_bertran') to UUID., I1: % of leads that sent at least one message after receiving a bot message. (+7 more)

### Community 192 - "Subsystem 192"
Cohesion: 0.12
Nodes (15): Tests for services/autolearning_analyzer.py (shim)  analyze_creator_action is no, Called with minimal args does not raise., _is_non_text_response correctly identifies media prefixes., Approval is a no-op — no rules or LLM calls., Edit is a no-op — no LLM call, no rule created., Discard is a no-op — no LLM call, no rule created., No exception when suggested_response is None., Unknown action type does not raise. (+7 more)

### Community 193 - "Subsystem 193"
Cohesion: 0.17
Nodes (15): episodic_search_for_case(), generate_l2_sys10_run(), _get_raw_connection(), _get_st_model(), _load_corpus(), main(), _print_report(), CPE Ablation — Layer 2 + System #10: Episodic Memory (conversation_embeddings). (+7 more)

### Community 194 - "Subsystem 194"
Cohesion: 0.16
Nodes (15): _make_rule(), Tests for services/learning_rules_service.py, Respects max_rules limit., Create a mock LearningRule object., Adjusts times_helped and confidence correctly., Returns False when rule doesn't exist., Creating a new rule stores it and returns its ID., Same pattern+text increments confidence instead of creating new rule. (+7 more)

### Community 195 - "Subsystem 195"
Cohesion: 0.18
Nodes (15): cliffs_delta(), compute_bertscore_for_runs(), _get_platform_user_id(), main(), _norm_cdf(), CPE Ablation Runner — Statistically Rigorous System Isolation  Runs the CPE v2 m, Standard normal CDF approximation., Cliff's delta effect size (non-parametric).      Interpretation:       |d| < 0.1 (+7 more)

### Community 196 - "Subsystem 196"
Cohesion: 0.15
Nodes (10): Category 5: EXPERIENCIA USUARIO - Test Latencia Tests that verify pipeline overh, Multiple calls to the same function produce similar timing.          Runs classi, No blocking operations in non-LLM pipeline stages.          Runs the full non-LL, Execute func and return (result, elapsed_ms)., Pipeline overhead must remain sub-100ms for non-LLM stages., Context detection + intent classification combined < 100ms.          In producti, Simple intent classification alone < 50ms.          classify_intent_simple is a, Length controller computation is fast (< 10ms per call).          get_length_gui (+2 more)

### Community 197 - "Subsystem 197"
Cohesion: 0.28
Nodes (15): api_get(), api_post(), check(), main(), Verifica RAG/contenido, Verifica copilot endpoints, Imprime resultado de verificación, POST request a la API (+7 more)

### Community 198 - "Subsystem 198"
Cohesion: 0.21
Nodes (15): build_categorization_prompt(), call_gemini(), categorize_batch(), fetch_creator_uuid(), fetch_existing_chunk_ids(), fetch_qa_pairs(), insert_chunks(), is_noise() (+7 more)

### Community 199 - "Subsystem 199"
Cohesion: 0.35
Nodes (15): check_content_index(), check_database(), check_env_vars(), check_instagram_token(), check_nurturing(), error(), info(), main() (+7 more)

### Community 200 - "Subsystem 200"
Cohesion: 0.12
Nodes (15): gdpr_anonymize_data(), gdpr_audit_log(), gdpr_data_inventory(), gdpr_delete_data(), gdpr_export_data(), gdpr_get_consent(), gdpr_record_consent(), GDPR Router - GDPR compliance endpoints Extracted from main.py as part of refact (+7 more)

### Community 201 - "Subsystem 201"
Cohesion: 0.23
Nodes (14): _fmt_opt(), _fmt_std(), _generate_run(), _load_json(), _load_json_optional(), main(), _print_comparison(), _print_report() (+6 more)

### Community 202 - "Subsystem 202"
Cohesion: 0.2
Nodes (14): compare_metrics(), compute_baseline(), compute_metrics(), compute_vocabulary_overlap(), _get_platform_user_id(), main(), CPE Level 1: Quantitative Style Comparison — Bot vs Creator  Compares measurable, Jaccard similarity between creator and bot vocabulary. (+6 more)

### Community 203 - "Subsystem 203"
Cohesion: 0.19
Nodes (14): build_history_metadata(), compute_clone_score(), get_active_flags(), get_model_name(), get_platform_user_id(), main(), Baseline Measurement Script v1 — Post-Blackout Clone Score  Measures Clone Score, Run the production pipeline for a single test conversation.      Returns result (+6 more)

### Community 204 - "Subsystem 204"
Cohesion: 0.17
Nodes (14): extract_faqs_from_text(), generate_ai_knowledge(), generate_ai_rules(), generate_fallback_about(), generate_fallback_faqs(), generate_knowledge_full(), AI Router - AI personality generation endpoints (Grok API) Extracted from main.p, Extract about info from content when API is unavailable (+6 more)

### Community 205 - "Subsystem 205"
Cohesion: 0.19
Nodes (13): extract_links_from_html(), extract_text_from_html(), extract_title_from_html(), extract_url_from_text(), Website Scraper - Extrae contenido de websites para indexar en RAG.  Usado duran, Extrae texto limpio de HTML., Extrae el titulo de una pagina HTML., Extrae links del mismo dominio. (+5 more)

### Community 206 - "Subsystem 206"
Cohesion: 0.21
Nodes (13): get_reranker(), Cross-Encoder Reranking para mejorar precisión de RAG.  Mejora la precisión del, Rerank using local Cross-Encoder model (mmarco-mMiniLMv2-L12-H384-v1)., Reordena documentos usando Cross-Encoder para mejor precisión.      Dispatches t, Rerank con filtro por threshold mínimo de relevancia.      Args:         query:, Lazy load del modelo Cross-Encoder (multilingual by default)., Pre-load model and run a dummy prediction to warm up the JIT/caches., Rerank using Cohere Rerank API (rerank-v3.5).      NOT ACTIVATED — skeleton for (+5 more)

### Community 207 - "Subsystem 207"
Cohesion: 0.2
Nodes (13): call_gemini_extraction(), call_openai_extraction(), extract_json_with_llm(), extract_with_llm(), _fix_double_encoding(), LLM client for personality extraction pipeline.  Uses Gemini 2.5 Flash (large co, Fallback: call OpenAI for extraction analysis., Call LLM for extraction with cascade: Gemini Flash → OpenAI GPT-4o.      Returns (+5 more)

### Community 208 - "Subsystem 208"
Cohesion: 0.21
Nodes (13): generate_run(), inject_memory_into_prompt(), load_layer2_per_case(), main(), _print_report(), CPE Ablation — Layer 2 + System #9 (Memory Engine).  Adds ONLY #9 (long-term mem, Resolve a test-case username/phone to a real lead UUID in the DB.     Returns No, Call Memory Engine recall() for a lead. Returns (memory_context_str, metadata). (+5 more)

### Community 209 - "Subsystem 209"
Cohesion: 0.14
Nodes (9): Extended payments router tests - Written BEFORE implementation (TDD). Tests for, Payments router should have customer purchases endpoint., Payments router should have attribute sale endpoint., Test main app includes extended payment endpoints., Main app should have customer purchases endpoint., Main app should have attribute sale endpoint., Test customer-related payment endpoints., TestMainAppPaymentsEndpoints (+1 more)

### Community 210 - "Subsystem 210"
Cohesion: 0.14
Nodes (8): Tests for RelationshipDNA SQL migration.  TDD: Tests written FIRST before implem, Test suite for RelationshipDNA migration file., Migration SQL file should exist., Migration should contain CREATE TABLE statement., Migration should contain all required columns., Migration should have unique constraint on creator_id + follower_id., Migration should create indexes for performance., TestRelationshipDNAMigration

### Community 211 - "Subsystem 211"
Cohesion: 0.14
Nodes (9): Startup module tests - Written BEFORE implementation (TDD). Tests for startup ha, Startup module should exist and be importable., Startup should have register_startup_handlers function., Test main app uses startup module., Main app should still import and work after startup extraction., Main app should have a startup event registered., Test startup module can be imported., TestMainAppStartup (+1 more)

### Community 212 - "Subsystem 212"
Cohesion: 0.14
Nodes (9): Tests for response fixes integration in dm_agent_v2.  Step 3 of cognitive module, Verify response_fixes module exists and is importable., apply_all_response_fixes function should exist., apply_all_response_fixes should return a string., Verify integration points in dm_agent_v2., ENABLE_RESPONSE_FIXES flag should exist in dm_agent_v2., ENABLE_RESPONSE_FIXES should default to True., TestResponseFixesIntegration (+1 more)

### Community 213 - "Subsystem 213"
Cohesion: 0.22
Nodes (13): build_cpt(), build_dpo(), build_sft(), _estimate_tokens(), _is_valid_text(), main(), print_stats(), Prepare CPT, SFT, and DPO datasets for Qwen3-32B fine-tuning with TRL.  Usage: (+5 more)

### Community 214 - "Subsystem 214"
Cohesion: 0.21
Nodes (13): classify_message_length(), classify_turn_position(), cluster_failures(), compute_pair_gap(), extract_failure_patterns(), main(), print_clustering_report(), Cluster failures by multiple axes. (+5 more)

### Community 215 - "Subsystem 215"
Cohesion: 0.21
Nodes (13): create_lead(), get_existing_leads(), get_existing_messages(), import_messages(), load_backup_data(), main(), Import messages for a lead. Returns (imported, skipped) counts., Update lead's first_contact_at and last_contact_at based on messages. (+5 more)

### Community 216 - "Subsystem 216"
Cohesion: 0.24
Nodes (3): FPDF, ClonnectPDF, generate_pdf()

### Community 217 - "Subsystem 217"
Cohesion: 0.15
Nodes (13): generate_weekly_report(), get_intelligent_dashboard(), get_patterns(), get_predictions(), get_recommendations(), get_weekly_report(), Intelligence API endpoints - Business Intelligence and Predictive Analytics.  Pr, Get recommendations for a creator.      Categories:     - content: Content creat (+5 more)

### Community 218 - "Subsystem 218"
Cohesion: 0.2
Nodes (13): batch_recalculate_scores(), batch_recalculate_scores_paged(), calculate_score(), classify_lead(), extract_signals(), Lead Classification + Scoring V3 — 6-Category Flat System.  Architecture:   1. e, Classify the lead into one of 6 categories based on extracted signals.      Prio, Calculate a score within the status's fixed range based on signal quality. (+5 more)

### Community 219 - "Subsystem 219"
Cohesion: 0.18
Nodes (13): capture_media_from_url(), capture_media_sync(), capture_story_thumbnail(), download_media(), get_content_type_from_headers(), is_cdn_url(), Media Capture Service.  Captures Instagram/WhatsApp media from temporary CDN URL, Extract content type from response headers. (+5 more)

### Community 220 - "Subsystem 220"
Cohesion: 0.18
Nodes (12): check_message_gaps(), _extract_media_from_attachments(), get_reconciliation_status(), Reconciliation logic for message reconciliation.  Core reconciliation functions, Reconcile messages for a single creator.      Fetches conversations from Instagr, # IMPORTANT: Only count messages FROM the follower, not creator echo messages, Extract media info from Instagram message attachments.      FIX 2026-02-05: Supp, Run reconciliation for all creators with Instagram connections.      Args: (+4 more)

### Community 221 - "Subsystem 221"
Cohesion: 0.15
Nodes (5): Tests for Gemini provider routing + LLM_MODEL_NAME dispatch., Routing layer: generate_dm_response dispatches based on LLM_MODEL_NAME., _call_gemini reads safety / penalties from config when model_id provided., TestCallGeminiConfigDriven, TestGenerateDmResponseRouting

### Community 222 - "Subsystem 222"
Cohesion: 0.15
Nodes (2): Test expanded fact tracking (9 types) in dm_agent_v2 (Step 22)., TestFullFactTracking

### Community 223 - "Subsystem 223"
Cohesion: 0.23
Nodes (12): fetch_clone_scores(), fetch_copilot_stats(), fetch_dm_count(), get_db_session(), main(), print_report(), Fetch CloneScore evaluations for the period., Count bot DM responses in the period. (+4 more)

### Community 224 - "Subsystem 224"
Cohesion: 0.24
Nodes (12): detect_lang(), extract_pairs(), has_url(), is_bad_response(), is_bad_user_msg(), load_system_prompt(), main(), make_line() (+4 more)

### Community 225 - "Subsystem 225"
Cohesion: 0.27
Nodes (12): _get_model_and_tokenizer(), _load_jsonl(), main(), Fine-tune Qwen3-32B with QLoRA using TRL (CPT -> SFT -> DPO pipeline).  Usage:, Supervised Fine-Tuning: chat format with system/user/assistant turns., Direct Preference Optimization: align to Iris's real responses., Load model with QLoRA quantization via Unsloth., Load a JSONL file as a HuggingFace Dataset. (+4 more)

### Community 226 - "Subsystem 226"
Cohesion: 0.23
Nodes (11): _clean_title(), extract_with_readability(), get_readability_stats(), _html_to_text(), is_readability_available(), Content extraction using Readability algorithm.  Readability is the algorithm us, Clean extracted title.      Removes common suffixes like " | Site Name" or " - C, Convert HTML to clean plain text.      Preserves paragraph structure while remov (+3 more)

### Community 227 - "Subsystem 227"
Cohesion: 0.23
Nodes (11): fetch_instagram_profile(), fetch_instagram_profile_detailed(), fetch_instagram_profile_with_retry(), fetch_profiles_batch(), ProfileResult, Instagram Profile Fetcher Fetches user profile data (name, profile_pic_url) from, Fetch Instagram profile with automatic retry for transient errors.      Retries, Fetch profiles for multiple users with rate limiting.      Args:         user_id (+3 more)

### Community 228 - "Subsystem 228"
Cohesion: 0.21
Nodes (11): calculate_confidence(), _get_historical_rate(), get_historical_rates(), Confidence Scorer — Multi-factor confidence scoring for copilot suggestions.  Fa, Get historical approval rate for this creator + intent combination.     Falls ba, Score response length quality. Ideal: 20-200 chars., Score based on blacklisted patterns. 1.0 = clean, 0.0 = many matches., Get historical approval rates by intent for a creator.     Used by the confidenc (+3 more)

### Community 229 - "Subsystem 229"
Cohesion: 0.23
Nodes (11): _capture_media_permanently(), extract_media_info(), process_message_impl(), _process_story_message(), Instagram media extraction and message processing.  Extracts media info from web, Process an Instagram message through DMResponderAgent.      Handles media extrac, Extract media URL and type from Instagram message attachments.      Supports bot, Process story reply/mention/reaction and capture media. (+3 more)

### Community 230 - "Subsystem 230"
Cohesion: 0.17
Nodes (7): Tests for PostContext SQL migration.  TDD: Tests written FIRST before implementa, Test suite for post_contexts table migration., Should have migration SQL file., Should define all required columns., Should have unique constraint on creator_id., Should have performance indexes., TestPostContextMigration

### Community 231 - "Subsystem 231"
Cohesion: 0.17
Nodes (8): Static file serving module tests - Written BEFORE implementation (TDD)., Static serving module should exist and be importable., Static serving should have register_static_routes function., Test main app has static endpoints registered., Main app should have catch-all route for SPA., Test static serving module can be imported., TestMainAppStaticEndpoints, TestStaticServingModuleImport

### Community 232 - "Subsystem 232"
Cohesion: 0.21
Nodes (11): export_table_to_json(), get_database_url(), list_backups(), Restore a table from JSON file (CAREFUL: Replaces existing data!), List available backups, Validate table name against whitelist to prevent SQL injection., Get database URL from environment, Export a table to JSON file (+3 more)

### Community 233 - "Subsystem 233"
Cohesion: 0.21
Nodes (11): call_judge_openai(), compute_metrics(), evaluate_pair(), main(), print_judge_report(), Evaluate a single pair with randomized A/B assignment., Run blind A/B evaluation across all pairs using GPT-4o-mini., Compute aggregate metrics from GPT-4o-mini judge evaluations. (+3 more)

### Community 234 - "Subsystem 234"
Cohesion: 0.24
Nodes (11): call_gemini(), check_existing(), fetch_context(), fetch_conversations(), format_context_for_prompt(), main(), Generate synthetic preference pairs using Pseudo Preference Tuning approach. (Ta, Check if we already have a pair for this message. (+3 more)

### Community 235 - "Subsystem 235"
Cohesion: 0.23
Nodes (11): disable_side_effects(), init_agent(), main(), print_backtest_report(), Run the massive backtest across all conversations., Print backtest summary., Disable side-effect features for safe backtest execution., Initialize the DM pipeline agent. (+3 more)

### Community 236 - "Subsystem 236"
Cohesion: 0.17
Nodes (11): calcom_webhook(), calendly_webhook(), hotmart_webhook(), paypal_webhook(), Webhooks Router - Payment and Calendar webhook endpoints Extracted from main.py, Calendly webhook endpoint.      Processes:     - invitee.created (new booking), Cal.com webhook endpoint.      Processes:     - BOOKING_CREATED     - BOOKING_CA, Stripe webhook endpoint.      Processes:     - checkout.session.completed     - (+3 more)

### Community 237 - "Subsystem 237"
Cohesion: 0.17
Nodes (11): clear_instagram_cache(), connect_instagram_page(), get_instagram_status(), list_instagram_creators(), Instagram Persistent Menu + Other Management Endpoints  Includes persistent menu, Connect/register an Instagram page to a creator.      This endpoint allows manua, Get Instagram connection status for a creator., List all creators with Instagram connections.     Useful for debugging multi-cre (+3 more)

### Community 238 - "Subsystem 238"
Cohesion: 0.24
Nodes (11): _classify_type(), _compute_baseline(), _detect_language(), generate_calibration(), Calibration Generator — auto-generate calibration files from conversation histor, Select diverse few-shot examples balancing type and language., Generate calibration file from DB conversation history.      Queries messages wh, Detect language of text. Returns 'ca', 'es', or 'mixto'. (+3 more)

### Community 239 - "Subsystem 239"
Cohesion: 0.23
Nodes (11): content_refresh_loop(), _embed_new_chunks(), _hydrate_rag_for_creator(), Content Refresh Service — Auto-refresh creator content every 24h.  Re-scrapes In, Generate embeddings for content_chunks that don't have a matching     content_em, Reload RAG documents from DB for this creator., Refresh content for all creators with bot_active=True and a valid IG token., Background loop that refreshes all active creators every 24h.      Follows the s (+3 more)

### Community 240 - "Subsystem 240"
Cohesion: 0.23
Nodes (11): _embed_chunk(), _fetch_post_details(), _post_exists_in_db(), process_feed_webhook(), _process_single_post(), Real-time content ingestion via Instagram feed webhooks (SPEC-004B).  When a cre, Check if a post already exists in instagram_posts table., Fetch full post details from Instagram Graph API.      Args:         access_toke (+3 more)

### Community 241 - "Subsystem 241"
Cohesion: 0.18
Nodes (12): Qwen/Qwen3-32B Base Model, Qwen/Qwen3-8B Base Model, Direct Preference Optimization (DPO), DPRF — Dynamic Persona Refinement Framework, Feedback Flywheel Architecture, Implementation Phase 3 — DPO Batch Training, Human Feedback System for Persona Clone Improvement, LoRA DPO Adapter — Qwen3-32B (+4 more)

### Community 242 - "Subsystem 242"
Cohesion: 0.2
Nodes (6): ConversationMode, Conversation Mode Detection — determines conversation type per message. Universa, Build factual context note for Recalling block.          Only injects if mode is, Detects conversation mode from message + intent + creator's discovered types., Detect conversation mode.          Returns:             (dominant_mode, probabil, Structural classification — same logic as discovery for consistency.

### Community 243 - "Subsystem 243"
Cohesion: 0.25
Nodes (10): call_google_ai(), _circuit_is_open(), Google AI Studio provider for Gemma 4 and other Google-hosted models.  Uses the, Call Google AI Studio via google-generativeai SDK.      Sampling params come fro, Raise FileNotFoundError if the model's template_file does not exist.      Call t, Strip Gemma 4 thought blocks and reasoning bullets.      Handles:       <|channe, _record_failure(), _record_success() (+2 more)

### Community 244 - "Subsystem 244"
Cohesion: 0.27
Nodes (10): compute_semsim(), generate_l2_sys06_run(), load_layer2_per_case(), main(), _print_report(), process_history(), CPE Ablation — Layer 2 + System #6: Conversation State Loader.  Inherits all Lay, Process conversation turns into LLM-ready multi-turn messages.      Mirrors prod (+2 more)

### Community 245 - "Subsystem 245"
Cohesion: 0.24
Nodes (10): analyze_validation_results(), _escape_html(), generate_card_html(), generate_validation_html(), main(), Stefano Subjective Validation — HTML Exam Generator.  Generates an interactive H, Escape HTML special characters., Generate HTML for a single evaluation card. (+2 more)

### Community 246 - "Subsystem 246"
Cohesion: 0.25
Nodes (10): categorize_lead_by_history(), extract_link_preview(), load_blacklist(), Extract Open Graph metadata from a URL for link preview., Main sync function - creates COMPLETE leads., Load conversation IDs that previously returned 403., Save conversation IDs that returned 403., Categorize lead based on conversation history age.      - No history or < 7 days (+2 more)

### Community 247 - "Subsystem 247"
Cohesion: 0.27
Nodes (10): classify_topic(), extract_conversations(), get_db_session(), is_real_stefano_message(), main(), print_extraction_report(), Determine if a message is genuinely from Stefano (not the bot)., Extract real conversations from the database.      Returns (conversations, stats (+2 more)

### Community 248 - "Subsystem 248"
Cohesion: 0.25
Nodes (10): configure_cloudinary(), get_oversized_messages(), main(), One-off migration: Upload oversized base64 media to Cloudinary.  Finds messages, Configure Cloudinary from CLOUDINARY_URL env var., Find messages with base64 > threshold., Upload base64 data to Cloudinary, return (url, public_id) or (None, error)., Update message metadata with Cloudinary URL and remove base64. (+2 more)

### Community 249 - "Subsystem 249"
Cohesion: 0.25
Nodes (10): _classify_structural(), _detect_language(), _detect_platform(), generate_test_set(), main(), CPE Test Set Generator — Universal, data-driven.  Generates evaluation test sets, Classify a user message by structural signals. Universal., Detect language. Returns ISO code or 'mixed'. (+2 more)

### Community 250 - "Subsystem 250"
Cohesion: 0.25
Nodes (10): classify_context(), get_stefan_messages(), has_emoji(), has_question(), main(), Stefan Length Analysis - Prove that response length varies by context.  Connects, Check if text contains emojis., Check if text contains a question mark. (+2 more)

### Community 251 - "Subsystem 251"
Cohesion: 0.18
Nodes (9): api_info(), metrics(), Static pages and utility endpoints, Terms of Service page, API info - moved to /api to let root serve frontend, Prometheus metrics endpoint.      Returns metrics in Prometheus exposition forma, Serve frontend index.html for root, serve_root() (+1 more)

### Community 252 - "Subsystem 252"
Cohesion: 0.2
Nodes (11): Audit: Fase 2 Carga + Fase 4 Generacion, Bug: Old [audio] Placeholders in History, Click-and-Play Rate (Copilot Metric), Context Budget 8000 Chars (Priority Order), Event Loop Blocking (Sync DB in Async), Bug: Gold Examples with Media Placeholders, Issue: RAG Near-Empty (24 chunks only), Style Prompt Dominance (81% of tokens) (+3 more)

### Community 253 - "Subsystem 253"
Cohesion: 0.22
Nodes (9): get_available_languages(), get_creator_languages(), load_patterns_for_languages(), _load_single_language(), Multilingual Sensitive Pattern Loader.  Loads regex patterns and crisis resource, List all available language codes (from files in patterns dir)., Get languages for a creator from calibration/Doc D.      Falls back to ["es"] if, Load patterns from a single language JSON file. (+1 more)

### Community 254 - "Subsystem 254"
Cohesion: 0.27
Nodes (9): _is_negation_leading(), _leading_content(), Negation Reducer — Universal post-processing for Doc D system prompts.  Removes, True if the line contains a critical rule that must be preserved., Remove non-critical negation lines from a Doc D system prompt.      Only process, Return line content after stripping bullets and numbered list markers., True when a negation word leads the line's meaningful content., reduce_negations() (+1 more)

### Community 255 - "Subsystem 255"
Cohesion: 0.22
Nodes (9): build_length_hint(), build_question_hint(), build_vocabulary_hint(), get_calibration_soft_max(), Prompt Builder — Calibration-driven helpers (v9+).  Contains get_calibration_sof, Build a question frequency hint for LLM (v9.3).      If creator asks questions i, Get soft_max from calibration, per-context if available (v9.2).      v12: If a p, Build a length guidance hint for the LLM prompt (v9.2).      Returns a short ins (+1 more)

### Community 256 - "Subsystem 256"
Cohesion: 0.22
Nodes (9): enrich_from_database(), get_follower_detail(), Follower management API for DM Agent V2.  Public API methods for follower profil, Save a manually sent message in the conversation history., Get unified follower profile from multiple data sources., Update the lead status for a follower., Enrich follower data from PostgreSQL tables using JOINs., save_manual_message() (+1 more)

### Community 257 - "Subsystem 257"
Cohesion: 0.29
Nodes (9): bootstrap_ci(), compute_bertscore_batch(), _get_platform_user_id(), main(), CPE Level 2 (v2): BERTScore — Multilingual Semantic Similarity  Computes BERTSco, Bootstrap confidence interval for BERTScore F1.      Used for significance testi, Run production DM pipeline on test conversations., Compute BERTScore for a batch of (candidate, reference) pairs.      Returns per- (+1 more)

### Community 258 - "Subsystem 258"
Cohesion: 0.2
Nodes (9): Tests for services/learning_consolidator.py, Below threshold returns skipped status., LLM timeout for a group is handled gracefully., 5 rules with same pattern are consolidated into fewer rules., Superseded rules are deactivated with superseded_by set., test_below_threshold_skips(), test_consolidation_merges(), test_llm_timeout_skips_group() (+1 more)

### Community 259 - "Subsystem 259"
Cohesion: 0.2
Nodes (5): Integration tests for frontend-backend compatibility, TestDashboardCompatibility, TestLeadsCompatibility, TestProductsCompatibility, TestResponseAdapter

### Community 260 - "Subsystem 260"
Cohesion: 0.2
Nodes (7): Extended debug router tests - Written BEFORE implementation (TDD). Tests for cit, Debug router should have /citations/debug/{creator_id} endpoint., Test main app includes debug endpoints via router., Main app should have /debug/citations/debug/{creator_id} endpoint., Test debug router has citations debug endpoint., TestDebugRouterEndpoints, TestMainAppDebugEndpoints

### Community 261 - "Subsystem 261"
Cohesion: 0.29
Nodes (9): cleanup(), main(), process_pending_followups(), Procesar todos los followups pendientes.      Args:         creator_id: Si se es, Mostrar estadísticas de nurturing, Limpiar followups antiguos, Enviar mensaje de followup.      En producción, esto debería usar el InstagramHa, send_followup_message() (+1 more)

### Community 262 - "Subsystem 262"
Cohesion: 0.29
Nodes (9): cleanup_old_backups(), create_backup(), list_backups(), main(), Listar backups existentes.      Args:         backup_path: Directorio de backups, Restaurar un backup.      Args:         backup_file: Ruta al archivo de backup, Crear backup comprimido del directorio data.      Args:         data_path: Direc, Eliminar backups antiguos.      Args:         backup_path: Directorio de backups (+1 more)

### Community 263 - "Subsystem 263"
Cohesion: 0.22
Nodes (9): format_chatml(), format_openai(), format_trl(), load_pairs(), main(), Prepare DPO dataset for fine-tuning from preference_pairs_export.jsonl.  Reads t, Format for HuggingFace TRL DPOTrainer., Format for OpenAI fine-tuning (chat completions DPO). (+1 more)

### Community 264 - "Subsystem 264"
Cohesion: 0.29
Nodes (9): extract_style_rules(), generate_prompt_fragments(), main(), print_learner_report(), Extract style rules purely from Stefano's real messages.      NO assumptions — e, Generate optimized prompt fragments for injection into the DM pipeline.      The, Print auto-learner summary., Select best-match and worst-match pairs for few-shot learning.      Best matches (+1 more)

### Community 265 - "Subsystem 265"
Cohesion: 0.29
Nodes (9): main(), Verify bot token by calling Telegram getMe., Register webhook with Telegram., Verify webhook is configured correctly., Register bot via Clonnect /telegram/register-bot API., register_in_clonnect(), set_webhook(), verify_token() (+1 more)

### Community 266 - "Subsystem 266"
Cohesion: 0.22
Nodes (9): build_clone_system_prompt(), build_response_guidelines(), CreatorMetrics, extract_creator_metrics(), Sistema de Prompt Universal para Clonación de Estilo de Comunicación.  Basado en, Construye guías adicionales por tipo de mensaje., Extrae métricas de los mensajes de un creador.      Vocabulary is data-mined fro, Métricas extraídas del análisis de mensajes del creador. (+1 more)

### Community 267 - "Subsystem 267"
Cohesion: 0.2
Nodes (9): fetch_comparisons(), fetch_history(), fetch_notifications(), fetch_pending_for_lead(), Heavy DB query functions for copilot analytics endpoints., Fetch pending copilot suggestion for a specific lead with conversation context., Fetch side-by-side comparisons of bot suggestions vs creator responses.      Ret, Fetch full copilot action history with aggregate stats.      Returns dict with i (+1 more)

### Community 268 - "Subsystem 268"
Cohesion: 0.24
Nodes (9): _handle_retry_failure(), process_retry_queue(), queue_failed_message(), Service for retrying failed Instagram message sends., Queue a message for retry after send failure., Process all messages due for retry. Returns count of messages processed., Update retry state after a failure., Background worker that processes the retry queue every 60 seconds. (+1 more)

### Community 269 - "Subsystem 269"
Cohesion: 0.31
Nodes (8): _analyze_creator_behavior(), _classify_message_universal(), discover(), main(), Discover conversation types from creator's historical messages. Universal — work, Classify a user message into a conversation type using structural signals., Analyze how the creator typically responds in this type., Discover conversation types from creator's historical data.

### Community 270 - "Subsystem 270"
Cohesion: 0.31
Nodes (8): extract_cpt(), extract_dpo(), extract_sft(), get_db_connection(), Extract CPT, SFT, and DPO datasets for Iris Bertran fine-tuning.  Usage:     rai, Export preference pairs in TRL DPO format., Extract all manual Iris messages (last 6 months) for continued pre-training., Build SFT dataset from calibration file in TRL chat format.

### Community 271 - "Subsystem 271"
Cohesion: 0.25
Nodes (8): create_faq_chunks(), detect_gaps(), generate_embeddings(), main(), Knowledge Gap Detection + Auto-Fill  Analyzes real conversations to find product, Generate OpenAI embeddings for FAQ chunks that don't have them., Find product questions where the bot failed., Insert FAQ chunks into content_chunks and generate embeddings.

### Community 272 - "Subsystem 272"
Cohesion: 0.36
Nodes (8): classify_score(), main(), print_results(), Run baseline evaluation for a creator., Print formatted results table., Save results to JSON file., run_baseline(), save_results()

### Community 273 - "Subsystem 273"
Cohesion: 0.39
Nodes (8): adapt_dashboard_response(), adapt_lead_response(), adapt_leads_response(), adapt_product_response(), adapt_products_response(), add_camel_case_aliases(), Response adapter for frontend compatibility, to_camel_case()

### Community 274 - "Subsystem 274"
Cohesion: 0.29
Nodes (7): download_story_thumbnail(), ensure_story_thumbnail(), is_story_url_expired(), Story Thumbnail Service Downloads and saves Instagram story thumbnails before th, Ensure we have a permanent thumbnail for a story.      If existing_thumbnail is, Download a story thumbnail from Instagram CDN and convert to base64.      Args:, Check if an Instagram CDN URL has likely expired.      Instagram CDN URLs contai

### Community 275 - "Subsystem 275"
Cohesion: 0.32
Nodes (7): count_emojis(), is_emoji_char(), is_emoji_only(), Universal emoji detection utilities.  Replaces the broken `ord(c) > 127000` heur, Return True if a single character is an emoji or emoji modifier.      Does NOT d, Return True if text is non-empty and contains only emoji/whitespace.      Handle, Count visible emoji characters (excludes modifiers, joiners, selectors).

### Community 276 - "Subsystem 276"
Cohesion: 0.32
Nodes (7): dispatch_response(), _handle_autopilot_mode(), _handle_copilot_mode(), Instagram response dispatch — copilot and autopilot modes.  Handles routing DM a, AUTOPILOT MODE: Check if creator already responded before sending., Dispatch a DM response through copilot or autopilot mode., COPILOT MODE: Save as pending approval, don't send.

### Community 277 - "Subsystem 277"
Cohesion: 0.25
Nodes (7): has_creator_responded_recently(), process_reaction_events(), Instagram echo, reaction, and anti-duplication handlers.  Records creator manual, Record a creator's manual response in the database.     This allows us to detect, Process message reaction events from webhook.      Reactions are saved as messag, Check if the creator has manually responded to this follower recently.     Used, record_creator_manual_response()

### Community 278 - "Subsystem 278"
Cohesion: 0.29
Nodes (7): get_active_model_config(), log_model_config(), SINGLE SOURCE OF TRUTH for all LLM model names and provider routing.  All code p, Return the requested model, or GEMINI_PRIMARY_MODEL if it's blocked.      Call t, Log current model config at startup. Call once from api/main.py., Return the active model config dict if LLM_MODEL_NAME is set, else None.      Re, safe_model()

### Community 279 - "Subsystem 279"
Cohesion: 0.32
Nodes (7): enrich_leads_without_profile(), _fetch_profile_for_lead(), _queue_profile_enrichment(), Profile enrichment functions for message reconciliation.  Functions for fetching, Fetch Instagram profile for a lead.     Returns dict with username, name, profil, Queue a lead for profile enrichment retry., Find and enrich leads that don't have profile info.     Called periodically to f

### Community 280 - "Subsystem 280"
Cohesion: 0.25
Nodes (7): _collect_internal_imports(), Import safety net — verifies all internal cross-module imports resolve correctly, Scan all .py files and collect internal import statements., Test that each internally-referenced module can be imported., Test that critical attributes are importable from their expected locations., test_critical_import(), test_module_importable()

### Community 281 - "Subsystem 281"
Cohesion: 0.25
Nodes (3): Test prompt_builder advanced integration in dm_agent_v2 (Step 12)., Advanced prompts should default to OFF (changes prompt significantly)., TestAdvancedPromptsIntegration

### Community 282 - "Subsystem 282"
Cohesion: 0.25
Nodes (2): Test reflexion_engine integration in dm_agent_v2 (Step 7)., TestReflexionEngineIntegration

### Community 283 - "Subsystem 283"
Cohesion: 0.25
Nodes (2): Test query_expansion integration in dm_agent_v2 (Step 6)., TestQueryExpansionIntegration

### Community 284 - "Subsystem 284"
Cohesion: 0.25
Nodes (3): Tests for dm_agent integration with PostContext.  TDD: Tests written FIRST befor, Test suite for dm_agent + PostContext integration., TestDMAgentPostContextIntegration

### Community 285 - "Subsystem 285"
Cohesion: 0.25
Nodes (2): Audit tests for core/link_preview.py, TestAuditLinkPreview

### Community 286 - "Subsystem 286"
Cohesion: 0.25
Nodes (2): Audit tests for core/calendar.py, TestAuditCalendar

### Community 287 - "Subsystem 287"
Cohesion: 0.25
Nodes (2): Audit tests for core/response_variation.py, TestAuditResponseVariation

### Community 288 - "Subsystem 288"
Cohesion: 0.25
Nodes (2): Audit tests for api/services/message_db.py, TestAuditMessageDB

### Community 289 - "Subsystem 289"
Cohesion: 0.25
Nodes (2): Audit tests for api/services/data_sync.py, TestAuditDataSync

### Community 290 - "Subsystem 290"
Cohesion: 0.25
Nodes (2): Audit tests for core/tone_service.py, TestAuditToneService

### Community 291 - "Subsystem 291"
Cohesion: 0.25
Nodes (2): Audit tests for core/whatsapp.py, TestAuditWhatsApp

### Community 292 - "Subsystem 292"
Cohesion: 0.25
Nodes (2): Audit tests for core/response_fixes.py, TestAuditResponseFixes

### Community 293 - "Subsystem 293"
Cohesion: 0.25
Nodes (2): Audit tests for core/embeddings.py, TestAuditEmbeddings

### Community 294 - "Subsystem 294"
Cohesion: 0.25
Nodes (2): Audit tests for core/payments.py, TestAuditPayments

### Community 295 - "Subsystem 295"
Cohesion: 0.25
Nodes (2): Audit tests for core/guardrails.py, TestAuditGuardrails

### Community 296 - "Subsystem 296"
Cohesion: 0.25
Nodes (2): Audit tests for core/dm_agent_v2.py, TestAuditDMAgent

### Community 297 - "Subsystem 297"
Cohesion: 0.25
Nodes (2): Audit tests for api/services/signals.py, TestAuditSignals

### Community 298 - "Subsystem 298"
Cohesion: 0.25
Nodes (2): Audit tests for core/personalized_ranking.py, TestAuditPersonalizedRanking

### Community 299 - "Subsystem 299"
Cohesion: 0.25
Nodes (2): Audit tests for core/ghost_reactivation.py, TestAuditGhostReactivation

### Community 300 - "Subsystem 300"
Cohesion: 0.25
Nodes (2): Audit tests for core/frustration_detector.py, TestAuditFrustrationDetector

### Community 301 - "Subsystem 301"
Cohesion: 0.25
Nodes (2): Audit tests for core/output_validator.py, TestAuditOutputValidator

### Community 302 - "Subsystem 302"
Cohesion: 0.25
Nodes (2): Audit tests for core/nurturing.py, TestAuditNurturing

### Community 303 - "Subsystem 303"
Cohesion: 0.25
Nodes (2): Audit tests for core/webhook_routing.py, TestAuditWebhookRouting

### Community 304 - "Subsystem 304"
Cohesion: 0.25
Nodes (2): Audit tests for core/copilot_service.py, TestAuditCopilotService

### Community 305 - "Subsystem 305"
Cohesion: 0.25
Nodes (2): Audit tests for api/services/db_service.py, TestAuditDBService

### Community 306 - "Subsystem 306"
Cohesion: 0.25
Nodes (2): Audit tests for core/context_detector.py, TestAuditContextDetector

### Community 307 - "Subsystem 307"
Cohesion: 0.25
Nodes (2): Audit tests for core/gdpr.py, TestAuditGDPR

### Community 308 - "Subsystem 308"
Cohesion: 0.29
Nodes (7): format_writing_patterns_for_prompt(), get_writing_patterns(), WritingPatterns - Detailed writing style patterns for a creator.  Based on analy, Detailed writing patterns extracted from real messages., Get writing patterns for a creator.      Args:         creator_id: Creator ident, Format writing patterns for LLM prompt.      Args:         creator_id: Creator i, WritingPatterns

### Community 309 - "Subsystem 309"
Cohesion: 0.25
Nodes (4): LearningRuleData, LearningRule domain model for autolearning feedback loop.  Dataclass representat, In-memory representation of a learning rule.      Used when passing rules betwee, Format rule for injection into DM prompt.

### Community 310 - "Subsystem 310"
Cohesion: 0.36
Nodes (7): aggregate_scores(), analyze_batch(), get_creator_messages(), main(), Analyze a batch of messages for BFI scores., Aggregate BFI scores across batches with mean + std., Fetch real creator messages from DB.

### Community 311 - "Subsystem 311"
Cohesion: 0.36
Nodes (7): compute_metrics(), detect_language(), get_creator_messages(), main(), Detect language using langdetect. Returns ISO 639-1 code., Compute all quantitative style metrics., Fetch real creator messages from DB.

### Community 312 - "Subsystem 312"
Cohesion: 0.32
Nodes (6): is_bad_chosen(), main(), parse_prompt(), Convert DPO dataset from TRL format to Together AI format.  Input  (data/dpo/trl, Skip pairs where 'chosen' looks like a generic bot response, not Iris., Convert the multi-line prompt string into an OpenAI-style messages list.      In

### Community 313 - "Subsystem 313"
Cohesion: 0.32
Nodes (7): apply_to_doc_d(), migrate_db(), migrate_disk(), Migration: Apply universal negation reducer to all existing Doc Ds.  Reads every, Apply reducer to on-disk doc_d_bot_configuration.md files., Apply reduce_negations to §4.1 system prompt within a Doc D document.      Retur, Apply reducer to all personality_docs rows in PostgreSQL.

### Community 314 - "Subsystem 314"
Cohesion: 0.29
Nodes (7): event_stream(), notify_creator(), SSE (Server-Sent Events) router for real-time frontend notifications.  When Inst, SSE endpoint for real-time updates. Frontend connects via EventSource.      Sinc, Send an SSE event to all connected clients for a creator.      Args:         cre, Verify JWT token and check access to creator_id., _verify_token_for_creator()

### Community 315 - "Subsystem 315"
Cohesion: 0.25
Nodes (7): get_latest_score(), get_score_history(), CloneScore Router — Endpoints for CloneScore evaluation results.  Endpoints: - G, Get CloneScore history for the last N days., Trigger an on-demand CloneScore evaluation., Get the latest CloneScore with trend info., trigger_evaluation()

### Community 316 - "Subsystem 316"
Cohesion: 0.25
Nodes (7): clear_escalations(), get_escalation_alerts(), mark_escalation_read(), Escalation alert endpoints, Get escalation alerts for a creator.     Returns leads that need human attention, Mark an escalation as read, Clear all escalation alerts for a creator.

### Community 317 - "Subsystem 317"
Cohesion: 0.25
Nodes (7): analyze_patterns(), get_pattern_analysis(), Analysis endpoints: consolidation trigger, pattern analysis., Manually trigger rule consolidation for a creator., Manually trigger LLM-as-Judge pattern analysis on accumulated preference pairs., View learning rules derived from pattern batch analysis., trigger_consolidation()

### Community 318 - "Subsystem 318"
Cohesion: 0.25
Nodes (7): deactivate_rule(), list_rules(), Rule management endpoints: list, deactivate, reactivate., Manually reactivate a learning rule., List learning rules for a creator., Manually deactivate a learning rule., reactivate_rule()

### Community 319 - "Subsystem 319"
Cohesion: 0.25
Nodes (7): delete_ice_breakers(), get_ice_breakers(), Instagram Ice Breakers Management  Endpoints for setting, getting, and deleting, Delete all Ice Breakers for a creator., Set Ice Breakers for a creator's Instagram.      Ice Breakers are conversation s, Get current Ice Breakers for a creator., set_ice_breakers()

### Community 320 - "Subsystem 320"
Cohesion: 0.36
Nodes (7): get_instagram_post_preview(), get_instagram_preview(), get_link_preview(), get_preview(), LinkPreviewService, Link Preview Service - Obtiene thumbnails de posts/reels compartidos, Servicio para obtener previews de links usando Microlink API

### Community 321 - "Subsystem 321"
Cohesion: 0.29
Nodes (7): _capture_sync(), media_capture_job(), _parse_cdn_expiry(), Periodic media capture job.  Scans messages with temporary CDN URLs that are mis, Async wrapper - runs sync capture in a thread to avoid blocking., Extract expiry timestamp from CDN URL's oe= hex parameter., Synchronous capture logic. Runs in asyncio.to_thread() to avoid     blocking the

### Community 322 - "Subsystem 322"
Cohesion: 0.33
Nodes (2): bar(), test()

### Community 323 - "Subsystem 323"
Cohesion: 0.33
Nodes (4): bar(), CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO (v2)  Cambios v2: - Todas las, expect: None = any non-5xx is PASS (legacy)             int  = exact HTTP code m, test()

### Community 324 - "Subsystem 324"
Cohesion: 0.48
Nodes (6): call_deepinfra(), flag_invented(), jaccard(), load_doc_d(), main(), Quick verification: anti-echo + vocabulary rules in new Doc D.  Runs 10 cases fr

### Community 325 - "Subsystem 325"
Cohesion: 0.29
Nodes (2): Test question_remover integration in dm_agent_v2 (Step 19)., TestQuestionRemoverIntegration

### Community 326 - "Subsystem 326"
Cohesion: 0.29
Nodes (3): Test citation_service integration in dm_agent_v2 (Step 17)., Citation service should return a string (empty if no index)., TestCitationIntegration

### Community 327 - "Subsystem 327"
Cohesion: 0.29
Nodes (2): Test fact_tracking integration in dm_agent_v2 (Step 10)., TestFactTrackingIntegration

### Community 328 - "Subsystem 328"
Cohesion: 0.29
Nodes (2): Test dna_update_triggers integration in dm_agent_v2 (Step 13)., TestDNATriggersIntegration

### Community 329 - "Subsystem 329"
Cohesion: 0.29
Nodes (2): Test message_splitter integration in dm_agent_v2 (Step 18)., TestMessageSplitIntegration

### Community 330 - "Subsystem 330"
Cohesion: 0.29
Nodes (3): Tests for PostContext auto-refresh scheduler.  TDD: Tests written FIRST before i, Test suite for auto-refresh scheduler., TestPostContextScheduler

### Community 331 - "Subsystem 331"
Cohesion: 0.48
Nodes (6): build_user_prompt(), load_few_shot(), load_system_prompt(), main(), DeepSeek V3.2 comparison against 20 test conversations. Reuses same prompt struc, score_response()

### Community 332 - "Subsystem 332"
Cohesion: 0.38
Nodes (6): bootstrap(), _collect_creators(), _parse_vocab_from_file(), Bootstrap vocab_metadata entries in personality_docs from on-disk doc_d files., Return {slug: best_doc_d_path} for creators with on-disk vocabulary files., Parse vocabulary from a doc_d file using calibration_loader logic.

### Community 333 - "Subsystem 333"
Cohesion: 0.38
Nodes (6): get_db_session(), get_lead_messages(), Get database session., Get messages for a lead., Recategorize all leads based on message content., recategorize_leads()

### Community 334 - "Subsystem 334"
Cohesion: 0.38
Nodes (6): extract_media_content(), fetch_conversations(), Recovery script for lost DMs from unmatched_webhooks. Uses psycopg2 + httpx only, Fetch conversations + messages from Instagram API., Returns (content_text, metadata_extras)., run()

### Community 335 - "Subsystem 335"
Cohesion: 0.48
Nodes (6): is_pic_expired_or_missing(), main(), Refresh Instagram lead profiles — fetch username, name, and profile pic from IG, Check if profile pic URL is missing, empty, or expired., refresh_all(), refresh_profiles()

### Community 336 - "Subsystem 336"
Cohesion: 0.4
Nodes (3): bar(), CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO, test()

### Community 337 - "Subsystem 337"
Cohesion: 0.33
Nodes (3): AgentThresholds, DM Agent configuration — all tunable parameters in one place. Override any value, All tunable thresholds for the DM agent pipeline.

### Community 338 - "Subsystem 338"
Cohesion: 0.33
Nodes (5): get_db_message_ids(), get_instagram_conversations(), Message retrieval functions for message reconciliation.  Functions for fetching, Get all platform_message_ids from database for a creator.      Args:         cre, Fetch conversations from Instagram API with messages.      Args:         access_

### Community 339 - "Subsystem 339"
Cohesion: 0.4
Nodes (5): capture_baseline(), Captura respuestas del bot ACTUAL para comparar después del refactor. FASE 0: Pr, Guardar resultados en JSON y Markdown., Captura respuestas del bot actual., save_results()

### Community 340 - "Subsystem 340"
Cohesion: 0.33
Nodes (3): Test chain_of_thought activation in dm_agent_v2 (Step 11)., Chain of thought should default to true after activation., TestChainOfThoughtActivation

### Community 341 - "Subsystem 341"
Cohesion: 0.47
Nodes (5): main(), migrate_creator(), migrate_follower(), Migrate a single follower record.      Returns: (status, message)         status, Migrate all followers for a single creator.

### Community 342 - "Subsystem 342"
Cohesion: 0.47
Nodes (5): build_product_chunks(), load_products(), main(), Seed product/service chunks into content_chunks and generate embeddings.  Usage:, Build text chunks from product catalog for RAG ingestion.

### Community 343 - "Subsystem 343"
Cohesion: 0.47
Nodes (5): extract_metrics_from_judge_results(), main(), print_comparison(), Print before/after comparison., Extract comparable metrics from judge results.

### Community 344 - "Subsystem 344"
Cohesion: 0.47
Nodes (5): main(), parse_content_file(), Parse the exported content file into structured chunks.      The file format is:, Split text into overlapping chunks, trying to break at sentence boundaries., split_into_chunks()

### Community 345 - "Subsystem 345"
Cohesion: 0.33
Nodes (5): error_response(), ok(), Standard API response helpers for consistent output.  Usage:     from api.utils., Standard success response., Standard error response (for non-exception returns, not HTTPException).

### Community 346 - "Subsystem 346"
Cohesion: 0.33
Nodes (5): err(), ok(), Standard API response envelope utilities.  Provides ok() and err() helpers for c, Return a success response envelope., Return an error response envelope.

### Community 347 - "Subsystem 347"
Cohesion: 0.33
Nodes (5): Shared creator resolution logic — replaces 20+ duplicated lookup patterns., Resolve a creator by name (slug) or UUID string.      Args:         session: SQL, Like resolve_creator but returns None instead of raising.     Use in services th, resolve_creator(), resolve_creator_safe()

### Community 348 - "Subsystem 348"
Cohesion: 0.33
Nodes (5): get_or_create_lead_sync(), Message storage compatible with SQLAlchemy models, Save message using SQLAlchemy (sync) - matches Message model, Get or create lead using SQLAlchemy (sync).      FIX: Previously loaded ALL lead, save_message_sync()

### Community 349 - "Subsystem 349"
Cohesion: 0.33
Nodes (5): downgrade(), add_product_fields  Add product_type, short_description, and payment_link to pro, Add new product fields, Remove new product fields, upgrade()

### Community 350 - "Subsystem 350"
Cohesion: 0.33
Nodes (5): downgrade(), add_analytics_tables  Create analytics tables for daily metrics and funnel track, Drop analytics tables., Create analytics tables., upgrade()

### Community 351 - "Subsystem 351"
Cohesion: 0.33
Nodes (5): downgrade(), add_nurturing_followups  Create nurturing_followups table for persistent follow-, Create nurturing_followups table with indexes for efficient querying., Drop nurturing_followups table and indexes., upgrade()

### Community 352 - "Subsystem 352"
Cohesion: 0.33
Nodes (5): downgrade(), add_user_profiles  Phase 2.3: Migrate User Profiles from JSON to PostgreSQL. Thi, Create user_profiles table, Drop user_profiles table, upgrade()

### Community 353 - "Subsystem 353"
Cohesion: 0.33
Nodes (5): downgrade(), add_intelligence_tables  Create tables for the Business Intelligence system: - P, Create intelligence tables., Drop intelligence tables., upgrade()

### Community 354 - "Subsystem 354"
Cohesion: 0.33
Nodes (5): downgrade(), add_follower_memories  Phase 2.2: Migrate Follower Memory from JSON to PostgreSQ, Create follower_memories table with all 27 fields, Drop follower_memories table, upgrade()

### Community 355 - "Subsystem 355"
Cohesion: 0.33
Nodes (5): downgrade(), add_conversation_embeddings  Phase 2.4: Add conversation_embeddings table for se, Create conversation_embeddings table with pgvector support, Drop conversation_embeddings table, upgrade()

### Community 356 - "Subsystem 356"
Cohesion: 0.33
Nodes (5): downgrade(), add_sync_queue_tables  Add tables for intelligent sync queue system: - sync_queu, Create sync queue tables, Drop sync queue tables, upgrade()

### Community 357 - "Subsystem 357"
Cohesion: 0.33
Nodes (5): downgrade(), add_profile_pic_url  Add profile_pic_url column to leads table for Instagram pro, Add profile_pic_url column to leads table (as TEXT for long CDN URLs), Remove profile_pic_url column from leads table, upgrade()

### Community 358 - "Subsystem 358"
Cohesion: 0.33
Nodes (5): downgrade(), add_conversation_states  Phase 2.1: Persist ConversationState to PostgreSQL. Thi, Create conversation_states table, Drop conversation_states table, upgrade()

### Community 359 - "Subsystem 359"
Cohesion: 0.33
Nodes (5): downgrade(), add_performance_indexes  P2 FIX: Add database indexes for query performance opti, Add performance indexes to frequently queried columns, Remove performance indexes, upgrade()

### Community 360 - "Subsystem 360"
Cohesion: 0.33
Nodes (5): compute_preference_profile(), format_preference_profile_for_prompt(), Preference Profile Service — compute and format creator communication style prof, Format profile dict into a prompt injection block., Compute preference profile from last 100 approved/edited messages.      Returns

### Community 361 - "Subsystem 361"
Cohesion: 0.4
Nodes (1): Read-only script: Extract Iris's best manual responses for calibration file. Two

### Community 362 - "Subsystem 362"
Cohesion: 0.4
Nodes (4): Test that status update also works with platform_user_id (legacy support), Test the complete Kanban drag & drop flow:     1. Create a lead (gets a UUID), test_kanban_status_update_with_uuid(), test_status_update_with_platform_user_id()

### Community 363 - "Subsystem 363"
Cohesion: 0.4
Nodes (2): Test vocabulary_extractor module imports and basic functionality., TestVocabularyExtractorIntegration

### Community 364 - "Subsystem 364"
Cohesion: 0.4
Nodes (2): Test self_consistency integration in dm_agent_v2 (Step 21)., TestSelfConsistencyIntegration

### Community 365 - "Subsystem 365"
Cohesion: 0.5
Nodes (4): _get_write_session(), main(), Backfill DNA vocabulary_uses for all records.  Extracts vocabulary from REAL cre, Get a session that can write — uses direct Neon endpoint (not pooler).

### Community 366 - "Subsystem 366"
Cohesion: 0.6
Nodes (4): normalise_name(), normalise_phone(), One-time migration script: create UnifiedLeads for all existing leads.  Steps:, run()

### Community 367 - "Subsystem 367"
Cohesion: 0.4
Nodes (4): Test adicional: verificar que la clasificación de intent funciona., Test del flujo de ACKNOWLEDGMENT con contexto., test_acknowledgment_classification(), test_acknowledgment_flow()

### Community 368 - "Subsystem 368"
Cohesion: 0.4
Nodes (4): Application startup handlers. Extracted from main.py following TDD methodology., Register startup and shutdown handlers on the FastAPI app., # NOTE: Cache warming is done at startup (_do_prewarm) + naturally by, register_startup_handlers()

### Community 369 - "Subsystem 369"
Cohesion: 0.4
Nodes (2): add lead_memories and conversation_summaries tables  Tables for the Memory Engin, # NOTE: requires at least 1 row to build; index is created but empty until data

### Community 370 - "Subsystem 370"
Cohesion: 0.5
Nodes (3): Simple Telegram message sender wrapper, Send a message to a Telegram chat.      Args:         chat_id: Telegram chat ID, send_telegram_message()

### Community 371 - "Subsystem 371"
Cohesion: 0.5
Nodes (3): auto_calibrate(), Auto-calibrate LLM generation parameters from creator message analysis.  Compute, Compute LLM generation parameters from creator message samples.      Args:

### Community 372 - "Subsystem 372"
Cohesion: 0.5
Nodes (3): _determine_response_strategy(), Response strategy determination for DM Agent V2.  Determines HOW the LLM should, Determine response strategy to inject as LLM guidance.      Returns a short inst

### Community 373 - "Subsystem 373"
Cohesion: 0.5
Nodes (3): detect_gaps(), Dynamic Persona Refinement Framework (DPRF) — Iteration 1 Based on Yao et al., O, Detect all divergence gaps between bot response and ground truth.

### Community 374 - "Subsystem 374"
Cohesion: 0.5
Nodes (0): 

### Community 375 - "Subsystem 375"
Cohesion: 0.5
Nodes (1): Config endpoint tests

### Community 376 - "Subsystem 376"
Cohesion: 0.5
Nodes (1): Health endpoint tests

### Community 377 - "Subsystem 377"
Cohesion: 0.67
Nodes (3): cleanup(), main(), Cleanup WhatsApp message duplicates — delete all but one copy of each message.

### Community 378 - "Subsystem 378"
Cohesion: 0.5
Nodes (3): backfill(), Backfill existing audio messages with the 4-layer intelligence pipeline.  Proces, Reprocess audio messages through 4-layer pipeline.

### Community 379 - "Subsystem 379"
Cohesion: 0.67
Nodes (2): dm(), req()

### Community 380 - "Subsystem 380"
Cohesion: 0.5
Nodes (3): Script to show ALL raw content saved for a creator. Shows products, RAG chunks,, Show all content for a creator., show_all_content()

### Community 381 - "Subsystem 381"
Cohesion: 0.5
Nodes (3): classify_lead_message(), Analyze Stefan's real message lengths by conversation context. Connects to Postg, Classify lead message into context category.

### Community 382 - "Subsystem 382"
Cohesion: 0.5
Nodes (3): export_training_data(), Export clean training data for fine-tuning.  Uses contamination_filter v3 to ens, Export clean conversation pairs for fine-tuning.

### Community 383 - "Subsystem 383"
Cohesion: 0.5
Nodes (3): Run V2 Ingestion Preview - Shows ALL raw content that would be extracted. No dat, Run V2 preview and show all raw content., run_preview()

### Community 384 - "Subsystem 384"
Cohesion: 0.67
Nodes (3): classify_context(), main(), Stefan Length Distribution - Detailed analysis of the 'otro' category and percen

### Community 385 - "Subsystem 385"
Cohesion: 0.67
Nodes (3): main(), Phase 1: Populate conversation_embeddings for ALL messages of a creator.  Uses l, _run()

### Community 386 - "Subsystem 386"
Cohesion: 0.5
Nodes (3): filter_turns(), Contamination filter — filters out bot-generated turns from calibration data.  S, Filter contaminated turns from conversation pairs.      Since load_conversation_

### Community 387 - "Subsystem 387"
Cohesion: 0.5
Nodes (3): Static file serving for frontend SPA. Extracted from main.py following TDD metho, Register static file routes on the FastAPI app.      IMPORTANT: Call this AFTER, register_static_routes()

### Community 388 - "Subsystem 388"
Cohesion: 0.5
Nodes (3): migrate_followers(), Script para migrar datos JSON a PostgreSQL, Migrar followers de JSON a PostgreSQL

### Community 389 - "Subsystem 389"
Cohesion: 0.5
Nodes (3): Audio Router - Whisper transcription endpoint for the inbox.  Endpoints: - POST, Transcribe an uploaded audio file using Whisper API.      Accepts audio files (w, transcribe_audio()

### Community 390 - "Subsystem 390"
Cohesion: 0.5
Nodes (1): Create commitments table.  Part of ECHO Engine Sprint 4 — Commitment Tracker. Tr

### Community 391 - "Subsystem 391"
Cohesion: 0.5
Nodes (1): Add pattern_analysis_runs table for Pattern Analyzer audit trail.  Revision ID:

### Community 392 - "Subsystem 392"
Cohesion: 0.5
Nodes (1): Add partial unique index on (lead_id, platform_message_id) where not null.  Revi

### Community 393 - "Subsystem 393"
Cohesion: 0.5
Nodes (1): Add evaluator_feedback table for structured human evaluator feedback.  Revision

### Community 394 - "Subsystem 394"
Cohesion: 0.5
Nodes (1): Fix personality_docs id DEFAULT: uuid_generate_v4() -> gen_random_uuid().  Revis

### Community 395 - "Subsystem 395"
Cohesion: 0.5
Nodes (1): Add is_active column to preference_pairs for quality filtering.  Revision ID: 04

### Community 396 - "Subsystem 396"
Cohesion: 0.5
Nodes (1): Add llm_usage_log table for per-call token tracking.  Revision ID: 036 Revises:

### Community 397 - "Subsystem 397"
Cohesion: 0.5
Nodes (1): add preference_pairs table for DPO/RLHF training data  Stores (chosen, rejected)

### Community 398 - "Subsystem 398"
Cohesion: 0.5
Nodes (1): Add creator_profiles table for storing CPE profiles in DB.  Revision ID: 042 Rev

### Community 399 - "Subsystem 399"
Cohesion: 0.5
Nodes (1): Add relationship_type and score_updated_at to leads table  Revision ID: 017 Revi

### Community 400 - "Subsystem 400"
Cohesion: 0.5
Nodes (1): Add partial index for copilot pending messages  Revision ID: 014 Revises: 013 Cr

### Community 401 - "Subsystem 401"
Cohesion: 0.5
Nodes (1): Replace IVFFlat index with HNSW for lead_memories.  IVFFlat with lists=100 requi

### Community 402 - "Subsystem 402"
Cohesion: 0.5
Nodes (1): Add (lead_id, created_at DESC) index on messages for DISTINCT ON last-message qu

### Community 403 - "Subsystem 403"
Cohesion: 0.5
Nodes (1): add source column to learning_rules table  Tracks where a learning rule originat

### Community 404 - "Subsystem 404"
Cohesion: 0.5
Nodes (1): Add indexes to messages table for performance  Revision ID: 013 Revises: 012 Cre

### Community 405 - "Subsystem 405"
Cohesion: 0.5
Nodes (1): Add unified_leads table and unified_lead_id FK on leads  Revision ID: 018 Revise

### Community 406 - "Subsystem 406"
Cohesion: 0.5
Nodes (1): Add dismissed_leads table for blocklist  Revision ID: 012 Revises: 011 Create Da

### Community 407 - "Subsystem 407"
Cohesion: 0.5
Nodes (1): add FAMILIA to relationship_dna CHECK constraint  The Sprint 1 lead profiling ch

### Community 408 - "Subsystem 408"
Cohesion: 0.5
Nodes (1): add website_url column to creators table  Revision ID: 020 Revises: 019 Create D

### Community 409 - "Subsystem 409"
Cohesion: 0.5
Nodes (1): add learning_rules table for autolearning feedback loop  Stores creator-specific

### Community 410 - "Subsystem 410"
Cohesion: 0.5
Nodes (1): add copilot_evaluations table for autolearning  Stores daily and weekly evaluati

### Community 411 - "Subsystem 411"
Cohesion: 0.5
Nodes (1): Create style_profiles table.  Part of ECHO Engine Sprint 1 — Style Analyzer. Sto

### Community 412 - "Subsystem 412"
Cohesion: 0.5
Nodes (1): add clone_score_evaluations and clone_score_test_sets tables  Tables for the Clo

### Community 413 - "Subsystem 413"
Cohesion: 0.5
Nodes (1): Add personality_docs table for persistent Doc D/E storage.  Revision ID: 033 Rev

### Community 414 - "Subsystem 414"
Cohesion: 0.5
Nodes (1): Add performance indexes and strip thumbnail_base64 from messages JSONB.  Revisio

### Community 415 - "Subsystem 415"
Cohesion: 0.5
Nodes (1): add missing indexes for platform_message_id product_creator nurturing_creator kb

### Community 416 - "Subsystem 416"
Cohesion: 0.5
Nodes (1): add copilot tracking columns to messages table  New columns for copilot autolear

### Community 417 - "Subsystem 417"
Cohesion: 0.5
Nodes (1): Add csat_ratings table for metrics system  Revision ID: 015 Revises: 014 Create

### Community 418 - "Subsystem 418"
Cohesion: 0.5
Nodes (1): add gold_examples table for few-shot prompt injection  Stores high-quality creat

### Community 419 - "Subsystem 419"
Cohesion: 0.5
Nodes (1): webhook_multi_creator_routing  Add support for multi-creator webhook routing wit

### Community 420 - "Subsystem 420"
Cohesion: 0.5
Nodes (1): add index on creators.whatsapp_phone_id for multi-tenant webhook routing  Revisi

### Community 421 - "Subsystem 421"
Cohesion: 0.5
Nodes (1): cleanup duplicate pending_approval messages  For each lead that has multiple pen

### Community 422 - "Subsystem 422"
Cohesion: 0.67
Nodes (0): 

### Community 423 - "Subsystem 423"
Cohesion: 0.67
Nodes (2): Test the complete flow:     1. Create a lead with email/phone/notes     2. Verif, test_full_lead_flow_with_conversations()

### Community 424 - "Subsystem 424"
Cohesion: 0.67
Nodes (2): Test that /dm/conversations reads message counts from PostgreSQL:     1. Create, test_conversations_reads_messages_from_db()

### Community 425 - "Subsystem 425"
Cohesion: 0.67
Nodes (1): Populate DNA for test leads that don't have it yet. Run: railway run python3.11

### Community 426 - "Subsystem 426"
Cohesion: 0.67
Nodes (1): Populate detected_topics from follower_memories interests + products_discussed.

### Community 427 - "Subsystem 427"
Cohesion: 0.67
Nodes (0): 

### Community 428 - "Subsystem 428"
Cohesion: 0.67
Nodes (2): migrate_stefano(), Migrate Stefano's Instagram IDs.

### Community 429 - "Subsystem 429"
Cohesion: 0.67
Nodes (1): Populate creator_metrics_daily from messages + leads history. IDEMPOTENT: Uses I

### Community 430 - "Subsystem 430"
Cohesion: 1.0
Nodes (2): main(), setup_logging()

### Community 431 - "Subsystem 431"
Cohesion: 0.67
Nodes (1): Compress lead memories for the 20 test set leads.  Usage: cd backend && python3

### Community 432 - "Subsystem 432"
Cohesion: 0.67
Nodes (1): Populate content_performance from instagram_posts. IDEMPOTENT: Uses INSERT ON CO

### Community 433 - "Subsystem 433"
Cohesion: 0.67
Nodes (1): RAG Health Check — validates data integrity post-deploy.  Checks: 1. Embedding c

### Community 434 - "Subsystem 434"
Cohesion: 0.67
Nodes (2): Remove <think>...</think> blocks from model responses., strip_think()

### Community 435 - "Subsystem 435"
Cohesion: 0.67
Nodes (1): Forensic Learning Audit — Run against production DB to verify learning activity.

### Community 436 - "Subsystem 436"
Cohesion: 1.0
Nodes (1): Verify Stefano's data counts pre/post re-ingestion.  Usage:   # Via production A

### Community 437 - "Subsystem 437"
Cohesion: 1.0
Nodes (1): Store Manel's DPO pair and learning rules from ablation DNA review.  Usage: rail

### Community 438 - "Subsystem 438"
Cohesion: 1.0
Nodes (1): Purga hechos contaminados en lead_memories que describen acciones del bot en lug

### Community 439 - "Subsystem 439"
Cohesion: 1.0
Nodes (1): Investigate DNA state for test leads. Run via: railway run python3.11 scripts/in

### Community 440 - "Subsystem 440"
Cohesion: 1.0
Nodes (1): Purgar gold examples contaminados (respuestas de error del sistema). Marca is_ac

### Community 441 - "Subsystem 441"
Cohesion: 1.0
Nodes (0): 

### Community 442 - "Subsystem 442"
Cohesion: 1.0
Nodes (1): Generate embeddings for content_chunks missing them. Run: railway run python3 sc

### Community 443 - "Subsystem 443"
Cohesion: 1.0
Nodes (1): Check best-of-N candidates in recent copilot suggestions.

### Community 444 - "Subsystem 444"
Cohesion: 1.0
Nodes (0): 

### Community 445 - "Subsystem 445"
Cohesion: 1.0
Nodes (1): Test DNA lookup for test leads. Run: railway run python3.11 scripts/test_dna_loo

### Community 446 - "Subsystem 446"
Cohesion: 1.0
Nodes (1): RAG DB Fixes — run with: railway run python3 scripts/fix_rag_db.py  Fix 1: Norma

### Community 447 - "Subsystem 447"
Cohesion: 1.0
Nodes (1): Temporary fix script — run with: railway run python3 scripts/_rag_fix_run.py

### Community 448 - "Subsystem 448"
Cohesion: 1.0
Nodes (0): 

### Community 449 - "Subsystem 449"
Cohesion: 1.0
Nodes (1): Backward compatibility — moved to api.routers.autolearning.

### Community 450 - "Subsystem 450"
Cohesion: 1.0
Nodes (1): Backward compatibility — all functions moved to api.services.db/ modules.

### Community 451 - "Subsystem 451"
Cohesion: 1.0
Nodes (1): Re-export shim — all logic moved to services/feedback_capture.py. Kept for backw

### Community 452 - "Subsystem 452"
Cohesion: 1.0
Nodes (2): Audit: Cross-Encoder Reranker (Sistema #12), Passage Re-ranking with BERT (Nogueira & Cho 2020)

### Community 453 - "Subsystem 453"
Cohesion: 1.0
Nodes (2): Qwen/Qwen3-14B Base Model, LoRA SFT Adapter — Qwen3-14B

### Community 454 - "Subsystem 454"
Cohesion: 1.0
Nodes (2): LoRA DPO Adapter — 8B MLX 4-bit Quantized, MLX Library (Apple Silicon)

### Community 455 - "Subsystem 455"
Cohesion: 1.0
Nodes (2): Clonnect Brand Logo — From Follow to Hello, Clonnect Brand Logo (PNG variant)

### Community 456 - "Subsystem 456"
Cohesion: 1.0
Nodes (1): Genera ID unico basado en feed URL.

### Community 457 - "Subsystem 457"
Cohesion: 1.0
Nodes (1): Extrae video ID de una URL de YouTube.

### Community 458 - "Subsystem 458"
Cohesion: 1.0
Nodes (1): Crea desde diccionario, filtrando campos desconocidos.

### Community 459 - "Subsystem 459"
Cohesion: 1.0
Nodes (1): Check if page has meaningful content.

### Community 460 - "Subsystem 460"
Cohesion: 1.0
Nodes (1): Genera ID unico basado en source.

### Community 461 - "Subsystem 461"
Cohesion: 1.0
Nodes (1): Verifica si el post tiene contenido util para indexar.

### Community 462 - "Subsystem 462"
Cohesion: 1.0
Nodes (1): Obtener descripción humana de la intención

### Community 463 - "Subsystem 463"
Cohesion: 1.0
Nodes (1): Create from FollowUp dataclass.

### Community 464 - "Subsystem 464"
Cohesion: 1.0
Nodes (1): Get a database session with proper error handling.

### Community 465 - "Subsystem 465"
Cohesion: 1.0
Nodes (1): Number of characters in content.

### Community 466 - "Subsystem 466"
Cohesion: 1.0
Nodes (1): send_message posts correct JSON to the API.

### Community 467 - "Subsystem 467"
Cohesion: 1.0
Nodes (1): handle_webhook_event returns empty list for empty payload.

### Community 468 - "Subsystem 468"
Cohesion: 1.0
Nodes (1): handle_webhook_event returns empty list when entry has no messages.

### Community 469 - "Subsystem 469"
Cohesion: 1.0
Nodes (1): handle_webhook_event handles malformed data gracefully.

### Community 470 - "Subsystem 470"
Cohesion: 1.0
Nodes (1): Handler.handle_webhook returns 0 messages_processed for empty payload.

### Community 471 - "Subsystem 471"
Cohesion: 1.0
Nodes (1): Crea directorio temporal para tests.

### Community 472 - "Subsystem 472"
Cohesion: 1.0
Nodes (1): Verifica guardar y cargar perfil.

### Community 473 - "Subsystem 473"
Cohesion: 1.0
Nodes (1): Verifica lista de perfiles con datos.

### Community 474 - "Subsystem 474"
Cohesion: 1.0
Nodes (1): Verifica generacion de perfil desde posts.

### Community 475 - "Subsystem 475"
Cohesion: 1.0
Nodes (1): When DB is completely unavailable, save returns False.

### Community 476 - "Subsystem 476"
Cohesion: 1.0
Nodes (1): ingest_website_v2 should return IngestV2Response on success.

### Community 477 - "Subsystem 477"
Cohesion: 1.0
Nodes (1): When the pipeline raises an exception, endpoint should return 500.

### Community 478 - "Subsystem 478"
Cohesion: 1.0
Nodes (1): Status endpoint should return 'empty' when no posts indexed.

### Community 479 - "Subsystem 479"
Cohesion: 1.0
Nodes (1): Status endpoint should return 'ready' when posts are indexed.

### Community 480 - "Subsystem 480"
Cohesion: 1.0
Nodes (1): Payment link request should return valid URL for stefano_bonanno

### Community 481 - "Subsystem 481"
Cohesion: 1.0
Nodes (1): Booking request should return Calendly or booking info

### Community 482 - "Subsystem 482"
Cohesion: 1.0
Nodes (1): Escalation request should set escalate_to_human flag

### Community 483 - "Subsystem 483"
Cohesion: 1.0
Nodes (1): First message should be received and processed

### Community 484 - "Subsystem 484"
Cohesion: 1.0
Nodes (1): Second message from same sender should be received

### Community 485 - "Subsystem 485"
Cohesion: 1.0
Nodes (1): Context should be maintained between messages

### Community 486 - "Subsystem 486"
Cohesion: 1.0
Nodes (1): Lead magnet request should be detected

### Community 487 - "Subsystem 487"
Cohesion: 1.0
Nodes (1): Lead magnet request should trigger action

### Community 488 - "Subsystem 488"
Cohesion: 1.0
Nodes (1): Price question should receive valid response

### Community 489 - "Subsystem 489"
Cohesion: 1.0
Nodes (1): Response should not contain placeholder patterns

### Community 490 - "Subsystem 490"
Cohesion: 1.0
Nodes (1): Response should be valid and relevant

### Community 491 - "Subsystem 491"
Cohesion: 1.0
Nodes (1): get_leads should return a list of lead dicts when creator exists.

### Community 492 - "Subsystem 492"
Cohesion: 1.0
Nodes (1): get_leads returns [] when the creator does not exist in DB.

### Community 493 - "Subsystem 493"
Cohesion: 1.0
Nodes (1): get_creator_by_name returns None for a non-existent creator.

### Community 494 - "Subsystem 494"
Cohesion: 1.0
Nodes (1): When get_session returns None, get_leads should return [].

### Community 495 - "Subsystem 495"
Cohesion: 1.0
Nodes (1): When DB is unavailable, credentials return success=False.

### Community 496 - "Subsystem 496"
Cohesion: 1.0
Nodes (1): toggle_bot should return None when the DB is down.

### Community 497 - "Subsystem 497"
Cohesion: 1.0
Nodes (1): The limit argument should be forwarded to SQLAlchemy .limit().

### Community 498 - "Subsystem 498"
Cohesion: 1.0
Nodes (1): get_db_message_ids returns a set of message IDs (mocked DB).

### Community 499 - "Subsystem 499"
Cohesion: 1.0
Nodes (1): reconcile_messages_for_creator handles zero conversations.

### Community 500 - "Subsystem 500"
Cohesion: 1.0
Nodes (1): run_startup_reconciliation updates global last_reconciliation.

### Community 501 - "Subsystem 501"
Cohesion: 1.0
Nodes (1): run_periodic_reconciliation updates global counters.

### Community 502 - "Subsystem 502"
Cohesion: 1.0
Nodes (1): run_startup_reconciliation returns error dict on exception.

### Community 503 - "Subsystem 503"
Cohesion: 1.0
Nodes (1): Platform message dedup returns early but doesn't crash tracking.

### Community 504 - "Subsystem 504"
Cohesion: 1.0
Nodes (1): resolved_externally handler should call _store_rule with confidence=0.7.

### Community 505 - "Subsystem 505"
Cohesion: 1.0
Nodes (1): Should skip if neither suggested nor final response exist.

### Community 506 - "Subsystem 506"
Cohesion: 1.0
Nodes (1): When ENABLE_AUTOLEARNING is false, analyze_creator_action should return immediat

### Community 507 - "Subsystem 507"
Cohesion: 1.0
Nodes (1): When ENABLE_AUTOLEARNING is true, should dispatch to handler.

### Community 508 - "Subsystem 508"
Cohesion: 1.0
Nodes (1): Skips if evaluation already exists for the date.

### Community 509 - "Subsystem 509"
Cohesion: 1.0
Nodes (1): Skips if no copilot actions for the day.

### Community 510 - "Subsystem 510"
Cohesion: 1.0
Nodes (1): Skips if weekly evaluation already exists.

### Community 511 - "Subsystem 511"
Cohesion: 1.0
Nodes (1): Skips if fewer than 3 daily evaluations.

### Community 512 - "Subsystem 512"
Cohesion: 1.0
Nodes (1): Paso 5: DM history respeta max_age_days (default 90)

### Community 513 - "Subsystem 513"
Cohesion: 1.0
Nodes (1): BUG-LR-02 regression: score should be linear in confidence, not quadratic.

### Community 514 - "Subsystem 514"
Cohesion: 1.0
Nodes (1): Two rules with confidence 0.5 and 1.0 — ratio should be ~2:1, not ~4:1.

### Community 515 - "Subsystem 515"
Cohesion: 1.0
Nodes (1): BUG-GE-01 regression: score should be linear in quality_score, not quadratic.

### Community 516 - "Subsystem 516"
Cohesion: 1.0
Nodes (1): save_feedback stores a record and returns feedback_id.

### Community 517 - "Subsystem 517"
Cohesion: 1.0
Nodes (1): When ideal_response provided, auto-creates preference pair.

### Community 518 - "Subsystem 518"
Cohesion: 1.0
Nodes (1): When lo_enviarias >= 4 AND ideal_response, also creates gold example.

### Community 519 - "Subsystem 519"
Cohesion: 1.0
Nodes (1): When ENABLE_EVALUATOR_FEEDBACK=false, returns status=disabled.

### Community 520 - "Subsystem 520"
Cohesion: 1.0
Nodes (1): get_feedback returns structured list of feedback records.

### Community 521 - "Subsystem 521"
Cohesion: 1.0
Nodes (1): get_feedback applies evaluator_id and score filters.

### Community 522 - "Subsystem 522"
Cohesion: 1.0
Nodes (1): FB-03: Empty string ideal_response should NOT create preference pair.

### Community 523 - "Subsystem 523"
Cohesion: 1.0
Nodes (1): FB-07: DB error returns status=error, not None.

### Community 524 - "Subsystem 524"
Cohesion: 1.0
Nodes (1): FB-08: Stats error returns status=error dict.

### Community 525 - "Subsystem 525"
Cohesion: 1.0
Nodes (1): save_feedback accepts any UUID creator_db_id.

### Community 526 - "Subsystem 526"
Cohesion: 1.0
Nodes (1): capture(evaluator_score) routes to save_feedback.

### Community 527 - "Subsystem 527"
Cohesion: 1.0
Nodes (1): capture(copilot_edit) routes to create_pairs_from_action.

### Community 528 - "Subsystem 528"
Cohesion: 1.0
Nodes (1): capture(copilot_approve) → quality 0.6.

### Community 529 - "Subsystem 529"
Cohesion: 1.0
Nodes (1): capture(copilot_discard) → quality 0.4.

### Community 530 - "Subsystem 530"
Cohesion: 1.0
Nodes (1): capture(copilot_resolved) → quality 0.9 (strongest signal).

### Community 531 - "Subsystem 531"
Cohesion: 1.0
Nodes (1): Unknown signal_type returns error.

### Community 532 - "Subsystem 532"
Cohesion: 1.0
Nodes (1): OAuth start should return auth URL when configured

### Community 533 - "Subsystem 533"
Cohesion: 1.0
Nodes (1): Test processing PAYMENT.SALE.COMPLETED event

### Community 534 - "Subsystem 534"
Cohesion: 1.0
Nodes (1): Test processing CHECKOUT.ORDER.APPROVED event

### Community 535 - "Subsystem 535"
Cohesion: 1.0
Nodes (1): Test that duplicate payments are not processed twice

### Community 536 - "Subsystem 536"
Cohesion: 1.0
Nodes (1): Test processing PAYMENT.SALE.REFUNDED event

### Community 537 - "Subsystem 537"
Cohesion: 1.0
Nodes (1): Verification should be skipped if PAYPAL_WEBHOOK_ID not set

### Community 538 - "Subsystem 538"
Cohesion: 1.0
Nodes (1): Verification should fail if required headers missing

### Community 539 - "Subsystem 539"
Cohesion: 1.0
Nodes (1): Purchases should be tracked in SalesTracker

### Community 540 - "Subsystem 540"
Cohesion: 1.0
Nodes (1): When no existing JSON, sync_lead_to_json should create a new file.

### Community 541 - "Subsystem 541"
Cohesion: 1.0
Nodes (1): When JSON exists, sync_lead_to_json merges data (no status downgrade).

### Community 542 - "Subsystem 542"
Cohesion: 1.0
Nodes (1): sync_lead_to_json should silently return if platform_user_id is empty.

### Community 543 - "Subsystem 543"
Cohesion: 1.0
Nodes (1): full_sync_creator returns zero stats when PostgreSQL is disabled.

### Community 544 - "Subsystem 544"
Cohesion: 1.0
Nodes (1): full_sync_creator returns zero stats when creator directory is missing.

### Community 545 - "Subsystem 545"
Cohesion: 1.0
Nodes (1): full_sync_creator only processes .json files, not .txt.

### Community 546 - "Subsystem 546"
Cohesion: 1.0
Nodes (1): When copilot service returns dict format, response includes pagination.

### Community 547 - "Subsystem 547"
Cohesion: 1.0
Nodes (1): When copilot service returns old list format, response is backward-compatible.

### Community 548 - "Subsystem 548"
Cohesion: 1.0
Nodes (1): Approving a response should return the service result on success.

### Community 549 - "Subsystem 549"
Cohesion: 1.0
Nodes (1): GET /copilot/{creator_id}/pending returns pending_count=0 for empty queue.

### Community 550 - "Subsystem 550"
Cohesion: 1.0
Nodes (1): The creator_id path param should be forwarded to the service layer.

### Community 551 - "Subsystem 551"
Cohesion: 1.0
Nodes (1): discard_response should forward both creator_id and message_id.

### Community 552 - "Subsystem 552"
Cohesion: 1.0
Nodes (1): Returns {pending: null} when no pending suggestion for the lead.

### Community 553 - "Subsystem 553"
Cohesion: 1.0
Nodes (1): Returns pending suggestion with conversation_context when found.

### Community 554 - "Subsystem 554"
Cohesion: 1.0
Nodes (1): Empty message should still produce a response (not crash).

### Community 555 - "Subsystem 555"
Cohesion: 1.0
Nodes (1): get_pending_responses returns empty when creator not found.

### Community 556 - "Subsystem 556"
Cohesion: 1.0
Nodes (1): get_pending_responses returns dict with pending, total_count, has_more.

### Community 557 - "Subsystem 557"
Cohesion: 1.0
Nodes (1): get_pending_responses returns empty on DB exception.

### Community 558 - "Subsystem 558"
Cohesion: 1.0
Nodes (1): discard_response returns error when message not found.

### Community 559 - "Subsystem 559"
Cohesion: 1.0
Nodes (1): discard_response handles DB exception gracefully.

### Community 560 - "Subsystem 560"
Cohesion: 1.0
Nodes (1): approve_response returns error when creator not found.

### Community 561 - "Subsystem 561"
Cohesion: 1.0
Nodes (1): approve_response rejects message not in pending_approval status.

### Community 562 - "Subsystem 562"
Cohesion: 1.0
Nodes (1): create_pending_response skips if user_message_id already in DB.

### Community 563 - "Subsystem 563"
Cohesion: 1.0
Nodes (1): create_pending_response preserves existing pending (no overwrite) and schedules

### Community 564 - "Subsystem 564"
Cohesion: 1.0
Nodes (1): After sleep, _debounced_regeneration updates pending message content.

### Community 565 - "Subsystem 565"
Cohesion: 1.0
Nodes (1): Regen exits early if the pending message was already approved.

### Community 566 - "Subsystem 566"
Cohesion: 1.0
Nodes (1): Instagram CDN URLs should return None immediately.

### Community 567 - "Subsystem 567"
Cohesion: 1.0
Nodes (1): When disabled, reactivate_ghost_leads returns disabled status.

### Community 568 - "Subsystem 568"
Cohesion: 1.0
Nodes (1): With 5+ preference pairs, produces Doc D update.

### Community 569 - "Subsystem 569"
Cohesion: 1.0
Nodes (1): Daily eval still works as before (regression test).

### Community 570 - "Subsystem 570"
Cohesion: 1.0
Nodes (1): Direct import from persona_compiler works.

### Community 571 - "Subsystem 571"
Cohesion: 1.0
Nodes (1): Weekly recalibration triggers compile_persona when recommendations exist.

### Community 572 - "Subsystem 572"
Cohesion: 1.0
Nodes (1): Legacy path: /no_think appended to last user msg when 'Qwen3' in model.

### Community 573 - "Subsystem 573"
Cohesion: 1.0
Nodes (1): A config with empty no_think_suffix must not inject /no_think.

### Community 574 - "Subsystem 574"
Cohesion: 1.0
Nodes (1): When config provides model_string, the env var DEEPINFRA_MODEL is ignored.

### Community 575 - "Subsystem 575"
Cohesion: 1.0
Nodes (1): No TOGETHER_API_KEY → returns None without calling API.

### Community 576 - "Subsystem 576"
Cohesion: 1.0
Nodes (1): Mocked successful Together API call.

### Community 577 - "Subsystem 577"
Cohesion: 1.0
Nodes (1): Empty content from API → returns None and records failure.

### Community 578 - "Subsystem 578"
Cohesion: 1.0
Nodes (1): Timeout → returns None and records failure.

### Community 579 - "Subsystem 579"
Cohesion: 1.0
Nodes (1): API error → returns None and records failure.

### Community 580 - "Subsystem 580"
Cohesion: 1.0
Nodes (1): Custom model is passed to API.

### Community 581 - "Subsystem 581"
Cohesion: 1.0
Nodes (1): When circuit is open, call_together returns None without API call.

### Community 582 - "Subsystem 582"
Cohesion: 1.0
Nodes (1): Real API call with 'Hola' to verify connectivity.

### Community 583 - "Subsystem 583"
Cohesion: 1.0
Nodes (1): LLM_MODEL_NAME unset → existing LLM_PRIMARY_PROVIDER cascade.

### Community 584 - "Subsystem 584"
Cohesion: 1.0
Nodes (1): No model_id → reads GEMINI_*_PENALTY env vars (current prod behavior).

### Community 585 - "Subsystem 585"
Cohesion: 1.0
Nodes (1): When model_id provided, penalties come from config not env.

### Community 586 - "Subsystem 586"
Cohesion: 1.0
Nodes (1): model_id=None → existing behavior preserved.

### Community 587 - "Subsystem 587"
Cohesion: 1.0
Nodes (1): Should load post context when generating response.

### Community 588 - "Subsystem 588"
Cohesion: 1.0
Nodes (1): Should include post context in prompt assembly.

### Community 589 - "Subsystem 589"
Cohesion: 1.0
Nodes (1): Should work gracefully when no post context.

### Community 590 - "Subsystem 590"
Cohesion: 1.0
Nodes (1): Should combine post context with relationship DNA.

### Community 591 - "Subsystem 591"
Cohesion: 1.0
Nodes (1): Mock de embeddings para tests consistentes

### Community 592 - "Subsystem 592"
Cohesion: 1.0
Nodes (1): Should refresh all expired contexts.

### Community 593 - "Subsystem 593"
Cohesion: 1.0
Nodes (1): Should continue on errors and report them.

### Community 594 - "Subsystem 594"
Cohesion: 1.0
Nodes (1): Should handle empty expired list.

### Community 595 - "Subsystem 595"
Cohesion: 1.0
Nodes (1): Ratio of times the rule helped vs times applied.

### Community 596 - "Subsystem 596"
Cohesion: 1.0
Nodes (1): Rule is considered effective if help ratio > 50% with enough data.

### Community 597 - "Subsystem 597"
Cohesion: 1.0
Nodes (1): Create PostContext from dictionary.

### Community 598 - "Subsystem 598"
Cohesion: 1.0
Nodes (0): 

### Community 599 - "Subsystem 599"
Cohesion: 1.0
Nodes (1): Obtiene preview de un link (thumbnail, título, descripción)         Microlink es

### Community 600 - "Subsystem 600"
Cohesion: 1.0
Nodes (1): Preview específico para posts de Instagram

### Community 601 - "Subsystem 601"
Cohesion: 1.0
Nodes (1): No-op for compatibility. Each capture manages its own browser.

### Community 602 - "Subsystem 602"
Cohesion: 1.0
Nodes (1): Captura screenshot de una URL y devuelve base64.         Cada captura crea su pr

### Community 603 - "Subsystem 603"
Cohesion: 1.0
Nodes (1): Captura específica para posts/reels de Instagram.         Intenta Playwright pri

### Community 604 - "Subsystem 604"
Cohesion: 1.0
Nodes (1): Captura específica para videos de YouTube         Returns dict con thumbnail_bas

### Community 605 - "Subsystem 605"
Cohesion: 1.0
Nodes (1): Captura genérica para cualquier URL.         Intenta Playwright primero, fallbac

### Community 606 - "Subsystem 606"
Cohesion: 1.0
Nodes (1): Auto-detecta el tipo de URL y captura el preview apropiado.         Uses Playwri

### Community 607 - "Subsystem 607"
Cohesion: 1.0
Nodes (1): Check if Cloudinary is properly configured.

### Community 608 - "Subsystem 608"
Cohesion: 1.0
Nodes (1): Legacy compat: True if score >= 0.6 (CLOSE or PERSONAL).

### Community 609 - "Subsystem 609"
Cohesion: 1.0
Nodes (1): Check if response content is empty.

### Community 610 - "Subsystem 610"
Cohesion: 1.0
Nodes (1): Score 0-1 measuring how much a response invites conversation continuation.

### Community 611 - "Subsystem 611"
Cohesion: 1.0
Nodes (1): CPE v2 Continuous Improvement Pipeline

### Community 612 - "Subsystem 612"
Cohesion: 1.0
Nodes (1): Audit: Edge Case Detection (Sistema #4)

### Community 613 - "Subsystem 613"
Cohesion: 1.0
Nodes (1): Audit: Postprocessing (Sistema #5)

### Community 614 - "Subsystem 614"
Cohesion: 1.0
Nodes (1): Audit: Context Signals (Sistema #3)

### Community 615 - "Subsystem 615"
Cohesion: 1.0
Nodes (1): Audit: Fase 2 Context Systems

### Community 616 - "Subsystem 616"
Cohesion: 1.0
Nodes (1): Audit: Memory Engine (Sistema #9)

### Community 617 - "Subsystem 617"
Cohesion: 1.0
Nodes (1): Instagram Message Dispatch

### Community 618 - "Subsystem 618"
Cohesion: 1.0
Nodes (1): Static robots.txt — Search Engine Rules

### Community 619 - "Subsystem 619"
Cohesion: 1.0
Nodes (1): PersoDPO — Scalable Preference Optimization for Persona Dialogue

### Community 620 - "Subsystem 620"
Cohesion: 1.0
Nodes (1): PAL — Persona-Aware Alignment Framework

### Community 621 - "Subsystem 621"
Cohesion: 1.0
Nodes (1): preference_pairs_service.py — Existing Preference Pairs Service

### Community 622 - "Subsystem 622"
Cohesion: 1.0
Nodes (1): gold_examples_service.py — Existing Gold Examples Service

### Community 623 - "Subsystem 623"
Cohesion: 1.0
Nodes (1): Placeholder Image SVG

## Knowledge Gaps
- **4378 isolated node(s):** `CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO`, `CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO (v2)  Cambios v2: - Todas las`, `expect: None = any non-5xx is PASS (legacy)             int  = exact HTTP code m`, `Shared SQLAlchemy base and common imports for all model modules.`, `Single metric measurement.` (+4373 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Subsystem 436`** (2 nodes): `verify_stefano_data.py`, `Verify Stefano's data counts pre/post re-ingestion.  Usage:   # Via production A`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 437`** (2 nodes): `store_manel_feedback.py`, `Store Manel's DPO pair and learning rules from ablation DNA review.  Usage: rail`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 438`** (2 nodes): `purge_bot_contaminated_memories.py`, `Purga hechos contaminados en lead_memories que describen acciones del bot en lug`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 439`** (2 nodes): `investigate_dna.py`, `Investigate DNA state for test leads. Run via: railway run python3.11 scripts/in`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 440`** (2 nodes): `purge_contaminated_gold_examples.py`, `Purgar gold examples contaminados (respuestas de error del sistema). Marca is_ac`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 441`** (2 nodes): `cpe_generate_length_profile.py`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 442`** (2 nodes): `_rag_gen_embeddings.py`, `Generate embeddings for content_chunks missing them. Run: railway run python3 sc`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 443`** (2 nodes): `check_bon.py`, `Check best-of-N candidates in recent copilot suggestions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 444`** (2 nodes): `generate_iris_eval_data.py`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 445`** (2 nodes): `test_dna_lookup.py`, `Test DNA lookup for test leads. Run: railway run python3.11 scripts/test_dna_loo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 446`** (2 nodes): `fix_rag_db.py`, `RAG DB Fixes — run with: railway run python3 scripts/fix_rag_db.py  Fix 1: Norma`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 447`** (2 nodes): `_rag_fix_run.py`, `Temporary fix script — run with: railway run python3 scripts/_rag_fix_run.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 448`** (2 nodes): `build_evaluator.py`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 449`** (2 nodes): `autolearning_api.py`, `Backward compatibility — moved to api.routers.autolearning.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 450`** (2 nodes): `db_service.py`, `Backward compatibility — all functions moved to api.services.db/ modules.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 451`** (2 nodes): `feedback_store.py`, `Re-export shim — all logic moved to services/feedback_capture.py. Kept for backw`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 452`** (2 nodes): `Audit: Cross-Encoder Reranker (Sistema #12)`, `Passage Re-ranking with BERT (Nogueira & Cho 2020)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 453`** (2 nodes): `Qwen/Qwen3-14B Base Model`, `LoRA SFT Adapter — Qwen3-14B`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 454`** (2 nodes): `LoRA DPO Adapter — 8B MLX 4-bit Quantized`, `MLX Library (Apple Silicon)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 455`** (2 nodes): `Clonnect Brand Logo — From Follow to Hello`, `Clonnect Brand Logo (PNG variant)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 456`** (1 nodes): `Genera ID unico basado en feed URL.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 457`** (1 nodes): `Extrae video ID de una URL de YouTube.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 458`** (1 nodes): `Crea desde diccionario, filtrando campos desconocidos.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 459`** (1 nodes): `Check if page has meaningful content.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 460`** (1 nodes): `Genera ID unico basado en source.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 461`** (1 nodes): `Verifica si el post tiene contenido util para indexar.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 462`** (1 nodes): `Obtener descripción humana de la intención`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 463`** (1 nodes): `Create from FollowUp dataclass.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 464`** (1 nodes): `Get a database session with proper error handling.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 465`** (1 nodes): `Number of characters in content.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 466`** (1 nodes): `send_message posts correct JSON to the API.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 467`** (1 nodes): `handle_webhook_event returns empty list for empty payload.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 468`** (1 nodes): `handle_webhook_event returns empty list when entry has no messages.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 469`** (1 nodes): `handle_webhook_event handles malformed data gracefully.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 470`** (1 nodes): `Handler.handle_webhook returns 0 messages_processed for empty payload.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 471`** (1 nodes): `Crea directorio temporal para tests.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 472`** (1 nodes): `Verifica guardar y cargar perfil.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 473`** (1 nodes): `Verifica lista de perfiles con datos.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 474`** (1 nodes): `Verifica generacion de perfil desde posts.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 475`** (1 nodes): `When DB is completely unavailable, save returns False.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 476`** (1 nodes): `ingest_website_v2 should return IngestV2Response on success.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 477`** (1 nodes): `When the pipeline raises an exception, endpoint should return 500.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 478`** (1 nodes): `Status endpoint should return 'empty' when no posts indexed.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 479`** (1 nodes): `Status endpoint should return 'ready' when posts are indexed.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 480`** (1 nodes): `Payment link request should return valid URL for stefano_bonanno`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 481`** (1 nodes): `Booking request should return Calendly or booking info`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 482`** (1 nodes): `Escalation request should set escalate_to_human flag`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 483`** (1 nodes): `First message should be received and processed`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 484`** (1 nodes): `Second message from same sender should be received`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 485`** (1 nodes): `Context should be maintained between messages`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 486`** (1 nodes): `Lead magnet request should be detected`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 487`** (1 nodes): `Lead magnet request should trigger action`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 488`** (1 nodes): `Price question should receive valid response`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 489`** (1 nodes): `Response should not contain placeholder patterns`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 490`** (1 nodes): `Response should be valid and relevant`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 491`** (1 nodes): `get_leads should return a list of lead dicts when creator exists.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 492`** (1 nodes): `get_leads returns [] when the creator does not exist in DB.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 493`** (1 nodes): `get_creator_by_name returns None for a non-existent creator.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 494`** (1 nodes): `When get_session returns None, get_leads should return [].`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 495`** (1 nodes): `When DB is unavailable, credentials return success=False.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 496`** (1 nodes): `toggle_bot should return None when the DB is down.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 497`** (1 nodes): `The limit argument should be forwarded to SQLAlchemy .limit().`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 498`** (1 nodes): `get_db_message_ids returns a set of message IDs (mocked DB).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 499`** (1 nodes): `reconcile_messages_for_creator handles zero conversations.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 500`** (1 nodes): `run_startup_reconciliation updates global last_reconciliation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 501`** (1 nodes): `run_periodic_reconciliation updates global counters.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 502`** (1 nodes): `run_startup_reconciliation returns error dict on exception.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 503`** (1 nodes): `Platform message dedup returns early but doesn't crash tracking.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 504`** (1 nodes): `resolved_externally handler should call _store_rule with confidence=0.7.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 505`** (1 nodes): `Should skip if neither suggested nor final response exist.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 506`** (1 nodes): `When ENABLE_AUTOLEARNING is false, analyze_creator_action should return immediat`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 507`** (1 nodes): `When ENABLE_AUTOLEARNING is true, should dispatch to handler.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 508`** (1 nodes): `Skips if evaluation already exists for the date.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 509`** (1 nodes): `Skips if no copilot actions for the day.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 510`** (1 nodes): `Skips if weekly evaluation already exists.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 511`** (1 nodes): `Skips if fewer than 3 daily evaluations.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 512`** (1 nodes): `Paso 5: DM history respeta max_age_days (default 90)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 513`** (1 nodes): `BUG-LR-02 regression: score should be linear in confidence, not quadratic.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 514`** (1 nodes): `Two rules with confidence 0.5 and 1.0 — ratio should be ~2:1, not ~4:1.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 515`** (1 nodes): `BUG-GE-01 regression: score should be linear in quality_score, not quadratic.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 516`** (1 nodes): `save_feedback stores a record and returns feedback_id.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 517`** (1 nodes): `When ideal_response provided, auto-creates preference pair.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 518`** (1 nodes): `When lo_enviarias >= 4 AND ideal_response, also creates gold example.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 519`** (1 nodes): `When ENABLE_EVALUATOR_FEEDBACK=false, returns status=disabled.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 520`** (1 nodes): `get_feedback returns structured list of feedback records.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 521`** (1 nodes): `get_feedback applies evaluator_id and score filters.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 522`** (1 nodes): `FB-03: Empty string ideal_response should NOT create preference pair.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 523`** (1 nodes): `FB-07: DB error returns status=error, not None.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 524`** (1 nodes): `FB-08: Stats error returns status=error dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 525`** (1 nodes): `save_feedback accepts any UUID creator_db_id.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 526`** (1 nodes): `capture(evaluator_score) routes to save_feedback.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 527`** (1 nodes): `capture(copilot_edit) routes to create_pairs_from_action.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 528`** (1 nodes): `capture(copilot_approve) → quality 0.6.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 529`** (1 nodes): `capture(copilot_discard) → quality 0.4.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 530`** (1 nodes): `capture(copilot_resolved) → quality 0.9 (strongest signal).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 531`** (1 nodes): `Unknown signal_type returns error.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 532`** (1 nodes): `OAuth start should return auth URL when configured`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 533`** (1 nodes): `Test processing PAYMENT.SALE.COMPLETED event`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 534`** (1 nodes): `Test processing CHECKOUT.ORDER.APPROVED event`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 535`** (1 nodes): `Test that duplicate payments are not processed twice`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 536`** (1 nodes): `Test processing PAYMENT.SALE.REFUNDED event`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 537`** (1 nodes): `Verification should be skipped if PAYPAL_WEBHOOK_ID not set`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 538`** (1 nodes): `Verification should fail if required headers missing`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 539`** (1 nodes): `Purchases should be tracked in SalesTracker`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 540`** (1 nodes): `When no existing JSON, sync_lead_to_json should create a new file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 541`** (1 nodes): `When JSON exists, sync_lead_to_json merges data (no status downgrade).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 542`** (1 nodes): `sync_lead_to_json should silently return if platform_user_id is empty.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 543`** (1 nodes): `full_sync_creator returns zero stats when PostgreSQL is disabled.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 544`** (1 nodes): `full_sync_creator returns zero stats when creator directory is missing.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 545`** (1 nodes): `full_sync_creator only processes .json files, not .txt.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 546`** (1 nodes): `When copilot service returns dict format, response includes pagination.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 547`** (1 nodes): `When copilot service returns old list format, response is backward-compatible.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 548`** (1 nodes): `Approving a response should return the service result on success.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 549`** (1 nodes): `GET /copilot/{creator_id}/pending returns pending_count=0 for empty queue.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 550`** (1 nodes): `The creator_id path param should be forwarded to the service layer.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 551`** (1 nodes): `discard_response should forward both creator_id and message_id.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 552`** (1 nodes): `Returns {pending: null} when no pending suggestion for the lead.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 553`** (1 nodes): `Returns pending suggestion with conversation_context when found.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 554`** (1 nodes): `Empty message should still produce a response (not crash).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 555`** (1 nodes): `get_pending_responses returns empty when creator not found.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 556`** (1 nodes): `get_pending_responses returns dict with pending, total_count, has_more.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 557`** (1 nodes): `get_pending_responses returns empty on DB exception.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 558`** (1 nodes): `discard_response returns error when message not found.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 559`** (1 nodes): `discard_response handles DB exception gracefully.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 560`** (1 nodes): `approve_response returns error when creator not found.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 561`** (1 nodes): `approve_response rejects message not in pending_approval status.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 562`** (1 nodes): `create_pending_response skips if user_message_id already in DB.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 563`** (1 nodes): `create_pending_response preserves existing pending (no overwrite) and schedules`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 564`** (1 nodes): `After sleep, _debounced_regeneration updates pending message content.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 565`** (1 nodes): `Regen exits early if the pending message was already approved.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 566`** (1 nodes): `Instagram CDN URLs should return None immediately.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 567`** (1 nodes): `When disabled, reactivate_ghost_leads returns disabled status.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 568`** (1 nodes): `With 5+ preference pairs, produces Doc D update.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 569`** (1 nodes): `Daily eval still works as before (regression test).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 570`** (1 nodes): `Direct import from persona_compiler works.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 571`** (1 nodes): `Weekly recalibration triggers compile_persona when recommendations exist.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 572`** (1 nodes): `Legacy path: /no_think appended to last user msg when 'Qwen3' in model.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 573`** (1 nodes): `A config with empty no_think_suffix must not inject /no_think.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 574`** (1 nodes): `When config provides model_string, the env var DEEPINFRA_MODEL is ignored.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 575`** (1 nodes): `No TOGETHER_API_KEY → returns None without calling API.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 576`** (1 nodes): `Mocked successful Together API call.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 577`** (1 nodes): `Empty content from API → returns None and records failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 578`** (1 nodes): `Timeout → returns None and records failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 579`** (1 nodes): `API error → returns None and records failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 580`** (1 nodes): `Custom model is passed to API.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 581`** (1 nodes): `When circuit is open, call_together returns None without API call.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 582`** (1 nodes): `Real API call with 'Hola' to verify connectivity.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 583`** (1 nodes): `LLM_MODEL_NAME unset → existing LLM_PRIMARY_PROVIDER cascade.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 584`** (1 nodes): `No model_id → reads GEMINI_*_PENALTY env vars (current prod behavior).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 585`** (1 nodes): `When model_id provided, penalties come from config not env.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 586`** (1 nodes): `model_id=None → existing behavior preserved.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 587`** (1 nodes): `Should load post context when generating response.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 588`** (1 nodes): `Should include post context in prompt assembly.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 589`** (1 nodes): `Should work gracefully when no post context.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 590`** (1 nodes): `Should combine post context with relationship DNA.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 591`** (1 nodes): `Mock de embeddings para tests consistentes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 592`** (1 nodes): `Should refresh all expired contexts.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 593`** (1 nodes): `Should continue on errors and report them.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 594`** (1 nodes): `Should handle empty expired list.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 595`** (1 nodes): `Ratio of times the rule helped vs times applied.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 596`** (1 nodes): `Rule is considered effective if help ratio > 50% with enough data.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 597`** (1 nodes): `Create PostContext from dictionary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 598`** (1 nodes): `native-48B9X9Wg.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 599`** (1 nodes): `Obtiene preview de un link (thumbnail, título, descripción)         Microlink es`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 600`** (1 nodes): `Preview específico para posts de Instagram`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 601`** (1 nodes): `No-op for compatibility. Each capture manages its own browser.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 602`** (1 nodes): `Captura screenshot de una URL y devuelve base64.         Cada captura crea su pr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 603`** (1 nodes): `Captura específica para posts/reels de Instagram.         Intenta Playwright pri`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 604`** (1 nodes): `Captura específica para videos de YouTube         Returns dict con thumbnail_bas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 605`** (1 nodes): `Captura genérica para cualquier URL.         Intenta Playwright primero, fallbac`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 606`** (1 nodes): `Auto-detecta el tipo de URL y captura el preview apropiado.         Uses Playwri`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 607`** (1 nodes): `Check if Cloudinary is properly configured.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 608`** (1 nodes): `Legacy compat: True if score >= 0.6 (CLOSE or PERSONAL).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 609`** (1 nodes): `Check if response content is empty.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 610`** (1 nodes): `Score 0-1 measuring how much a response invites conversation continuation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 611`** (1 nodes): `CPE v2 Continuous Improvement Pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 612`** (1 nodes): `Audit: Edge Case Detection (Sistema #4)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 613`** (1 nodes): `Audit: Postprocessing (Sistema #5)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 614`** (1 nodes): `Audit: Context Signals (Sistema #3)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 615`** (1 nodes): `Audit: Fase 2 Context Systems`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 616`** (1 nodes): `Audit: Memory Engine (Sistema #9)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 617`** (1 nodes): `Instagram Message Dispatch`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 618`** (1 nodes): `Static robots.txt — Search Engine Rules`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 619`** (1 nodes): `PersoDPO — Scalable Preference Optimization for Persona Dialogue`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 620`** (1 nodes): `PAL — Persona-Aware Alignment Framework`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 621`** (1 nodes): `preference_pairs_service.py — Existing Preference Pairs Service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 622`** (1 nodes): `gold_examples_service.py — Existing Gold Examples Service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subsystem 623`** (1 nodes): `Placeholder Image SVG`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Business logic services for Clonnect. Extracted from dm_agent.py following TDD m` connect `Lead Abandonment Detection` to `System Audit Documentation`, `Core DM Systems Audit`, `DM Responder Agent`, `Bio & Profile Extraction`, `Clone Auto-Configuration`, `Clone Setup & Onboarding`, `Copilot Response Actions`, `Bot API & Middleware`, `Best-of-N Response Selection`, `System Prompt Configuration`, `Data Migration Scripts`, `Analytics & Events`, `Subsystem 21`, `Subsystem 22`, `Subsystem 23`, `Subsystem 27`, `Subsystem 32`, `Subsystem 39`, `Subsystem 42`, `Subsystem 44`, `Subsystem 48`, `Subsystem 51`, `Subsystem 59`, `Subsystem 66`, `Subsystem 70`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Why does `BoundedTTLCache` connect `Core DM Systems Audit` to `System Audit Documentation`, `DM Responder Agent`, `Clone Auto-Configuration`, `Bot API & Middleware`, `Vocabulary & Batch Processing`, `Analytics & Events`, `Subsystem 22`, `Subsystem 27`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `Intent` connect `System Audit Documentation` to `Bot API & Middleware`, `DM Responder Agent`, `Lead Abandonment Detection`, `Best-of-N Response Selection`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 352 inferred relationships involving `BoundedTTLCache` (e.g. with `ProductInfo` and `BookingInfo`) actually correct?**
  _`BoundedTTLCache` has 352 INFERRED edges - model-reasoned connections that need verification._
- **Are the 322 inferred relationships involving `Intent` (e.g. with `Prompt Builder — Main prompt building and convenience functions.  Contains build` and `Run all detectors and return complete context.      Main entry point for context`) actually correct?**
  _`Intent` has 322 INFERRED edges - model-reasoned connections that need verification._
- **Are the 212 inferred relationships involving `CreatorData` (e.g. with `BookingLink` and `BoundedTTLCache`) actually correct?**
  _`CreatorData` has 212 INFERRED edges - model-reasoned connections that need verification._
- **Are the 205 inferred relationships involving `IntentClassifier` (e.g. with `Prompt Builder — Main prompt building and convenience functions.  Contains build` and `Run all detectors and return complete context.      Main entry point for context`) actually correct?**
  _`IntentClassifier` has 205 INFERRED edges - model-reasoned connections that need verification._