# Qwen reviewer selection — 2026-11-13

Selected default: **qwen3.8-flash**, using Jev screening and ready source-evidence packets. This is a value candidate, not an established best model or a measured corpus-wide accuracy claim.

The Singapore endpoint authenticated with the locally configured key. No credential is present in a request body, source file, public JSON, or report. Standard inference list prices used for accounting:

| Model | Input / 1M tokens | Output / 1M tokens |
|---|---:|---:|
| Qwen3.7-Flash, ≤32k input | $0.030 | $0.130 |
| Qwen3.8-Flash | $0.150 | $0.470 |
| Qwen3.7-Plus, ≤256k input | $0.400 | $1.600 |

Source: https://www.alibabacloud.com/help/en/model-studio/model-pricing. These are Singapore standard prices, not discounted Batch prices. Account discounts, tokenization, input context tier, and reasoning length can change actual charges. Thinking is enabled with a 1,024-token budget; the entire completion is bounded at 3,072 tokens (with a small accounting allowance for the documented tolerance).

## Development regression results

Two known source-backed cases were used: SparseMAP → LP-SparseMAP and Oko et al. → the later minimax diffusion analysis. Expected type: Extends for both.

- Initial Qwen3.7-Flash responses copied/paraphrased source text using ellipses, causing the exact-quote guard to withhold them. Improving evidence instructions did not reliably solve that.
- The integration now extracts evidence options in code and requires the model to select allowed evidence IDs. Source quotations and page provenance are reconstructed from those exact options; unknown IDs fail closed.
- With that adapter, Qwen3.7-Flash got SparseMAP right but mislabeled the theorem generalization as Challenges. A review policy prevents publishing that known error.
- Qwen3.8-Flash with the same evidence-ID adapter labeled both cases Extends, selected exact-source evidence, and passed the guard. Actual two-call cost: approximately $0.002252.
- Qwen3.7-Plus also labeled both cases correctly in the earlier quote-based adapter. Its two-call cost was approximately $0.007233. Because adapters differed, this is not a controlled accuracy comparison with 3.8-Flash.

All tests in this pilot are development examples, not a held-out scientific benchmark. No 100% accuracy claim is justified. A fresh labeled set covering all relation types and hard negatives remains necessary.

## Cost implications

The two source-backed Qwen3.8-Flash calls averaged roughly $1.126 per 1,000 reviews. Extrapolating this selected sample yields about $79.79 for 70,861 such reviews, excluding new Jev screening, retries, longer inputs, and extra reviews. Remaining all-candidate Jev screening was previously estimated around $27. A selective graph can cost less; source availability and the acceptance threshold determine the number of final reviews. These are planning estimates, not a guarantee of high-quality coverage or budget approval.

The existing shared $5 cap remains active. Qwen requests use the same durable spending ledger as prior Haiku calls and any new Jev screening. Unknown paid outcomes retain reservations, malformed/truncated outputs are not published, and no automatic retries resubmit ambiguous requests.
