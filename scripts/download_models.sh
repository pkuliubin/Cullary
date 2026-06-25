#!/usr/bin/env bash
set -euo pipefail

# Download Cullary model assets with parallel, resumable curl jobs.
# Usage:
#   scripts/download_models.sh
#   MODEL_DIR=/path/to/models PARALLEL=4 HF_BASE=https://hf-mirror.com scripts/download_models.sh

MODEL_DIR="${MODEL_DIR:-$HOME/.cullary/models}"
PARALLEL="${PARALLEL:-4}"
HF_BASE="${HF_BASE:-https://hf-mirror.com}"
HF_FALLBACK_BASE="${HF_FALLBACK_BASE:-https://huggingface.co}"
OPENCV_BASE="${OPENCV_BASE:-https://github.com/opencv/opencv_zoo/raw/main}"
PYIQA_BASE="${PYIQA_BASE:-https://hf-mirror.com/chaofengc/IQA-PyTorch-Weights/resolve/main}"

mkdir -p "$MODEL_DIR"
TMP_LIST="$(mktemp -t cullary-models.XXXXXX)"
trap 'rm -f "$TMP_LIST"' EXIT

add() {
  # add primary-url fallback-url relative-output-path
  printf '%s\t%s\t%s\n' "$1" "$2" "$MODEL_DIR/$3" >> "$TMP_LIST"
}

hf() {
  # hf repo filename output-dir
  repo="$1"
  file="$2"
  outdir="$3"
  add "$HF_BASE/$repo/resolve/main/$file" \
    "$HF_FALLBACK_BASE/$repo/resolve/main/$file" \
    "$outdir/$file"
}

# Face detection: OpenCV YuNet.
add "$OPENCV_BASE/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  "$OPENCV_BASE/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  "yunet/face_detection_yunet_2023mar.onnx"

# Embedding: OpenAI CLIP ViT-B/32.
hf openai/clip-vit-base-patch32 config.json hf-direct/openai__clip-vit-base-patch32
hf openai/clip-vit-base-patch32 preprocessor_config.json hf-direct/openai__clip-vit-base-patch32
hf openai/clip-vit-base-patch32 tokenizer.json hf-direct/openai__clip-vit-base-patch32
hf openai/clip-vit-base-patch32 tokenizer_config.json hf-direct/openai__clip-vit-base-patch32
hf openai/clip-vit-base-patch32 vocab.json hf-direct/openai__clip-vit-base-patch32
hf openai/clip-vit-base-patch32 merges.txt hf-direct/openai__clip-vit-base-patch32
hf openai/clip-vit-base-patch32 pytorch_model.bin hf-direct/openai__clip-vit-base-patch32

if [ "${INCLUDE_CLIP_L14:-0}" = "1" ]; then
  # Optional aesthetic predictor encoder: OpenAI CLIP ViT-L/14.
  # This is much larger than ViT-B/32, so it is opt-in.
  hf openai/clip-vit-large-patch14 config.json hf-direct/openai__clip-vit-large-patch14
  hf openai/clip-vit-large-patch14 preprocessor_config.json hf-direct/openai__clip-vit-large-patch14
  hf openai/clip-vit-large-patch14 tokenizer.json hf-direct/openai__clip-vit-large-patch14
  hf openai/clip-vit-large-patch14 tokenizer_config.json hf-direct/openai__clip-vit-large-patch14
  hf openai/clip-vit-large-patch14 vocab.json hf-direct/openai__clip-vit-large-patch14
  hf openai/clip-vit-large-patch14 merges.txt hf-direct/openai__clip-vit-large-patch14
  hf openai/clip-vit-large-patch14 pytorch_model.bin hf-direct/openai__clip-vit-large-patch14
fi

# Embedding: DINOv2 small/base.
hf facebook/dinov2-small config.json hf-direct/facebook__dinov2-small
hf facebook/dinov2-small preprocessor_config.json hf-direct/facebook__dinov2-small
hf facebook/dinov2-small model.safetensors hf-direct/facebook__dinov2-small
hf facebook/dinov2-base config.json hf-direct/facebook__dinov2-base
hf facebook/dinov2-base preprocessor_config.json hf-direct/facebook__dinov2-base
hf facebook/dinov2-base model.safetensors hf-direct/facebook__dinov2-base

# Embedding: SigLIP base vision/text package.
hf google/siglip-base-patch16-224 config.json hf-direct/google__siglip-base-patch16-224
hf google/siglip-base-patch16-224 preprocessor_config.json hf-direct/google__siglip-base-patch16-224
hf google/siglip-base-patch16-224 tokenizer.json hf-direct/google__siglip-base-patch16-224
hf google/siglip-base-patch16-224 tokenizer_config.json hf-direct/google__siglip-base-patch16-224
hf google/siglip-base-patch16-224 spiece.model hf-direct/google__siglip-base-patch16-224
hf google/siglip-base-patch16-224 model.safetensors hf-direct/google__siglip-base-patch16-224

# pyiqa lightweight metric weights used in Phase 0 tests.
add "$PYIQA_BASE/brisque_svm_weights.pth" "$PYIQA_BASE/brisque_svm_weights.pth" torch/hub/pyiqa/brisque_svm_weights.pth
add "$PYIQA_BASE/niqe_modelparameters.mat" "$PYIQA_BASE/niqe_modelparameters.mat" torch/hub/pyiqa/niqe_modelparameters.mat
add "$PYIQA_BASE/NRQM_model.mat" "$PYIQA_BASE/NRQM_model.mat" torch/hub/pyiqa/NRQM_model.mat

printf 'Model dir: %s\n' "$MODEL_DIR"
printf 'Parallel jobs: %s\n' "$PARALLEL"
printf 'HF base: %s\n' "$HF_BASE"
printf 'HF fallback base: %s\n' "$HF_FALLBACK_BASE"
printf 'Total files: %s\n' "$(wc -l < "$TMP_LIST" | tr -d ' ')"

download_one() {
  primary_url="$1"
  fallback_url="$2"
  out="$3"
  mkdir -p "$(dirname "$out")"

  if [ -s "$out" ]; then
    printf "skip existing: %s\n" "$out"
    return 0
  fi

  log="$out.download.log"
  printf "download: %s\n" "$out"

  for url in "$primary_url" "$fallback_url"; do
    [ -n "$url" ] || continue
    printf "  source: %s\n" "$url" > "$log"
    if curl -L -C - --fail --silent --show-error \
      --retry 30 --retry-delay 8 --retry-all-errors --retry-connrefused \
      --connect-timeout 120 --speed-time 300 --speed-limit 1024 \
      -o "$out" "$url" >> "$log" 2>&1; then
      printf "ok: %s\n" "$out"
      rm -f "$log"
      return 0
    fi
    printf "  failed source, trying fallback if available: %s\n" "$url" >> "$log"
  done

  printf "failed: %s (see %s)\n" "$out" "$log" >&2
  return 1
}
export -f download_one

# macOS ships xargs; use bash -c so each row can create its own output directory.
xargs -P "$PARALLEL" -n 3 bash -c 'download_one "$1" "$2" "$3"' bash < "$TMP_LIST"

printf '\nDownloaded files:\n'
find "$MODEL_DIR" -type f \( -name '*.onnx' -o -name '*.safetensors' -o -name 'pytorch_model.bin' -o -name '*.json' -o -name '*.model' -o -name '*.txt' -o -name '*.pth' -o -name '*.mat' \) \
  -maxdepth 6 -print | sort
