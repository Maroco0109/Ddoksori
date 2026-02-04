def input_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not MODERATION_ENABLED:
        return {}

    # [핵심 변경] state의 user_query보다 '메시지 기록 내의 마지막 HumanMessage'를 최우선 순위로 둡니다.
    messages = state.get("messages", [])
    last_user_msg = None
    
    # 메시지 역순 탐색하여 가장 최근의 '사람' 메시지를 찾음
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg
            break

    # 1. 메시지 기록에 사용자의 발화가 아예 없거나, 마지막 메시지가 AI라면 루프 차단
    if not last_user_msg or (messages and not isinstance(messages[-1], HumanMessage)):
        logger.warning("[InputGuardrail] No new HumanMessage detected. Current last message is AI. Blocking.")
        return {
            "guardrail_blocked": True,
            "guardrail_type": "loop_prevention",
            "final_answer": "상담을 원하시는 구체적인 상황을 입력해 주세요.",
            "user_query": "" 
        }

    # 2. 실제 사용자 발화 추출
    user_query = last_user_msg.content.strip() if hasattr(last_user_msg, "content") else ""

    # 3. 봇의 시그니처 키워드 검사 (기존 유지 및 강화)
    # 봇이 스스로를 소개하는 표현이 포함되어 있다면 무조건 차단
    BOT_INDICATORS = ["소비자 분쟁 상담", "똑소리입니다", "도와 드리는", "도와드리는", "안내해 드립니다"]
    if any(indicator in user_query for indicator in BOT_INDICATORS):
        logger.warning(f"[InputGuardrail] Bot identity detected in message: {user_query[:50]}")
        return {
            "guardrail_blocked": True,
            "guardrail_type": "loop_prevention",
            "final_answer": "죄송합니다. 시스템 오류가 감지되었습니다. 궁금하신 내용을 다시 한번 말씀해 주시겠어요?",
            "user_query": ""
        }

    # 4. 유해성 검사 (Moderation)
    result = check_input(user_query)
    if result["blocked"]:
        return {
            "guardrail_blocked": True,
            "guardrail_type": "input",
            "final_answer": result["fallback_message"],
            "user_query": user_query,
        }

    # [핵심] 성공 시 state의 user_query를 실제 추출된 값으로 강제 업데이트하여 다음 노드로 전달
    return {
        "guardrail_blocked": False,
        "user_query": user_query,
    }