import json, os, re, time
from openai import OpenAI


def strip_think(text):
    """Remove <think>...</think> blocks from model responses."""
    if not text:
        return text
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()

# Cargar test set
with open('tests/test_set_v2.json') as f:
    data = json.load(f)
convs = data['conversations'][:20]  # 20 convs para baseline rápido

# Cargar system prompt Doc D
with open('data/personality_extractions/iris_bertran_v2_distilled.md') as f:
    system_prompt = f.read()

print(f"System prompt: {len(system_prompt)} chars")
print(f"Test convs: {len(convs)}")

# Providers a testear
PROVIDERS = {
    'qwen3-8b-dashscope': {
        'base_url': 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
        'api_key': os.environ.get('DASHSCOPE_API_KEY', ''),
        'model': 'qwen3-8b',
        'extra': {'enable_thinking': False}
    },
    'qwen3-4b-dashscope': {
        'base_url': 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
        'api_key': os.environ.get('DASHSCOPE_API_KEY', ''),
        'model': 'qwen3-4b',
        'extra': {'enable_thinking': False}
    },
    'qwen3-8b-fireworks': {
        'base_url': 'https://api.fireworks.ai/inference/v1',
        'api_key': os.environ.get('FIREWORKS_API_KEY', 'fw_RxDs3xEtMqCDodmnpniyt2'),
        'model': 'accounts/fireworks/models/qwen3-8b',
        'extra': {'thinking': {'type': 'disabled'}}
    },
    'qwen3-32b-deepinfra': {
        'base_url': 'https://api.deepinfra.com/v1/openai',
        'api_key': os.environ.get('DEEPINFRA_API_KEY', ''),
        'model': 'Qwen/Qwen3-32B',
        'extra': {}
    },
}

# Si no hay DASHSCOPE_API_KEY, skip esos providers
if not os.environ.get('DASHSCOPE_API_KEY'):
    print("\n⚠️  No DASHSCOPE_API_KEY — skipping DashScope models")
    print("   Crear cuenta gratis: https://modelstudio.alibabacloud.com/")
    PROVIDERS = {k: v for k, v in PROVIDERS.items() if 'dashscope' not in k}

results = {}

for provider_name, config in PROVIDERS.items():
    print(f"\n{'='*60}")
    print(f"Testing: {provider_name}")
    print(f"{'='*60}")

    if not config['api_key']:
        print(f"  SKIP — no API key")
        continue

    client = OpenAI(api_key=config['api_key'], base_url=config['base_url'])

    responses = []
    errors = 0

    for i, conv in enumerate(convs):
        try:
            messages = [{'role': 'system', 'content': system_prompt}]

            # Añadir historial de conversación (últimas 6 turns)
            for turn in conv.get('turns', [])[-6:]:
                role = turn.get('role', '')
                content = turn.get('content', '')
                if not content:
                    continue
                if role == 'iris':
                    messages.append({'role': 'assistant', 'content': content})
                elif role == 'lead':
                    messages.append({'role': 'user', 'content': content})

            messages.append({'role': 'user', 'content': conv['test_input']})

            kwargs = {
                'model': config['model'],
                'messages': messages,
                'max_tokens': 300,
                'temperature': 0.7,
            }
            if config['extra']:
                kwargs['extra_body'] = config['extra']

            resp = client.chat.completions.create(**kwargs)
            response_text = strip_think(resp.choices[0].message.content)

            responses.append({
                'conv_id': conv['id'],
                'type': conv.get('type', ''),
                'language': conv.get('language', ''),
                'test_input': conv['test_input'],
                'response': response_text,
                'ground_truth': conv.get('ground_truth', ''),
                'tokens': resp.usage.total_tokens if resp.usage else 0
            })

            print(f"  [{i+1}/20] {conv['id']} ({conv.get('type','')}/{conv.get('language','')}) — {response_text[:80]}...")
            time.sleep(0.3)

        except Exception as e:
            errors += 1
            print(f"  [{i+1}/20] ERROR — {e}")
            time.sleep(1)

    results[provider_name] = {
        'responses': responses,
        'total': len(responses),
        'errors': errors
    }

    with open(f'tests/baseline_{provider_name}.json', 'w') as f:
        json.dump(responses, f, ensure_ascii=False, indent=2)

    print(f"\n  Completado: {len(responses)}/20 OK, {errors} errores")

# Resumen final
print(f"\n{'='*60}")
print("RESUMEN BASELINES")
print(f"{'='*60}")
for name, r in results.items():
    print(f"\n  {name}: {r['total']} respuestas, {r['errors']} errores")
    if r['responses']:
        avg_tokens = sum(x['tokens'] for x in r['responses']) / len(r['responses'])
        print(f"    Avg tokens/response: {avg_tokens:.0f}")
        print(f"    Ejemplo conv_001: {r['responses'][0]['response'][:200]}")

print(f"\nArchivos: tests/baseline_*.json")
print("Siguiente: correr LLM-judge sobre estos resultados")
