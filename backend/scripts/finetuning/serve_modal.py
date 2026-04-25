"""
Modal serving — Gemma4-31B Dense merged (LoRA baked-in) via vLLM
Levanta con:
    modal deploy scripts/finetuning/serve_modal.py

Endpoint público OpenAI-compatible:
    https://manelbertran-arch--clonnect-iris-serve-serve.modal.run/v1/chat/completions

    - model: "gemma31b-iris-sft"
    - messages: [{"role": "user", "content": "..."}]

Notas:
- A100-80GB para servir merged bf16 nativo (60GB model, 80GB VRAM disponible)
- Sin --enable-lora: pesos LoRA ya fusionados en merged model
- chat_template permisivo: acepta roles consecutivos (igual que DeepInfra server-side)
- Auto-scale down tras 30 min idle para evitar cold-starts durante CCEE
"""
import modal

app = modal.App("clonnect-iris-serve")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.19.1",
        "huggingface_hub",
        "hf_transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .add_local_file(
        "scripts/finetuning/gemma4_permissive_template.jinja",
        remote_path="/templates/gemma4_permissive.jinja",
    )
)

volume = modal.Volume.from_name("clonnect-models")

MERGED_MODEL = "/models/gemma31b-iris-sft-merged"
SERVED_MODEL_NAME = "gemma31b-iris-sft"
CHAT_TEMPLATE = "/templates/gemma4_permissive.jinja"


@app.function(
    image=image,
    gpu="A100-80GB",
    volumes={"/models": volume},
    timeout=60 * 60,
    scaledown_window=60 * 30,  # 30 min para evitar cold-starts durante CCEE
)
@modal.concurrent(max_inputs=10)
@modal.web_server(port=8000, startup_timeout=900)
def serve():
    """
    vLLM OpenAI server:
    - Merged model (Gemma4-31B Dense + LoRA Iris fusionados)
    - bf16 nativo en A100-80GB (sin re-cuantizar)
    - chat_template permisivo: roles consecutivos → merged silenciosamente
      (replica DeepInfra server-side preprocessing, tokens exactos Gemma4)
    """
    import subprocess
    subprocess.Popen(
        [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", MERGED_MODEL,
            "--served-model-name", SERVED_MODEL_NAME,
            "--host", "0.0.0.0",
            "--port", "8000",
            "--dtype", "bfloat16",
            "--max-model-len", "16384",
            "--gpu-memory-utilization", "0.95",
            "--trust-remote-code",
            "--chat-template", CHAT_TEMPLATE,
        ]
    )
