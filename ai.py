import numpy as np
import openai
import tiktoken
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import Config


class AI:
    """The AI class."""

    def __init__(self, cfg: Config):
        openai.api_key = cfg.open_ai_key
        self._use_stream = cfg.use_stream
        self._encoding = tiktoken.encoding_for_model('gpt-3.5-turbo')

    def _chat_stream(self, messages: list[dict]):
        response = openai.ChatCompletion.create(
            stream=self._use_stream,
            model="gpt-3.5-turbo",
            messages=messages,
        )
        if self._use_stream:
            for chunk in response:
                if chunk.choices[0].delta.get('content', None) is not None:
                    print(chunk.choices[0].delta.content, end='')
            print()
        else:
            tokens_used = response.usage.total_tokens

            print("使用的tokens：", response.usage.total_tokens, "，花费：", response.usage.total_tokens / 1000 * 0.002,
                  "美元")
            print(response.choices[0].message.content.strip())
            return response.choices[0].message.content.strip(), tokens_used

    def _num_tokens_from_string(self, string: str) -> int:
        """Returns the number of tokens in a text string."""
        num_tokens = len(self._encoding.encode(string))
        return num_tokens

    def completion(self, query: str, context: list[str]):
        """Create a completion."""
        context = self._cut_texts(context)

        text = "\n".join(f"{index}. {text}" for index, text in enumerate(context))
        return self._chat_stream([
            {'role': 'system',
             'content': f'你是一个有帮助的AI文章助手，以下是从文中搜索到具有相关性的文章内容片段，相关性从高到底排序：\n\n{text}'},
            {'role': 'user', 'content': query},
        ])

    def _cut_texts(self, context):
        maximum = 4096 - 1024
        for index, text in enumerate(context):
            maximum -= self._num_tokens_from_string(text)
            if maximum < 0:
                context = context[:index + 1]
                print("超过最大长度，截断到前", index + 1, "个片段")
                break
        return context

    @staticmethod
    def create_embedding(text: str) -> (str, list[float]):
        """Create an embedding for the provided text."""
        embedding = openai.Embedding.create(model="text-embedding-ada-002", input=text)
        return text, embedding.data[0].embedding

    def create_embeddings(self, texts: list[str]) -> (list[tuple[str, list[float]]], int):
        """Create embeddings for the provided input."""
        result = []
        query_len = 0
        start_index = 0
        tokens = 0

        def get_embedding(input_slice: list[str]):
            embedding = openai.Embedding.create(model="text-embedding-ada-002", input=input_slice)
            return [(txt, data.embedding) for txt, data in
                    zip(input_slice, embedding.data)], embedding.usage.total_tokens

        for index, text in enumerate(texts):
            query_len += self._num_tokens_from_string(text)
            if query_len > 8192 - 1024:
                ebd, tk = get_embedding(texts[start_index:index + 1])
                print("查询片段 使用的tokens：", tk, "，花费：", tk / 1000 * 0.0004, "美元")
                query_len = 0
                start_index = index + 1
                tokens += tk
                result.extend(ebd)

        if query_len > 0:
            ebd, tk = get_embedding(texts[start_index:])
            print("查询片段 使用的tokens：", tk, "，花费：", tk / 1000 * 0.0004, "美元")
            tokens += tk
            result.extend(ebd)
        return result, tokens

    def generate_summary(self, embeddings, num_candidates=3, use_sif=False):
        """Generate a summary for the provided embeddings."""
        avg_func = self._calc_paragraph_avg_embedding_with_sif if use_sif else self._calc_avg_embedding
        avg_embedding = np.array(avg_func(embeddings))

        paragraphs = [e[0] for e in embeddings]
        embeddings = np.array([e[1] for e in embeddings])
        # 计算每个段落与整个文本的相似度分数
        similarity_scores = cosine_similarity(embeddings, avg_embedding.reshape(1, -1)).flatten()

        # 选择具有最高相似度分数的段落作为摘要的候选段落
        candidate_indices = np.argsort(similarity_scores)[::-1][:num_candidates]
        candidate_paragraphs = [paragraphs[i] for i in candidate_indices]

        print("完成计算，开始生成摘要")

        candidate_paragraphs = self._cut_texts(candidate_paragraphs)

        text = "\n".join(f"{index}. {text}" for index, text in enumerate(candidate_paragraphs))
        return self._chat_stream([
            {'role': 'system',
             'content': f'你是一个有帮助的AI文章助手，以下是从文中搜索到具有相关性的文章内容片段，相关性从高到底排序，你需要从这些相关内容中总结全文内容，最后的结果需要用中文展示：\n\n{text}\n\n中文总结：'},
        ])

    @staticmethod
    def _calc_avg_embedding(embeddings) -> list[float]:
        # 没有权重
        avg_embedding = np.zeros(len(embeddings[0][1]))
        for emb in embeddings:
            avg_embedding += np.array(emb[1])
        avg_embedding /= len(embeddings)
        return avg_embedding.tolist()

    @staticmethod
    def _calc_paragraph_avg_embedding_with_sif(paragraph_list) -> list[float]:
        alpha = 0.001
        # 中文不适用
        # calculate the total number of sentences
        n_sentences = len(paragraph_list)

        # calculate the total number of dimensions in the embeddings
        n_dims = len(paragraph_list[0][1])

        # calculate the IDF values for each word in the sentences
        vectorizer = TfidfVectorizer(use_idf=True)
        vectorizer.fit_transform([paragraph for paragraph, _ in paragraph_list])
        idf = vectorizer.idf_

        # calculate the SIF weights for each sentence
        weights = np.zeros((n_sentences, n_dims))
        for i, (sentence, embedding) in enumerate(paragraph_list):
            sentence_words = sentence.split()
            for word in sentence_words:
                try:
                    word_index = vectorizer.vocabulary_[word]
                    word_idf = idf[word_index]
                    word_weight = alpha / (alpha + word_idf)
                    weights[i] += word_weight * (np.array(embedding) / np.max(embedding))
                except KeyError:
                    pass

        # calculate the weighted average of the sentence embeddings
        weights_sum = np.sum(weights, axis=0)
        weights_sum /= n_sentences
        avg_embedding = np.zeros(n_dims)
        for i, (sentence, embedding) in enumerate(paragraph_list):
            avg_embedding += (np.array(embedding) / np.max(embedding)) - weights[i]
        avg_embedding /= n_sentences

        return avg_embedding.tolist()
