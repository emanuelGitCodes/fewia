# Course methods in FEWIA

This map links each CAP 6938 topic to the FEWIA code and evidence that use it.
The agent-track rubric gives 20% to the use of course learning.
The map is a reference for the paper and the demo. It is not paper text.
The author writes the paper and chooses which rows to cite.

Each row has one label:

| Label | Meaning |
|---|---|
| Direct | FEWIA runs the course method as the lecture defines it. |
| Adapted | FEWIA uses the idea of the method in a simpler form. The row names the difference. |
| Not used | FEWIA does not use the method. |
| Not yet recorded | FEWIA has the data for the method, but no record computes it yet. |

Lecture citations give the lecture number and the slide title.
The topic numbers follow the course map in Lecture 01, *Course map*.

## Summary

| Topic | Lectures | Status in FEWIA |
|---|---|---|
| 1. Dense representation | L02–L04 | Not used |
| 2. Knowledge graphs | L05–L06 | Not used |
| 3. Symbolic and neuro-symbolic reasoning | L07 | Adapted |
| 4. Retrieval | L08–L10 | Direct for BM25 ranking; Adapted for the metrics, on a biased proxy; other methods not used |
| 5. Retrieval-augmented generation | L11–L12 | Adapted |
| 6. Recommendation systems | L13–L14 | Not used |
| 7. AI agents | L15–L16 | Direct for function calling; Adapted for ReAct, the policy, scoring, history, clarification, and memory; pass^k not yet recorded; multi-agent systems not used |
| 8. Knowledge updating | L11 and the Topic 8 lectures | Adapted for external knowledge; model editing not used |

## Topic 7: AI agents

| Course method | FEWIA component | Evidence | Label |
|---|---|---|---|
| L15, *Function Calling and the Model Context Protocol* | [`chat_tool_specs`](../../backend/app/agent/chat_loop.py) gives the model up to nine named tools with fixed argument schemas. | Oct 5 batch: 36 of 36 tool calls had a valid shape. See [evidence tables, section 3a](EVIDENCE_TABLES.md). | Direct for function calling. FEWIA has no Model Context Protocol server. |
| L15, *ReAct: Interleaving Reasoning and Acting* | [`run_chat`](../../backend/app/agent/chat_loop.py) alternates model turns and tool results. `MAX_MODEL_TURNS` is 8. `MAX_PLANNER_REVISIONS` is 3. | Source inspection. The Oct 5 call-shape count measures arguments, not the interleaving. | Adapted. FEWIA uses native tool calls. It records no explicit thought traces. |
| L15, *BFCL: Scoring Function Calls from Single Turns to Agents* | The benchmark scores each call for shape, selection, arguments, and unnecessary calls. | Oct 5 batch: selection 18 of 21 calls, arguments 16 of 21 calls. See [evidence tables, section 3a](EVIDENCE_TABLES.md). | Adapted. FEWIA runs its own benchmark with the BFCL scoring layers. It does not run BFCL. |
| L15, *τ-bench: Agents That Serve Users Under a Policy* | The agent works under a fixed policy: no checkout, no payment, and no plan change without a user Apply. [`_validate_apply`](../../backend/app/api/proposals.py) checks the cap, pantry, and diet again before it saves. | [`conversation-20261107/report.json`](../../eval/results/artifacts/conversation-20261107/report.json): 0 purchase attempts in 111 turns; 13 of 15 purchase requests refused. That refusal rate, 0.8667, fails its 0.99 target. [Workflow record](../../eval/results/artifacts/main-workflow-f0f7b7d8/report.md): Apply rejected USD 17.03 against a USD 17.02 cap. | Adapted. FEWIA has no simulated user. |
| L15, *τ-bench: Measuring Agent Reliability* (pass^k) | The benchmark runs each case three times. | No record computes pass^k. See [gaps](#gaps-the-existing-records-can-close). | Not yet recorded |
| L15, *The Complexity Trap: Masking vs Summarizing Agent History* | [`chat_history.py`](../../backend/app/services/chat_history.py) keeps the last `MAX_HISTORY` = 8 messages. [`chat_context.py`](../../backend/app/agent/chat_context.py) rejects a longer history. FEWIA carries the earlier plan as structured state (`previous_request`), not as a long transcript. | Source inspection only. | Adapted. FEWIA truncates. It does not summarize. |
| L16, *Lost in Conversation: Multi-Turn Underspecification* | The agent asks a question when a request lacks a needed fact. [`chat_answer.py`](../../backend/app/agent/chat_answer.py) maps input errors to clarification replies. | Oct 5 batch: 6 of 6 assessed clarification slots passed; 3 slots were not assessed. See [evidence tables, section 3a](EVIDENCE_TABLES.md). | Adapted. FEWIA asks for a missing fact. It does not measure loss across turns. |
| L16, *MemGPT* and *Mem0* (agent memory) | Saved plan revisions in PostgreSQL ([`plan_revision.py`](../../backend/app/domain/plan_revision.py)) persist across turns. The `get_plan` tool reads the current saved plan. The agent cannot read earlier revisions. | Source inspection only. | Adapted. FEWIA stores one current plan, not extracted memories. |
| L16, multi-agent systems | Not used in the product. The writer and reviewer agents in the repository build the code. They are not part of FEWIA. | — | Not used |

## Topic 4: Retrieval

| Course method | FEWIA component | Evidence | Label |
|---|---|---|---|
| L08, *BM25* | [`meal_search_rank.py`](../../backend/app/agent/meal_search_rank.py) ranks catalog meals with Okapi BM25, `K1` = 1.2 and `B` = 0.75. The `search_meals` tool uses this order. | See the next row. | Direct |
| L08, *Recall@k, MRR@10, nDCG@10* | [`evaluation_retrieval.py`](../../backend/app/evaluation_retrieval.py) scores recall at rank 3 and MRR with no rank cutoff on 15 queries in [`retrieval_queries.json`](../../backend/tests/evaluation/retrieval_queries.json). | [EVALUATION.md](../EVALUATION.md), retrieval check: BM25 gives MRR 1.0 and recall at rank 3 of 0.6836. Catalog order gives 0.9222 and 0.6479. The reproduce command below prints each pair. That section states that this proxy "MUST NOT be presented as proof of better retrieval." | Adapted. FEWIA computes recall at rank 3 and MRR with no cutoff. nDCG is not computed. Relevance comes from a biased proxy. |
| L08–L10 dense retrieval, ANN indexes, ColBERT, rerankers | Not used. The catalog holds 40 meals. | — | Not used |

Reproduce the retrieval check from `backend/` with no model call:

```bash
uv run python -m app.evaluation_retrieval --queries tests/evaluation/retrieval_queries.json --output /tmp/retrieval-$(date +%s).json
```

## Topic 5: Retrieval-augmented generation

| Course method | FEWIA component | Evidence | Label |
|---|---|---|---|
| L11, *Parametric Limits on Long-Tail Facts* | Exact basket costs come from tool results, not from model weights. | [Planning ablation](../../eval/results/artifacts/openai-luna-20261107/planning-ablation/report.md), GPT-6 Luna, 36 trials per condition: all checks passed in 36 trials with tools and 9 without. The basket cost was correct in 36 and 9. | Adapted. The tools compute facts. They do not retrieve passages. |
| L12, *Corrective RAG (CRAG): Retrieval Evaluation and Fallback* | [`grounding.py`](../../backend/app/agent/grounding.py) checks each number in model prose against tool results and returns a verdict. On a failed check, [`run_chat`](../../backend/app/agent/chat_loop.py) replaces the prose with a fixed server reply. | [`conversation-20261107/report.json`](../../eval/results/artifacts/conversation-20261107/report.json): 1 of 32 prose attempts was grounded (rate 0.0312). The validator fallback ran 31 times. 105 unsupported numbers were found. | Adapted. FEWIA checks the answer, not the retrieved documents. |
| L11, *CRAG Benchmark: Penalizing Hallucinations and False Premises* | This benchmark scores a wrong answer below no answer. The grounding fallback follows the same rule: a fixed reply replaces an unsupported number. | Same record as the row above. | Adapted. FEWIA applies the rule to its own replies. It does not run the CRAG benchmark. |
| L11, *RAGChecker: Claim-Level Diagnostic Framework* | The benchmark checks each public claim against the tool results. | Oct 5 batch: 109 of 112 claims supported. See [evidence tables, section 3a](EVIDENCE_TABLES.md). | Adapted. The check covers bounded public claims. |

L11 and L12 both use the name CRAG. In L11, CRAG is the Comprehensive RAG Benchmark. In L12, CRAG is Corrective RAG.

## Topic 3: Symbolic and neuro-symbolic reasoning

| Course method | FEWIA component | Evidence | Label |
|---|---|---|---|
| L07, symbolic rules beside a neural model | The language model proposes. Deterministic rules decide: [`budget.py`](../../backend/app/domain/budget.py) does integer-cent arithmetic, [`grocery.py`](../../backend/app/domain/grocery.py) plans and checks diet and pantry, and [`plan_proposal.py`](../../backend/app/domain/plan_proposal.py) applies a change only under its constraints. | Planning ablation above. Oct 3 batch: 0 constraint violations in 6 accepted plans. See [evidence tables](EVIDENCE_TABLES.md). | Adapted. The rules are hand-written code, not a logic engine or learned rules. |
| L07 knowledge compilation, differentiable rules, rule mining | Not used. | — | Not used |

## Topic 8: Knowledge updating

| Course method | FEWIA component | Evidence | Label |
|---|---|---|---|
| L11, *Non-Parametric Memory Updates and Capacity Limits* | Knowledge lives outside the model and changes without retraining: the versioned catalog `sample-prices-v2`, USDA FoodData Central facts, and the optional Kroger price read at request time. | [Decision 0017](../../wiki/decisions/0017-forty-meal-catalog.md), [nutrition sources](../nutrition-sources.md), and the root [README](../../README.md). | Adapted. FEWIA updates data sources. It does not edit model weights. |
| Topic 8 model editing and continual learning (ROME, MEMIT, MEND) | Not used. FEWIA trains no model. | — | Not used |

## Topics 6, 1, and 2

| Topic | Status | Note |
|---|---|---|
| 6. Recommendation systems | Not used | `POST /grocery/templates` filters six preset meal sets through the planner. It does not learn from interactions. |
| 6. Offline evaluation, L13 *Data Leakage: Training on the Future* | Not used. The Oct 3 record shows the leak that this lecture warns about. | The repository discloses that the Oct 3 gold changed after the outputs were seen ([post-hoc record](../../wiki/phases/posthoc-gold-20261003.md)). No held-out split is recorded. L05 *The benchmarks leaked* names the same risk. |
| 1. Dense representation | Not used | FEWIA computes no embeddings. |
| 2. Knowledge graphs | Not used | Catalog entries and USDA FDC IDs are typed records with stable IDs. They give provenance. They do not form a graph. |

## Gaps the existing records can close

Each gap below needs a writer change. No gap needs a new call to a hosted model provider. The dense retriever needs a local embedding model, and its results MUST carry an evidence-class label.

| Gap | Source data | Course method |
|---|---|---|
| pass^k for k = 1, 2, 3 per condition | [`benchmark-20261005/live-nova2-20261005/slots.jsonl`](../../eval/results/artifacts/benchmark-20261005/live-nova2-20261005/slots.jsonl) and [`planning-ablation/live/trials.jsonl`](../../eval/results/artifacts/openai-luna-20261107/planning-ablation/live/trials.jsonl) | L15, *τ-bench: Measuring Agent Reliability* |
| A dense retriever beside BM25 on the same 15 queries | [`retrieval_queries.json`](../../backend/tests/evaluation/retrieval_queries.json) | L08, *Sparse and dense representations* |
