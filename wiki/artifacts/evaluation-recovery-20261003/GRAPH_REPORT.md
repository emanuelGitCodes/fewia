# Graph Report - fewia  (2026-10-03)

## Corpus Check
- 488 files · ~360,518 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6564 nodes · 19238 edges · 322 communities (180 shown, 142 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 957 edges (avg confidence: 0.9)
- Token cost: unavailable for the native semantic agent; deterministic AST extraction uses no model calls.

## Graph Freshness
- Built from commit: `e119a2d4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Instacart Handoff Service
- Evaluation Claim Score
- Evaluation Summary Metrics
- Evaluation Model Turn
- Sync API
- Chat API Tests
- Supervisor Gates
- Chat Dispatch and Routes
- Evaluation No Tool Turn
- Evaluation Plan Score
- Grocery Job API
- Evaluation Io
- Supervisor Review Command
- Backend Test Fixtures
- Budget Form
- Ledger Budget
- Handoff Intents and Dispatch
- Evaluation Model
- Job Submission
- Chat Workspace UI
- Evidence API 2
- Alembic Migrations
- Frontend Estimate View
- Shared HTTP Client and Instacart
- Chat Public Answers
- Chat Message Parsing (2)
- Chat History Store
- Frontend Chat Client
- Supermarket Cost Overlay
- Evaluation Database
- Evaluation Summary Task Validation
- Evaluation Runner
- Evaluation Duplicate
- Evaluation Summary Task Assessments
- Runtime Rules and Bedrock Access
- Accepted Project Scope
- Recipe Catalog Domain
- Delegation Rules and Decisions 2
- Budget Summary Tool
- Evaluation Protocol
- Supervisor Lease and CLI
- Meal Template Service
- Handoff Contract 2
- Frontend Package Manifest
- Planning Tool
- Grocery Provider Runtime
- Template API Tests
- Job Worker
- Frontend Handoff Types
- Apivalidation
- Bedrock Session Refresh
- Evaluation Claim Propositions
- Budget Summary Tool
- Alembic Migrations
- Supervisor Process and Events
- Chat Dispatch and Provider 2
- Course Proposal Concepts
- Evaluation Summary
- Spoonacular Cost Adapter
- Job Consumer
- Chat Public Answers
- Evaluation Baseline Response
- Frontend App Shell
- FastAPI App and Errors
- Local Artifacts
- Planning Tool and Followup Eval (part 2)
- Provider Settings
- Agent Job Handlers
- Evaluation Components
- Agent Team and Writers
- Evaluation Matrix
- Plaid Sync Loading
- Evaluation Manifest
- Evaluation Cost
- Evaluation Markdown Format
- Evaluation Refresh
- Plaid Http
- Planning Tool and Followup Eval
- Supervisor Lease and CLI 2
- Recipe Catalog Domain
- Evaluation Refresh Fixture
- Database Session and Job Models
- Evaluation Summary Task
- Usda Refresh
- Evidence API 2
- Chat Public Answers
- Grocery Job API (2)
- Bedrock Provider
- Recipe Catalog Domain
- Evaluation Handoff
- Evaluation Inputs
- Floci Bootstrap
- Planning Tool (2)
- Chat Context Builder
- Chat Context Builder 3
- Evaluation Plan Schema
- Plaid Contract
- Job Heartbeat and Delivery
- Job Recovery
- Agent Job Handlers
- Meal Nutrition Tests
- Recipe Catalog Domain 2
- Database Session and Job Models
- Local Sqs Consumer
- Frontend Estimate View
- Delegation Rules and Decisions
- Supermarket Cost Overlay (2)
- Evaluation Telemetry
- Handoff Models
- Plaid Sync Job
- Worker
- Shared AWS Client Config 2
- Consume Jobs
- Apifixtures
- Runtime Rules and Bedrock Access
- Database Session and Job Models 3
- Plaid Sync Job
- Plaid Sync
- Evidence API
- Meal Nutrition Tests 2
- Frontend App Shell 2
- Chat Refusal Parser
- Provider Settings 2
- Provider Settings 2
- Evidence API
- Evaluation Runner 2
- USDA and Spoonacular Decisions (2)
- USDA and Spoonacular Decisions
- Frontend Chat Client
- Project Plan
- Sync Api Models
- Meal Nutrition Tests
- Evaluation Runner 3
- Database Session and Job Models
- Meal Nutrition Tests 3
- Consume Jobs (2)
- Supervisor Events and Process 3
- Budget Summary Tool
- Meal Nutrition Tests
- Chat Context Builder 2
- Handoff Contract
- Handoff (2)
- Alembic Migrations
- Bedrock Provider
- Alembic Migrations 2
- Supervisor Lease and CLI
- Phase 2
- Tool Evidence IDs
- Accepted Project Scope
- FastAPI App and Errors
- Local Sqs
- Job Delivery
- Supervisor Lease and CLI
- Ci Components
- Chat Context Builder
- Sync Route and Dependencies
- Chat Context Builder 2
- Meal Nutrition Tests
- Grocery Chat Concept
- Tsconfig
- 0012 Tool Calling Orchestration
- Job Heartbeat and Delivery (2)
- Evaluation Telemetry
- Meal Nutrition Tests 4
- Evaluation Summary Task Validation
- Provider Settings 2
- Database Session and Job Models
- Agent Job Handlers
- Supervisor Events and Process 3
- Cap6938 August 25
- Evaluation-Publication Components
- Delegation Rules and Decisions 2
- Chat Public Answers
- Cap6938 August 25 2
- Cap6938 Mvp Project Plan
- Shared AWS Client Config
- Cap6938 Mvp Project Plan 2
- Readme
- Budget Summary Tool
- Local Sqs Consumer 2
- Cap6938 Mvp Project Plan 3
- Dev Supervisor Verification
- Cap6938 Mvp Project Plan 4
- Project Context and Runbooks
- Project Context and Runbooks (2)
- Grocery Build Progress
- 0005 Human Gated Agent Learning
- Cap6938 Mvp Project Plan 5
- Audit
- 0008 Grocery Bot Pivot
- Tool Evidence IDs
- Chat Public Answers
- Notice Parity Test
- Writing Block
- Index
- Catalog Dev
- Database Session and Job Models
- Writing Block 2
- Grocery Build Progress 2
- Ten-Phase Build Plan
- Feature Loop Skills
- Feature Loop Skills (2)
- Cap6938 August 25 3
- Feature Loop Skills (3)
- Agent Dev
- Aws Infra
- Backend Dev
- Database Dev
- Docs Dev
- Frontend Dev
- Provider Dev
- Reliability Dev
- Security Dev
- Test Engineer
- Pyproject
- Pyproject 2
- Grocery Build Progress 4
- Dev Supervisor (3)
- Migration 0003 Model Runs
- Plaid Instacart Update Plan

## God Nodes (most connected - your core abstractions)
1. `execute_plan()` - 80 edges
2. `classify_slot()` - 60 edges
3. `summarize_metrics()` - 59 edges
4. `CaptureProvider` - 56 edges
5. `score_plan()` - 55 edges
6. `_run()` - 51 edges
7. `assessment_status()` - 50 edges
8. `_slot()` - 49 edges
9. `_case()` - 46 edges
10. `_observation()` - 46 edges

## Surprising Connections (you probably didn't know these)
- `ChatWorkspace and ChatPanel Beside Manual Planner` --references--> `ChatWorkspace()`  [AMBIGUOUS]
  wiki/phases/grocery-mvp-checkpoint.md → frontend/src/ChatWorkspace.tsx
- `120-Second Visibility and Three-Receive Dead-Letter Policy` --semantically_similar_to--> `Job Leases (claim_job, renew_lease, finish_job)`  [INFERRED] [semantically similar]
  infra/README.md → runbooks/durable-jobs.md
- `Request-Key Idempotency (IdempotencyConflict)` --references--> `create_job()`  [EXTRACTED]
  runbooks/durable-jobs.md → backend/app/services/job_submission.py
- `Prompt-Injection Defense` --semantically_similar_to--> `Runtime and evidence rules`  [INFERRED] [semantically similar]
  plans/plaid-instacart-repository-update-plan.md → .codex/project-context.md
- `Bedrock agent design with client-side tool use` --semantically_similar_to--> `Decision 0012: Tool calling as the orchestration boundary`  [INFERRED] [semantically similar]
  docs/CAP6938_MVP_PROJECT_PLAN.md → wiki/decisions/0012-tool-calling-orchestration.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **CI validation jobs** — github_workflows_ci_workflow, github_workflows_ci_compose_job, github_workflows_ci_backend_job, github_workflows_ci_frontend_job [EXTRACTED 1.00]
- **Development Bedrock credential path** — infra_bedrock_readme_iam_role, infra_bedrock_readme_mfa_trust_policy, infra_bedrock_readme_host_credentials, compose_bedrock_x_bedrock [EXTRACTED 1.00]
- **Default Compose Stack Services** — compose_postgres, compose_floci, compose_bootstrap, compose_api, compose_worker, compose_sync_worker, compose_web [EXTRACTED 1.00]
- **Roles in the delegation loop** — docs_delegation_coordinator_role, docs_delegation_junior_role, docs_delegation_writer_role, docs_delegation_review_model, docs_delegation_tier_l_probes [EXTRACTED 1.00]
- **dev_supervisor command suite (writer, gates, review, usage)** — docs_dev_supervisor, docs_delegation_dev_supervisor_gates, docs_delegation_dev_supervisor_review, docs_delegation_dev_supervisor_usage [EXTRACTED 1.00]
- **Concept dialogue, constraints, and ingredient planning workspace** — docs_design_grocery_chat_concept_conversation_panel, docs_design_grocery_chat_concept_budget_panel, docs_design_grocery_chat_concept_estimate_table, docs_design_grocery_chat_concept_pantry_controls [EXTRACTED 1.00]
- **Deterministic tool set with a shared evidence contract** — docs_cap6938_mvp_project_plan_get_financial_context, docs_cap6938_mvp_project_plan_get_environment_context, docs_cap6938_mvp_project_plan_get_health_context, docs_cap6938_mvp_project_plan_run_activity_prediction, docs_cap6938_mvp_project_plan_compare_periods, docs_cap6938_mvp_project_plan_evidence_id [EXTRACTED 1.00]
- **Forty-meal catalog rollout across decision, backlog, and scope docs** — wiki_decisions_0017_forty_meal_catalog_forty_meal_catalog, wiki_decisions_0017_forty_meal_catalog_sample_prices_v2, wiki_phases_moderate_backlog_forty_meal_catalog_item, _codex_project_context_supported_meal_catalog, wiki_log_easy_backlog_2 [EXTRACTED 1.00]
- **Hybrid data source rules** — docs_nutrition_sources_usda_fooddata_central, wiki_decisions_0010_usda_spoonacular_overlay_spoonacular_overlay, wiki_decisions_0010_usda_spoonacular_overlay_sample_catalog_cents, wiki_decisions_0010_usda_spoonacular_overlay_park_instacart [EXTRACTED 1.00]
- **Shared Junior Developer Protocol (brief, worktree, dev_supervisor writer, no direct edits)** — _claude_agents_agent_dev, _claude_agents_aws_infra, _claude_agents_backend_dev, _claude_agents_catalog_dev, _claude_agents_database_dev, _claude_agents_docs_dev, _claude_agents_eval_engineer, _claude_agents_frontend_dev, _claude_agents_ml_dev, _claude_agents_provider_dev, _claude_agents_reliability_dev, _claude_agents_security_dev, _claude_agents_test_engineer, docs_delegation_junior, dev_supervisor [EXTRACTED 1.00]
- **External Sources to Grounded Explanation Path** — docs_writing_block_plaid_api, docs_writing_block_garmin_health_api, docs_writing_block_geographic_context_api, docs_writing_block_feature_engineering, docs_writing_block_aurora_postgresql, docs_writing_block_reason_act_agent, docs_writing_block_grounded_explanation [EXTRACTED 1.00]
- **Three-Condition Predictive Experiment** — docs_writing_block_model_a_financial, docs_writing_block_model_b_environmental, docs_writing_block_model_c_combined, docs_writing_block_ablation_study [EXTRACTED 1.00]
- **Three-layer learning** — wiki_decisions_0005_human_gated_agent_learning_human_gated_agent_learning, wiki_decisions_0005_human_gated_agent_learning_wiki_facts, wiki_decisions_0005_human_gated_agent_learning_behavioral_definition_changes, wiki_decisions_0005_human_gated_agent_learning_mechanical_hooks [EXTRACTED 1.00]
- **Wiki Record-Keeping System** — wiki_schema_wiki_schema, wiki_phases_phase_0_record [EXTRACTED 1.00]
- **Codex/Grok Writers Dispatched Through dev_supervisor** — codex_writer, grok_writer, dev_supervisor [EXTRACTED 1.00]
- **Writer difficulty ladder (Luna, Grok, Sol by index score)** — wiki_decisions_0015_writer_routing_by_difficulty_artificial_analysis_index [EXTRACTED 1.00]
- **Durable Agent Job Pipeline** — compose_api, runbooks_durable_jobs_transactional_outbox, runbooks_durable_jobs_outbox_publisher, infra_readme_fewia_agent, compose_worker, runbooks_durable_jobs_job_leases, infra_readme_fewia_agent_dlq [INFERRED 0.85]
- **Grounded answer flow from question to cited evidence** — docs_cap6938_mvp_project_plan_first_working_demo, docs_cap6938_mvp_project_plan_bedrock_agent_design, docs_cap6938_mvp_project_plan_llmprovider, docs_cap6938_mvp_project_plan_postgresql_schema, docs_cap6938_mvp_project_plan_run_activity_prediction, docs_cap6938_mvp_project_plan_non_causal_constraint [INFERRED 0.85]
- **LLM selects tools; server owns budget, totals, and refusals** — _codex_project_context_llm_tool_boundary, wiki_phases_moderate_backlog_tool_derived_public_answers, wiki_phases_moderate_backlog_get_budget_summary, wiki_phases_moderate_backlog_bounded_refusal_parser, wiki_phases_moderate_backlog_validated_tool_call_replay, wiki_phases_moderate_backlog_plan_cap_context [INFERRED 0.85]
- **Labeled overlays beside sample-catalog budget cents** — _codex_project_context_estimate_notice, wiki_decisions_0010_usda_spoonacular_overlay_spoonacular_cost_notice, readme_usda_nutrition, wiki_log_hybrid_data_stack, wiki_phases_moderate_backlog_read_time_overlay_stripping [INFERRED 0.85]
- **Shared ruff/mypy/pytest quality-gate pattern across backend, dev_supervisor, and Bedrock infra** — _github_workflows_ci_backend, github_workflows_tooling_tools, github_workflows_tooling_bedrock_infra [INFERRED 0.85]
- **Spoonacular Read-Time Overlay Rollout** — wiki_decisions_0016_spoonacular_read_time_overlay_read_time_overlay, readme_spoonacular_overlay, _github_workflows_ci_compose, compose_api [INFERRED 0.85]
- **Tool-calling orchestration boundary over deterministic services** — wiki_decisions_0012_tool_calling_orchestration_run_chat, wiki_decisions_0012_tool_calling_orchestration_plan_groceries_tool [INFERRED 0.85]

## Communities (322 total, 142 thin omitted)

### Community 0 - "Instacart Handoff Service"
Cohesion: 0.05
Nodes (72): create_handoff(), _dispatch(), _fail(), get_session_factory(), estimate_from_snapshot(), HandoffRouteError, job_shopping_payload(), planning_fields() (+64 more)

### Community 1 - "Evaluation Claim Score"
Cohesion: 0.07
Nodes (95): _facts(), score_claims(), _turns(), _frame(), observe_reference_case(), as_map(), typed_equal(), valid_public_result() (+87 more)

### Community 2 - "Evaluation Summary Metrics"
Cohesion: 0.06
Nodes (97): _count(), _rate(), sum_binary_metrics(), sum_claim_counts(), summarize_assessment_statuses(), _check_name(), failure_record(), validate_checks() (+89 more)

### Community 3 - "Evaluation Model Turn"
Cohesion: 0.05
Nodes (69): CaptureProvider, observe_model_turn(), public(), record(), _OrdinaryErrorBoundary, response(), ScriptedProvider, test_bounded_capture_keeps_attempt_count_and_protocol_state() (+61 more)

### Community 4 - "Sync API"
Cohesion: 0.06
Nodes (64): create_sync_job(), _is_plaid_sync_payload(), _owned_item(), read_sync_job(), create_job(), assert_lease_time_matches_stored(), load_job(), queued_job() (+56 more)

### Community 5 - "Chat API Tests"
Cohesion: 0.06
Nodes (60): create_chat_job(), CreateChatJobBody, read_chat_job(), read_providers(), ChatJobInput, add_parent(), chat_body(), _clear_fewia_env() (+52 more)

### Community 6 - "Supervisor Gates"
Cohesion: 0.06
Nodes (74): CommandResult, emit(), invoke_command(), main(), provision_floci(), resolve_infra_script(), run_command(), seed_demo_user() (+66 more)

### Community 7 - "Chat Dispatch and Routes"
Cohesion: 0.06
Nodes (20): _llm_tool_payload(), _money_display(), _usd_cents_display(), LLMProvider, LLMUnavailable, _ny_now(), _ny_now(), _parse_clock() (+12 more)

### Community 8 - "Evaluation No Tool Turn"
Cohesion: 0.07
Nodes (69): observe_no_tool_case(), observe_no_tool_turn(), _ProviderExceptionBoundary, _ProviderFailure, _SanitizedProvider, case_with(), context_of(), messages_of() (+61 more)

### Community 9 - "Evaluation Plan Score"
Cohesion: 0.11
Nodes (84): plan_integrity(), _has(), _ids(), _lines(), score_plan(), _line(), _lines(), multi_package_observed() (+76 more)

### Community 10 - "Grocery Job API"
Cohesion: 0.07
Nodes (53): create_grocery_job(), _ny_now(), read_grocery_config(), read_grocery_job(), require_spending(), _clear_fewia_env(), commit_without_ending_the_test_transaction(), freeze_new_york_clock() (+45 more)

### Community 11 - "Evaluation Io"
Cohesion: 0.05
Nodes (49): _emit(), EvaluationOutput, EvaluationPaths, canonical_json_bytes(), _constant(), _invalid(), load_json(), _object() (+41 more)

### Community 12 - "Supervisor Review Command"
Cohesion: 0.09
Nodes (61): choose_provider(), first_error(), git_text(), grok_command(), grok_effort(), grok_report(), main(), git() (+53 more)

### Community 13 - "Backend Test Fixtures"
Cohesion: 0.05
Nodes (40): client(), _database_skip_reason(), _days(), engine(), pytest_runtest_logreport(), pytest_sessionstart(), pytest_terminal_summary(), require_test_database_url() (+32 more)

### Community 14 - "Budget Form"
Cohesion: 0.05
Nodes (50): GroceryConfig, mount(), BudgetForm(), checks(), FormState, MealRow, Props, SERVINGS (+42 more)

### Community 15 - "Ledger Budget"
Cohesion: 0.08
Nodes (54): snapshot(), test_dataclasses_are_immutable(), test_exactly_24_hours_is_fresh(), test_fall_back_day_counts_25_elapsed_hours_as_stale(), test_fold_future_refresh_is_rejected_by_utc_ordering(), test_fresh_budget_subtracts_posted_and_keeps_pending_separate(), test_fresh_explicit_cap_is_applied_after_net_posted_spending(), test_integer_controls_reject_booleans_and_negative_caps() (+46 more)

### Community 16 - "Handoff Intents and Dispatch"
Cohesion: 0.09
Nodes (44): factory(), _FailBegin, FailCommitFactory, FakeProvider, handoff_engine(), owners(), postgres_factory(), test_claim_commit_failure_does_not_post() (+36 more)

### Community 17 - "Evaluation Model"
Cohesion: 0.11
Nodes (52): _EvidenceErrorBoundary, observe_model_case(), case(), context(), observe(), OrdinaryError, reply(), request() (+44 more)

### Community 18 - "Job Submission"
Cohesion: 0.07
Nodes (33): _canonical(), find_job(), IdempotencyConflict, JobConflict, JobInputInvalid, JobUnavailable, reuse_job(), submit_job() (+25 more)

### Community 19 - "Chat Workspace UI"
Cohesion: 0.05
Nodes (38): ProviderCapabilities, sourceLabel(), App(), bindJob(), Bucket, chatJob(), flushMicrotasks(), HookHost() (+30 more)

### Community 20 - "Evidence API 2"
Cohesion: 0.07
Nodes (31): _CountingLinkProvider, DuplicateHandler, EvaluationEvidence, CaseContext, _context(), harness(), _Store, test_artifact_failure_propagates_and_retry_caches_handoff() (+23 more)

### Community 21 - "Alembic Migrations"
Cohesion: 0.05
Nodes (14): run_migrations_offline(), run_migrations_online(), may_retry(), Settings, create_app_engine(), engine_connect_kwargs(), EngineConnectKwargs, ReportStore (+6 more)

### Community 22 - "Frontend Estimate View"
Cohesion: 0.06
Nodes (51): fetchJob(), CatalogItem, Diet, GroceryBudget, GroceryJob, GroceryJobAck, GroceryJobCreate, GroceryJobResult (+43 more)

### Community 23 - "Shared HTTP Client and Instacart"
Cohesion: 0.07
Nodes (35): InstacartDevelopmentProvider, InstacartRejected, InstacartUncertain, _parse_create_link_response(), _parse_url(), _require_api_key(), _url_is_allowed(), validate_link_url() (+27 more)

### Community 24 - "Chat Public Answers"
Cohesion: 0.14
Nodes (48): _assert_public(), _budget_block(), _budget_trace(), _error_trace(), plan_args(), _reply(), _run(), _success_trace() (+40 more)

### Community 25 - "Chat Message Parsing (2)"
Cohesion: 0.11
Nodes (52): _as_str_map(), build_chat_result(), ChatProtocolError, _invalid(), parse_assistant_message(), parse_provider_response(), _parse_tool_use(), tool_result_block() (+44 more)

### Community 26 - "Chat History Store"
Cohesion: 0.14
Nodes (42): _assistant_turn(), _chat_context(), ChatContextUnavailable, _copy_request(), _fail(), _history(), load_chat_context(), _mapping() (+34 more)

### Community 27 - "Frontend Chat Client"
Cohesion: 0.06
Nodes (39): fetchChatJob(), submitChatJob(), body, FetchMock, queuedJob, result, succeededJob, beginDispatch() (+31 more)

### Community 28 - "Supermarket Cost Overlay"
Cohesion: 0.08
Nodes (37): _require_line_cents(), _require_notice(), _require_total_cents(), SupermarketEstimate, SupermarketLine, attach_supermarket_estimate(), estimate_supermarket_cost(), _plan_from_result() (+29 more)

### Community 29 - "Evaluation Database"
Cohesion: 0.10
Nodes (37): _cleanup(), _drop_schema(), _enable_foreign_keys(), EvaluationDatabaseError, fixture_database(), __init__(), FixtureDatabase, _validated_url() (+29 more)

### Community 30 - "Evaluation Summary Task Validation"
Cohesion: 0.16
Nodes (54): classify_slot(), _assessment(), _ExecutionStatus, _map(), _slot(), test_assessment_failure_precedes_missing_execution_evidence(), test_assessment_scope_is_exact(), test_capture_flags_at_exact_levels() (+46 more)

### Community 31 - "Evaluation Runner"
Cohesion: 0.09
Nodes (50): _as_map(), evaluate_meal_case(), _merge(), _observe(), _score(), _typed_equal(), _as_map(), _catalog() (+42 more)

### Community 32 - "Evaluation Duplicate"
Cohesion: 0.08
Nodes (33): _evaluate(), evaluate_duplicate_case(), _Services, default_adapters(), MemoryArtifacts, MemoryQueue, run_case(), schemas() (+25 more)

### Community 33 - "Evaluation Summary Task Assessments"
Cohesion: 0.11
Nodes (49): assessment_status(), _checks(), _claims(), combine_statuses(), _metric(), _status(), _assessment(), DictSubclass (+41 more)

### Community 34 - "Runtime Rules and Bedrock Access"
Cohesion: 0.06
Nodes (46): Real Bedrock via LLMProvider, PostgreSQL owns jobs and outbox state, First release scope, Eight model turns and three planner revisions, .codex/project-context.md (accepted product scope), docs/LUNA_ACCESS_REQUEST.md (unsent AWS draft), AccessDeniedException (Luna Converse denial), us.openai.gpt-6-luna (Bedrock model) (+38 more)

### Community 35 - "Accepted Project Scope"
Cohesion: 0.06
Nodes (41): Grocery bot project context, 30-scenario evaluation corpus, Evaluation targets, Evidence class separation, Plaid work is last, Forty supported meals (1-3 meals, 1-8 servings), Plaid and Instacart Repository Update Plan (Superseded), Bounded Agent State Machine (+33 more)

### Community 36 - "Recipe Catalog Domain"
Cohesion: 0.17
Nodes (45): _argument_matches(), pair(), _arguments(), _matches(), _metric(), score_tools(), _arguments(), _case() (+37 more)

### Community 37 - "Delegation Rules and Decisions 2"
Cohesion: 0.07
Nodes (38): Codex brief template stub (moved), Codex junior protocol stub (moved), Codex reviewer protocol stub (moved), feature-loop Brief Template (Redirect Stub), feature-loop Reviewer Protocol (Redirect Stub), Grocery bot agent team (.codex/TEAM.md), OpenCode fewia-workflow skill, AGENTS.md (FEWIA rules for Codex) (+30 more)

### Community 38 - "Budget Summary Tool"
Cohesion: 0.13
Nodes (35): dispatch(), _is_revision_id(), _revision_index(), arguments(), budget(), _error_trace(), _success_trace(), test_budget_summary_rejects_overrides_without_sentinel() (+27 more)

### Community 39 - "Evaluation Protocol"
Cohesion: 0.12
Nodes (34): FaultProvider, evaluate_protocol_case(), _messages(), test_expected_and_evidence_fields_do_not_control_behavior(), test_missing_content_observes_no_rejected_results(), test_only_latest_rejected_tool_results_count_per_invocation(), test_response_mutation_does_not_affect_later_envelopes(), test_source_call_sequences_preserve_counters_and_cutoff() (+26 more)

### Community 40 - "Supervisor Lease and CLI"
Cohesion: 0.10
Nodes (39): dispatch(), execute(), _file_hash(), main(), _owned_hashes(), _prompt_guard(), _record_attempt(), _shell_rule() (+31 more)

### Community 41 - "Meal Template Service"
Cohesion: 0.09
Nodes (26): suggest_plan_templates(), SuggestTemplatesBody, TemplateSuggestionsResponse, _validate_control_ids(), MealTemplateSuggestion, _normalize_control_ids(), suggest_templates(), _suggest_templates_cached() (+18 more)

### Community 42 - "Handoff Contract 2"
Cohesion: 0.11
Nodes (28): ShoppingHandoff, _aware_utc(), _canonical_json(), _db_utc(), HandoffNotFound, HandoffView, _json_copy(), _require_owner() (+20 more)

### Community 43 - "Frontend Package Manifest"
Cohesion: 0.04
Nodes (45): dependencies, @fontsource/lora, @fontsource/source-sans-3, react, react-dom, devDependencies, eslint, @eslint/js (+37 more)

### Community 44 - "Planning Tool"
Cohesion: 0.15
Nodes (37): _evidence_id(), execute_plan(), _unsupported_ingredient_field(), arguments(), _assert_static(), budget(), _converse_tool_result_params(), _expected_evidence() (+29 more)

### Community 45 - "Grocery Provider Runtime"
Cohesion: 0.14
Nodes (29): build_bedrock(), build_instacart(), build_plaid(), build_spoonacular(), capabilities(), ProviderCapabilities, GroceryProviderSettings, _clear_fewia_env() (+21 more)

### Community 46 - "Template API Tests"
Cohesion: 0.12
Nodes (26): spending_input(), PlanJobInput, SpendingInput, assert_hidden_templates_validation(), _clear_fewia_env(), commit_without_ending_the_test_transaction(), freeze_new_york_clock(), post_templates() (+18 more)

### Community 47 - "Job Worker"
Cohesion: 0.14
Nodes (28): clear_fewia(), dummy_factory(), dummy_handler(), dummy_queue(), DummySender, forbid_provider_builds(), frozen_now(), invoke_main() (+20 more)

### Community 48 - "Frontend Handoff Types"
Cohesion: 0.08
Nodes (32): abortable(), readJson(), SHAPE_ERROR, createHandoff(), fetchHandoff(), retryHandoff(), FetchMock, prepared (+24 more)

### Community 49 - "Apivalidation"
Cohesion: 0.16
Nodes (36): isBool(), isNonemptyString(), isRecord(), isSafeInteger(), isSpendingSource(), isStatus(), isString(), copyErrorDetail() (+28 more)

### Community 50 - "Bedrock Session Refresh"
Cohesion: 0.13
Nodes (28): _atomic_write(), _credential_text(), main(), _parse_expiration(), _prepare_directory(), prompt_mfa_token(), refresh_session(), _reject_symlink_ancestors() (+20 more)

### Community 51 - "Evaluation Claim Propositions"
Cohesion: 0.13
Nodes (39): ClaimParse, _clauses(), _parse_clause(), parse_public_claims(), PublicProposition, mapping(), public_tags(), test_allergy_and_cross_contact_assertions_stay_unknown() (+31 more)

### Community 52 - "Budget Summary Tool"
Cohesion: 0.10
Nodes (27): budget_summary_answer(), budget_tool_spec(), BudgetToolError, _exact_int(), execute_budget_summary(), _usd(), _validate_budget(), _validate_facts() (+19 more)

### Community 53 - "Alembic Migrations"
Cohesion: 0.08
Nodes (20): Base, DailyEnvironment, DailyFinance, DailyHealth, ModelRun, Prediction, User, PlaidItem (+12 more)

### Community 54 - "Supervisor Process and Events"
Cohesion: 0.11
Nodes (35): coverage(), fingerprint(), group_coverage(), _ledger_file(), ledger_path(), main(), parse_grok_usage(), phase_name() (+27 more)

### Community 55 - "Chat Dispatch and Provider 2"
Cohesion: 0.12
Nodes (32): sanitize_public(), copy(), redact(), scenario_markers(), ScenarioProvider, injection_case(), NoRepresentation, RecordingProvider (+24 more)

### Community 56 - "Course Proposal Concepts"
Cohesion: 0.05
Nodes (32): Knowledge-Source Ablation Study, Amazon Bedrock Reasoning Layer, Amazon SageMaker Model Hosting, Amazon Aurora PostgreSQL Structured Store, CAP 6938 Course Material (cited source), Central Research Question: Finance and Geography Predicting Health, Multi-Level Evaluation Metrics, Feature Engineering Layer (+24 more)

### Community 57 - "Evaluation Summary"
Cohesion: 0.23
Nodes (37): summarize_evaluation(), _assessment(), _groups(), _map(), _quality(), _slot(), test_actual_reference_and_plan_score_producer_integration(), test_applicable_assessment_scope_is_exact() (+29 more)

### Community 58 - "Spoonacular Cost Adapter"
Cohesion: 0.09
Nodes (18): _information_url(), _parse_estimated_cents(), _require_api_key(), SpoonacularEstimateProvider, SpoonacularUnavailable, assert_static_error(), make_provider(), test_api_key_marker_is_absent_from_exception_strings() (+10 more)

### Community 59 - "Job Consumer"
Cohesion: 0.23
Nodes (26): process_one(), body(), factory(), FakeQueue, seed_job(), stored_job(), test_ack_failure_leaves_terminal_state_for_safe_replay(), test_active_duplicate_extends_without_acknowledgment() (+18 more)

### Community 60 - "Chat Public Answers"
Cohesion: 0.11
Nodes (24): ChatUnavailable, _end_status(), run_chat(), _tool_error_payload(), _tool_use_history(), _assert_static(), budget(), FakeLLM (+16 more)

### Community 61 - "Evaluation Baseline Response"
Cohesion: 0.16
Nodes (30): BaselineResponseError, _check_public_fields(), _finite_float(), _invalid(), _json_object(), parse_baseline_response(), _reject_constant(), assert_invalid() (+22 more)

### Community 62 - "Frontend App Shell"
Cohesion: 0.09
Nodes (26): fetchConfig(), isAbortError(), submitJob(), buildRequest(), initialForm(), buttonNamed(), click(), config (+18 more)

### Community 63 - "FastAPI App and Errors"
Cohesion: 0.06
Nodes (8): healthz(), _http_error_code(), starlette_http_error_handler(), validation_error_handler(), test_disallowed_method_uses_the_api_error_envelope(), test_existing_404_and_422_responses_keep_their_bodies(), test_unknown_path_uses_the_api_error_envelope(), test_unnamed_http_status_uses_a_fallback_error_code()

### Community 64 - "Local Artifacts"
Cohesion: 0.10
Nodes (21): ArtifactPut, _encode_report(), LocalArtifactError, LocalArtifactStore, _reject_bad(), BoomS3, _canonical(), FakeS3 (+13 more)

### Community 65 - "Planning Tool and Followup Eval (part 2)"
Cohesion: 0.18
Nodes (33): build_shopping_payload(), NoShoppingItems, shopping_payload_hash(), assert_static(), bean_plan(), line_names(), line_quantities(), mutate_first_measurement() (+25 more)

### Community 66 - "Provider Settings"
Cohesion: 0.14
Nodes (26): get_provider_settings(), _plaid_is_configured(), get_provider_settings(), load_provider_settings(), ProviderConfigurationError, TokenFileResolver, _clear_fewia_env(), _static() (+18 more)

### Community 67 - "Agent Job Handlers"
Cohesion: 0.15
Nodes (22): chat_job(), chat_payload(), expected_planning(), FailLLM, FakeLLM, _patch_save(), plan_args(), _planner_then_final() (+14 more)

### Community 68 - "Evaluation Components"
Cohesion: 0.07
Nodes (32): Exclusive evaluation report completion marker, Evidence-aware cost estimation API, Evaluation guide, Deterministic structured reference API, Pure prepare_matrix API, Required sample-price estimate notice, Legacy fixture-only run_evaluation API, Evaluation summary API (+24 more)

### Community 69 - "Agent Team and Writers"
Cohesion: 0.10
Nodes (35): agent-dev Junior Developer Agent, aws-infra Junior Developer Agent, backend-dev Junior Developer Agent, catalog-dev Junior Developer Agent, database-dev Junior Developer Agent, docs-dev Junior Developer Agent, eval-engineer Junior Developer Agent, frontend-dev Junior Developer Agent (+27 more)

### Community 70 - "Evaluation Matrix"
Cohesion: 0.14
Nodes (28): EvaluationSlot, _list(), _object(), prepare_matrix(), _text(), _validate_case(), _validate_json(), _cases() (+20 more)

### Community 71 - "Plaid Sync Loading"
Cohesion: 0.26
Nodes (25): assert_utc(), clock(), factory(), load_item(), load_txn(), owned_item(), page(), postgres_plaid() (+17 more)

### Community 72 - "Evaluation Manifest"
Cohesion: 0.13
Nodes (27): build_manifest(), _canonical_json(), catalog_snapshot(), _copy_object(), _hash(), _validate_config(), _validate_json(), corpus() (+19 more)

### Community 73 - "Evaluation Cost"
Cohesion: 0.22
Nodes (32): estimate_cost(), estimate(), rates(), slot(), test_approved_decimal_syntax_and_serialized_metadata(), test_conditions_and_evidence_remain_separate(), test_deterministic_condition_alone_does_not_prove_not_applicable(), test_exact_decimal_beyond_default_precision() (+24 more)

### Community 74 - "Evaluation Markdown Format"
Cohesion: 0.11
Nodes (21): cell(), source_link(), table(), CustomInt, test_empty_table_is_valid(), test_integer_cells_preserve_256_character_values(), test_integer_cells_reject_257_character_values(), test_integer_conversion_failure_has_a_static_error() (+13 more)

### Community 75 - "Evaluation Refresh"
Cohesion: 0.14
Nodes (19): evaluate_refresh_case(), FakeUnavailableSyncProvider, RefreshFixture, _run(), _snapshot(), _case(), _map(), test_expected_poison_cannot_change_execution() (+11 more)

### Community 76 - "Plaid Http"
Cohesion: 0.12
Nodes (23): PlaidSandboxProvider, assert_static_error(), make_provider(), request_payload(), resolve(), test_access_token_is_resolved_only_at_request_time(), test_blank_credentials_are_rejected_without_echo(), test_cursor_is_sent_only_when_provided() (+15 more)

### Community 77 - "Planning Tool and Followup Eval"
Cohesion: 0.20
Nodes (23): ExclusionConflict, plan_groceries(), PlanEstimate, PlanningError, ShoppingLine, _validate_budget(), _validate_ids(), budget() (+15 more)

### Community 78 - "Supervisor Lease and CLI 2"
Cohesion: 0.15
Nodes (23): _git_setup(), _main_argv(), setup(), _state_dir(), _supervisor_paths(), test_attempt_writes_grok_usage_on_end(), test_attempt_writes_usage_on_completed(), test_attempt_writes_usage_on_stop() (+15 more)

### Community 79 - "Recipe Catalog Domain"
Cohesion: 0.09
Nodes (14): Ingredient, _load_recipes(), _parse_recipe_record(), Recipe, _plan_budget(), _plan_request(), test_all_recipes_plan_labeled_integer_estimates_for_serving_bounds(), test_ingredient_keys_match_ids() (+6 more)

### Community 80 - "Evaluation Refresh Fixture"
Cohesion: 0.12
Nodes (22): _clock(), fixture(), _period(), _transaction(), case(), database_url(), observed(), _forbid_database() (+14 more)

### Community 81 - "Database Session and Job Models"
Cohesion: 0.19
Nodes (17): PublicationError, publish_pending(), count_rows(), factory(), outbox_engine(), outbox_marker(), RecordingSender, seed_outbox() (+9 more)

### Community 82 - "Evaluation Summary Task"
Cohesion: 0.25
Nodes (29): summarize_tasks(), _map(), _quality(), _slot(), test_capture_flags_require_exact_booleans(), test_completed_execution_does_not_imply_quality(), test_conservative_rate_uses_literal_applicable_denominator(), test_distinct_case_identities_are_allowed() (+21 more)

### Community 83 - "Usda Refresh"
Cohesion: 0.13
Nodes (20): compare(), fetch_facts(), _load_api_key(), main(), _parse_facts(), _fetch_payload(), test_compare_reports_diff_unavailable_and_skips_match(), test_compare_reports_unavailable_when_fetched_key_absent() (+12 more)

### Community 84 - "Evidence API 2"
Cohesion: 0.15
Nodes (16): accepted_planning(), assert_not_found(), assert_secret_absent(), _clear_fewia_env(), client(), evidence_inputs(), factory(), forbid_provider() (+8 more)

### Community 85 - "Chat Public Answers"
Cohesion: 0.14
Nodes (26): _examples_question(), _exclusion_answer(), _input_clarification(), _over_budget_line(), _plan_answer(), render_public_answer(), _unsupported_answer(), _usd() (+18 more)

### Community 86 - "Grocery Job API (2)"
Cohesion: 0.15
Nodes (20): CatalogRef, CreateGroceryJobBody, GroceryConfig, GroceryJobAccepted, GroceryJobView, PlanJobView, test_caller_fields_match_stored_payload_not_spending(), test_catalog_ref_fields_exclude_price() (+12 more)

### Community 87 - "Bedrock Provider"
Cohesion: 0.22
Nodes (23): FakeClient, FakeSession, install_session(), provider(), response(), test_accepts_supported_stop_reasons(), test_forwards_profile_without_dummy_credentials(), test_forwards_shape_and_omits_empty_tools() (+15 more)

### Community 88 - "Recipe Catalog Domain"
Cohesion: 0.26
Nodes (28): as_bool(), as_int(), as_list(), as_object(), as_str(), call_names(), load_corpus(), recipe_ids_from() (+20 more)

### Community 89 - "Evaluation Handoff"
Cohesion: 0.15
Nodes (19): _checks(), evaluate_handoff_case(), _execute(), FakeUncertainHandoffProvider, _snapshot(), _validate(), case(), _map() (+11 more)

### Community 90 - "Evaluation Inputs"
Cohesion: 0.25
Nodes (26): _copy_inputs(), EvaluationInputError, prepare_case(), _text(), _case(), _corpus_cases(), _inputs(), test_context_period_matches_spending_period() (+18 more)

### Community 91 - "Floci Bootstrap"
Cohesion: 0.12
Nodes (13): FakeS3, FakeSession, FakeSqs, test_bootstrap_constructs_an_explicit_dummy_session(), test_bootstrap_creates_resources_and_redrive_policies(), test_bootstrap_is_idempotent_with_existing_bucket_and_queues(), test_bootstrap_propagates_unowned_bucket_errors(), test_bootstrap_rejects_non_local_endpoint_before_client_creation() (+5 more)

### Community 92 - "Planning Tool (2)"
Cohesion: 0.22
Nodes (20): JobFailure, _is_revision_id(), plan_job(), _utc_now(), expected_plan(), payload(), test_plan_job_callback_failure_does_not_return(), test_plan_job_exclusion_raises_job_failure() (+12 more)

### Community 93 - "Chat Context Builder"
Cohesion: 0.17
Nodes (20): read_usage(), _sum_usage(), _assert_static(), budget(), _context(), _converse_params(), pair(), previous() (+12 more)

### Community 94 - "Chat Context Builder 3"
Cohesion: 0.21
Nodes (23): BudgetResult, _as_map(), evaluate_budget_case(), _merge(), _observe(), _score(), _typed_equal(), _blob() (+15 more)

### Community 95 - "Evaluation Plan Schema"
Cohesion: 0.23
Nodes (23): ObservedBudget, ObservedPlan, parse_plan_observation(), PlanLine, PlanObservation, _line(), observation(), _section() (+15 more)

### Community 96 - "Plaid Contract"
Cohesion: 0.22
Nodes (21): _amount_cents(), _boolean(), _invalid(), InvalidPlaidResponse, _list(), _object(), parse_sync_page(), _string() (+13 more)

### Community 97 - "Job Heartbeat and Delivery"
Cohesion: 0.16
Nodes (14): Heartbeat, LeaseLost, RetryableJobError, _alive_heartbeats(), test_background_renews_several_times_while_handler_runs(), test_handler_error_is_preserved_when_the_lease_is_held(), test_initial_failure_does_not_start_a_thread(), test_interval_must_be_finite_and_positive() (+6 more)

### Community 98 - "Job Recovery"
Cohesion: 0.24
Nodes (16): load_job(), load_outbox(), recovery_engine(), recovery_factory(), seed_job(), test_active_and_terminal_jobs_are_untouched(), test_classifier_exception_rolls_back_all_recovery_changes(), test_final_attempt_crash_fails_without_classifier() (+8 more)

### Community 99 - "Agent Job Handlers"
Cohesion: 0.23
Nodes (15): make_agent_handler(), count_rows(), evidence_engine(), factory(), freeze_clocks(), seed_user(), stored_job(), submit_agent_job() (+7 more)

### Community 100 - "Meal Nutrition Tests"
Cohesion: 0.18
Nodes (21): _as_list(), _assume_statements(), _identity_statements(), _role_tags(), _split_identity(), _stack(), _statements_from(), _tag_mapping() (+13 more)

### Community 101 - "Recipe Catalog Domain 2"
Cohesion: 0.14
Nodes (15): GroceryRequest, MealRequest, request(), test_meal_request_rejects_non_strict_servings(), test_plan_cap_requires_a_nonnegative_strict_integer(), test_request_accepts_supported_bounds_and_defaults(), test_request_limits_meal_count(), test_request_rejects_a_client_user_id_and_other_extras() (+7 more)

### Community 102 - "Database Session and Job Models"
Cohesion: 0.23
Nodes (17): Job, JobOutbox, job_engine(), job_session(), seed_user(), test_foreign_keys_reject_orphan_jobs_and_outbox_rows(), test_invalid_job_kind_is_rejected(), test_invalid_job_status_is_rejected() (+9 more)

### Community 103 - "Local Sqs Consumer"
Cohesion: 0.26
Nodes (16): LocalSqsConsumer, QueueMessage, _patch_client(), _queue_url(), test_acknowledge_deletes_with_receipt_handle(), test_disallowed_queue_url_is_rejected_before_receive(), test_empty_receipt_is_rejected_before_acknowledge_or_extend(), test_extend_accepts_visibility_bounds() (+8 more)

### Community 104 - "Frontend Estimate View"
Cohesion: 0.10
Nodes (17): SAMPLE_ESTIMATE_NOTICE, noPlanResult(), plannedResult(), Conversation(), exclusionJob, failedWithoutCode, ingredients, recipes (+9 more)

### Community 105 - "Delegation Rules and Decisions"
Cohesion: 0.11
Nodes (19): Codex loop ledger template, Codex feature-loop skill, Claude loop ledger template, Claude Code feature-loop skill, code-reviewer role (supplies review model instructions), Role routing table (15 roles), tech-lead role (Codex coordinator), no_edits writer outcome (+11 more)

### Community 106 - "Supermarket Cost Overlay (2)"
Cohesion: 0.13
Nodes (21): Docker Compose Stack, API Service, Bootstrap Service, Floci Emulator Service, PostgreSQL Service, Sync Worker Service, Web Frontend Service, Agent Worker Service (+13 more)

### Community 107 - "Evaluation Telemetry"
Cohesion: 0.33
Nodes (21): _group(), _groups(), _mapping(), _slot(), test_conditions_and_evidence_classes_stay_distinct(), test_failed_attempts_retain_calls_and_measured_elapsed(), test_failed_status_does_not_discard_known_usage(), test_huge_latency_values_do_not_produce_nonfinite_report_numbers() (+13 more)

### Community 108 - "Handoff Models"
Cohesion: 0.22
Nodes (14): add_handoff(), handoff_engine(), handoff_session(), seed_user(), test_dispatching_requires_token_and_started_at(), test_handoff_defaults_and_payload_round_trip(), test_invalid_states_are_rejected(), test_negative_attempts_are_rejected() (+6 more)

### Community 109 - "Plaid Sync Job"
Cohesion: 0.20
Nodes (12): make_sync_handler(), SyncJobInput, dummy_factory(), factory(), owned_item(), payload(), test_input_forbids_cursor_token_and_owner(), test_invalid_payload_does_not_call_provider() (+4 more)

### Community 110 - "Worker"
Cohesion: 0.13
Nodes (8): _bedrock_provider(), _default_handler(), job_replay_safe(), main(), run_worker(), _write_result(), make_job(), test_strict_replay_classification()

### Community 111 - "Shared AWS Client Config 2"
Cohesion: 0.13
Nodes (7): aws_client_config(), build_http_client(), _normalize_queue_url(), SqsClient, test_aws_client_config_local_policy(), test_aws_client_config_remote_policy(), test_build_http_client_policy()

### Community 112 - "Consume Jobs"
Cohesion: 0.19
Nodes (9): JobHandler, JobQueue, invoke(), test_empty_stops_and_consumes_only_the_agent_queue(), test_max_messages_bounds_processing(), test_max_messages_rejects_invalid_bounds(), test_operational_errors_emit_only_static_sanitized_json(), test_operational_errors_restore_signal_handlers() (+1 more)

### Community 113 - "Apifixtures"
Cohesion: 0.23
Nodes (17): NUTRITION_NOTICE, NUTRITION_PORTION_NOTICE, SPOONACULAR_COST_NOTICE, candidate(), expectShapeError(), noPlan(), request(), trace() (+9 more)

### Community 114 - "Runtime Rules and Bedrock Access"
Cohesion: 0.13
Nodes (16): Retired health-prediction scope, Deterministic Model Tool Dispatch (chat_dispatch), Deterministic Integer-Cent Grocery Budget, Deterministic meal planner, Evaluation runner stack, Decision 0007: Evidence ID Format (build_evidence_id), exclusion_reject tool error, Medium backlog loop (+8 more)

### Community 115 - "Database Session and Job Models 3"
Cohesion: 0.22
Nodes (11): get_session(), client(), commit_without_ending_the_test_transaction(), fake_settings(), forbid_provider_io(), owned_item(), post_job(), test_disabled_configuration_returns_static_503() (+3 more)

### Community 116 - "Plaid Sync Job"
Cohesion: 0.19
Nodes (8): _mutation_error(), _parse_success(), PlaidNotReady, PlaidSyncMutation, PlaidUnavailable, _raise_failure(), _reject_incomplete_update(), _require_nonblank()

### Community 117 - "Plaid Sync"
Cohesion: 0.18
Nodes (9): SyncPage, _apply_pages(), _aware_utc(), _collect_pages(), _require_int(), _row(), sync_item(), SyncProvider (+1 more)

### Community 118 - "Evidence API"
Cohesion: 0.24
Nodes (12): canonical_json(), EvidenceInputs, _json_object(), _normalize(), normalize_snapshot(), _reject_bad(), _evidence_id(), EvidenceConflict (+4 more)

### Community 119 - "Meal Nutrition Tests 2"
Cohesion: 0.27
Nodes (16): facts(), grocery_request(), test_all_supported_recipes_are_available(), test_each_portions_use_grams_not_counts(), test_energy_is_not_derived_from_macro_formula(), test_hand_calculated_custom_fixture_macros(), test_invalid_or_missing_portions_are_unavailable(), test_missing_facts_are_unavailable() (+8 more)

### Community 120 - "Frontend App Shell 2"
Cohesion: 0.12
Nodes (10): AppUnresolvedHost(), ChatHook, demoConfig, demoState(), HandoffHook, handoffState(), instacartProviders(), providersReady (+2 more)

### Community 121 - "Chat Refusal Parser"
Cohesion: 0.19
Nodes (13): _one_pair(), parse_refusal(), _reject_constant(), _RaisingLenStr, test_parse_refusal_accepts_exact_reasons(), test_parse_refusal_does_not_echo_raw_text(), test_parse_refusal_rejects_deeply_nested_malformed_input(), test_parse_refusal_rejects_empty_object() (+5 more)

### Community 122 - "Provider Settings 2"
Cohesion: 0.16
Nodes (3): _cost(), _count(), EvaluationRates

### Community 123 - "Provider Settings 2"
Cohesion: 0.24
Nodes (17): parse_rates(), rates(), test_decimal_notation_preserves_value(), test_direct_model_validation_rejects_numeric_rates(), test_extra_fields_fail_with_static_error(), test_fixture_preserves_exact_decimals(), test_invalid_dates_fail(), test_invalid_metadata_fails() (+9 more)

### Community 124 - "Evidence API"
Cohesion: 0.27
Nodes (10): assert_static_404(), client(), count_rows(), evidence_engine(), factory(), save_owned(), seed_users(), test_foreign_missing_and_malformed_use_static_404() (+2 more)

### Community 125 - "Evaluation Runner 2"
Cohesion: 0.29
Nodes (15): _as_map(), evaluate_followup_case(), _gold(), _observe(), _score(), _typed_equal(), _followup_case(), _mapping() (+7 more)

### Community 126 - "USDA and Spoonacular Decisions (2)"
Cohesion: 0.13
Nodes (15): api service, AWS_SHARED_CREDENTIALS_FILE /run/fewia/aws-credentials, FEWIA_BEDROCK_CREDENTIALS_FILE, worker service, x-bedrock Compose overlay, compose.bedrock.yaml override, Grocery Bedrock provider, ~/.config/fewia/bedrock/credentials (+7 more)

### Community 127 - "USDA and Spoonacular Decisions"
Cohesion: 0.14
Nodes (14): USDA Foundation oat milk (FDC 2257046), Ingredient nutrition catalog (per 100 g), Ingredient preparation states, USDA SR Legacy CSV dataset, USDA FoodData Central, Decision 0008 grocery bot pivot, Decision 0010 Park Instacart USDA Spoonacular, FEWIA_SPOONACULAR_KEY_FILE (+6 more)

### Community 128 - "Frontend Chat Client"
Cohesion: 0.14
Nodes (11): bindJob(), budget, flushMicrotasks(), HookValue, JobMocks, mount(), resultOf(), retryAndSettle() (+3 more)

### Community 129 - "Project Plan"
Cohesion: 0.11
Nodes (18): project-plan.md (FEWIA Project Plan), aws-infra agent, backend-dev agent, frontend-dev agent, /graphify knowledge-graph tool, ml-dev agent, Phase 0 — Repo bootstrap and the agent team, Phase 1 — Skeleton: Compose, schema, CI (+10 more)

### Community 130 - "Sync Api Models"
Cohesion: 0.22
Nodes (8): CreateSyncJobBody, test_caller_fields_match_stored_sync_payload(), test_create_body_accepts_item_id(), test_create_body_enforces_item_id_length(), test_create_body_preserves_item_id_text(), test_create_body_rejects_blank_item_id(), test_create_body_rejects_forbidden_fields(), valid_body()

### Community 131 - "Meal Nutrition Tests"
Cohesion: 0.22
Nodes (9): _item(), nutrition_for_plan(), PlanNutrition, PlanNutritionItem, make_plan(), shopping_line(), test_empty_lines_yield_empty_items(), test_known_ingredients_copy_facts_and_leave_plan_total() (+1 more)

### Community 132 - "Evaluation Runner 3"
Cohesion: 0.29
Nodes (13): fixture_plan(), _meal_requests(), _assert_static_clock_error(), _inputs(), _mapping(), _meal_cases(), test_empty_meals_raises_without_calling_planner(), test_m01_plan_matches_gold() (+5 more)

### Community 133 - "Database Session and Job Models"
Cohesion: 0.26
Nodes (7): _aware_utc(), _bound_int(), claim_job(), finish_job(), renew_lease(), test_concurrent_claims_one_winner_and_stale_token_fencing(), Job Leases (claim_job, renew_lease, finish_job)

### Community 134 - "Meal Nutrition Tests 3"
Cohesion: 0.21
Nodes (10): _as_int(), _facts_from_row(), _grams_to_mg(), _ingredient_rows(), _load_usda_macros(), test_catalog_matches_usda_macros_fixture(), test_catalog_uses_verified_ingredient_identities(), test_energy_nutrient_ids_match_source_dataset() (+2 more)

### Community 135 - "Consume Jobs (2)"
Cohesion: 0.15
Nodes (3): _bounded_count(), main(), _write_result()

### Community 136 - "Supervisor Events and Process 3"
Cohesion: 0.23
Nodes (13): Events, test_completed_question_does_not_wait(), test_embedded_grok_permission_code(), test_feed_grok_end_records_tokens(), test_feed_grok_usage_event_adds_nothing(), test_observed_grok_tool_lifecycle(), test_pending_question_waits_until_cleared(), test_permission_and_untrusted_text() (+5 more)

### Community 137 - "Budget Summary Tool"
Cohesion: 0.23
Nodes (11): PlanningToolError, test_budget_summary_dispatch_passes_only_server_facts(), test_exclusion_reject_with_invalid_detail_returns_invalid_args(), fake_execute(), fake_execute(), test_other_planning_tool_error_returns_invalid_args(), fake_execute(), fake_execute_none() (+3 more)

### Community 138 - "Meal Nutrition Tests"
Cohesion: 0.21
Nodes (5): _require_non_negative_int(), _require_positive_int(), main(), BedrockChatStack, _context_str()

### Community 139 - "Chat Context Builder 2"
Cohesion: 0.27
Nodes (11): _cents(), fixture_budget(), _parse_date(), _assert_static_clock_error(), _budget_cases(), _inputs(), _mapping(), test_fixture_budget_matches_gold_cents() (+3 more)

### Community 140 - "Handoff Contract"
Cohesion: 0.25
Nodes (10): is_handoff_unique_conflict(), _Diag, _PgError, _SqliteError, test_pg_unique_pgcode_and_constraint(), test_pg_unique_sqlstate_and_constraint(), test_pg_unique_wrong_constraint_is_false(), test_raw_integrity_error_sentinel_is_not_unique() (+2 more)

### Community 141 - "Handoff (2)"
Cohesion: 0.27
Nodes (9): CreateHandoffBody, PlanLine, RetryHandoffBody, SnapshotPlan, snapshot_values(), test_create_body_accepts_job_id_and_forbids_extra(), test_plan_line_forbids_extra_and_non_strict_values(), test_retry_body_requires_positive_strict_attempt() (+1 more)

### Community 142 - "Alembic Migrations"
Cohesion: 0.22
Nodes (9): GroceryEvidence, load_revision_0007(), test_create_table_sql_compiles_for_postgresql(), test_grocery_evidence_columns_nullability_and_defaults(), test_grocery_evidence_is_registered_on_base_metadata(), test_grocery_evidence_pk_fk_and_id_check(), test_migration_0007_rejects_downgrade(), test_migration_0007_upgrade_sql_compiles_for_postgresql() (+1 more)

### Community 143 - "Bedrock Provider"
Cohesion: 0.22
Nodes (8): BedrockClient, BedrockConverseProvider, ConverseRequest, _is_luna_us_model(), _is_nova2_us_model(), _is_us_profile(), _valid_content(), _valid_message()

### Community 144 - "Alembic Migrations 2"
Cohesion: 0.24
Nodes (7): _integral_cents(), load_spending(), _month_end(), _require_period(), _require_user_id(), SpendingUnavailable, _stored_utc()

### Community 145 - "Supervisor Lease and CLI"
Cohesion: 0.35
Nodes (12): _reap(), run(), test_active_tool_cannot_be_declared_stalled(), test_child_is_stopped_before_return(), test_confirmed_stall(), test_launching_marker_before_popen(), test_missing_and_failed(), test_non_main_thread_attempt_still_stops_child() (+4 more)

### Community 146 - "Phase 2"
Cohesion: 0.15
Nodes (4): Evidence ID format, Historical phase 1 skeleton, Historical phase 2 synthetic data, Historical phase 3 deterministic context tools

### Community 147 - "Tool Evidence IDs"
Cohesion: 0.23
Nodes (5): build_evidence_id(), _build_evidence_span(), test_evidence_id_uses_day_form_for_a_partial_month(), test_evidence_id_uses_day_form_for_any_other_range(), test_evidence_id_uses_month_form_for_a_whole_month()

### Community 148 - "Accepted Project Scope"
Cohesion: 0.17
Nodes (11): Sample-price estimate notice, CI Workflow, Backend Checks Job, Compose Config Job, Frontend Checks Job, .github/workflows/tooling.yml — Tooling workflow, Bedrock CDK checks job (infra/bedrock ruff, mypy, pytest), Tooling checks job (lint/type/test dev_supervisor, infra) (+3 more)

### Community 149 - "FastAPI App and Errors"
Cohesion: 0.26
Nodes (5): get_session_factory(), GroceryEvidenceView, _is_revision_id(), _not_found(), read_grocery_evidence()

### Community 150 - "Local Sqs"
Cohesion: 0.24
Nodes (5): LocalSqsSender, main(), test_invalid_endpoint_is_rejected_before_session_creation(), test_invalid_kind_is_rejected_before_queue_network_calls(), test_send_routes_kind_and_sends_only_the_job_id()

### Community 151 - "Job Delivery"
Cohesion: 0.29
Nodes (8): _job_id(), _json_object(), _object_without_duplicates(), test_job_id_enforces_the_bounded_envelope_length(), test_job_id_rejects_duplicate_keys(), test_job_id_requires_a_canonical_uuid(), test_json_object_rejects_non_json_objects(), test_json_object_returns_a_deep_copy()

### Community 152 - "Supervisor Lease and CLI"
Cohesion: 0.41
Nodes (8): lease(), occupied(), _lock(), test_ambiguous_launch_state_blocks(), test_lease_refuses_second_owner(), test_missing_status_blocks(), test_orphan_group_blocks_new_writer(), test_stopped_status_allows_new_lease()

### Community 153 - "Ci Components"
Cohesion: 0.21
Nodes (12): Database validation command and URL requirements, Backend lint, format, type, migration, and test gates, Backend checks job, Compose configuration validation, Compose config job, DATABASE_URL, FEWIA_JOB_TEST_DATABASE_URL, and FEWIA_EVALUATION_DATABASE_URL use fewia_eval with FEWIA_REQUIRE_DB=1, fewia_eval CI test database, Frontend lint, test, and build gates (+4 more)

### Community 154 - "Chat Context Builder"
Cohesion: 0.31
Nodes (7): _budget_ok(), build_messages(), _exact_int(), _history(), _plan_cap_ok(), _previous(), _public_text()

### Community 155 - "Sync Route and Dependencies"
Cohesion: 0.22
Nodes (5): get_supermarket_estimator(), clear_estimator_override(), FixedEstimator, ForbiddenEstimator, test_get_supermarket_estimator_none_without_key_file()

### Community 156 - "Chat Context Builder 2"
Cohesion: 0.31
Nodes (8): calculate_budget(), _is_integer(), SpendingSnapshot, StaleSpendingError, _validate_aware_datetime(), _validate_integer(), _validate_nonnegative_integer(), _validate_snapshot()

### Community 157 - "Meal Nutrition Tests"
Cohesion: 0.33
Nodes (7): NutritionFacts, facts(), test_constructs_integer_nutrition_facts(), test_nutrition_facts_are_frozen(), test_rejects_negative_mass_and_energy(), test_rejects_non_positive_fdc_id(), test_zero_mass_and_energy_are_valid()

### Community 159 - "Tsconfig"
Cohesion: 0.18
Nodes (10): compilerOptions, jsx, lib, module, moduleResolution, noEmit, strict, target (+2 more)

### Community 160 - "0012 Tool Calling Orchestration"
Cohesion: 0.24
Nodes (7): planner_tool_spec(), Query: how Tool Calling changes FEWIA, Memory: accepted tool-calling orchestration direction, Read-only budget-summary tool (optional), plan_groceries tool, run_chat(), Tool-calling evaluation metrics

### Community 162 - "Evaluation Telemetry"
Cohesion: 0.44
Nodes (7): _label(), _map(), _measure(), _metric(), _number(), summarize_telemetry(), _turns()

### Community 163 - "Meal Nutrition Tests 4"
Cohesion: 0.36
Nodes (7): _grams(), _macros(), MacroTotals, meal_nutrition(), MealNutrition, MealPlanNutrition, _unavailable()

### Community 164 - "Evaluation Summary Task Validation"
Cohesion: 0.31
Nodes (5): _execution_quality(), _status(), TaskFacts, test_not_applicable_facts_are_excluded_from_rates(), classify()

### Community 165 - "Provider Settings 2"
Cohesion: 0.42
Nodes (5): _has_control(), _invalid(), _load_token_mapping(), _read_bounded_utf8(), read_secret_file()

### Community 166 - "Database Session and Job Models"
Cohesion: 0.33
Nodes (3): _aware_utc(), _bound_int(), recover_jobs()

### Community 168 - "Supervisor Events and Process 3"
Cohesion: 0.28
Nodes (5): attempt(), snapshot(), publish(), stop(), _write_usage()

### Community 169 - "Cap6938 August 25"
Cohesion: 0.25
Nodes (6): Course deliverables (8-page paper, GitHub, demo video), Scientific research track, System Implementation Track, Evaluation plan and measurement layers, LLMProvider provider interface, Local architecture flow

### Community 170 - "Evaluation-Publication Components"
Cohesion: 0.25
Nodes (7): Evaluation Publication Log Snapshot 8dfdb50f, Evaluation Draft Publication Snapshot 2026-10-03, Graphify Snapshot for Source 8dfdb50f, Held Draft Pull Requests 288 to 290, Integrated Local Gate Snapshot 8dfdb50f, Proposed Pull Request Merge Order, Remote CI Snapshot 2026-10-03 07:27

### Community 171 - "Delegation Rules and Decisions 2"
Cohesion: 0.29
Nodes (7): Backend gates: ruff, ruff format, mypy --strict, pytest, dev_supervisor.gates (path-selected checks recorded by SHA), dev_supervisor.review (read-only time-capped review, exit 0/1/2), dev_supervisor.usage (token and time ledger), Review model (independent read-only Codex, Grok fallback), Delegation loop (intake, probe, design, approve, dispatch, review, verify, repair, publish), Tier L coordinator probes and mutation checks

### Community 172 - "Chat Public Answers"
Cohesion: 0.25
Nodes (6): planner_tool_spec(), _chat_tools(), test_pantry_owned_ingredient_request_stays_planner_capable(), test_planner_then_final_keeps_evidence_and_usage(), _usd(), _validate_converse()

### Community 173 - "Cap6938 August 25 2"
Cohesion: 0.25
Nodes (5): Eight course topics, External knowledge base, Knowledge graph topic, Parametric knowledge, EvoGraph-R1

### Community 174 - "Cap6938 Mvp Project Plan"
Cohesion: 0.29
Nodes (6): Bedrock agent design with client-side tool use, Three-feature-set experiment (A/B/C), Baseline models and metrics, Privacy, security, and responsible-use caveats, FEWIA project objective, run_activity_prediction tool

### Community 176 - "Cap6938 Mvp Project Plan 2"
Cohesion: 0.29
Nodes (7): daily_environment table, Environmental API integration, get_environment_context tool, get_environment_features provider function, model_runs table, PostgreSQL relational schema, predictions table

### Community 180 - "Cap6938 Mvp Project Plan 3"
Cohesion: 0.33
Nodes (4): AWS migration mapping, daily_health table, get_health_context tool, Synthetic data strategy

### Community 182 - "Cap6938 Mvp Project Plan 4"
Cohesion: 0.40
Nodes (4): daily_finance table, Garmin integration behind a health adapter, get_financial_context tool, Plaid integration behind a finance adapter

### Community 185 - "Grocery Build Progress"
Cohesion: 0.40
Nodes (5): .codex/project-context.md active scope, Grocery build progress, Professor feedback checkpoint, Remaining delivery sequence, Reviewed local slices table

### Community 187 - "Cap6938 Mvp Project Plan 5"
Cohesion: 0.50
Nodes (4): compare_periods tool, Evidence ID, First working demo (POST /agent/analyze), MVP-complete checkpoint

### Community 188 - "Audit"
Cohesion: 0.50
Nodes (4): .github/dependabot.yml — dependency update configuration, .github/workflows/audit.yml — Audit workflow, npm dependency audit job (npm audit --audit-level=high), Python dependency audit job (pip-audit via uv export)

### Community 198 - "Chat Public Answers"
Cohesion: 0.67
Nodes (3): previous(), test_followup_history_and_previous_request_are_context_only(), test_followup_provider_receives_cap_and_latest_pantry_context()

### Community 202 - "Catalog Dev"
Cohesion: 0.67
Nodes (3): catalog-dev OpenCode adapter, eval-engineer OpenCode adapter, ml-dev OpenCode adapter (compatibility role)

## Ambiguous Edges - Review These
- `ChatWorkspace()` → `ChatWorkspace and ChatPanel Beside Manual Planner`  [AMBIGUOUS]
  wiki/phases/grocery-mvp-checkpoint.md · relation: references
- `Manual Spending Source (User-Entered Budget)` → `Tech-Debt Audit Phases 1-4`  [AMBIGUOUS]
  wiki/log.md · relation: conceptually_related_to
- `First release scope` → `Parked Instacart handoff`  [AMBIGUOUS]
  .codex/project-context.md · relation: conceptually_related_to
- `Directional comparison evidence ID` → `Historical symmetric comparison open item`  [AMBIGUOUS]
  wiki/phases/phase-3.md · relation: conceptually_related_to
- `Codex feature-loop skill` → `Decision 0015: Writer routing by difficulty`  [AMBIGUOUS]
  .agents/skills/feature-loop/SKILL.md · relation: conceptually_related_to

## Knowledge Gaps
- **308 isolated node(s):** `DictSubclass`, `FetchMock`, `Props`, `FormSetter`, `Mounted` (+303 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1470 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **142 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `ChatWorkspace()` and `ChatWorkspace and ChatPanel Beside Manual Planner`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `Manual Spending Source (User-Entered Budget)` and `Tech-Debt Audit Phases 1-4`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `First release scope` and `Parked Instacart handoff`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Directional comparison evidence ID` and `Historical symmetric comparison open item`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Codex feature-loop skill` and `Decision 0015: Writer routing by difficulty`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `POST /grocery/templates meal suggestions` connect `Accepted Project Scope` to `Delegation Rules and Decisions 2`, `Budget Form`, `Chat Dispatch and Routes`?**
  _High betweenness centrality (0.220) - this node is a cross-community bridge._
- **Why does `0017 Forty-meal sample catalog` connect `Accepted Project Scope` to `Runtime Rules and Bedrock Access`, `Delegation Rules and Decisions 2`, `Chat Dispatch and Routes`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._