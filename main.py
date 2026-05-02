"""
CLI entry point — python main.py
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.main import main

if __name__ == "__main__":
    asyncio.run(main())
