# Stage 4A — Literature positioning

Verified lines of work (DOIs as cited in the Stage 4A brief):

| Work | Relevance |
| --- | --- |
| Basso et al., 2022, *TRE* (DS-EVRP + safe RL) | Stochastic requests + energy + charging with anticipative safe policies |
| Ulmer et al., *Transportation Science* ADP offline–online | Value-function / rollout anticipation for dynamic routing |
| Soeffker et al., 2024, OR Spectrum | Balancing resources for dynamic VRP with stochastic requests |
| Dynamic parcel pickup lower-bound rollout (*Computers & OR*, 2023) | Rollout for same-day pickup |

## What Stage 4A implemented

Sample-average post-decision ranking of **feasible claims and depot-charge actions** under a training-only synthetic continuation model and conservative EV gate, with a transparent greedy base rollout.

## What is *not* automatically novel

- Monte Carlo / one-step rollout anticipation  
- Conservative energy-feasible insertion  
- Depot charging as an operational lever  
- Applying the above on Casablanca geography  

## Candidate distinction tested

**Joint** endogenous evaluation of **charge-now vs accept-now** under the same \(\widehat{Q}\) and shared futures, versus claim-only rollout + separate reactive charging.

## Pilot verdict on distinction

Not established. Joint postdecision matched adaptive greedy (29/40) and did not beat always-on greedy (33/40) or show a durable edge over claim-only rollout. The operational gap remains **charging timing**, which existing reactive rules already exploit more effectively than this bounded lookahead.
