"""
Brain Module for William-1 Personal AI Voice Companion.
Handles LLM reasoning, bounded context memory, topic transitions,
function/tool calling schemas, safe tool execution handoff,
and sentence-level token buffering for real-time speech.
"""

import json
import re
import time
from typing import List, Dict, Tuple, Generator, Optional, Any, Callable
from config import config
from ui import UI, presence
from tools.tool_manager import tool_manager
from memory.memory_manager import memory_manager


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class Brain:
    def __init__(self):
        self.api_key = config.LLM_API_KEY
        self.base_url = config.LLM_BASE_URL
        self.model = config.LLM_MODEL
        self.temperature = config.LLM_TEMPERATURE
        self.max_tokens = config.LLM_MAX_TOKENS
        self.max_history = config.MAX_HISTORY_TURNS
        self.system_prompt = config.SYSTEM_PROMPT

        # Bounded in-memory conversation history
        self.conversation_history: List[Dict[str, Any]] = []
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initializes the OpenAI-compatible LLM client."""
        if OpenAI is None:
            return

        if not self.api_key:
            return

        try:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.client = OpenAI(**kwargs)
        except Exception as e:
            UI.error_api(config.LLM_PROVIDER, f"Client initialization error: {e}")
            self.client = None

    def reset_history(self):
        """Clears the short-term conversation memory."""
        self.conversation_history.clear()

    def _clean_token_or_sentence(self, text: str) -> str:
        """
        Cleans markdown, code fences, emojis, and unpronounceable characters from text.
        """
        if not text:
            return ""

        # Remove markdown code blocks
        text = re.sub(r"```[\s\S]*?```", " Code snippet omitted. ", text)
        # Remove inline code marks
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove markdown headers (# Title)
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
        # Remove markdown links [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove bullet points and numbered list markers
        text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        # Remove emojis and unpronounceable symbols
        text = re.sub(r"[^\x00-\x7F]+", " ", text)
        # Strip leading role markers (e.g. 'assistant:', 'ai:', 'william:')
        text = re.sub(r"^(?:assistant|ai|william)\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:assistant|ai|william)\s+", "", text, flags=re.IGNORECASE)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text


    def _parse_json_tool_fallback(self, content: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Detects if the LLM emitted raw JSON tool call(s) instead of native tool_calls.
        Handles single tools, tool lists, and multiple JSON blocks for multi-tool composition.
        """
        if not content or "{" not in content:
            return []

        results: List[Tuple[str, Dict[str, Any]]] = []

        # 1. Check for JSON array of tool calls
        array_match = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
        if array_match:
            try:
                items = json.loads(array_match.group(0))
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            t_name = item.get("tool") or item.get("name")
                            t_args = item.get("arguments") or item.get("parameters") or {}
                            if t_name and tool_manager.is_tool_registered(t_name):
                                results.append((t_name, t_args))
                    if results:
                        return results
            except Exception:
                pass

        # 2. Check for object containing 'tools' or 'tool_calls' array
        obj_match = re.search(r"\{.*\}", content, re.DOTALL)
        if obj_match:
            try:
                data = json.loads(obj_match.group(0))
                if isinstance(data, dict):
                    tool_list = data.get("tools") or data.get("tool_calls")
                    if isinstance(tool_list, list):
                        for item in tool_list:
                            if isinstance(item, dict):
                                t_name = item.get("tool") or item.get("name")
                                t_args = item.get("arguments") or item.get("parameters") or {}
                                if t_name and tool_manager.is_tool_registered(t_name):
                                    results.append((t_name, t_args))
                        if results:
                            return results
                    elif data.get("type") == "tool_call" and "tool" in data:
                        t_name = data["tool"]
                        if tool_manager.is_tool_registered(t_name):
                            return [(t_name, data.get("arguments", {}))]
                    elif "tool" in data:
                        t_name = data["tool"]
                        if tool_manager.is_tool_registered(t_name):
                            return [(t_name, data.get("arguments", {}))]
                    elif "name" in data and "parameters" in data:
                        t_name = data["name"]
                        if tool_manager.is_tool_registered(t_name):
                            return [(t_name, data.get("parameters", {}))]
            except Exception:
                pass

        # 3. Check for standalone JSON objects in text
        for block in re.findall(r"\{[^{}]*\}", content):
            try:
                d = json.loads(block)
                if isinstance(d, dict):
                    t_name = d.get("tool") or d.get("name")
                    t_args = d.get("arguments") or d.get("parameters") or {}
                    if t_name and tool_manager.is_tool_registered(t_name):
                        results.append((t_name, t_args))
            except Exception:
                pass

        return results

    def _get_tool_intent_phrase(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Generates spoken narration announcing intent before action execution.
        """
        if tool_name == "open_application":
            app = arguments.get("application", "the application")
            from tools.applications import resolve_application_alias
            canonical = resolve_application_alias(app)
            display = config.APP_ALLOWLIST.get(canonical, {}).get("display_name", app.title())
            return f"Opening {display}..."
        elif tool_name == "close_application":
            app = arguments.get("application", "the application")
            from tools.applications import resolve_application_alias
            canonical = resolve_application_alias(app)
            display = config.APP_ALLOWLIST.get(canonical, {}).get("display_name", app.title())
            return f"Closing {display}..."
        elif tool_name == "open_url":
            url = arguments.get("url", "website")
            from tools.browser import _resolve_website_alias
            alias = _resolve_website_alias(url)
            return f"Opening {alias.capitalize()}..."
        elif tool_name == "search_web":
            q = arguments.get("query", "the web")
            return f"Searching the web for '{q}'..."
        elif tool_name == "open_folder":
            folder = arguments.get("folder", "documents")
            return f"Opening your {folder} folder..."
        elif tool_name == "open_file":
            path = arguments.get("file_path", "file")
            import os
            return f"Opening {os.path.basename(path)}..."
        elif tool_name == "delete_file":
            path = arguments.get("target_path", "target")
            import os
            return f"Deleting {os.path.basename(path)}..."
        elif tool_name == "list_directory":
            folder = arguments.get("folder", "folder")
            return f"Checking files in {folder}..."
        elif tool_name == "search_files":
            q = arguments.get("query", "files")
            return f"Searching for files matching '{q}'..."
        elif tool_name == "get_system_health":
            return "Checking system health..."
        elif tool_name == "get_battery_status":
            return "Checking battery status..."
        elif tool_name == "get_cpu_usage":
            return "Checking CPU load..."
        elif tool_name == "get_ram_usage":
            return "Checking memory usage..."
        elif tool_name == "get_disk_usage":
            return "Checking disk space..."
        elif tool_name == "get_recent_actions":
            return "Checking recent actions..."
        elif tool_name == "explain_last_action":
            return "Checking my action log..."
        elif tool_name == "mute":
            return "Muting the computer..."
        elif tool_name == "unmute":
            return "Unmuting the audio..."
        elif tool_name == "set_volume":
            lvl = arguments.get("level", 50)
            return f"Setting volume to {lvl} percent..."
        elif tool_name == "lock_computer":
            return "Locking the computer..."
        elif tool_name == "sleep_system":
            return "Putting the computer to sleep..."
        elif tool_name == "restart_system":
            return "Restarting the computer..."
        elif tool_name == "shutdown_system":
            return "Shutting down the computer..."
        elif tool_name == "save_memory":
            return "Saving that to your memory..."
        elif tool_name == "query_memory":
            return "Checking your saved memories..."
        elif tool_name == "list_memories":
            return "Retrieving your saved memories..."
        elif tool_name == "show_all_memories":
            return "Showing all memories by category..."
        elif tool_name == "update_project_status":
            proj = arguments.get("project_name", "the project")
            return f"Updating status for project {proj}..."
        elif tool_name == "show_project":
            proj = arguments.get("project_name", "the project")
            return f"Showing full record for project {proj}..."
        elif tool_name == "forget_memory":
            tgt = arguments.get("target", "memory")
            return f"Permanently erasing memory of '{tgt}'..."
        elif tool_name == "forget_memory_by_id":
            mid = arguments.get("memory_id", "")
            return f"Erasing memory record {mid}..."
        elif tool_name == "delete_project_memories":
            proj = arguments.get("project_name", "the project")
            return f"Deleting project memories for {proj}..."
        elif tool_name == "set_memory_mode":
            mode = "enabling" if arguments.get("enabled", True) else "disabling"
            return f"{mode.capitalize()} persistent memory..."
        elif tool_name == "configure_memory":
            return "Applying memory settings..."
        elif tool_name == "get_memory_settings":
            return "Fetching memory settings..."
        elif tool_name == "export_memories":
            return "Exporting your memories to a backup file..."
        elif tool_name == "import_memories":
            return "Importing memories from backup..."
        elif tool_name == "continue_project":
            proj = arguments.get("project_name", "your project")
            return f"Retrieving project status for {proj}..."
        elif tool_name == "why_decision":
            return "Searching decision history..."
        elif tool_name == "project_health":
            return "Checking project health..."
        elif tool_name == "generate_session_summary":
            return "Generating session summary..."
        elif tool_name == "record_project_event":
            return "Recording project event..."
        else:
            return f"Executing {tool_name.replace('_', ' ')}..."

    def _synthesize_natural_summary(
        self,
        tools_to_run: List[Tuple[str, Dict[str, Any]]],
        results: List[Dict[str, Any]]
    ) -> str:
        """
        Creates a clean single-sentence conversational summary of all executed actions,
        handling multi-tool composition and graceful degradation alternatives.
        """
        # 1. If any tool failed, explain and offer alternative
        failed = [r for r in results if not r.get("success", False)]
        if failed:
            first_fail = failed[0]
            msg = first_fail.get("message", "An action could not be completed.")
            return msg

        # 2. Rich telemetry & direct informational tool shortcuts
        direct_result_tools = {
            "get_system_health",
            "explain_last_action",
            "get_battery_status",
            "get_cpu_usage",
            "get_ram_usage",
            "get_disk_usage",
            "get_datetime",
            "list_directory",
            "search_files",
            "save_memory",
            "query_memory",
            "list_memories",
            "show_all_memories",
            "show_project",
            "update_project_status",
            "forget_memory",
            "forget_memory_by_id",
            "delete_project_memories",
            "set_memory_mode",
            "configure_memory",
            "get_memory_settings",
            "export_memories",
            "import_memories",
            "continue_project",
            "why_decision",
            "project_health",
            "generate_session_summary",
            "record_project_event",
        }
        if len(tools_to_run) == 1 and tools_to_run[0][0] in direct_result_tools:
            return results[0].get("message", "Action completed.")


        # 3. Multi-tool composition phrasing
        parts = []
        for (name, args), res in zip(tools_to_run, results):
            if name == "open_application":
                app = args.get("application", "app")
                from tools.applications import resolve_application_alias
                display = config.APP_ALLOWLIST.get(resolve_application_alias(app), {}).get("display_name", app.title())
                parts.append(f"opened {display}")
            elif name == "open_url":
                from tools.browser import _resolve_website_alias
                site = _resolve_website_alias(args.get("url", "website"))
                parts.append(f"opened {site.capitalize()} in your browser")
            elif name == "open_folder":
                folder = args.get("folder", "your project")
                parts.append(f"opened your {folder} folder")
            elif name == "mute":
                parts.append("muted the computer")
            elif name == "unmute":
                parts.append("unmuted system sound")
            elif name == "set_volume":
                parts.append(f"set volume to {args.get('level', 50)} percent")
            elif name == "lock_computer":
                parts.append("locked your workstation")
            elif name == "search_web":
                parts.append(f"searched for {args.get('query', '')}")
            elif name == "delete_file":
                import os
                parts.append(f"deleted {os.path.basename(args.get('target_path', 'target'))}")
            else:
                parts.append(f"completed {name.replace('_', ' ')}")

        if len(parts) == 1:
            return f"I've {parts[0]}."
        elif len(parts) == 2:
            return f"I've {parts[0]} and {parts[1]}."
        else:
            return f"I've {', '.join(parts[:-1])}, and {parts[-1]}."

    def _execute_and_report_tool_stream(
        self,
        tools_to_run: List[Tuple[str, Dict[str, Any]]],
        user_input: str,
        confirm_callback: Optional[Callable[[str], str]] = None,
    ) -> Generator[str, None, None]:
        """
        Executes an ordered batch of validated tools with:
        1. Single combined confirmation if any step is L2/L3.
        2. Spoken action narration before acting ("Opening VS Code... done").
        3. Reported back as one natural sentence with graceful degradation alternatives.
        """
        from security.permissions import requires_confirmation
        from security.confirmation import ConfirmationHandler

        # Step 1: Single combined confirmation if any action requires confirmation
        needs_confirm = [t for t in tools_to_run if requires_confirmation(t[0])]
        skip_confirm = False

        if needs_confirm:
            prompts = []
            for name, args in needs_confirm:
                prompts.append(ConfirmationHandler._build_consequence_prompt(name, args))

            if len(needs_confirm) == 1:
                combined_prompt = prompts[0]
            else:
                combined_prompt = "I need to perform the following sensitive actions: " + " Also, ".join(prompts)

            if confirm_callback:
                reply = confirm_callback(combined_prompt)
                if not ConfirmationHandler._is_affirmative(reply):
                    yield "Action cancelled. I did not proceed without your confirmation."
                    return
                skip_confirm = True
            else:
                print(f"\n[Security Notice] {combined_prompt}")
                try:
                    reply = input("Confirm action (yes/no): ").strip()
                except Exception:
                    reply = "no"
                if not ConfirmationHandler._is_affirmative(reply):
                    yield "Action cancelled. I did not proceed without your confirmation."
                    return
                skip_confirm = True

        # Step 2: Spoken action narration and execution loop
        results = []
        for name, args in tools_to_run:
            intent_phrase = self._get_tool_intent_phrase(name, args)
            yield intent_phrase

            presence.set_state("thinking")
            UI.print_tool_call(name, args)

            result = tool_manager.execute_tool(
                tool_name=name,
                arguments=args,
                user_request=user_input,
                confirm_callback=None,
                skip_confirmation=skip_confirm,
            )

            success = result.get("success", not result.get("cancelled", False))
            UI.print_tool_result(name, result.get("message", ""), success=success)
            results.append(result)

            if success:
                yield "Done."
            else:
                # Narrate degradation explanation immediately
                fail_msg = result.get("message", f"I couldn't complete {name.replace('_', ' ')}.")
                yield fail_msg

        # Step 3: Single cohesive natural sentence reporting the outcome
        telemetry_tools = {"get_system_health", "explain_last_action", "get_battery_status", "get_cpu_usage", "get_ram_usage", "get_disk_usage", "get_datetime", "list_directory", "search_files"}
        if len(tools_to_run) == 1 and tools_to_run[0][0] in telemetry_tools and results[0].get("success"):
            yield results[0].get("message", "")
            return

        tool_output_str = json.dumps(results, ensure_ascii=False)
        if self.client is not None:
            try:
                messages = [
                    {"role": "system", "content": self.system_prompt},
                ] + self.conversation_history + [
                    {
                        "role": "system",
                        "content": (
                            f"The following tools were executed in order for user request: '{user_input}'.\n"
                            f"Execution Results: {tool_output_str}\n"
                            f"Provide exactly one natural, conversational spoken sentence summarizing the outcome. "
                            f"If all succeeded, confirm them naturally together. "
                            f"If any failed, explain what failed and why, and proactively offer the nearest safe alternative."
                        )
                    }
                ]

                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=15.0,
                )

                spoken_reply = completion.choices[0].message.content or "Actions completed."
                cleaned = self._clean_token_or_sentence(spoken_reply)
                yield cleaned
                return
            except Exception as e:
                if config.DEBUG:
                    print(f"[Brain Secondary Call Error] {e}")

        # Deterministic fallback summary
        fallback_sentence = self._synthesize_natural_summary(tools_to_run, results)
        yield fallback_sentence


    def think(
        self,
        user_input: str,
        confirm_callback: Optional[Callable[[str], str]] = None,
    ) -> Tuple[str, float]:
        """
        Non-streaming LLM reasoning cycle with tool calling support.
        Returns: (spoken_response, turnaround_latency)
        """
        if not user_input or not user_input.strip():
            return "", 0.0

        user_input_cleaned = user_input.strip()
        start_time = time.time()

        presence.set_state("thinking")

        if self.client is None:
            if not self.api_key:
                UI.error_api("LLM", "No API key in .env.")
                return "My API key is not configured in the environment file.", 0.0

            self._init_client()
            if self.client is None:
                UI.error_api("LLM", "Unable to connect to reasoning client.")
                return "I am currently unable to connect to my reasoning engine.", 0.0

        # Add user turn to conversation memory
        self.conversation_history.append({
            "role": "user",
            "content": user_input_cleaned
        })
        memory_manager.note_session_event(f"User: {user_input_cleaned}")

        # Bound history
        max_messages = max(2, self.max_history * 2)
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

        # Retrieve context from memory
        memory_ctx = memory_manager.retrieve_context_for_prompt(user_input_cleaned)
        system_content = self.system_prompt
        if memory_ctx:
            system_content = (
                f"{self.system_prompt}\n\n{memory_ctx}\n\n"
                "Personalization Rule: Use retrieved memories and records quietly to tailor your response "
                "(technical depth, stack, style). Never volunteer private details unprompted, never recite "
                "the memory database, and never say 'According to my memory database'."
            )

        messages = [
            {"role": "system", "content": system_content}
        ] + self.conversation_history

        tools_param = tool_manager.get_schemas() if config.ENABLE_TOOLS else None

        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "timeout": 25.0,
            }
            if tools_param:
                kwargs["tools"] = tools_param
                kwargs["tool_choice"] = "auto"

            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # Check 1: Native tool_calls
            if message.tool_calls:
                tools_to_run = []
                for call in message.tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments) if call.function.arguments else {}
                    except Exception:
                        args = {}
                    tools_to_run.append((name, args))

                final_spoken = ""
                for sentence in self._execute_and_report_tool_stream(tools_to_run, user_input_cleaned, confirm_callback):
                    final_spoken += sentence + " "
                
                final_spoken = final_spoken.strip()
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_spoken
                })
                return final_spoken, time.time() - start_time

            # Check 2: Raw JSON tool call fallback in text content
            content = message.content or ""
            json_tools = self._parse_json_tool_fallback(content)
            if json_tools:
                final_spoken = ""
                for sentence in self._execute_and_report_tool_stream(json_tools, user_input_cleaned, confirm_callback):
                    final_spoken += sentence + " "
                    
                final_spoken = final_spoken.strip()
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_spoken
                })
                return final_spoken, time.time() - start_time

            # Outcome: Plain conversation or information answer
            cleaned_reply = self._clean_token_or_sentence(content)
            self.conversation_history.append({
                "role": "assistant",
                "content": cleaned_reply
            })
            return cleaned_reply, time.time() - start_time

        except Exception as e:
            UI.error_api(config.LLM_PROVIDER, str(e))
            fallback = "I encountered a problem with my reasoning engine."
            return fallback, time.time() - start_time
        finally:
            presence.set_state("idle")

    def think_stream(
        self,
        user_input: str,
        confirm_callback: Optional[Callable[[str], str]] = None,
    ) -> Generator[Tuple[str, float, float], None, None]:
        """
        Streaming LLM reasoning generator with dynamic tool-calling interception.
        Yields: (sentence_chunk, first_token_time, total_time)
        """
        if not user_input or not user_input.strip():
            return

        user_input_cleaned = user_input.strip()
        start_time = time.time()
        first_token_time = None

        presence.set_state("thinking")

        if self.client is None:
            if not self.api_key:
                UI.error_api("LLM", "No API key in .env.")
                yield "My API key is not configured in the environment file.", 0.0, 0.0
                return

            self._init_client()
            if self.client is None:
                UI.error_api("LLM", "Unable to connect to reasoning client.")
                yield "I am currently unable to connect to my reasoning engine.", 0.0, 0.0
                return

        self.conversation_history.append({
            "role": "user",
            "content": user_input_cleaned
        })
        memory_manager.note_session_event(f"User: {user_input_cleaned}")

        max_messages = max(2, self.max_history * 2)
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

        # Retrieve context from memory
        memory_ctx = memory_manager.retrieve_context_for_prompt(user_input_cleaned)
        system_content = self.system_prompt
        if memory_ctx:
            system_content = (
                f"{self.system_prompt}\n\n{memory_ctx}\n\n"
                "Personalization Rule: Use retrieved memories and records quietly to tailor your response "
                "(technical depth, stack, style). Never volunteer private details unprompted, never recite "
                "the memory database, and never say 'According to my memory database'."
            )

        messages = [
            {"role": "system", "content": system_content}
        ] + self.conversation_history

        tools_param = tool_manager.get_schemas() if config.ENABLE_TOOLS else None

        accumulated_full_reply = []
        token_buffer = ""
        tool_call_detected = False
        tool_calls_dict = {}

        sentence_end_regex = re.compile(r"([.!?]+(?:\s+|$))")

        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": True,
                "timeout": 25.0,
            }
            if tools_param:
                kwargs["tools"] = tools_param
                kwargs["tool_choice"] = "auto"

            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if not delta:
                    continue

                # Check for streaming tool call
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    tool_call_detected = True
                    for call_chunk in delta.tool_calls:
                        idx = call_chunk.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {"name": "", "arguments": ""}
                        if call_chunk.function and call_chunk.function.name:
                            tool_calls_dict[idx]["name"] += call_chunk.function.name
                        if call_chunk.function and call_chunk.function.arguments:
                            tool_calls_dict[idx]["arguments"] += call_chunk.function.arguments
                    continue

                if not delta.content:
                    continue

                text = delta.content
                if first_token_time is None:
                    first_token_time = time.time() - start_time

                token_buffer += text
                accumulated_full_reply.append(text)

                # Keep extracting complete sentences
                while True:
                    match = sentence_end_regex.search(token_buffer)
                    if not match:
                        break

                    split_idx = match.end()
                    sentence = token_buffer[:split_idx]
                    token_buffer = token_buffer[split_idx:]

                    cleaned_sentence = self._clean_token_or_sentence(sentence)
                    if cleaned_sentence:
                        yield (cleaned_sentence, first_token_time or 0.0, 0.0)

            # Handle tool execution if tool call was generated
            if tool_call_detected and tool_calls_dict:
                tools_to_run = []
                for idx in sorted(tool_calls_dict.keys()):
                    t_name = tool_calls_dict[idx]["name"]
                    t_args_raw = tool_calls_dict[idx]["arguments"]
                    try:
                        t_args = json.loads(t_args_raw) if t_args_raw else {}
                    except Exception:
                        t_args = {}
                    tools_to_run.append((t_name, t_args))

                final_reply = ""
                for sentence in self._execute_and_report_tool_stream(tools_to_run, user_input_cleaned, confirm_callback):
                    final_reply += sentence + " "
                    yield (sentence, first_token_time or 0.0, time.time() - start_time)
                
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_reply.strip()
                })
                return

            # Check for JSON tool fallback in accumulated text
            full_text = "".join(accumulated_full_reply).strip()
            json_tools = self._parse_json_tool_fallback(full_text)
            if json_tools:
                final_reply = ""
                for sentence in self._execute_and_report_tool_stream(json_tools, user_input_cleaned, confirm_callback):
                    final_reply += sentence + " "
                    yield (sentence, first_token_time or 0.0, time.time() - start_time)
                
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_reply.strip()
                })
                return

            # Speak leftover tokens in buffer
            if token_buffer.strip():
                cleaned_sentence = self._clean_token_or_sentence(token_buffer)
                if cleaned_sentence:
                    yield (cleaned_sentence, first_token_time or 0.0, 0.0)

            if full_text:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": full_text
                })

        except Exception as e:
            UI.error_api(config.LLM_PROVIDER, str(e))
            error_message = "I encountered a problem with my reasoning engine."
            yield (error_message, first_token_time or 0.0, time.time() - start_time)
        finally:
            presence.set_state("idle")
