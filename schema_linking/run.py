import json

from sl1 import select_relevant_tables as sl1_select_relevant_tables
from sl2 import select_relevant_tables as sl2_select_relevant_tables, generate_result_from_last_round, \
    generate_schema_description
from utils.graphloader import GraphLoader
from schema_linking.surfing_in_graph import SchemaGenerator

# 示例使用
if __name__ == "__main__":
    # 初始化GraphLoader
    graph_loader = GraphLoader()
    sg = SchemaGenerator()
    graph_loader.load_graph("bird", "trains")  # 加载数据库图
    # 问题
    question = """Among the trains that run in the east direction, how many of them have at least one car in a non-regular shape?
    """
    db_schema = "\n".join(
        sg.generate_combined_description(table) for table in sg.tables
    )
    # 调用sl1
    sl1_result = sl1_select_relevant_tables("Identify relevant database entities for SQL query generation.", db_schema,
                                            question)
    # 获取sl1的结果
    selected_table = sl1_result["selected_entity"]
    print(selected_table)
    print(sl1_result['reason'])

    sl2_schema = generate_schema_description([selected_table[0]])
    sl2_result = json.dumps(sl2_select_relevant_tables(sl2_schema, question, [selected_table[0]]), indent=2)
    print(sl2_result)
    # result_from_last_round = generate_result_from_last_round(sl2_result)
    # print(result_from_last_round)
