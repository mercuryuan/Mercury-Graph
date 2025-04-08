import json
import os
import time
from datetime import datetime

import config
from sl1_ds import TableSelector
from sl2_ds import SubgraphSelector
from sl3 import CandidateSelector
from utils.graphloader import GraphLoader
from schema_linking.surfing_in_graph import SchemaGenerator
from validator import SLValidator


class SchemaLinkingPipeline:
    def __init__(self, dataset_name, db_name):
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.graph_loader = GraphLoader()
        self.graph_loader.load_graph(dataset_name, db_name)
        self.validator = SLValidator(dataset_name, db_name)
        self.sg = SchemaGenerator()
        self.sl1 = TableSelector()
        self.sl2 = SubgraphSelector(dataset_name, db_name)
        self.sl3 = CandidateSelector(dataset_name, db_name)
        self.logs = []
        self.hint = ''
        self.per_table_results = {}  # 用于保存每个起点的最终子图选择结果
        self.ultimate_answer = {}

    def log(self, msg):
        print(msg)
        self.logs.append(msg)

    def save_log(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        markdown_filename = os.path.join(config.SCHEMA_LINKING, "logs", self.dataset_name, self.db_name,
                                         f"iteration_log_{timestamp}.md")
        os.makedirs(os.path.dirname(markdown_filename), exist_ok=True)
        with open(markdown_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(self.logs))

    def save_final_results(self, question):
        # 生成文件名: 数据集/数据库名目录下的 JSON 文件
        filename = os.path.join(config.SCHEMA_LINKING, "results", self.dataset_name, f"{self.db_name}.json")
        # 如果文件已存在，则加载已有结果，否则初始化为空字典
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
        else:
            existing_results = {"results": []}

        # 当前问题的结果
        current_result = {
            "question": question,
            "schema_linking_result": self.per_table_results,
            "final_results": self.ultimate_answer
        }
        # 将当前结果追加到已有结果中
        existing_results["results"].append(current_result)

        # 确保路径存在后写入文件
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_results, f, indent=2, ensure_ascii=False)
        self.log(f"\n最终结果已保存至 {filename}")

    def select_initial_tables(self, question):
        db_schema = "\n".join(self.sg.generate_combined_description(table) for table in self.sg.tables)
        self.log("## 第一轮表选择")
        sl1_result = self.sl1.select_relevant_tables(db_schema, question)
        selected_tables = sl1_result.get("selected_entity", [])
        if not selected_tables:
            self.log("未找到合适的表，终止执行。")
        else:
            self.log(f"选中的表: {selected_tables}")
        self.log("选择理由:")
        self.log("```json\n" + json.dumps(sl1_result['reasoning'], indent=2, ensure_ascii=False) + "\n```")
        return selected_tables, sl1_result

    def expand_subgraph_once(self, question, selected_table, reasoning_json):
        self.log(f"\n### 起始表: {selected_table}")
        self.log("#### 第一次子图扩展")
        sl2_schema = self.sl2.generate_schema_description([selected_table])
        self.hint = self.sl2.generate_hint(reasoning_json)
        sl2_result = self.sl2.select_relevant_tables(sl2_schema, question, [selected_table], hint=self.hint)
        # 验证、修正结果
        if self.validator.validate_foreign_keys(
                sl2_result["selected_reference_path"]) and self.validator.validate_entities(
            sl2_result["selected_columns"]):
            sl2_result = self.validator.validate_and_correct(sl2_result)
            self.log("迭代扩展结果:")
        else:
            sl2_result = self.validator.validate_and_correct(sl2_result)
            self.log("修正后的结果:")
        self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```")
        return sl2_result

    def iterate_until_solvable(self, question, sl2_result, max_iterations=10):
        # 迭代直到达到最大轮数或生成可解析方案，返回最终的 sl2_result
        is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
        self.log(f"初始 is_solvable: {is_solvable}\n")
        result_from_last_round = self.sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))
        iteration = 0
        while not is_solvable and iteration < max_iterations:
            iteration += 1
            self.log(f"\n#### 第 {iteration} 轮迭代")

            if "selected_columns" not in sl2_result or not sl2_result["selected_columns"]:
                self.log("selected_columns 为空，终止循环。")
                break

            selected_tables = list(sl2_result["selected_columns"].keys())
            self.log(f"新选择的表: {selected_tables}")

            sl2_schema = self.sl2.generate_schema_description(selected_tables)
            sl2_result = self.sl2.select_relevant_tables(sl2_schema, question, selected_tables, result_from_last_round,
                                                         self.hint)
            # 验证、修正结果
            if self.validator.validate_entities(
                    sl2_result["selected_columns"]) and self.validator.validate_foreign_keys(
                sl2_result["selected_reference_path"]):
                sl2_result = self.validator.validate_and_correct(sl2_result)
                self.log("迭代扩展结果:")
            else:
                sl2_result = self.validator.validate_and_correct(sl2_result)
                self.log("修正后的结果:")
            self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```")

            is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
            self.log(f"当前 is_solvable: {is_solvable}")
            result_from_last_round = self.sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))
        return sl2_result

    def select_candidate(self, question):
        self.log("## 候选查询生成")

        candidates = self.per_table_results
        final_selected_result, is_consistent = self.sl3.select_candidate(candidates, question)
        final_selected_result = self.validator.validate_and_correct(final_selected_result)

        is_solvable = final_selected_result.get("to_solve_the_question", {}).get("is_solvable", False)

        # 如果不可解析，最多迭代 3 次重新选择候选
        iteration = 0
        while not is_solvable and iteration < 3:
            iteration += 1
            self.log(f"\n#### 候选选择第 {iteration} 次重试")
            final_selected_result, is_consistent = self.sl3.select_candidate(candidates, question)
            final_selected_result = self.validator.validate_and_correct(final_selected_result)
            is_solvable = final_selected_result.get("to_solve_the_question", {}).get("is_solvable", False)

        if not is_solvable:
            self.log("\n⚠️ 最终候选方案依然不可解析，请检查候选生成模块或人工介入。")

        return final_selected_result, is_consistent

    def run(self, question):
        # self.graph_loader.load_graph(self.dataset_name, self.db_name)
        # 过一秒后再执行后续操作
        time.sleep(1)
        self.log(f"### 数据集: {self.dataset_name}")
        self.log(f"### 数据库: {self.db_name}")
        self.log(f"### 自然语言问题:\n{question.strip()}\n")

        # 阶段一：获取所有初始选中的表
        selected_tables, sl1_result = self.select_initial_tables(question)
        if not selected_tables:
            self.save_log()
            return

        reasoning_json = json.dumps(sl1_result['reasoning'], indent=2, ensure_ascii=False)

        # 阶段二 & 三：遍历每个起点表，执行扩展与迭代
        solvable_count = 0
        for table in selected_tables:
            self.log(f"\n---\n## 起点表 `{table}` 的扩展与推理过程")

            # 执行首次扩展
            sl2_result = self.expand_subgraph_once(question, table, reasoning_json)
            # 迭代更新，返回最终的结果
            final_sl2_result = self.iterate_until_solvable(question, sl2_result)

            if final_sl2_result.get("to_solve_the_question", {}).get("is_solvable", False):
                self.log(f"\n✅ 起点 `{table}` 成功生成可解析的 SQL 查询方案。")
                solvable_count += 1
            else:
                self.log(f"\n❌ 起点 `{table}` 未能生成可解析 SQL 查询。")

            # 保存每个起点的最终扩展结果（完整推理流程的结果）
            self.per_table_results[table] = final_sl2_result

        # 总结：输出有效方案数量，例如 “有效方案：2/3个”
        if solvable_count > 0:
            self.log(f"\n🎯 有效方案：{solvable_count}/{len(selected_tables)}个")
        else:
            self.log("\n🛑 所有起点均未能找到可解析方案，建议人工检查。")
        # 阶段四：选择候选查询
        self.ultimate_answer, is_consistent = self.select_candidate(question)
        self.log("无需 LLM介入：" + str(is_consistent))
        self.log("# 最终选择的候选查询:")
        self.log("```json\n" + json.dumps(self.ultimate_answer, indent=2, ensure_ascii=False) + "\n```")
        # 保存日志和最终 JSON 结果
        self.save_log()
        self.save_final_results(question)


if __name__ == "__main__":
    pipeline = SchemaLinkingPipeline("bird", "mondial_geo")
    # pipeline = SchemaLinkingPipeline("spider", "college_2")
    pipeline.run(
        """Of the deserts on the America Continent, which one covers the greatest area?""")
