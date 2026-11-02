# Request limits for automated prose editing

These changes bound automated editing work and keep paragraph repairs separate from intentional chat. They preserve the selected provider, model, reasoning effort, source text, and author-review workflow.

## What changed

- Conditioning defaults to two action spans. An explicit batch limit must be an integer from one to ten; an omitted limit no longer means the whole manuscript.
- Each span retains the existing maximum of two validation attempts. The default therefore permits at most four high-level generation calls, and an explicit ten-span batch permits at most twenty.
- The first provider exception stops the remainder of a conditioning batch. Earlier proposals and the failed proposal are retained and saved by the ordinary file runner.
- Automated Codex repairs use the existing ephemeral CLI provider. Automated DeepSeek repairs use the stateless API provider. They no longer append every repair to the persistent chat history.
- Explicit chat continues to use its persistent session. DeepSeek's API size and completion caps below also apply to that chat.
- One live automated proposal job is admitted per editor. A second distinct live job is rejected before claiming its durable request ID. Local mock work remains available; ordinary editing and polling remain available.
- DeepSeek submits an explicit `max_tokens` value. Both Venice generation paths submit `max_completion_tokens`.
- Oversized messages and Codex prompts are rejected before transport. Source material is never silently truncated.
- The package declares its existing `httpx` runtime dependency.

## Default request bounds

| Setting | Default | Explicit supported range |
|---|---:|---:|
| Conditioning spans per batch | 2 | 1–10 |
| Validation attempts per span | 2 | Existing fixed maximum |
| DeepSeek / Venice completion allowance | 4,096 tokens | 1–32,768 |
| API messages or ephemeral Codex prompt | 65,536 UTF-8 bytes | 1–262,144 |

Provider constructors expose `max_output_tokens` and `max_input_bytes`; Codex exposes only the input bound. These are programmatic settings, not new UI sliders. Limits reject booleans, nonintegers, zero, negatives, and values above the range.

The byte check counts serialized API messages or the complete ephemeral Codex instruction. It is not a token estimate or a dollar estimate. API completion allowances include reasoning where the provider counts it within the completion cap. A truncated result remains rejected and stops the remaining batch; the app does not automatically raise the allowance or change providers.

## Compatibility

Callers that explicitly supplied `limit=None` must omit the argument or provide a bounded integer. Large jobs need deliberately selected smaller batches. Repeating an unchanged unscoped request still selects the first flagged spans; this patch does not add pagination, automatic advancement, or resumable document processing.

Large DeepSeek chat histories may now be refused before submission. Existing history remains saved. Start a separate chat or deliberately configure a larger bounded input allowance if that is the intended operation.

Codex remains on the same model and reasoning setting. Its input and request counts are bounded here; this patch does not invent a CLI output-token flag or claim an account-level Codex subscription limit.

Admission is per editor and covers automated proposals. Separate processes, deliberate chat requests, and external scripts do not share an account-wide budget. Completed proposal replay can temporarily return a busy response while another live proposal is running; retry afterward returns the saved result without generation.

## Verification

The focused regression workflow uses Python 3.13, fake HTTP responses, injected CLI runners, and disposable local documents. It blocks outbound sockets and unmocked subprocess execution during the tests.

The tests cover batch bounds, invalid limits, failure during validation retry, partial-batch persistence, truncation, UTF-8 size handling, explicit completion caps, independent repair requests, proposal admission, and retrying a busy request with the same durable ID.

Existing conditioner, API/session, ephemeral Codex, and editor integration regressions are included. Live model quality and actual account billing are not exercised by these tests.

## Remaining work

Account-level spending limits, durable token/cost receipts, cancellation propagation, crash checkpoints, and legacy direct recook/composer callers require separate work. This patch does not establish the cause or exact cost of any historical run.
