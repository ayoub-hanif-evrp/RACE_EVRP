# Stage 4A — New mathematical formulation

## Research question

Can an online electric pickup fleet improve completed on-time service by valuing the **future energy-feasible service opportunities** preserved by each pickup commitment and depot-charging decision?

## Objects

At decision time \(t\), observe fleet/request state \(s_t\) under Stage 3A/3C information rules (no unreleased evaluation requests; no hidden \(\xi\)).

**Feasible action set** \(\mathcal{A}(s_t)\) (hard-gated by conservative energy, windows, payload, reserve):

- Claim released request \(i\) on vehicle \(v\) at editable insertion position \(p\)
- No-op (retain plans)
- Return idle eligible vehicle \(v\) to depot **and charge**
- (Optional) defer uncommitted request while window open — represented by no-op at this epoch

## Post-decision value (ideal)

After action \(a\), post-decision state \(s^+(a)\). True opportunity value:

\[
Q_t(a)=\mathbb{E}\big[N_{\mathrm{on\text{-}time}}(s^+(a),\pi^\star)\big]
\]

unknown; not claimed computable.

## Tractable estimate (implemented)

Training-side synthetic continuation model \(\widehat{\mathcal{D}}\) (empirical attributes from **train** request tables only). Draw \(K\) continuations \(\omega_1,\ldots,\omega_K\) **shared across all candidate actions** (common random numbers).

Base continuation policy \(\pi_{\mathrm{base}}\): marginal-cost greedy + adaptive charging.

\[
\widehat{Q}_t(a)=\frac{1}{K}\sum_{k=1}^{K} N_{\mathrm{on\text{-}time}}^{(k)}\big(s^+(a),\pi_{\mathrm{base}};\omega_k\big)
\]

evaluated on a finite lookahead horizon \(H\) (pilot default \(H=3600\) s) for computational tractability.

**Selection:** \(\arg\max_a \widehat{Q}_t(a)\); ties broken by mean served, then lower travel, then lower energy.

## Distinctions

| Symbol | Meaning |
| --- | --- |
| \(Q_t\) | Unknown true future opportunity value |
| \(\widehat{Q}_t\) | Sample-average estimate under \(\widehat{\mathcal{D}},\pi_{\mathrm{base}},H\) |
| Safety certificate | Unchanged conservative physical gate; \(\widehat{Q}\) ranks only feasible \(a\) |
| Charging | Endogenous action in \(\mathcal{A}\), not an external threshold |

## Explicit non-claims

- \(\widehat{Q}\) is **not** an optimal ADP value function or Bellman optimality theorem.
- Using Monte Carlo rollout is **established**; Casablanca application alone is not novelty.
- Candidate RACE distinction to test: **joint** ranking of **commitment vs charge-now** under the same conservative EV certificate and shared synthetic futures — vs claim-only rollout + separate reactive charging.
