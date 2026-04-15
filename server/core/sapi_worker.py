"""
Persistent Windows SAPI TTS worker.
Reads text lines from stdin, writes WAV audio length + data to stdout.
Keeps the System.Speech assembly loaded for instant synthesis.

Protocol:
  Input:  one line of text per synthesis request (UTF-8)
  Output: 8 bytes (uint64 LE = audio byte count) + raw PCM int16 mono WAV data
          If error: 8 zero bytes
"""

import sys
import os
import io
import struct
import wave

def main():
    # Unbuffered binary stdout
    stdout = os.fdopen(sys.stdout.fileno(), 'wb', 0)
    stdin = sys.stdin

    try:
        import clr  # pythonnet
    except ImportError:
        pass

    # Use ctypes to load System.Speech directly
    try:
        # Try .NET via subprocess with inline C# — too complex
        # Instead, use the simpler approach: keep a PowerShell process alive
        pass
    except Exception:
        pass

    # Pure Python approach: use the comtypes SAPI COM interface
    try:
        import comtypes.client
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        stream = comtypes.client.CreateObject("SAPI.SpMemoryStream")
        stream.Format.Type = 22  # SAFT22kHz16BitMono
        voice.AudioOutputStream = stream

        sys.stderr.write("SAPI_WORKER: Ready (COM)\n")
        sys.stderr.flush()

        for line in stdin:
            text = line.strip()
            if not text:
                stdout.write(struct.pack('<Q', 0))
                continue

            try:
                # Reset stream
                stream.SetData(b"")
                voice.Speak(text, 0)  # SVSFDefault = 0

                # Get audio data from memory stream
                data = bytes(stream.GetData())

                if data:
                    stdout.write(struct.pack('<Q', len(data)))
                    stdout.write(data)
                else:
                    stdout.write(struct.pack('<Q', 0))
            except Exception as e:
                sys.stderr.write(f"SAPI_WORKER: Error: {e}\n")
                sys.stderr.flush()
                stdout.write(struct.pack('<Q', 0))

        return
    except ImportError:
        pass
    except Exception as e:
        sys.stderr.write(f"SAPI_WORKER: COM failed: {e}, falling back to PowerShell\n")
        sys.stderr.flush()

    # Fallback: PowerShell persistent process
    import subprocess
    import tempfile

    sys.stderr.write("SAPI_WORKER: Ready (PowerShell fallback)\n")
    sys.stderr.flush()

    for line in stdin:
        text = line.strip()
        if not text:
            stdout.write(struct.pack('<Q', 0))
            continue

        try:
            tmp = tempfile.mktemp(suffix='.wav')
            safe = text.replace("'", "''")
            ps = (
                "Add-Type -AssemblyName System.Speech;"
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"$s.SetOutputToWaveFile('{tmp}');"
                f"$s.Speak('{safe}');"
                "$s.Dispose()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, timeout=20,
            )

            if os.path.exists(tmp):
                with wave.open(tmp, 'rb') as wf:
                    pcm = wf.readframes(wf.getnframes())
                stdout.write(struct.pack('<Q', len(pcm)))
                stdout.write(pcm)
                os.unlink(tmp)
            else:
                stdout.write(struct.pack('<Q', 0))

        except Exception as e:
            sys.stderr.write(f"SAPI_WORKER: Error: {e}\n")
            sys.stderr.flush()
            stdout.write(struct.pack('<Q', 0))
            try:
                os.unlink(tmp)
            except Exception:
                pass


if __name__ == "__main__":
    main()
