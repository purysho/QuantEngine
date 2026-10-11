# AI resource and repository audit

Verified on **2026-10-11** for a proposed free local QuantEngine on **Windows, Intel Core 5 210H, 16 GB system RAM, integrated graphics, and no discrete GPU**.

This is a source inspection, not an installation or performance reproduction. Repository metadata, actual licence files, manifests, relevant implementations, model metadata/configuration, papers, and first-party institutional descriptions were checked. No models, datasets, or released binaries were downloaded; no model training, inference benchmark, or trading backtest was run.

## Decision matrix

| Resource | What the inspected resource provides | Free local QuantEngine role | Availability / cost boundary |
|---|---|---|---|
| `xai-org/grok-build` | Rust terminal coding agent, tools, and agent runtime | Optional software-building interface; does not supply a financial backtest engine or investment model | Apache-2.0 first-party source. Hosted models are the default; documented local model endpoints are an option. Vendor currently advertises a free trial; permanent free hosted inference was not established. |
| `addyosmani/agent-skills` | Markdown engineering workflows, agent adapters, hooks, and validation scripts | Optional development/review guidance for building QuantEngine | MIT source; no bundled LLM weights or quant engine. The chosen host agent supplies inference and its own access/cost conditions. |
| `meta-models/Muse-Glimmer-30B` | Available dense multimodal language-model weights | Unsuitable as this laptop's default local model | Actual Apache-2.0 licence plus a separate published usage policy. Released full-precision weights are about 59.6 GB; the card's 17 GB quantized deployment targets a 24 GB GPU envelope. |
| Bridgewater AIA Macro / AIA Labs | Investment funds, an internal artificial-investor programme, and public research/talks | Architecture and research references | A fund/operating programme, not a downloadable local software package. No public release of the complete investment system, proprietary corpus, or fund strategy was verified. |
| Wang et al. **Alpha-GPT** | Human–AI alpha-mining research and demonstrations | Research design: generate formulas, evaluate them numerically, and refine with human feedback | Public paper; complete author implementation, its proprietary alpha base, and system-specific trained weights were not verified as publicly downloadable. The evaluated chat model is Llama 3 70B. |
| Citadel AI Assistant | Internal equities-research chatbot | Institutional research-workflow reference | Internal deployment; no public downloadable code, weights, training set, or consumer API was verified. |
| Balyasny / BAM GPT and investment-research agents | Internal analyst tools and agent infrastructure | Evaluation, retrieval, and orchestration reference | Company descriptions and an OpenAI customer case study are public; the complete internal platform, evaluations, and proprietary financial data were not verified as released. |
| Tang et al. **AlphaAgent** | Public alpha-mining paper; its linked repository now contains a different daily A-share factor framework | Candidate ideas for a CPU numerical layer, subject to resolving licence and data conditions | Current repository has no licence file in the inspected recursive tree. Optional mining invokes a model API. Do not identify today's `main` as a reproduced KDD implementation. |
| Zhang et al. **FinAgent** | Public multimodal financial-agent research and Python implementation | Agent-workflow reference; CPU orchestration is plausible | MIT implementation, but its default inference/embeddings use OpenAI APIs and its data workflow uses external services. It is not a verified free, fully local deployment. |

“No public release verified” describes the inspected sources and current access. It is not a claim that no release could exist anywhere.

## Exact GitHub repositories

Both requested repositories were accessible through the selected GitHub connection as public repositories, with `pull=true`, `push=false`, `archived=false`, and default branch `main`.

| Repository | Inspected default-branch commit | Commit date (UTC) | Actual licence / manifest |
|---|---|---|---|
| `xai-org/grok-build` | `2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8` | 2026-09-29 16:57:09 | Actual `LICENSE`: Apache License 2.0, copyright 2023–2026 SpaceXAI. Root `Cargo.toml`: Rust workspace, edition 2024, Apache-2.0 metadata. |
| `addyosmani/agent-skills` | `1be8e34187e34647bb83adc3a1323b26ae6f6abe` | 2026-10-10 08:28:48 | Actual `LICENSE`: MIT, copyright 2025 Addy Osmani. Root, Claude, and Codex manifests: version `0.6.12`. |

### Grok Build: implementation evidence

The README describes a terminal coding agent and provides released binaries for Windows, macOS, and Linux. Building the source on Windows is explicitly best-effort and untested in this tree; binary support and source-build support are different claims.

The custom-model guide documents Ollama at `http://localhost:11434/v1` and local OpenAI-compatible servers. Model-provider code merges configurable endpoints/authentication, and the model-list implementation makes HTTP requests to the selected `/v1/models` service. This supports using Grok as a client of local inference; it does **not** show that this repository contains an inference engine or model weights. Default login/model discovery and a complete offline startup path were not executed.

Third-party/vendored code keeps its original licences and notices. Reuse must preserve applicable upstream obligations; the first-party Apache label does not replace them.

Primary inspected files:

- [README](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/README.md), [actual LICENSE](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/LICENSE), [Cargo workspace](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/Cargo.toml).
- [Authentication guide](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md), [custom-model guide](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-pager/docs/user-guide/11-custom-models.md).
- [Provider configuration implementation](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-shell/src/agent/model_providers.rs), [HTTP model-list implementation](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-shell/src/remote/model_source/oai.rs).
- [Vendor product page](https://x.ai/build) and [overview](https://docs.x.ai/build/overview), checked 2026-10-11. The page says the service is available to try free; this is not an unlimited free-inference guarantee.

### Agent Skills: implementation evidence

The README enumerates 25 skills: 24 engineering lifecycle workflows and the discovery meta-skill. The manifests point to shared `skills/` directories. A reviewed Bash session-start hook injects Markdown instructions into a host session; it is not wired by default for hosts with native routing. Bash/`jq` and contributor JavaScript scripts are ancillary tooling. No quant dataset, trained financial model, or portfolio/backtest engine was identified in the inspected tree.

Primary inspected files:

- [README](https://github.com/addyosmani/agent-skills/blob/1be8e34187e34647bb83adc3a1323b26ae6f6abe/README.md), [actual LICENSE](https://github.com/addyosmani/agent-skills/blob/1be8e34187e34647bb83adc3a1323b26ae6f6abe/LICENSE).
- [Root manifest](https://github.com/addyosmani/agent-skills/blob/1be8e34187e34647bb83adc3a1323b26ae6f6abe/plugin.json), [Claude manifest](https://github.com/addyosmani/agent-skills/blob/1be8e34187e34647bb83adc3a1323b26ae6f6abe/.claude-plugin/plugin.json), [Codex manifest](https://github.com/addyosmani/agent-skills/blob/1be8e34187e34647bb83adc3a1323b26ae6f6abe/.codex-plugin/plugin.json).
- [Session-start implementation](https://github.com/addyosmani/agent-skills/blob/1be8e34187e34647bb83adc3a1323b26ae6f6abe/hooks/session-start.sh).

## Muse-Glimmer-30B: exact availability and hardware audit

The exact requested URL **exists and was publicly accessible**. Hugging Face API metadata reported `private=false`, `gated=false`, `disabled=false`, commit **`a4e59da52a7bc87ae7251dd5545c0dd437c44b68`**, last modified **2026-08-11 19:23:35 UTC**. The model card gives an August 2026 release. This conclusion comes from the current endpoint, not prior model-name familiarity.

| Item | Inspected evidence |
|---|---|
| Actual licence | `LICENSE` contains Apache License 2.0. `USAGE_POLICY.md` is also shipped separately. |
| Architecture / dtype | `config.json`: `MuseGlimmerForConditionalGeneration`, `model_type=muse_glimmer`, `dtype=bfloat16`. |
| Weight footprint | `model.safetensors.index.json` reports `total_size=59553253376` bytes: approximately **59.55 GB / 55.46 GiB**. File tree lists two weight shards, rounded to 50 GB and 9.6 GB. |
| Card size / deployment | Approximately 29.6B parameters; full precision targets 64 GB VRAM, K-Quant-Dynamic 32 GB VRAM, K-Quant-17GB 24 GB VRAM. |
| Published speed evidence | Vendor measurements use Apple M4/M5 Max and NVIDIA RTX 5090. They do not establish Intel Core 5 CPU performance. |

Hardware interpretation: [Intel's graphics-memory documentation](https://www.intel.com/content/www/us/en/support/articles/000020962/graphics.html), reviewed 2026-01-13, confirms that integrated processor graphics uses system memory rather than a separate graphics memory bank. Even the card's 17 GB quantized deployment exceeds the laptop's entire nominal 16 GB RAM before Windows, application state, context/KV cache, and other components. Neither this model nor training it is an appropriate default for this machine. Smaller quantizations, disk paging, or component offloading would require separate verification and cannot inherit the published speed claims.

Primary sources: [model card](https://huggingface.co/meta-models/Muse-Glimmer-30B), [metadata API](https://huggingface.co/api/models/meta-models/Muse-Glimmer-30B), [pinned actual licence](https://huggingface.co/meta-models/Muse-Glimmer-30B/raw/a4e59da52a7bc87ae7251dd5545c0dd437c44b68/LICENSE), [configuration](https://huggingface.co/meta-models/Muse-Glimmer-30B/raw/main/config.json), [weight index](https://huggingface.co/meta-models/Muse-Glimmer-30B/raw/main/model.safetensors.index.json), [file tree](https://huggingface.co/meta-models/Muse-Glimmer-30B/tree/main), [usage policy](https://huggingface.co/meta-models/Muse-Glimmer-30B/raw/main/USAGE_POLICY.md).

## Resolve the institutional and research names

### AIA Macro

This name refers to Bridgewater's investment programme/funds, not an open local model. An SEC issuer filing identifies **Bridgewater AIA Labs Macro Fund (DE), LP**; another identifies the `(DE) II` vehicle with a 2026-04-27 filing date. Bridgewater describes AIA Labs as its AI investment lab, with proprietary macro/market data and investment reasoning. Its Pocket Analyst Tool (PAT) talk, recorded 2026-05-19, describes an internal exploratory-research assistant.

These are useful first-party descriptions, not an availability or reproducible-performance claim for the complete system. Public AIA papers/talks do not establish release of fund strategies, full training data, model weights, or PAT code.

Sources: [SEC issuer filing](https://www.sec.gov/Archives/edgar/data/2019328/000090514825001946/xslFormDX01/primary_doc.xml), [SEC filing index, 2026-04-27](https://www.sec.gov/Archives/edgar/data/2022937/000090514826001848/0000905148-26-001848-index.htm), [Bridgewater AIA Labs](https://www.bridgewater.com/aia-labs), [official PAT presentation](https://www.bridgewater.com/aia-labs/how-bridgewaters-aia-labs-built-pat-the-ai-pocket-analyst-tool).

### AlphaGPT / Alpha-GPT

The name is ambiguous. The verified academic identity is **Alpha-GPT: Human-AI Interactive Alpha Mining for Quantitative Investment**, Wang et al.: first submitted 2023-07-31, revised 2025-09-20, EMNLP 2025 system demonstration. Similar GitHub/project names must not be silently treated as that authors' implementation.

The published experimental system uses **Llama 3 70B**, **BGE-M3** embeddings, and a proprietary alpha base. GPT-4 also judges generated expressions and simulates human feedback in reported studies. Its workflow combines formula generation, search enhancement, and numerical backtesting; reported contest/evaluation outcomes are author results, not results reproduced here. The public **Alpha-GPT 2.0** paper, submitted 2024-02-15, identifies itself as a draft/work in progress. A complete local distribution and its licence were not verified. Running/training the reported 70B foundation model is outside the proposed laptop's practical budget.

Sources: [Alpha-GPT metadata/version history](https://arxiv.org/abs/2308.00016), [final EMNLP paper and experimental setup](https://aclanthology.org/2025.emnlp-demos.14.pdf), [Alpha-GPT 2.0](https://arxiv.org/abs/2402.09746).

### Citadel AI Assistant

Citadel's official company post identifies its AI Assistant as an investor research chatbot. Reuters' direct CTO interview describes licensed transcripts, filings, brokerage research, and Citadel strategies, with deployment inside the firm. The interview happened 2025-12-03; the article was refiled 2025-12-08. Neither source supplies a public local implementation, training recipe/data release, weights, or external product API.

Sources: [Citadel's first-party post](https://www.linkedin.com/posts/citadel-llc_at-reuters-next-chief-technology-officer-activity-7402461726761455616-sA6f), [Reuters interview](https://www.reuters.com/business/citadel-debuts-new-ai-tool-equities-investors-cto-subramanian-says-2025-12-03/).

### Balyasny / BAM GPT

Balyasny's official video transcript names **BAM GPT** and describes internal product planning and data analysis. Its technology page describes custom applications and proprietary quantitative research. The 2026-03-06 OpenAI case study describes a broader investment-research platform using GPT-5.4 alongside internal models, task-specific selection, proprietary evaluations, retrieval, and team-specific agents. Public descriptions are not downloadable platforms. No complete internal system or financial training dataset release was verified; API-based components cannot be assumed free or offline. The case study is vendor/customer evidence, not an independent benchmark reproduction.

Sources: [Balyasny's BAM GPT video transcript](https://www.linkedin.com/posts/balyasny-asset-management-l.p._leveraging-applied-ai-activity-7328107741674196992-oyHj), [Balyasny technology](https://www.bamfunds.com/how-we-work/technology), [Balyasny's case-study announcement](https://www.bamfunds.com/news-and-insights/balyasny-openai-feature), [OpenAI customer case study](https://openai.com/index/balyasny-asset-management/).

## Open research implementations: CPU feasibility and reproduction boundaries

### AlphaAgent: paper versus current repository

Tang et al.'s [KDD 2025 paper, revision 2025-06-09](https://arxiv.org/html/2502.16789v2) links `RndmVariableQ/AlphaAgent`. It reports GPT-3.5-turbo agents, Qlib backtests, and a depth-4 LightGBM prediction model. The numerical factor/backtest layer is a more plausible CPU workload than training an LLM; substituting a small local model would be a new experiment.

The linked repository's current `main` is **`b42cb397025510da44355db9dcf278304321f589`**, dated **2026-07-03 11:54:54 UTC**. Its history labels a July 2026 release of a new factor research framework. Today's README describes a CSI 1000 daily panel, FactorZoo DSL/memmap factors, and optional AgentScope mining. It should not be cited as unchanged original KDD code.

The inspected recursive tree contained **no licence file**, and `pyproject.toml` had no licence declaration. The README's “open source” wording does not resolve the missing explicit reuse licence. Data redistribution must comply with Tushare terms; the listed Baidu data package was not downloaded or checked. Python 3.11+, NumPy, pandas, PyArrow, Numba, and optional LightGBM indicate a CPU-oriented numerical path. Mining requires `OPENAI_API_KEY` and `MODEL`, accepts `OPENAI_API_BASE`, and includes memory/concurrency controls; local endpoint functionality and 16 GB capacity were not tested.

Primary inspected files: [current README](https://github.com/RndmVariableQ/AlphaAgent/blob/b42cb397025510da44355db9dcf278304321f589/README.md), [manifest](https://github.com/RndmVariableQ/AlphaAgent/blob/b42cb397025510da44355db9dcf278304321f589/pyproject.toml), [mining CLI](https://github.com/RndmVariableQ/AlphaAgent/blob/b42cb397025510da44355db9dcf278304321f589/scripts/factor_mining_agentscope.py), [data-release documentation](https://github.com/RndmVariableQ/AlphaAgent/blob/b42cb397025510da44355db9dcf278304321f589/docs/data_release.md), [recursive tree](https://api.github.com/repos/RndmVariableQ/AlphaAgent/git/trees/b42cb397025510da44355db9dcf278304321f589?recursive=1).

### FinAgent

The inspected author implementation is **`DVampire/FinAgent`**, `main` commit **`17248a0b8b729ee3e093e30bb7bea7f52181f363`**, dated **2024-08-31 18:13:54 UTC**. Its actual licence is **MIT**, copyright 2024 FinAgent Authors. The public paper was submitted 2024-02-28 and revised 2024-06-28.

The implementation's AAPL configuration uses `gpt-4-1106-preview` and `gpt-4-vision-preview`; its provider configuration uses `text-embedding-3-large`. `OpenAIProvider` constructs an OpenAI/Azure client and calls remote embeddings/completion services. The README lists OpenAI and several external market/news-service credentials; installation uses CPU FAISS. Thus CPU orchestration is plausible, while inference is external in the inspected configuration. Old preview-model identifiers and current Windows/API compatibility were not validated. No local foundation-model weights or foundation-model training route is supplied by this repository.

Reported results concern five stocks and Ethereum, with an evaluation period in the second half of 2023. They do not establish future profits, broad market generalization, or the performance of a small local-model substitution.

Primary sources: [paper](https://arxiv.org/html/2402.18485v3), [README](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/README.md), [actual LICENSE](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/LICENSE), [requirements](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/requirements.txt), [AAPL configuration](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/configs/exp/trading/AAPL.py), [OpenAI configuration](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/configs/openai_config.json), [provider implementation](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/finagent/provider/provider.py).

## Implications for this QuantEngine

Build the quantitative core around deterministic local data handling, numeric research/backtests, and explicit evaluation. An LLM can be an optional interface or candidate generator; it should not be required for the engine to calculate returns, costs, risk, or validation results. Keep any selected local model within RAM headroom and measure it on the actual laptop. Repository visibility, a free software licence, and paper-reported accuracy are separate facts; none guarantees free model inference, unrestricted market-data redistribution, or replicated investment performance.

No paid books, proprietary institutional source code, or model weights were copied into this audit.
