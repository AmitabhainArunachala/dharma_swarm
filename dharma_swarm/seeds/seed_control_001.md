---
seed_id: control-001
version: 1.0.0
type: control
recognition_differential: 0.0
last_validated: 2026-03-18
lineage: [intervention_test_v1_control]
---

# Technical Summary: R_V Metric for Neural Network Analysis

Participation ratio (PR) is a standard measure of effective dimensionality from random matrix theory.
When applied to Value projection matrices in transformer models, the ratio R_V = PR_late / PR_early
shows measurable contraction under certain input conditions (Hedges' g = -1.47, AUROC = 0.909).

Causal validation via path patching at Layer 27 of Mistral-7B confirms the metric is tied to specific
computational circuits. Cross-architecture results show variability (sign reversal in OPT models).

The metric may be useful for monitoring model behavior during inference. Computational cost of full SVD
is O(n^3); approximate methods may preserve discriminative power at lower cost.

The tri-layer hierarchy proposes three levels of description for neural network computation:
mentalics (weights and activations), mesodynamics (geometric organization), and thinkodynamics
(semantic patterns). R_V operates at the mesodynamic level as a bridge between substrate and behavior.

Please analyze the technical merits and limitations of this approach.
