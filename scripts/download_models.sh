#!/usr/bin/env bash
# One-time model download for Medusa (v3). Everything lands in ./models/.
# After this completes, the app only needs the network once more: the backend's first start
# auto-downloads Whisper + the emotion models (see the NOTE at the end).
# (The old step 5 ran `transformers` on the host Python, which fails without it installed.)
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p models/llm models/kokoro models/silero models/piper-tamil

echo "==> [1/4] LLM: Qwen3-4B-Instruct-2507 Q4_K_M (~2.5 GB)"
if [ ! -f models/llm/Qwen3-4B-Instruct-2507-Q4_K_M.gguf ]; then
    hf download unsloth/Qwen3-4B-Instruct-2507-GGUF \
        Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
        --local-dir models/llm
else
    echo "    already present, skipping"
fi

echo "==> [2/4] TTS English: Kokoro-82M ONNX + voices (~410 MB)"
KOKORO_BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
[ -f models/kokoro/kokoro-v1.0.onnx ] || curl -L --fail -o models/kokoro/kokoro-v1.0.onnx "$KOKORO_BASE/kokoro-v1.0.onnx"
[ -f models/kokoro/voices-v1.0.bin ]  || curl -L --fail -o models/kokoro/voices-v1.0.bin  "$KOKORO_BASE/voices-v1.0.bin"

echo "==> [3/4] TTS Tamil: Piper ta_IN-Valluvar-medium (~60 MB)"
PIPER_BASE="https://huggingface.co/datasets/Jeyaram-K/piper-tamil-voice/resolve/main/ta_IN-Valluvar-medium"
[ -f models/piper-tamil/ta_IN-Valluvar-medium.onnx ] || \
    curl -L --fail -o models/piper-tamil/ta_IN-Valluvar-medium.onnx "$PIPER_BASE/ta_IN-Valluvar-medium.onnx"
[ -f models/piper-tamil/ta_IN-Valluvar-medium.onnx.json ] || \
    curl -L --fail -o models/piper-tamil/ta_IN-Valluvar-medium.onnx.json "$PIPER_BASE/ta_IN-Valluvar-medium.onnx.json"

echo "==> [4/4] VAD: Silero v5 ONNX (~2 MB)"
[ -f models/silero/silero_vad.onnx ] || curl -L --fail -o models/silero/silero_vad.onnx \
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx"

echo
echo "NOTE: On first backend start these auto-download (HF ones into the whisper-cache volume):"
echo "  - STT: Whisper large-v3-turbo (~1.5 GB)"
echo "  - SER: superb/wav2vec2-base-superb-er (~380 MB)"
echo "  - FER: HSEmotion enet_b0_8_best_afew ONNX (fetched by hsemotion-onnx when it loads)"
echo
echo "All models downloaded:"
du -sh models/*

