#!/bin/bash
# CATALYST AI - Startup Script
cd /home/z/my-project/catalyst-ai
source venv/bin/activate
exec python -c "
import catalyst_ai, uvicorn
uvicorn.run(catalyst_ai.app, host='0.0.0.0', port=8000)
"
