FROM ubuntu:latest
ENV PYTHONUNBUFFERED 1
RUN apt update && apt -y install python3
COPY ./webhook.py .
ENTRYPOINT ["./webhook.py"]

# Hint: Ugly and insecure image for fast prototyping
# Use a smaller base image
# Don't use latest version of your base image. 
# Don't distribute a packet cache with our image.
# Don't use root in your images. 
