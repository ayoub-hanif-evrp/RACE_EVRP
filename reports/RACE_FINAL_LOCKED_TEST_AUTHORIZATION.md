# Locked-Final Authorization Decision

**Reviewed baseline:** `e221243`  
**This gate:** trust-horizon causality factorial (60 development scenarios).

## Binding decision: **PARTIAL — Valuable safe fallback, weak communication contribution**

### Meaning

The timing/trust mechanism (especially vs legacy selective) **prevents communication-induced losses** under delay, but **most of H_CURRENT’s benefit arises from ignoring delayed peer information** and using a shorter assign wait — operationally equivalent to **no-communication with a matched wait schedule**, while still spending bytes on unused messages.

Describe it as a **robust delayed-link fallback / deadline-aware scheduler**, **not** a novel information-exchange optimizer.

### Locked final

**NOT AUTHORIZED** for a paper claiming strong multi-agent delayed-communication innovation.

Optional path (analyst only): if the manuscript is explicitly scoped as *deadline-aware commitment under delayed links for EV pickups* with selective bidding at delay 0, a locked-final of **NONE_NOW vs SELECTIVE (delay 0) vs H_CURRENT-as-fallback (delay>0)** could still be considered — without claiming peer-info value.

### Why not PASS

PASS required: corrected protocol **demonstrably uses valid delivered peer information** and beats matched no-peer controls.  
`H_VALID_PEER` uses peers but **loses** OT at 30s; `H_CURRENT` does **not** use delayed peers.

### Why not FAIL

Clear gains vs **SELECTIVE_LEGACY** under delay from fixing avoidable wait/deferral; real causality audit; energy-safe cooperative core and delay-0 selective savings remain.

### Statistics hygiene

- 2 pp noninferiority margin was frozen in closeout scripts *before* that expanded eval; it does **not** prove communication benefit vs none.
- Noninferiority of H_CURRENT to none under delay is explained by **matched wait + ignore peers**, not messaging.
- Preserve e221243 closeout as historical (confounded trust interpretation).

### STOP

No locked_final in this commit. No MARL. No Casablanca rebuild.
