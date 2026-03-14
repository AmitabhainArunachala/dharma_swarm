"""Cascade domain configurations for the universal loop engine.

Each domain defines phase functions (generate, test, score, gate, mutate, select)
as importable string references. The LoopEngine resolves these at runtime via importlib.

Available domains:
  common   — shared utilities (telos_gate, default_eigenform)
  code     — wraps DarwinEngine (propose/gate_check/evaluate)
  product  — wraps foreman scoring
  skill    — wraps MetricsAnalyzer + skill evaluation
  research — wraps ThinkodynamicDirector
  meta     — evolves LoopDomain configs themselves (the strange loop)
"""
