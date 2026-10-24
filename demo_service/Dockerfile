FROM python:3.12-slim-bookworm
WORKDIR /service
COPY server.py traffic.py ./
RUN useradd -m -u 10002 demo && chown -R demo:demo /service
USER demo
CMD ["python", "server.py"]
