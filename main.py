"""
Main Entry Point for William-1 Personal AI Voice Assistant (v0.2).
Orchestrates the live voice conversation & tool execution loop:
- Startup diagnostic self-check (apps, roots, libraries)
- Time-of-day companion greeting
- Crisp intent routing -> tool calling -> natural result phrasing
- Multi-tier permission validation & interactive confirmation
- Color-coded terminal UX for tool calls, results, and presence
- Dual audit logging (text + JSONL)
- Automated verification suite (--demo)
"""

import sys
import time
import argparse
from typing import Optional
from config import config
from ui import UI, presence
from speech_to_text import SpeechToText
from brain import Brain
from text_to_speech import TextToSpeech
from tools.tool_manager import tool_manager
from demo_runner import run_demo_suite, run_safety_test_suite
try:
    from ui import dashboard
except ImportError:
    dashboard = None


class WilliamAssistant:
    def __init__(self):
        # 1. Startup validation & self-check diagnostics
        is_valid, errors, warnings = config.validate()
        if not is_valid:
            UI.print_setup_error(errors)

        # 2. Time-aware opener + optional "Last time we..." recap
        recap = None
        try:
            from memory.memory_manager import memory_manager
            recap = memory_manager.get_last_session_recap()
        except Exception:
            recap = None

        base_greeting = config.get_daily_greeting()
        if recap:
            self.daily_greeting = f"{base_greeting} {recap}"
        else:
            self.daily_greeting = base_greeting

        # 3. Display assistant banner
        tool_count = len(tool_manager._registry)
        UI.print_banner(
            name=config.ASSISTANT_NAME,
            mode=config.ACTIVATION_MODE,
            model=config.LLM_MODEL,
            stt=config.STT_ENGINE,
            tts=config.TTS_ENGINE,
            barge_in=config.BARGE_IN_ENABLED,
            greeting=self.daily_greeting,
            tools_enabled=config.ENABLE_TOOLS,
            tool_count=tool_count,
        )

        # 4. Display startup diagnostics table
        self_check_report = config.run_startup_self_check()
        UI.print_startup_diagnostics(self_check_report)

        if warnings:
            for w in warnings:
                print(f"[Config Notice] {w}")
            print()

        # 5. Initialize core components
        self.stt = SpeechToText()
        self.brain = Brain()
        self.tts = TextToSpeech()
        self.is_running = True

    def _is_stop_phrase(self, text: str) -> bool:
        """Checks whether the user utterance contains a shutdown command."""
        text_normalized = text.lower().strip()
        text_normalized = "".join(c for c in text_normalized if c.isalnum() or c.isspace())

        for stop_phrase in config.STOP_PHRASES:
            if stop_phrase in text_normalized:
                return True
        return False

    def _voice_confirmation_callback(self, consequence_question: str) -> str:
        """
        Speaks the consequence question and captures the user's spoken confirmation within timeout.
        """
        UI.print_confirmation_prompt(consequence_question)
        self.tts.speak(consequence_question)

        # Listen for confirmation reply with configurable timeout
        presence.set_state("listening")
        audio_data = self.stt.listen(timeout=config.CONFIRMATION_TIMEOUT_SECONDS)
        if audio_data is None:
            return ""

        user_reply, _ = self.stt.transcribe(audio_data)
        UI.print_user_speech(f"(Confirmation) {user_reply}")
        return user_reply

    def _text_confirmation_callback(self, consequence_question: str) -> str:
        """
        Prompts for confirmation in text console mode.
        """
        UI.print_confirmation_prompt(consequence_question)
        try:
            user_reply = input("Confirm action (yes/no): ").strip()
            return user_reply
        except (EOFError, KeyboardInterrupt):
            return "no"

    def _handle_session_end(self, confirm_callback=None):
        """Generates episodic session summary, requests approval, and persists."""
        try:
            from memory.memory_manager import memory_manager
            draft = memory_manager.generate_session_summary(approved=False)
            summary_text = draft.get("message", "")
            if summary_text and "Session summary draft:" in summary_text:
                clean_summary = summary_text.replace("Session summary draft:\n", "").strip()
                prompt = (
                    f"Session summary:\n{clean_summary}\n\n"
                    "Would you like me to save this session summary to episodic memory? (yes/no): "
                )
                if confirm_callback:
                    ans = confirm_callback(prompt)
                else:
                    try:
                        ans = input(f"\n[Session Wrap-up]\n{prompt}").strip()
                    except Exception:
                        ans = "no"
                if ans.lower() in ("yes", "y", "sure", "ok"):
                    res = memory_manager.generate_session_summary(approved=True)
                    print(f"\n[Memory] {res.get('message')}")
        except Exception as e:
            if config.DEBUG:
                print(f"[Session Summary Notice] {e}")

    def run_voice_loop(self):
        """Runs the live streaming conversational voice loop with tool calling."""
        self.tts.speak(self.daily_greeting)
        presence.set_state("idle")

        while self.is_running:
            try:
                # 1. Listen with smart VAD
                audio_data = self.stt.listen(timeout=8.0)
                if audio_data is None:
                    time.sleep(0.05)
                    continue

                # 2. Transcribe speech
                user_text, stt_latency = self.stt.transcribe(audio_data)
                if not user_text or not user_text.strip():
                    UI.error_unintelligible()
                    presence.set_state("idle")
                    continue

                # 3. Wake-word check (if wake_word mode is active)
                has_wake, prompt = self.stt.check_wake_word(user_text)
                if not has_wake:
                    presence.set_state("idle")
                    continue

                if config.ACTIVATION_MODE == "wake_word" and not prompt.strip():
                    self.tts.speak("Yes, I am listening.")
                    presence.set_state("idle")
                    continue

                active_prompt = prompt if config.ACTIVATION_MODE == "wake_word" else user_text
                UI.print_user_speech(active_prompt)

                # 4. Check for stop command
                if self._is_stop_phrase(active_prompt):
                    farewell = f"Goodbye! Shutting down {config.ASSISTANT_NAME}."
                    self.tts.speak(farewell)
                    self.is_running = False
                    break

                # 5. Reasoning & Safe Tool Execution Pipeline
                if config.STREAM_RESPONSES:
                    sentence_stream = self.brain.think_stream(
                        active_prompt,
                        confirm_callback=self._voice_confirmation_callback,
                    )
                    tts_start_lat, total_tts_time = self.tts.speak_stream(sentence_stream)

                    if config.LATENCY_TRACKING:
                        total_turnaround = stt_latency + tts_start_lat
                        UI.print_telemetry({
                            "stt_sec": stt_latency,
                            "first_token_sec": tts_start_lat,
                            "tts_sec": total_tts_time,
                            "total_sec": total_turnaround,
                        })
                else:
                    ai_response, llm_latency = self.brain.think(
                        active_prompt,
                        confirm_callback=self._voice_confirmation_callback,
                    )
                    if ai_response:
                        self.tts.speak(ai_response)
                        if config.LATENCY_TRACKING:
                            UI.print_telemetry({
                                "stt_sec": stt_latency,
                                "llm_sec": llm_latency,
                                "tts_sec": 0.0,
                                "total_sec": stt_latency + llm_latency,
                            })

                presence.set_state("idle")

            except KeyboardInterrupt:
                print("\n")
                self.tts.speak("Goodbye!")
                self.is_running = False
                break
            except Exception as e:
                print(f"\n[Loop Recovery] Handled exception: {e}")
                presence.set_state("idle")
                time.sleep(0.5)

        self._handle_session_end(confirm_callback=self._voice_confirmation_callback)
        print(f"\n[{config.ASSISTANT_NAME}-1 Session Ended]")

    def run_text_loop(self):
        """Interactive text console mode."""
        self.tts.speak(f"{self.daily_greeting} in text console mode.")
        presence.set_state("idle")

        while self.is_running:
            try:
                user_text = input("\nYou: ").strip()
                if not user_text:
                    continue

                if self._is_stop_phrase(user_text):
                    self.tts.speak(f"Goodbye! Shutting down {config.ASSISTANT_NAME}.")
                    self.is_running = False
                    break

                if config.STREAM_RESPONSES:
                    sentence_stream = self.brain.think_stream(
                        user_text,
                        confirm_callback=self._text_confirmation_callback,
                    )
                    self.tts.speak_stream(sentence_stream)
                else:
                    ai_response, _ = self.brain.think(
                        user_text,
                        confirm_callback=self._text_confirmation_callback,
                    )
                    if ai_response:
                        self.tts.speak(ai_response)

                presence.set_state("idle")

            except (KeyboardInterrupt, EOFError):
                print("\n[Exiting text console...]")
                self.is_running = False
                break
            except Exception as e:
                print(f"\n[Error] {e}")

        self._handle_session_end(confirm_callback=self._text_confirmation_callback)
        print(f"\n[{config.ASSISTANT_NAME}-1 Session Ended]")


def main():
    parser = argparse.ArgumentParser(description=f"{config.ASSISTANT_NAME}-1 Personal AI Voice Assistant (v0.3)")
    parser.add_argument(
        "--text",
        action="store_true",
        help="Run in interactive text console mode."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the automated Phase 2 validation suite and exit."
    )
    parser.add_argument(
        "--safety-test",
        action="store_true",
        help="Run the pre-scripted safety demo to test the Tool Manager's defenses."
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Run in live dashboard observability mode."
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Run the interactive terminal Memory Dashboard."
    )
    parser.add_argument(
        "--memory-test",
        action="store_true",
        help="Run the automated Phase 3 safety and privacy verification walkthrough."
    )
    args = parser.parse_args()

    # If --memory is requested, run the interactive memory dashboard
    if args.memory:
        from memory.memory_dashboard import run_memory_dashboard
        run_memory_dashboard()
        sys.exit(0)

    # If --memory-test is requested, run the automated Phase 3 walkthrough
    if args.memory_test:
        from memory.memory_test_suite import run_memory_test_walkthrough
        success = run_memory_test_walkthrough()
        sys.exit(0 if success else 1)

    # If --demo is requested, execute the automated validation suite
    if args.demo:
        success = run_demo_suite()
        sys.exit(0 if success else 1)

    if args.safety_test:
        success = run_safety_test_suite()
        sys.exit(0 if success else 1)

    assistant = WilliamAssistant()

    if args.dashboard and dashboard:
        dashboard.run_standalone(assistant=assistant)
        sys.exit(0)

    try:
        # If mic is unavailable or --text flag passed, fallback cleanly
        if args.text or assistant.stt.microphone is None:
            if assistant.stt.microphone is None and not args.text:
                print("\n[Notice] No active microphone detected. Running in interactive text console.\n")
            assistant.run_text_loop()
        else:
            assistant.run_voice_loop()
    finally:
        pass


if __name__ == "__main__":
    main()
