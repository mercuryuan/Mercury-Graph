import multiprocessing
from collections import defaultdict

import torch

from utils.sql_executor import SQLiteExecutor
from sentence_transformers import SentenceTransformer, util
import concurrent.futures
import time
import threading
from sentence_transformers import SentenceTransformer

_model_lock = threading.Lock()
_shared_model = None


def get_shared_model(model_name="all-MiniLM-L6-v2"):
    global _shared_model
    with _model_lock:
        if _shared_model is None:
            _shared_model = SentenceTransformer(model_name)
        return _shared_model


def search_keyword_worker(keyword, mode, dataset, database_name, queue):
    searcher = KeywordSearcher(dataset, database_name)
    result = searcher._search_keyword_internal(keyword, mode)
    queue.put(result)


class KeywordSearcher:
    def __init__(self, dataset, database_name, embed_model="all-MiniLM-L6-v2"):
        self.dataset = dataset
        self.database_name = database_name
        self.model = get_shared_model(embed_model)  # 使用共享模型,防止多线程重复加载

    @staticmethod
    def quote_identifier(s):
        return f'"{s}"'

    import multiprocessing

    def search_keyword_with_timeout(self, keyword, mode="auto", timeout=60):
        queue = multiprocessing.Queue()
        p = multiprocessing.Process(
            target=search_keyword_worker,
            args=(keyword, mode, self.dataset, self.database_name, queue)
        )
        p.start()
        p.join(timeout)

        if p.is_alive():
            print(f"关键词 `{keyword}` 查询超时（>{timeout}s），终止子进程。")
            p.terminate()
            p.join()
            return []

        if not queue.empty():
            return queue.get()
        return []

    def _search_keyword_internal(self, keyword, mode="auto"):
        results = []
        is_numeric = keyword.isdigit()

        with SQLiteExecutor(self.dataset, self.database_name) as db:
            table_query = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = db.query(table_query)
            table_names = [row[0] for row in tables]

            for table in table_names:
                pragma_query = f"PRAGMA table_info({self.quote_identifier(table)});"
                columns = db.query(pragma_query)

                for col in columns:
                    col_name = col[1]
                    col_type = col[2].lower()
                    quoted_col = self.quote_identifier(col_name)
                    quoted_table = self.quote_identifier(table)

                    try:
                        if is_numeric and ('int' in col_type or 'real' in col_type or 'numeric' in col_type):
                            if mode in ("auto", "exact"):
                                query = f"SELECT DISTINCT {quoted_col} FROM {quoted_table} WHERE {quoted_col} = ?"
                                matches = db.query(query, (int(keyword),))
                                for match in matches:
                                    results.append((table, col_name, match[0]))

                        elif 'char' in col_type or 'text' in col_type or 'clob' in col_type:
                            if mode == "exact":
                                query = f"SELECT DISTINCT {quoted_col} FROM {quoted_table} WHERE {quoted_col} = ?"
                                matches = db.query(query, (keyword,))
                            elif mode in ("auto", "fuzzy"):
                                query = f"SELECT DISTINCT {quoted_col} FROM {quoted_table} WHERE {quoted_col} LIKE ?"
                                matches = db.query(query, (f"%{keyword}%",))
                            else:
                                matches = []
                            for match in matches:
                                results.append((table, col_name, match[0]))

                    except Exception as e:
                        print(f"跳过列 {col_name}（表 {table}），出错：{e}")
                        continue

        return results

    def get_llm_formatted_results(self, keyword, mode="auto", topk=3, sim_threshold=0.8):
        # 设定超时时间为60秒
        raw_matches = self.search_keyword_with_timeout(keyword, mode, timeout=120)
        grouped_raw = defaultdict(list)

        for table, column, value in raw_matches:
            key = f"{table}.{column}"
            grouped_raw[key].append(value)

        keyword_embedding = self.model.encode(keyword, convert_to_tensor=True)
        result = {}

        for key, values in grouped_raw.items():
            value_texts = [str(v) for v in values]
            value_embeddings = self.model.encode(value_texts, convert_to_tensor=True)
            scores = util.cos_sim(keyword_embedding, value_embeddings)[0]

            # 提取相似度高的值
            value_score_pairs = list(zip(value_texts, scores.tolist()))
            value_score_pairs.sort(key=lambda x: x[1], reverse=True)

            # 如果最高相似度 < 阈值，跳过整个列
            if value_score_pairs[0][1] < sim_threshold:
                continue

            top_values = [v for v, s in value_score_pairs[:topk]]
            result[key] = top_values

        return result

    def format_llm_hints_as_string(self, keyword, mode="auto", topk=3, sim_threshold=0.8):
        grouped = self.get_llm_formatted_results(keyword, mode, topk, sim_threshold)
        lines = []

        for key, values in grouped.items():
            formatted_values = [
                f'"{v}"' if not str(v).isdigit() else str(v)
                for v in values
            ]
            line = f"{key}: [{', '.join(formatted_values)}]"
            lines.append(line)

        return "\n".join(lines)


if __name__ == "__main__":
    # searcher = KeywordSearcher("bird", "superhero")
    #
    # keyword = "Blue Beetle II"
    # print(searcher.format_llm_hints_as_string(keyword))
    #
    # keyword = "294"
    # print("\n---\n")
    # print(searcher.format_llm_hints_as_string(keyword))

    # searcher = KeywordSearcher("bird", "california_schools")
    # keyword = "Fresno"
    # # keyword = "12"
    # print(searcher.format_llm_hints_as_string(keyword, sim_threshold=0.85))

    # searcher = KeywordSearcher("bird", "student_club")
    # keyword = "Women's Soccer"
    # print(searcher.format_llm_hints_as_string(keyword))
    # searcher = KeywordSearcher("bird", "debit_card_specializing", )
    # for k in ['LAM', 'Euro', 'October 2013', '201310']:
    #     print(searcher.format_llm_hints_as_string(k, sim_threshold=0.3))
    searcher = KeywordSearcher("bird", "codebase_community")
    print(searcher.format_llm_hints_as_string("humor", sim_threshold=0.8))
    # `['World Championship Decks 2004', '3']`
    # `['Coldsnap', '4']`
