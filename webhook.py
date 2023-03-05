#!/bin/env python3

# A simple imagePolicyWebhook admission controller that only allows nginx images in the cluster
# Only to play with the imagePolicyWebhoook for the CKS certification
# Not useful, not secure and not for production.

# Import modules
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
from io import BytesIO
import json

# Set the allowed image name
ALLOWED = "nginx"

# Print a message to indicate the server is starting
print("Starting webhook")


# Define a custom request handler by inheriting from BaseHTTPRequestHandler
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    # Set the HTTP protocol version
    protocol_version = "HTTP/1.1"

    # Respond to a GET request
    def do_GET(self):
        self.send_response(200)  # Set the response status code
        self.end_headers()  # Send an empty line to indicate the end of the headers
        self.wfile.write(  # Send a response body
            b"I am a imagePolicyWebhook example!\nYou need to post a json object of kind ImageReview"
        )

    # Respond to a POST request
    def do_POST(self):
        content_length = int(
            self.headers["Content-Length"]
        )  # Get the length of the request body
        body = self.rfile.read(content_length)  # Read the request body
        body_string = body.decode(
            "utf8"
        )  # Convert the request body from bytes to string
        body_json = json.loads(body_string)  # Parse the request body as JSON
        images = body_json.get("spec").get(
            "containers"
        )  # Get the image names from the request

        # Check if any of the image names match the allowed image name
        for i in images:
            image = i.get("image")
            if ALLOWED in image:
                body_json["status"] = {
                    "allowed": True
                }  # If an allowed image is found, set the response status to allowed
            else:
                body_json[
                    "status"
                ] = {  # If no allowed image is found, set the response status to not allowed
                    "allowed": False,
                    "reason": "Only nginx images are allowed",
                }
                break

        # Check if the request includes annotations
        annotations = body_json.get("spec").get("annotations")
        if annotations:
            body_json["status"] = {
                "allowed": True,
                "reason": "You broke the glass",
            }  # If annotations are found, modify the response status and message accordingly

        message = bytes(
            json.dumps(body_json), "utf-8"
        )  # Convert the response body from JSON to bytes
        self.send_response(200)  
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        response = BytesIO()
        response.write(message) 
        self.wfile.write(response.getvalue())  # Send the response body to the client


# Create an HTTP server on port 443 with an SSL context and certificate/key files
httpd = HTTPServer(("0.0.0.0", 443), SimpleHTTPRequestHandler)
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(
    certfile="/etc/ssl/certs/webhook-server.crt",
    keyfile="/etc/ssl/private/webhook-server.key",
)
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

# Start the Webhook
httpd.serve_forever()
