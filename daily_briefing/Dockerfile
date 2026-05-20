FROM python:3.12-slim

WORKDIR /app

RUN useradd -m -u 1000 agent

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY daily_briefing/ daily_briefing/

USER agent

CMD ["python", "-m", "daily_briefing.main"]
