"""Guards for host-side scripts (run on the developer machine, not in Docker)."""

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "download_models.sh"


def _code_lines(text: str) -> list[str]:
    """Script lines without comments/blank lines (comments may mention history)."""
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def test_download_script_does_not_run_host_python():
    """`make models` runs on the host, where Python ML deps are not installed
    (deps live in Docker only). A host `python3 -c` importing transformers made
    the script fail at its last step. Emotion models now download on first
    backend start inside the container instead."""
    code = _code_lines(SCRIPT.read_text())
    host_python = [ln for ln in code if re.match(r"\s*python3?\b", ln)]
    ml_imports = [ln for ln in code if re.search(r"\b(from|import) (transformers|torch|hsemotion_onnx)\b", ln)]
    assert not host_python, f"download_models.sh must not invoke host Python: {host_python}"
    assert not ml_imports, f"download_models.sh must not import ML packages: {ml_imports}"
