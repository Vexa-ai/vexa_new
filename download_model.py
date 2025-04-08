import os
os.environ['HF_HOME'] = '.'
from faster_whisper import WhisperModel

model_size = "medium"

model = WhisperModel(model_size, device="cuda", compute_type="float16")