#!/usr/bin/env python
"""
똑소리 Chat CLI 테스트 도구

사용법:
    python chat_cli.py                    # 대화형 모드
    python chat_cli.py --message "질문"   # 단일 질문 모드

대화형 명령어:
    /new      새 세션 시작
    /session  현재 세션 ID 표시
    /history  대화 기록 표시
    /quit     종료
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 상대 임포트 지원
sys.path.insert(0, str(Path(__file__).parent))

from client import ChatClient
from formatter import OutputFormatter


class ChatCLI:
    """CLI 테스트 도구"""

    def __init__(self, args: argparse.Namespace):
        self.client = ChatClient(args.server_url, timeout=args.timeout)
        self.formatter = OutputFormatter(args.verbose)
        self.session_id = args.session_id or str(uuid.uuid4())
        self.chat_type = args.chat_type
        self.log_enabled = not args.no_save
        self.log_dir = Path(args.log_dir)
        self.history: List[Dict[str, Any]] = []
        self.verbose = args.verbose
        self.server_url = args.server_url

    def run_interactive(self):
        """대화형 모드 실행"""
        self._print_header()

        if not self.client.health_check():
            print(f"[오류] 서버에 연결할 수 없습니다: {self.server_url}")
            print("       백엔드 서버가 실행 중인지 확인하세요.")
            return

        print("[연결됨] 서버 상태 정상\n")

        while True:
            try:
                user_input = input("[질문] > ").strip()
                if not user_input:
                    continue

                if user_input.startswith("/"):
                    if not self._handle_command(user_input):
                        break
                    continue

                self._process_message(user_input)

            except KeyboardInterrupt:
                print("\n\n종료합니다.")
                break
            except EOFError:
                print("\n종료합니다.")
                break
            except Exception as e:
                print(f"[오류] {e}")

    def run_single(self, message: str):
        """단일 질문 모드 실행"""
        if not self.client.health_check():
            print(f"[오류] 서버에 연결할 수 없습니다: {self.server_url}")
            sys.exit(1)

        self._process_message(message)

    def _print_header(self):
        """헤더 출력"""
        print("=" * 60)
        print("똑소리 Chat CLI (대화형 모드)")
        print("=" * 60)
        print(f"  서버: {self.server_url}")
        print(f"  세션 ID: {self.session_id}")
        print(f"  상담 유형: {self.chat_type}")
        print("-" * 60)
        print("  명령어: /new, /session, /history, /quit")
        print("=" * 60)

    def _process_message(self, message: str):
        """메시지 처리 및 응답 출력"""
        request = {
            "message": message,
            "session_id": self.session_id,
            "chat_type": self.chat_type,
            "debug": True,
        }

        print("\n처리 중...")

        try:
            response = self.client.send_message(
                message=message,
                session_id=self.session_id,
                chat_type=self.chat_type,
                debug=True,
            )

            # 응답을 딕셔너리로 변환
            response_dict = {
                "session_id": response.session_id,
                "answer": response.answer,
                "chunks_used": response.chunks_used,
                "model": response.model,
                "sources": response.sources,
                "has_sufficient_evidence": response.has_sufficient_evidence,
                "clarifying_questions": response.clarifying_questions,
                "domain": response.domain,
                "similar_cases": response.similar_cases,
                "related_laws": response.related_laws,
                "related_criteria": response.related_criteria,
                "node_timings": response.node_timings,
                "request_id": response.request_id,
                "total_time_ms": response.total_time_ms,
            }

            # 세션 ID 업데이트 (첫 요청 시)
            self.session_id = response.session_id

            # 히스토리 저장
            self.history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "request": request,
                    "response": response_dict,
                }
            )

            # 출력
            output = self.formatter.format_response(response_dict, request)
            print(output)

            # 로그 저장
            if self.log_enabled:
                self._save_log(request, response_dict)

        except Exception as e:
            print(f"[오류] 요청 실패: {e}")

    def _handle_command(self, command: str) -> bool:
        """
        슬래시 명령어 처리

        Returns:
            True: 계속 진행
            False: 종료
        """
        cmd = command.lower().strip()

        if cmd in ["/quit", "/exit", "/q"]:
            print("종료합니다.")
            return False

        elif cmd == "/new":
            self.session_id = str(uuid.uuid4())
            self.history = []
            print(f"[새 세션] 세션 ID: {self.session_id}")

        elif cmd == "/session":
            print("[세션 정보]")
            print(f"  세션 ID: {self.session_id}")
            print(f"  상담 유형: {self.chat_type}")
            print(f"  대화 수: {len(self.history)}")

        elif cmd == "/history":
            if not self.history:
                print("[히스토리] 대화 기록이 없습니다.")
            else:
                print("[히스토리]")
                for i, h in enumerate(self.history, 1):
                    msg = h["request"]["message"]
                    ts = h["timestamp"][:19]
                    answer_preview = (
                        h["response"]["answer"][:50] + "..."
                        if len(h["response"]["answer"]) > 50
                        else h["response"]["answer"]
                    )
                    print(f"  [{i}] {ts}")
                    print(f"      Q: {msg}")
                    print(f"      A: {answer_preview}")

        elif cmd == "/help":
            print("[명령어]")
            print("  /new      - 새 세션 시작")
            print("  /session  - 현재 세션 정보")
            print("  /history  - 대화 기록")
            print("  /quit     - 종료")

        else:
            print(f"[알 수 없는 명령어] {command}")
            print("  /help 로 명령어 목록을 확인하세요.")

        return True

    def _save_log(self, request: Dict[str, Any], response: Dict[str, Any]):
        """로그 저장"""
        today = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H%M%S")

        log_path = self.log_dir / today
        log_path.mkdir(parents=True, exist_ok=True)

        filename = f"{time_str}_{self.session_id[:8]}.json"
        filepath = log_path / filename

        log_entry = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "request": request,
            "response": response,
            "cli_metadata": {
                "version": "1.0.0",
                "chat_type": self.chat_type,
                "verbose": self.verbose,
            },
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)

        print(f"[로그 저장] {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="똑소리 Chat CLI 테스트 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python chat_cli.py                           # 대화형 모드
  python chat_cli.py -m "노트북 환불 방법"     # 단일 질문
  python chat_cli.py -t dispute                # 분쟁 상담 모드
  python chat_cli.py --session-id abc123       # 기존 세션 이어서
        """,
    )

    parser.add_argument(
        "--server-url",
        "-s",
        default="http://localhost:8000",
        help="백엔드 서버 URL (기본: http://localhost:8000)",
    )
    parser.add_argument(
        "--chat-type",
        "-t",
        choices=["dispute", "general"],
        default="general",
        help="상담 유형 (기본: general)",
    )
    parser.add_argument(
        "--message", "-m", help="단일 질문 메시지 (대화형 모드 대신 사용)"
    )
    parser.add_argument("--session-id", help="기존 세션 ID (멀티턴 대화용)")
    parser.add_argument(
        "--log-dir", default="logs/cli", help="로그 저장 디렉토리 (기본: logs/cli)"
    )
    parser.add_argument("--no-save", action="store_true", help="로그 저장 안 함")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 출력 모드")
    parser.add_argument(
        "--timeout", type=int, default=120, help="요청 타임아웃 초 (기본: 120)"
    )

    args = parser.parse_args()

    cli = ChatCLI(args)

    if args.message:
        cli.run_single(args.message)
    else:
        cli.run_interactive()


if __name__ == "__main__":
    main()
