"""Open Night repo-local startup hook for the shared v1.0 GridWorld refinement."""
try:
    import v100_runtime_refinement
    v100_runtime_refinement.install()
except Exception:
    # Setup/bootstrap commands may run before optional game dependencies exist.
    # Canonical v1.0 entrypoints install the refinement again after setup.
    pass
