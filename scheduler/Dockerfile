FROM continuumio/miniconda3

WORKDIR /app

# Install build tools and cron first (needed for scikit-surprise compilation)
RUN apt-get update && apt-get install -y cron gcc g++ build-essential python3-dev && apt-get clean

# Copy environment file and create conda environment
COPY environment.yml .
RUN conda env create -f environment.yml

# Activate environment
SHELL ["conda", "run", "-n", "scheduler_env", "/bin/bash", "-c"] 

# Copy cron file
COPY retrain-cron /etc/cron.d/retrain-cron
RUN chmod 0644 /etc/cron.d/retrain-cron

# Copy training script
COPY run_training.sh /run_training.sh
RUN chmod +x /run_training.sh

# Run cron in foreground
CMD ["cron", "-f"]
