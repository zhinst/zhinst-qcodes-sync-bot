FROM python:3.9-buster
WORKDIR /app 
COPY . /app 
RUN curl -sL https://deb.nodesource.com/setup_18.x | bash - 
RUN apt-get install -y nodejs
RUN npm install --global smee-client
RUN pip install -r requirements.txt

ENTRYPOINT ["./start_service.sh"] 