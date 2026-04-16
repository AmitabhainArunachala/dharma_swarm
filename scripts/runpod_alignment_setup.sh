#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# RunPod Alignment Experiment Setup
# ═══════════════════════════════════════════════════════════════════════════
# Downloads dependencies, models, and runs the alignment benchmark.
#
# Usage:
#   bash runpod_alignment_setup.sh              # Full setup + base model run
#   bash runpod_alignment_setup.sh --skip-setup # Skip pip/model download
#   bash runpod_alignment_setup.sh --instruct   # Run instruct model instead
#   bash runpod_alignment_setup.sh --both       # Run both base and instruct
#   bash runpod_alignment_setup.sh --scan       # Layer scan on instruct
#   bash runpod_alignment_setup.sh --dry-run    # Quick 10-question test
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

WORKDIR="/workspace/alignment_experiment"
SCRIPT_URL=""  # Will be set if pulling from gist
SCRIPT_PATH="$WORKDIR/run_alignment_benchmark.py"
RESULTS_DIR="$WORKDIR/results"

# Parse flags
SKIP_SETUP=false
RUN_INSTRUCT=false
RUN_BOTH=false
LAYER_SCAN=false
DRY_RUN=false
MAX_Q=0

for arg in "$@"; do
    case $arg in
        --skip-setup)  SKIP_SETUP=true ;;
        --instruct)    RUN_INSTRUCT=true ;;
        --both)        RUN_BOTH=true ;;
        --scan)        LAYER_SCAN=true ;;
        --dry-run)     DRY_RUN=true; MAX_Q=10 ;;
        *)             echo "Unknown flag: $arg"; exit 1 ;;
    esac
done

echo "═══════════════════════════════════════════════════════════════"
echo "  ALIGNMENT EXPERIMENT — RunPod Setup"
echo "═══════════════════════════════════════════════════════════════"
echo "  Workdir:    $WORKDIR"
echo "  Skip setup: $SKIP_SETUP"
echo "  Instruct:   $RUN_INSTRUCT"
echo "  Both:       $RUN_BOTH"
echo "  Layer scan: $LAYER_SCAN"
echo "  Dry run:    $DRY_RUN"
echo "═══════════════════════════════════════════════════════════════"

# ─── Step 1: Environment Setup ────────────────────────────────────────────

if [ "$SKIP_SETUP" = false ]; then
    echo ""
    echo ">>> [1/4] Installing Python dependencies..."
    pip install --quiet --upgrade \
        torch \
        transformers \
        datasets \
        accelerate \
        numpy \
        scipy \
        huggingface_hub

    echo ""
    echo ">>> [2/4] Creating workspace..."
    mkdir -p "$WORKDIR" "$RESULTS_DIR"

    # If the script isn't already in place, check if it's in the current dir
    if [ ! -f "$SCRIPT_PATH" ]; then
        if [ -f "./run_alignment_benchmark.py" ]; then
            cp ./run_alignment_benchmark.py "$SCRIPT_PATH"
            echo "  Copied script from current directory"
        elif [ -f "/workspace/run_alignment_benchmark.py" ]; then
            cp /workspace/run_alignment_benchmark.py "$SCRIPT_PATH"
            echo "  Copied script from /workspace"
        else
            echo "  ERROR: run_alignment_benchmark.py not found!"
            echo "  Place it in $WORKDIR or current directory and re-run with --skip-setup"
            exit 1
        fi
    fi

    echo ""
    echo ">>> [3/4] Pre-downloading models (this may take a few minutes)..."
    python3 -c "
from huggingface_hub import snapshot_download
import os

# Always download base
print('Downloading Mistral-7B-v0.1 (base)...')
snapshot_download('mistralai/Mistral-7B-v0.1', ignore_patterns=['*.bin'])
print('Base model cached.')

# Download instruct if needed
if os.environ.get('DOWNLOAD_INSTRUCT', 'false') == 'true':
    print('Downloading Mistral-7B-Instruct-v0.2...')
    snapshot_download('mistralai/Mistral-7B-Instruct-v0.2', ignore_patterns=['*.bin'])
    print('Instruct model cached.')
" 2>&1

    echo ""
    echo ">>> [4/4] Verifying GPU..."
    python3 -c "
import torch
if torch.cuda.is_available():
    name = torch.cuda.get_device_name(0)
    mem = torch.cuda.get_device_properties(0).total_mem / 1e9
    print(f'  GPU: {name} ({mem:.1f} GB)')
else:
    print('  WARNING: No GPU detected!')
"
else
    echo ">>> Skipping setup (--skip-setup)"
fi

# ─── Step 2: Run Experiment ───────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  LAUNCHING EXPERIMENT"
echo "═══════════════════════════════════════════════════════════════"

COMMON_ARGS="--output-dir $RESULTS_DIR --seed 42"
if [ "$MAX_Q" -gt 0 ]; then
    COMMON_ARGS="$COMMON_ARGS --max-questions $MAX_Q"
fi

if [ "$LAYER_SCAN" = true ]; then
    echo ">>> Running layer scan on instruct model..."
    python3 "$SCRIPT_PATH" \
        --model instruct \
        --mode scan \
        --layers 3,4,5,6,7,8 \
        --scan-n 100 \
        $COMMON_ARGS
    echo ""
    echo ">>> Layer scan complete. Check $RESULTS_DIR for results."

elif [ "$RUN_BOTH" = true ]; then
    echo ">>> Running full experiment on BASE model..."
    python3 "$SCRIPT_PATH" \
        --model base \
        --mode full \
        --layers 5 \
        $COMMON_ARGS

    echo ""
    echo ">>> Running full experiment on INSTRUCT model..."
    python3 "$SCRIPT_PATH" \
        --model instruct \
        --mode full \
        --layers 5 \
        $COMMON_ARGS

    echo ""
    echo ">>> Both models complete. Check $RESULTS_DIR for results."

elif [ "$RUN_INSTRUCT" = true ]; then
    echo ">>> Running full experiment on INSTRUCT model..."
    python3 "$SCRIPT_PATH" \
        --model instruct \
        --mode full \
        --layers 5 \
        $COMMON_ARGS

else
    echo ">>> Running full experiment on BASE model..."
    python3 "$SCRIPT_PATH" \
        --model base \
        --mode full \
        --layers 5 \
        $COMMON_ARGS
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  EXPERIMENT COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo "  Results directory: $RESULTS_DIR"
echo ""
ls -la "$RESULTS_DIR"/ 2>/dev/null || echo "  (no results files found)"
echo ""
echo "  To view summary:"
echo "    cat $RESULTS_DIR/alignment_summary_*.txt"
echo ""
echo "  To view full JSON:"
echo "    python3 -m json.tool $RESULTS_DIR/alignment_truthfulqa_*.json"
