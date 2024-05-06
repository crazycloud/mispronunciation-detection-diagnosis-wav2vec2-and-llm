import base64
import tempfile
from typing import Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from modal import Image, Secret, Stub, build, enter, gpu, web_endpoint

whisper_image = (
    Image.micromamba()
    .apt_install("ffmpeg", "espeak")
    .micromamba_install(
        "cudatoolkit=11.8",
        "cudnn=8.1.0",
        "cuda-nvcc",
        channels=["conda-forge", "nvidia"],
    )
    .pip_install(
        "torch==2.0.1",
        "transformers==4.37.2",
        "phonemizer",
    )
)

stub = Stub("phoneme-recognizer")
auth_scheme = HTTPBearer()


with whisper_image.imports():
    import sys
    import os
    # import torch
    from transformers import pipeline


class TranscriptionRequest(BaseModel):
    audio: str

@stub.cls(
    gpu=gpu.T4(),
    container_idle_timeout=120,
    keep_warm=1,
    image=whisper_image,
    secrets=[
        Secret.from_name("huggingface-secret-2"),
        Secret.from_name("whisper-web-auth-token"),
    ],
)
class Model:
    @build()
    @enter()
    def setup(self):
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model="facebook/wav2vec2-xlsr-53-espeak-cv-ft",
        )

    @web_endpoint(method="POST", label="phoneme-recognizer")
    def transcribe(
        self,
        request: TranscriptionRequest,
        token: HTTPAuthorizationCredentials = Depends(auth_scheme),
    ):
        # if token.credentials != os.environ["WHISPER_AUTH_TOKEN"]:
        #     raise HTTPException(
        #         status_code=status.HTTP_401_UNAUTHORIZED,
        #         detail="Incorrect bearer token",
        #         headers={"WWW-Authenticate": "Bearer"},
        #     )

        audio_data = base64.b64decode(request.audio.split(",")[1])

        with tempfile.NamedTemporaryFile(suffix=".mp3") as temp_audio:
            temp_audio.write(audio_data)

            outputs = self.pipe(
                temp_audio.name,
                chunk_length_s=30,
            )

        return outputs