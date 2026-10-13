"""
Speech-to-Text (STT) Module for William-1.
Captures audio from the microphone and transcribes it into text using
local Faster-Whisper or cloud STT APIs, with smart VAD and wake-word support.
"""

import io
import re
import sys
import time
import tempfile
from typing import Optional, Tuple

try:
    import speech_recognition as sr
except ImportError:
    sr = None

from config import config
from ui import UI, presence


class SpeechToText:
    def __init__(self):
        self.engine_type = config.STT_ENGINE
        self.recognizer = None
        self.microphone = None
        self.whisper_model = None
        self._openai_client = None
        self.mic_error_detail = ""

        self._init_microphone()
        self._init_transcription_engine()

    def _init_microphone(self):
        """Initialize the speech recognizer and calibrate microphone with smart VAD."""
        if sr is None:
            self.mic_error_detail = "SpeechRecognition package not installed."
            UI.error_no_microphone(self.mic_error_detail)
            return

        try:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = config.MIC_ENERGY_THRESHOLD
            self.recognizer.dynamic_energy_threshold = config.MIC_DYNAMIC_ENERGY_THRESHOLD
            self.recognizer.pause_threshold = config.MIC_PAUSE_THRESHOLD
            self.recognizer.non_speaking_duration = 0.5

            mics = sr.Microphone.list_microphone_names()
            if not mics:
                self.mic_error_detail = "No audio input devices found."
                UI.error_no_microphone(self.mic_error_detail)
                self.microphone = None
                return

            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(
                    source, duration=config.MIC_CALIBRATION_DURATION
                )

        except Exception as e:
            self.mic_error_detail = str(e)
            UI.error_no_microphone(self.mic_error_detail)
            self.microphone = None

    def _init_transcription_engine(self):
        """Initialize the selected Whisper / STT engine."""
        if self.engine_type == "faster-whisper":
            try:
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(
                    config.WHISPER_MODEL_SIZE,
                    device=config.WHISPER_DEVICE,
                    compute_type=config.WHISPER_COMPUTE_TYPE,
                )
            except ImportError:
                self.whisper_model = None
            except Exception:
                self.whisper_model = None

        elif self.engine_type in ("openai-api", "groq-api"):
            try:
                from openai import OpenAI
                base_url = "https://api.groq.com/openai/v1" if self.engine_type == "groq-api" else config.LLM_BASE_URL
                self._openai_client = OpenAI(
                    api_key=config.LLM_API_KEY,
                    base_url=base_url if self.engine_type == "groq-api" else None,
                )
            except Exception:
                pass

    def check_wake_word(self, text: str) -> Tuple[bool, str]:
        """
        Checks if the transcribed text contains the wake word.
        Returns: (has_wake_word, remaining_prompt)
        """
        if config.ACTIVATION_MODE != "wake_word":
            return True, text

        wake_word = config.WAKE_WORD.lower().strip()
        text_lower = text.lower()

        patterns = [
            rf"\bhey\s+{re.escape(wake_word)}\b",
            rf"\bok\s+{re.escape(wake_word)}\b",
            rf"\b{re.escape(wake_word)}\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                end_pos = match.end()
                remaining = text[end_pos:].strip(" ,.?!")
                return True, remaining

        return False, ""

    def listen(self, timeout: float = 8.0) -> Optional[any]:
        """
        Listens to the microphone with dynamic VAD turn-taking.
        """
        if self.microphone is None or self.recognizer is None:
            return None

        try:
            if config.ACTIVATION_MODE == "push_to_talk":
                input("\n[Press ENTER to speak] ")

            presence.set_state("listening")
            if config.AUDIO_CUES_ENABLED:
                UI.play_audio_cue("listen_start")

            with self.microphone as source:
                audio_data = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=config.MIC_PHRASE_TIME_LIMIT,
                )

            if config.AUDIO_CUES_ENABLED:
                UI.play_audio_cue("listen_stop")

            return audio_data

        except sr.WaitTimeoutError:
            presence.set_state("idle")
            return None
        except Exception as e:
            presence.set_state("idle")
            UI.error_no_microphone(str(e))
            return None

    def transcribe(self, audio_data) -> Tuple[str, float]:
        """
        Transcribes captured audio into text.
        Returns: (transcribed_text, stt_latency_seconds)
        """
        if audio_data is None:
            return "", 0.0

        start_time = time.time()
        presence.set_state("transcribing")

        transcription = ""

        # Strategy 1: Local Faster-Whisper
        if self.whisper_model is not None:
            try:
                wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
                wav_stream = io.BytesIO(wav_bytes)
                segments, _ = self.whisper_model.transcribe(
                    wav_stream,
                    beam_size=5,
                    language="en",
                    vad_filter=True,
                )
                transcription = " ".join([segment.text for segment in segments]).strip()
            except Exception:
                transcription = ""

        # Strategy 2: Cloud API (OpenAI or Groq Whisper)
        if not transcription and self._openai_client and config.LLM_API_KEY:
            try:
                wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as temp_wav:
                    temp_wav.write(wav_bytes)
                    temp_wav.flush()
                    temp_wav.seek(0)
                    model_name = "whisper-large-v3" if self.engine_type == "groq-api" else "whisper-1"
                    with open(temp_wav.name, "rb") as f:
                        response = self._openai_client.audio.transcriptions.create(
                            model=model_name,
                            file=f,
                            language="en",
                        )
                    transcription = response.text.strip()
            except Exception as e:
                UI.error_api("STT Provider", str(e))

        # Strategy 3: SpeechRecognition Google fallback
        if not transcription and self.recognizer:
            try:
                transcription = self.recognizer.recognize_google(audio_data).strip()
            except (sr.UnknownValueError, sr.RequestError):
                transcription = ""
            except Exception:
                transcription = ""

        stt_latency = time.time() - start_time
        return transcription, stt_latency
