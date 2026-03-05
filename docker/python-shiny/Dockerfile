FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    shiny \
    shinywidgets \
    plotly \
    pandas \
    jinja2

COPY python-app/app.py /app/app.py

EXPOSE 3839

CMD ["python", "-m", "shiny", "run", "--host", "0.0.0.0", "--port", "3839", "/app/app.py"]
