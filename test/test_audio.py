def capture_voice():
    return streamin.read(CHUNK)

def play_audio(audio_data):
    streamout.write(audio_data)