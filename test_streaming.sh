#!/bin/bash
# Token Streaming Test Script
# Tests the SSE /chat/stream endpoint for real-time token streaming

echo "=========================================="
echo "Token Streaming Test - TC1: Basic Dispute"
echo "=========================================="

curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "노트북을 구매했는데 배터리가 부풀어올랐습니다. 환불 받을 수 있나요?",
    "chat_type": "dispute",
    "top_k": 3
  }' 2>&1 | head -100

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""
echo "Expected behavior:"
echo "1. Should see 'type': 'status' events for node progress"
echo "2. Should see 'type': 'token' events with individual tokens"
echo "3. Should see 'type': 'complete' event with final answer"
echo "4. If fallback occurs, should see 'type': 'fallback' event"
