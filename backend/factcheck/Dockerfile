FROM mwader/static-ffmpeg:7.1@sha256:32dfd1df302753d47fb4a87344b5ba005c9cae8e58b4d842959fc387fd004a01 AS ffmpeg

FROM public.ecr.aws/lambda/python:3.12@sha256:9531d39617b0966d2238cd30328087d53803110d50948feca99d29437422cffa

COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /ffprobe /usr/local/bin/ffprobe

COPY factcheck/requirements-worker.txt ${LAMBDA_TASK_ROOT}/requirements-worker.txt
RUN pip install --no-cache-dir \
        -r ${LAMBDA_TASK_ROOT}/requirements-worker.txt \
        --target ${LAMBDA_TASK_ROOT} \
    && python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small', local_dir='/opt/models/faster-whisper-small')"

COPY core ${LAMBDA_TASK_ROOT}/core
COPY factcheck ${LAMBDA_TASK_ROOT}/factcheck

ENV WHISPER_MODEL_PATH=/opt/models/faster-whisper-small \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8 \
    HF_HUB_OFFLINE=1

CMD ["factcheck.worker.lambda_handler"]

