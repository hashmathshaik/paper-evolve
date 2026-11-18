# Qwen seed source audit

Assistant source review on 2026-11-14; not expert human verification.

Five initial Qwen3.7-Flash positive suggestions were withdrawn from publication
and sent, with the same source packets but without the proposed answers, to
Qwen3.7-Plus. One type survived the agreement/evidence gate. The other four were
withheld. This deliberately selected diagnostic set is not an accuracy estimate.

| Earlier → later paper | Audit finding |
| --- | --- |
| Smooth Normalizing Flows → Rigid Body Flows for Sampling Molecular Crystal Structures | Transfers/Combines were unsupported by the selected evidence: a coordinate/pose restriction is not automatically a new application, and “can be combined” is not an implemented combination. The reviewer inferred Extends, which neither had explicit evidence nor matched the proposal types. Withheld. |
| Gradient-based Constrained Sampling from Language Models → BOLT | A shared constrained-generation problem and a speed baseline did not establish inheritance of MuCoLa. The reviewer abstained. Withheld. |
| Fair Regression → Demographic Parity Constrained Minimax Optimal Regression under Linear Model | The decisive method passage explicitly builds on Chzhen et al., not the asserted earlier reduction-based paper. The reviewer abstained. Withheld. |
| Scalable Marginal Likelihood Estimation → Adapting the Linearised Laplace Model Evidence | Extends retained. The earlier source describes Laplace/Gauss-Newton marginal likelihood, the later text cites the earlier work in its adopted linearised-Laplace method, and its Discussion specifies stationarity/normalisation adaptations. The later PDF's page 8 was rendered and checked against the stored quotation. No additional Challenges label was published. |
| Conditional Generators of Words Definitions → Bridging the Defined and the Defining | The source packet did not establish retention of the particular earlier architecture beyond related definition-modeling work. The explicit-link/type-overlap gate withheld it. |

The shared instructions now distinguish actual inherited contributions from
shared tasks, actual combinations from possible future combinations, and the
asserted parent from a different cited method. Only agreed types with explicit
source evidence enter this new seed pool; older predictions remain labeled as
predictions. Similarity links are unchanged.

An isolated constrained-decoder numeric loop was also found. It was rejected and
fully charged in the local allowance; it produced no edge. The response schema
now uses finite confidence choices and a smaller per-pair output bound. Invalid
results are not automatically retried. The seed worker quarantines isolated
invalid outputs and stops after repeated failures or uncertain billing outcomes.

The contribution path has 100 frozen starter tasks, exact-quote validation,
separate maintainer acceptance and a static correction overlay. Validator tests
cover fabricated quotes, stale evidence, one-sided claims, duplicate tasks,
non-finite scores, assistant-vs-human review provenance and accepted withdrawals.
