import json
from sl1 import TableSelector
from sl2 import SubgraphSelector
from utils.graphloader import GraphLoader
from schema_linking.surfing_in_graph import SchemaGenerator
from validator import SLValidator


def main():
    # 初始化各个组件
    graph_loader = GraphLoader()
    sl1 = TableSelector()
    sl2 = SubgraphSelector()
    sg = SchemaGenerator()
    validator = SLValidator()  # 只创建一次 validator

    # 加载数据库模式图
    # graph_loader.load_graph("spider", "college_2")

    # 处理的自然语言查询
    question = """
    Find the name of students who have taken the prerequisite course of the course with title International Finance.
    """

    # 生成数据库模式的文本描述
    db_schema = "\n".join(
        sg.generate_combined_description(table) for table in sg.tables
    )

    # 第一轮表选择
    print("=== 第一轮表选择 ===")
    sl1_result = sl1.select_relevant_tables(
        "Identify relevant database entities for SQL query generation.",
        db_schema, question
    )
    selected_table = sl1_result.get("selected_entity", [])

    if not selected_table:
        print("未找到合适的表，终止执行。")
        return

    print(f"选中的表: {selected_table[0]}")
    print("选择理由:")
    print(json.dumps(sl1_result['reason'], indent=2, ensure_ascii=False))

    # 第一轮表选择后进行子图扩展
    print("\n=== 第一轮子图扩展 ===")
    sl2_schema = sl2.generate_schema_description([selected_table[0]])

    sl2_result = sl2.select_relevant_tables(sl2_schema, question, [selected_table[0]])
    print("扩展结果:")
    print(json.dumps(sl2_result, indent=2, ensure_ascii=False))

    # 进行校验与修正
    sl2_result = validator.validate_and_correct(sl2_result)
    print("修正后的结果:")
    print(json.dumps(sl2_result, indent=2, ensure_ascii=False))

    is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
    print(f"初始 is_solvable: {is_solvable}")

    # 生成初始状态的结果
    result_from_last_round = sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))

    # 迭代扩展，最大 10 轮，防止死循环
    max_iterations = 10
    iteration = 0
    while not is_solvable and iteration < max_iterations:
        iteration += 1
        print(f"\n=== 第 {iteration} 轮迭代 ===")

        # 确保 "selected_columns" 存在
        if "selected_columns" not in sl2_result or not sl2_result["selected_columns"]:
            print("selected_columns 为空，终止循环。")
            break

        selected_table = list(sl2_result["selected_columns"].keys())
        print(f"新选择的表: {selected_table}")

        sl2_schema = sl2.generate_schema_description(selected_table)

        sl2_result = sl2.select_relevant_tables(sl2_schema, question, selected_table, result_from_last_round)
        print("迭代扩展结果:")
        print(json.dumps(sl2_result, indent=2, ensure_ascii=False))

        # 进行校验与修正
        sl2_result = validator.validate_and_correct(sl2_result)
        print("修正后的结果:")
        print(json.dumps(sl2_result, indent=2, ensure_ascii=False))

        is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
        print(f"当前 is_solvable: {is_solvable}")

        # 更新上轮结果
        result_from_last_round = sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))

    # 最终结果
    if is_solvable:
        print("\n✅ 成功找到可解析的 SQL 查询方案！")
    else:
        print("\n❌ 未能找到可解析的 SQL 查询方案，可能需要手动干预。")


if __name__ == "__main__":
    main()
