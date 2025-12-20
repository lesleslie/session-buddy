#!/usr/bin/env python3
"""Debug server startup with enhanced error logging."""

import logging
import sys
import traceback
from pathlib import Path

# Setup comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(Path.home() / ".claude/logs/session-buddy-debug.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

try:
    from session_buddy.server import main

    logger.info("Starting session-buddy in HTTP mode with debug logging...")
    main(http_mode=True, http_port=8678)
except Exception as e:
    logger.exception(f"Server startup failed: {e}")
    logger.exception(f"Full traceback:\n{traceback.format_exc()}")
    raise
