# Start from an official slim Python image
# "slim" = smaller size, no unnecessary OS packages
FROM python:3.11-slim

# Set the working directory inside the container
# All subsequent commands run from here
WORKDIR /app

# Copy requirements first (before copying app code)
# Why? Docker caches layers. If requirements don't change,
# Docker skips reinstalling them on every rebuild. Faster builds.
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the application code
COPY . .

# Create a directory for uploaded files
RUN mkdir -p /app/uploads

# Expose port 8000 so it's reachable from outside the container
EXPOSE 8000
