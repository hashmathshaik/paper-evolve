# Qwen3.7-Flash Batch availability — November 14, 2026

The current Singapore key authenticated successfully, files uploaded, and both
jobs were created by the OpenAI-compatible Batch API. Both failed model
validation before inference:

| Requested model | Provider job | Result |
| --- | --- | --- |
| `qwen3.7-flash` | `batch_6d293465-c202-405e-8fcd-58a00125b8cc` | `model_not_found`: model is not supported by the Batch API |
| `qwen3.7-flash-2026-07-15` | `batch_2ab3bf52-6688-4b78-87bc-97d2f41dd927` | `model_not_found`: model is not supported by the Batch API |

Each job contained 16 real candidate comparisons. All 32 reservations were
released after explicit validation rejection. No inference charge was reported,
no accepted edges were changed, and the remaining project request allowance is
$26.516652. Paid real-time inference remains paused. Known unsupported models
are blocked from repeat submission by the worker.

The [pricing page](https://www.alibabacloud.com/help/en/model-studio/model-pricing)
advertises a Batch discount for Qwen3.7-Flash. The
[Batch API documentation](https://www.alibabacloud.com/help/en/model-studio/batch-interfaces-compatible-with-openai)
lists a narrower Singapore model selection. Live validation is the decisive
evidence for this endpoint; an advertised price is not proof of availability.

The prior approximate $29 full-queue Batch estimate is not actionable with this
key and endpoint. No substitute model, regional endpoint, or paid real-time
fallback has been authorized or started as part of these probes.

## Beijing follow-up

The user subsequently supplied a dedicated Beijing key and authorized the
Beijing route. Read-only authentication succeeded and the first 16-request file
uploaded successfully. Creating the Batch job returned HTTP 400: "Access denied,
please make sure your account is in good standing." No provider job ID was
issued, no inference started, and all reservations were released. Alibaba's
[error documentation](https://www.alibabacloud.com/help/en/model-studio/error-code)
maps this message to Arrearage. The account owning that key must resolve its
billing status before the Batch job can be retried. No automatic paid retry or
real-time fallback was started; Kimi's free run continues independently.

Concurrent workers now atomically claim paper pairs across model/request IDs
and serialize publication, so the remaining free allowance can run alongside
paid batches without duplicate reviews or conflicting static builds.
