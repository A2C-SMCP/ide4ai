# Use Python 3.11 slim image from Docker Hub
FROM python:3.11.9-slim

# Update packages and install socat
RUN apt-get update && apt-get install -y \
    socat \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Install Pyright using pip
RUN pip install pyright

# Copy the Pyright configuration file
COPY pyrightconfig.json /app/

# Expose port 3000 for external access
EXPOSE 3000

# Start the pyright-langserver listening on TCP port 3000 using socat
CMD socat TCP-LISTEN:3000,fork SYSTEM:'tee /dev/stderr | pyright-langserver --stdio | tee /dev/stderr'
