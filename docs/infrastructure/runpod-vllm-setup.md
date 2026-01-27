# RunPod vLLM Setup Guide

This guide describes how to set up and run the EXAONE-4.0-1.2B model using vLLM on RunPod for the DDOKSORI project.

## Prerequisites

- RunPod account with credits.
- GPU Pod with at least 24GB VRAM (RTX 4090, A6000, or A100 recommended).
- SSH key configured in RunPod.

## 1. Deploying the Pod

1. Log in to [RunPod](https://www.runpod.io/).
2. Navigate to **Pods** and click **+ Deploy**.
3. Select a GPU (e.g., RTX 4090).
4. Choose the **RunPod PyTorch** template or a dedicated **vLLM** template if available.
5. Ensure you have enough disk space (at least 50GB for model weights and cache).
6. Click **Deploy**.

## 2. Installing vLLM

Once the Pod is running, connect via SSH and install vLLM:

```bash
pip install vllm
```

## 3. Running the vLLM Server

Run the following command to start the OpenAI-compatible API server for EXAONE-4.0-1.2B:

```bash
python -m vllm.entrypoints.openai.api_server \
    --model LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct \
    --port 8000 \
    --trust-remote-code
```

*Note: The first run will download the model weights from Hugging Face.*

## 4. SSH Tunneling for Local Development

To access the vLLM server from your local machine (or the backend server), use SSH tunneling:

```bash
ssh -L 8001:localhost:8000 -i ~/.ssh/id_rsa root@<RUNPOD_POD_IP>
```

Now, the EXAONE API will be available at `http://localhost:8001/v1`.

## 5. Configuration

Update your `.env` file with the following variables:

```env
MODEL_EXAONE_BASE_URL=http://localhost:8001/v1
MODEL_EXAONE_API_KEY=empty
MODEL_EXAONE_NAME=LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct
```

## 6. Health Check Verification

You can verify the connection using the health check endpoint:

```bash
curl http://localhost:8000/health/llm/exaone
```

## Troubleshooting

- **Out of Memory (OOM):** If you encounter OOM errors, try reducing `--max-model-len` or using a GPU with more VRAM.
- **Connection Refused:** Ensure the SSH tunnel is active and the vLLM server is running on the correct port.
- **Model Download Issues:** Check your internet connection within the Pod and ensure you have enough disk space.
