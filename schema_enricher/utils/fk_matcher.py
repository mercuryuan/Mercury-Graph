import numpy as np
from sentence_transformers import SentenceTransformer, util
from schema_enricher.utils.fk_compare import extract_foreign_keys
from graph_construction.graph_query import GraphQuery


def get_text_for_column(col):
    """
    将列的名称和描述组合成一个字符串，作为生成文本嵌入的输入。
    """
    return f"{col['column_name']}. {col['description']}"


if __name__ == '__main__':
    dataset_name = "bird"
    db_name = "books"
    # 获取所有列节点信息
    query = GraphQuery(dataset_name,db_name)
    all_columns_info = query.col_infos_for_fk()

    # 获取已存在的外键
    existing_foreign_keys = extract_foreign_keys(dataset_name,db_name)

    # ----------------------------------------------------------
    # Step 1: 预筛选——不同表 & 数据类型完全匹配 & 不在已有外键中
    # ----------------------------------------------------------
    candidate_pairs = set()  # 使用集合去重
    n = len(all_columns_info)

    for i in range(n):
        for j in range(i + 1, n):  # 避免重复，i < j
            col1 = all_columns_info[i]
            col2 = all_columns_info[j]
            if col1['table_name'] != col2['table_name'] and col1['data_type'] == col2['data_type']:
                pair = frozenset({(col1['table_name'], col1['column_name']), (col2['table_name'], col2['column_name'])})
                if pair not in existing_foreign_keys:
                    candidate_pairs.add((i, j))

    print("符合要求的候选外键对（去除已存在外键后）：", len(candidate_pairs))

    # ----------------------------------------------------------
    # Step 2: 生成文本嵌入
    # ----------------------------------------------------------
    texts = [get_text_for_column(col) for col in all_columns_info]
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(texts, convert_to_tensor=True)

    # ----------------------------------------------------------
    # Step 3: 计算候选对的语义相似度
    # ----------------------------------------------------------
    candidates = []
    for (i, j) in candidate_pairs:
        sim_score = util.cos_sim(embeddings[i], embeddings[j]).item()
        candidates.append({
            'source': all_columns_info[i],
            'target': all_columns_info[j],
            'similarity': sim_score
        })

    # ----------------------------------------------------------
    # Step 4: 根据语义相似度对候选外键对进行排序
    # ----------------------------------------------------------
    sorted_candidates = sorted(candidates, key=lambda x: x['similarity'], reverse=True)

    # 输出排序后的候选外键对
    for idx, candidate in enumerate(sorted_candidates):
        src = candidate['source']
        tgt = candidate['target']
        print(f"候选对 {idx + 1}: {src['table_name']}.{src['column_name']} -> {tgt['table_name']}.{tgt['column_name']}")
        print(f"  数据类型：{src['data_type']}（匹配）")
        print(f"  语义相似度得分：{candidate['similarity']:.4f}\n")
