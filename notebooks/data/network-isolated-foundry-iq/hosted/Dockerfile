ARG UV_IMAGE
ARG PYTHON_IMAGE
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /uvx /bin/
WORKDIR /app/user_agent
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --frozen --no-dev --no-install-project
COPY main.py egress_probe.py ./
RUN .venv/bin/python -m compileall -q main.py egress_probe.py
EXPOSE 8088
CMD ["/app/user_agent/.venv/bin/python", "main.py"]
