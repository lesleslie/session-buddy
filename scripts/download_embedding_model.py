#!/usr/bin/env python3
"""Download all-MiniLM-L6-v2 ONNX model for semantic search.

This script downloads the pre-converted ONNX model from HuggingFace.
The Xenova model is optimized for ONNX Runtime and requires no PyTorch.

Usage:
    python scripts/download_embedding_model.py
"""

import logging
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
except ImportError as e:
    print(f"❌ Missing required dependency: {e}")
    print("\nInstall with:")
    print("  uv pip install transformers huggingface_hub")
    print("\nOr install all dependencies:")
    print("  uv sync --group dev")
    raise SystemExit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def download_onnx_model() -> None:
    """Download Xenova/all-MiniLM-L6-v2 ONNX model from HuggingFace."""
    # Xenova provides pre-converted ONNX models
    model_name = "Xenova/all-MiniLM-L6-v2"

    logger.info(f"Downloading {model_name} from HuggingFace...")
    logger.info("This is a pre-converted ONNX model - no PyTorch required!")
    logger.info("")

    try:
        # Download model files including ONNX
        logger.info("Downloading model files (tokenizer + ONNX model)...")
        cache_dir = snapshot_download(
            repo_id=model_name,
            allow_patterns=[
                "*.json",
                "*.txt",
                "*.onnx",
                "model.*",
                "tokenizer*",
                "vocab*",
                "config*",
            ],
        )
        logger.info(f"✅ Model files downloaded to: {cache_dir}")

        # Verify ONNX model exists
        onnx_files = list(Path(cache_dir).glob("*.onnx"))
        if onnx_files:
            logger.info(f"✅ Found {len(onnx_files)} ONNX file(s):")
            for onnx_file in onnx_files:
                logger.info(f"  • {onnx_file.name}")
        else:
            logger.warning(
                "⚠️  No ONNX files found - model may still work with tokenizers"
            )

        logger.info("")
        logger.info("=" * 70)
        logger.info("✅ ONNX Embedding Model Downloaded Successfully!")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Model Details:")
        logger.info(f"  • Model: {model_name}")
        logger.info("  • Type: Pre-converted ONNX (no PyTorch needed)")
        logger.info(f"  • Cache: {cache_dir}")
        logger.info("  • Dimensions: 384")
        logger.info("  • Max tokens: 256 (recommended: 128)")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Update reflection adapter to use this model")
        logger.info("  2. Restart the MCP server")
        logger.info("  3. Use semantic search: reflect_on_past('your query')")
        logger.info("")

    except Exception as e:
        logger.exception(f"❌ Failed to download model: {e}")
        logger.info("\nTroubleshooting:")
        logger.info("  • Check internet connection")
        logger.info("  • Verify HuggingFace Hub is accessible")
        logger.info("  • Try: pip install --upgrade transformers huggingface_hub")
        raise SystemExit(1)


if __name__ == "__main__":
    download_onnx_model()
