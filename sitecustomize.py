"""Open Night repo-local startup hook for shared v1.0 GridWorld refinements."""
try:
    import v100_runtime_refinement
    import v100_safe_layout
    v100_safe_layout.install(v100_runtime_refinement)
    v100_runtime_refinement.install()
    import v100_scale_normalization
    v100_scale_normalization.install()
except Exception:
    # Setup/bootstrap commands may run before optional game dependencies exist.
    # Canonical v1.0 entrypoints install the refinements again after setup.
    pass
