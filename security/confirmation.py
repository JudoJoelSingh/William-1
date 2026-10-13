"""
Confirmation Module for William-1 Safe Tool Execution Layer (v0.2).
Handles interactive user confirmation for sensitive (Level 2) and destructive (Level 3) actions.
- Accepts natural affirmative phrasings ("yes", "go ahead", "do it", "sure", "proceed", etc.)
- Strict rejection on negative words or timeout
- Ambiguous responses default to cancellation
"""

import re
import time
from typing import Optional, Callable, Tuple
from config import config
from security.permissions import get_consequence_prompt, requires_confirmation


class ConfirmationHandler:
    """Manages the verification, timeout, and evaluation of user confirmation responses."""

    AFFIRMATIVE_WORDS = {
        "yes", "yeah", "yep", "sure", "proceed", "continue", "confirm",
        "do it", "go ahead", "affirmative", "ok", "okay", "please do",
        "yup", "aye", "right ahead", "absolutely", "positive", "all good",
        "do that", "execute"
    }

    NEGATIVE_WORDS = {
        "no", "nope", "cancel", "stop", "abort", "don't", "dont",
        "negative", "wait", "nevermind", "never mind", "halt", "deny",
        "do not", "refuse"
    }

    @classmethod
    def evaluate_response(cls, user_utterance: str) -> Tuple[bool, str]:
        """
        Evaluates user utterance for confirmation.
        Returns: (is_confirmed, status_reason)
        """
        if not user_utterance or not user_utterance.strip():
            return False, f"No response received within {config.CONFIRMATION_TIMEOUT_SECONDS:.0f} seconds; action cancelled."

        # Normalize text
        cleaned = user_utterance.lower().strip()
        tokens = set(re.findall(r"\b[\w']+\b", cleaned))

        # 1. Check negative/cancellation first
        for neg in cls.NEGATIVE_WORDS:
            if neg in cleaned or neg in tokens:
                return False, "Cancelled by user."

        # 2. Check explicit affirmative phrases
        phrase_affirmatives = [
            "go ahead", "do it", "do that", "please do", "right ahead",
            "all good", "of course", "yes please", "yes do it"
        ]
        for phrase in phrase_affirmatives:
            if phrase in cleaned:
                return True, "User confirmed (phrase match)."

        # 3. Check affirmative single tokens
        for aff in cls.AFFIRMATIVE_WORDS:
            if aff in tokens or aff == cleaned:
                return True, "User confirmed."

        # 4. Ambiguous responses default to cancel
        return False, "Ambiguous response; action safely cancelled."

    @classmethod
    def _build_consequence_prompt(cls, tool_name: str, arguments: dict) -> str:
        """Build the security consequence prompt for a tool action."""
        return get_consequence_prompt(tool_name, arguments)

    @classmethod
    def _is_affirmative(cls, user_utterance: str) -> bool:
        """Return True when the user's response is an accepted confirmation."""
        confirmed, _ = cls.evaluate_response(user_utterance)
        return confirmed

    @classmethod
    def request_confirmation(
        cls,
        tool_name: str,
        arguments: dict,
        prompt_callback: Optional[Callable[[str], str]] = None,
    ) -> Tuple[bool, str]:
        """
        Prompts the user for confirmation if required.
        If prompt_callback is provided, invokes prompt_callback(consequence_prompt) -> user_reply.
        If prompt_callback is None, falls back to terminal input.
        """
        if not requires_confirmation(tool_name):
            return True, "No confirmation required."

        consequence_question = get_consequence_prompt(tool_name, arguments)

        if prompt_callback is not None:
            user_reply = prompt_callback(consequence_question)
        else:
            print(f"\n[Security Notice] {consequence_question}")
            try:
                user_reply = input("Confirmation (yes/no): ").strip()
            except (EOFError, KeyboardInterrupt):
                return False, "Input interrupted; cancelled."

        is_confirmed, reason = cls.evaluate_response(user_reply)
        return is_confirmed, reason
