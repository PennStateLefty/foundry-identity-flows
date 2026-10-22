FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock.txt ./
COPY src ./src
RUN --mount=type=secret,id=pip_config,required=true,target=/etc/pip.conf \
    python -m pip install --no-cache-dir -c requirements.lock.txt .
USER vscode
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "identity_lab.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
