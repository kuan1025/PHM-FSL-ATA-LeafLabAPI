FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir boto3
COPY report.py /app/report.py
ENTRYPOINT ["python","/app/report.py"]
