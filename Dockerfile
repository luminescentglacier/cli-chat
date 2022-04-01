FROM oraclelinux:8.5

RUN dnf module install -y python39 && dnf install -y python39-pip python39-setuptools

COPY src requirements.txt /cli-chat/
WORKDIR /cli-chat
RUN python3.9 -m pip install -r requirements.txt
CMD ["uvicorn", "server:app"]
