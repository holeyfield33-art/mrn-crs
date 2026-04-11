#!/usr/bin/env bash
# Quick smoke-test against a running CRS instance.
set -euo pipefail

BASE="${CRS_URL:-http://localhost:8000}"

echo "=== Health check ==="
curl -s "$BASE/health" | python3 -m json.tool

echo ""
echo "=== POST /reason ==="
REASON=$(curl -s -X POST "$BASE/reason" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "demo-agent",
    "premise": "All humans are mortal",
    "inference_type": "deductive",
    "conclusion": "Socrates is mortal",
    "confidence": 0.95
  }')
echo "$REASON" | python3 -m json.tool
STEP_ID=$(echo "$REASON" | python3 -c "import sys,json; print(json.load(sys.stdin)['step_id'])")
FP=$(echo "$REASON" | python3 -c "import sys,json; print(json.load(sys.stdin)['fingerprint'])")

echo ""
echo "=== GET /trace?fingerprint=$FP ==="
curl -s "$BASE/trace?fingerprint=$FP" | python3 -m json.tool

echo ""
echo "=== POST /consensus/frame ==="
FRAME=$(curl -s -X POST "$BASE/consensus/frame" \
  -H "Content-Type: application/json" \
  -d "{\"competing_steps\": [\"$STEP_ID\"]}")
echo "$FRAME" | python3 -m json.tool
FRAME_ID=$(echo "$FRAME" | python3 -c "import sys,json; print(json.load(sys.stdin)['frame_id'])")

echo ""
echo "=== POST /consensus/update ==="
curl -s -X POST "$BASE/consensus/update" \
  -H "Content-Type: application/json" \
  -d "{\"frame_id\": \"$FRAME_ID\", \"step_id\": \"$STEP_ID\", \"summary\": \"Strong deductive result\", \"confidence\": 0.92}" \
  | python3 -m json.tool

echo ""
echo "=== GET /consensus/$FRAME_ID ==="
curl -s "$BASE/consensus/$FRAME_ID" | python3 -m json.tool

echo ""
echo "Demo complete."
