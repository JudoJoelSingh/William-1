"""
Text-to-Speech (TTS) Module for William-1.
Converts text into spoken audio with pipelined streaming synthesis,
fine-tuned natural conversational pacing, and barge-in interruption.
"""

import os
import re
import time
import threading
from typing import Optional, Generator, Tuple
from config import config
from ui import UI, presence

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class TextToSpeech:
    def __init__(self):
        self.engine_type = config.TTS_ENGINE
        self.pyttsx3_engine = None
        self._openai_client = None
        self._lock = threading.Lock()
        self._is_speaking = False
        self._interrupted = threading.Event()

        self._init_engine()

    def _init_engine(self):
        """Initializes the active TTS engine with fine-tuned conversational parameters."""
        if self.engine_type == "pyttsx3":
            if pyttsx3 is None:
                UI.error_tts("pyttsx3 library is not installed.")
                return

            try:
                self.pyttsx3_engine = pyttsx3.init()
                self.pyttsx3_engine.setProperty("rate", config.VOICE_RATE)
                self.pyttsx3_engine.setProperty("volume", config.VOICE_VOLUME)

                if config.VOICE_ID:
                    self.pyttsx3_engine.setProperty("voice", config.VOICE_ID)
                else:
                    voices = self.pyttsx3_engine.getProperty("voices")
                    if voices and len(voices) > 0:
                        for v in voices:
                            if any(k in v.name.lower() for k in ["david", "zira", "george", "mark", "english"]):
                                self.pyttsx3_engine.setProperty("voice", v.id)
                                break
            except Exception as e:
                UI.error_tts(f"Failed to initialize pyttsx3 driver: {e}")
                self.pyttsx3_engine = None

        elif self.engine_type == "openai-api":
            try:
                if OpenAI is not None and config.LLM_API_KEY:
                    self._openai_client = OpenAI(api_key=config.LLM_API_KEY)
            except Exception as e:
                UI.error_tts(f"Failed to initialize OpenAI TTS client: {e}")

    def stop_speaking(self):
        """Signals William to immediately stop speaking (Barge-in)."""
        self._interrupted.set()
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.stop()
            except Exception:
                pass
        self._is_speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def speak_stream(self, sentence_generator: Generator[Tuple[str, float, float], None, None]) -> Tuple[float, float]:
        """
        Consumes streamed sentences from the LLM and speaks them sentence-by-sentence
        with zero perceived latency.
        Returns: (first_speech_latency_sec, total_tts_sec)
        """
        self._interrupted.clear()
        self._is_speaking = True
        first_speech_time = None
        start_time = time.time()

        UI.print_assistant_start(config.ASSISTANT_NAME)
        presence.set_state("speaking")

        with self._lock:
            try:
                if self.pyttsx3_engine is None and self.engine_type == "pyttsx3":
                    self._init_engine()

                for sentence, ttft, _ in sentence_generator:
                    if self._interrupted.is_set():
                        UI.print_interrupted()
                        if config.AUDIO_CUES_ENABLED:
                            UI.play_audio_cue("interrupted")
                        break

                    if not sentence or not sentence.strip():
                        continue

                    # Record when audio begins
                    if first_speech_time is None:
                        first_speech_time = time.time() - start_time

                    # Print chunk to terminal
                    UI.print_assistant_chunk(sentence)

                    # Speak sentence via active engine
                    if self.engine_type == "pyttsx3" and self.pyttsx3_engine:
                        self.pyttsx3_engine.say(sentence)
                        self.pyttsx3_engine.runAndWait()

                    elif self.engine_type == "openai-api" and self._openai_client:
                        self._speak_openai_sentence(sentence)

            except Exception as e:
                UI.error_tts(str(e))
                self.pyttsx3_engine = None

        UI.print_assistant_end()
        self._is_speaking = False
        presence.set_state("idle")

        total_tts_time = time.time() - start_time
        return (first_speech_time or 0.0), total_tts_time

    def _speak_openai_sentence(self, sentence: str):
        """Helper to stream individual sentences via OpenAI TTS."""
        try:
            import sounddevice as sd
            import soundfile as sf
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_mp3 = f.name

            response = self._openai_client.audio.speech.create(
                model="tts-1",
                voice=config.TTS_OPENAI_VOICE,
                input=sentence,
            )
            response.stream_to_file(temp_mp3)

            if not self._interrupted.is_set():
                data, fs = sf.read(temp_mp3)
                sd.play(data, fs)
                sd.wait()

            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
        except Exception as e:
            UI.error_tts(f"OpenAI TTS playback error: {e}")

    def speak(self, text: str) -> float:
        """Synchronous playback using a fresh pyttsx3 engine."""

        if not text or not text.strip():
            return 0.0

        start_time = time.time()

        try:
            if self.engine_type == "pyttsx3":
                import pyttsx3

                # Create a fresh SAPI engine for every speech call.
                engine = pyttsx3.init()

                engine.setProperty("rate", config.VOICE_RATE)
                engine.setProperty("volume", config.VOICE_VOLUME)

                if config.VOICE_ID:
                    engine.setProperty("voice", config.VOICE_ID)
                else:
                    voices = engine.getProperty("voices")
                    if voices:
                        for v in voices:
                            if any(
                                k in v.name.lower()
                                for k in ["david", "zira", "george", "mark", "english"]
                            ):
                                engine.setProperty("voice", v.id)
                                break

                self._is_speaking = True
                presence.set_state("speaking")

                UI.print_assistant_start(config.ASSISTANT_NAME)
                UI.print_assistant_chunk(text)

                engine.say(text)
                engine.runAndWait()

                # Explicitly stop and destroy this engine.
                engine.stop()
                del engine

                self._is_speaking = False
                presence.set_state("idle")
                UI.print_assistant_end()

                return time.time() - start_time

            # Keep the existing streaming/API behavior for other engines.
            def text_gen():
                yield text, 0.0, 0.0

            ttft, total = self.speak_stream(text_gen())
            return total

        except Exception as e:
            self._is_speaking = False
            presence.set_state("idle")
            UI.error_tts(str(e))
            return time.time() - start_time
