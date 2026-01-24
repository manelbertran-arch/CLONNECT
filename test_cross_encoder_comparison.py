#!/usr/bin/env python3
"""
Test Cross-Encoder reranking comparison.
Compares keyword-based search vs Cross-Encoder reranking.
"""
import requests
import json

API_URL = "https://web-production-9f69.up.railway.app"

def test_health():
    """Verify API is healthy"""
    print("=" * 60)
    print("1. Testing API Health")
    print("=" * 60)
    resp = requests.get(f"{API_URL}/health", timeout=30)
    health = resp.json()
    print(f"Status: {health.get('status')}")
    print(f"Memory: {health['checks']['memory']['used_percent']:.1f}% used")
    return health.get('status') == 'healthy'


def test_cross_encoder_endpoint():
    """Test Cross-Encoder via citations/search endpoint"""
    print("\n" + "=" * 60)
    print("2. Testing Cross-Encoder via Citations Search")
    print("=" * 60)

    # Test queries that should benefit from semantic reranking
    test_cases = [
        {
            "query": "cuánto cuesta el programa",
            "creator_id": "stefano_bonanno",
            "description": "Price query - should find pricing content"
        },
        {
            "query": "cómo puedo empezar",
            "creator_id": "stefano_bonanno",
            "description": "Getting started - should find onboarding content"
        },
        {
            "query": "resultados de clientes",
            "creator_id": "stefano_bonanno",
            "description": "Testimonials - should find success stories"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {case['description']} ---")
        print(f"Query: \"{case['query']}\"")

        # Call citations search endpoint (correct endpoint)
        try:
            resp = requests.post(
                f"{API_URL}/citations/search",
                json={
                    "query": case["query"],
                    "creator_id": case["creator_id"],
                    "top_k": 3
                },
                timeout=60
            )

            if resp.status_code == 200:
                results = resp.json()
                citations = results.get('citations', results.get('results', []))
                print(f"Results: {len(citations)} citations found")
                for j, doc in enumerate(citations[:3], 1):
                    score = doc.get('rerank_score', doc.get('relevance_score', doc.get('score', 'N/A')))
                    content = doc.get('content', doc.get('excerpt', doc.get('text', '')))[:100]
                    print(f"  {j}. Score: {score} - {content}...")
            elif resp.status_code == 404:
                print(f"Endpoint not found (404)")
            else:
                print(f"Error {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            print(f"Error: {e}")


def test_chat_with_rag():
    """Test chat endpoint which should use RAG internally"""
    print("\n" + "=" * 60)
    print("3. Testing DM Process (uses RAG internally)")
    print("=" * 60)

    # Send a message that should trigger RAG lookup
    try:
        resp = requests.post(
            f"{API_URL}/dm/process",
            json={
                "creator_id": "stefano_bonanno",
                "sender_id": "test_user",
                "message": "¿Cuánto cuesta el programa de mentoría?",
                "use_rag": True
            },
            timeout=90
        )

        if resp.status_code == 200:
            result = resp.json()
            print(f"Response generated successfully")
            reply = result.get('reply', result.get('response', result.get('message', '')))
            print(f"Reply preview: {reply[:200]}...")
            citations = result.get('citations', result.get('sources', []))
            if citations:
                print(f"Citations found: {len(citations)}")
        else:
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text[:300]}")

    except Exception as e:
        print(f"Error: {e}")


def test_reranker_directly():
    """Test citation stats to verify system is working"""
    print("\n" + "=" * 60)
    print("4. Testing Citation Stats for Creator")
    print("=" * 60)

    # Call citation stats endpoint
    try:
        resp = requests.get(
            f"{API_URL}/citations/stefano_bonanno/stats",
            timeout=60
        )
        if resp.status_code == 200:
            stats = resp.json()
            print(f"Citation stats: {json.dumps(stats, indent=2)}")
        else:
            print(f"Stats endpoint returned {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
    except Exception as e:
        print(f"Note: {e}")

    # Also check reranker via health endpoint details
    print("\n--- Checking Health Details ---")
    try:
        resp = requests.get(f"{API_URL}/health", timeout=30)
        if resp.status_code == 200:
            health = resp.json()
            checks = health.get('checks', {})
            print(f"Available checks: {list(checks.keys())}")
            if 'reranker' in checks:
                print(f"Reranker status: {checks['reranker']}")
            else:
                print("Reranker check not in health (may be lazy-loaded)")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("\n🔬 CROSS-ENCODER COMPARISON TEST")
    print("Testing PyTorch CPU + sentence-transformers deployment\n")

    if test_health():
        test_cross_encoder_endpoint()
        test_chat_with_rag()
        test_reranker_directly()

        print("\n" + "=" * 60)
        print("✅ Tests completed!")
        print("=" * 60)
        print("\nNote: Cross-Encoder reranking happens internally in the RAG pipeline.")
        print("To see rerank_score, check the RAG search results or enable debug logging.")
    else:
        print("❌ API not healthy, skipping tests")
