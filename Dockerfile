FROM python:3.11-slim
LABEL org.opencontainers.image.source="https://github.com/Unique50101/uniquechat"
LABEL org.opencontainers.image.description="Local AI chat with Hugging Face models"
ENV HF_HOME=/cache/huggingface
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && python -m pip install --no-cache-dir .
EXPOSE 7860
CMD ["python","-c","from uniquechat.server import serve; serve(inbrowser=False, bind='0.0.0.0')"]
