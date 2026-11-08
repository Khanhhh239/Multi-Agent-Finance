# Frozen renderer fixtures

`p2_controls_renderer.json` contains the renderer inputs for 32 synthetic P2 controls and 73 transactions. It is exported from the previously frozen source tables, rule hits, queues, configurations and predictions used by the UI regression suite. SHA256 values for all 162 input files are stored in `input_sha256`.

The UI tests read this fixture without scoring, training a model or requiring the full datasets. Expected business outcomes and source evidence are preserved from the frozen snapshot. This fixture supports VM/DOM regressions; it is separate from browser and independent accounting acceptance.
