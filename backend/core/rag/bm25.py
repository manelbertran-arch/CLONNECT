import math
import re
from typing import List, Dict, Any
from collections import Counter
import logging

logger = logging.getLogger("clonnect.rag.bm25")

class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = []
        self.corpus_ids = []
        self.idf = {}
        self.doc_len = []
        self.avgdl = 0
        self.N = 0
        self.tokenized_corpus = []

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens = re.findall(r'\b\w+\b', text.lower())
        return [t for t in tokens if len(t) > 2]

    def fit(self, corpus: List[Dict[str, Any]]) -> None:
        self.corpus = corpus
        self.corpus_ids = [doc.get('id', str(i)) for i, doc in enumerate(corpus)]
        self.N = len(corpus)
        if self.N == 0:
            return
        self.tokenized_corpus = []
        self.doc_len = []
        for doc in corpus:
            tokens = self._tokenize(doc.get('text', ''))
            self.tokenized_corpus.append(tokens)
            self.doc_len.append(len(tokens))
        self.avgdl = sum(self.doc_len) / self.N if self.N > 0 else 0
        df = {}
        for tokens in self.tokenized_corpus:
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        self.idf = {}
        for token, freq in df.items():
            self.idf[token] = math.log((self.N - freq + 0.5) / (freq + 0.5) + 1)
        logger.info(f"BM25: indexados {self.N} docs, vocabulario {len(self.idf)} terminos")

    def _score(self, query_tokens: List[str], doc_idx: int) -> float:
        score = 0.0
        doc_tokens = self.tokenized_corpus[doc_idx]
        doc_len = self.doc_len[doc_idx]
        doc_freqs = Counter(doc_tokens)
        for token in query_tokens:
            if token not in self.idf:
                continue
            freq = doc_freqs.get(token, 0)
            if freq == 0:
                continue
            idf = self.idf[token]
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * (numerator / denominator)
        return score

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.corpus or self.N == 0:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        scores = []
        for idx in range(self.N):
            score = self._score(query_tokens, idx)
            if score > 0:
                scores.append((idx, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scores[:top_k]:
            doc = self.corpus[idx].copy()
            doc['bm25_score'] = float(score)
            results.append(doc)
        return results

    def get_stats(self) -> Dict[str, Any]:
        return {"num_documents": self.N, "avg_doc_length": self.avgdl, "vocabulary_size": len(self.idf), "k1": self.k1, "b": self.b}
