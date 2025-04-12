import json
import os
import time
import concurrent.futures
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from schema_enricher.utils.fk_filler import FKFiller
from schema_linking.sl1_ds import TableSelector
from schema_linking.sl2_ds import SubgraphSelector
from schema_linking.sl3 import CandidateSelector
from utils.dataloader import DataLoader
from utils.graphloader import GraphLoader
from schema_linking.surfing_in_graph import SchemaGenerator
from schema_linking.validator import SLValidator


class SchemaLinkingPipeline:
    def __init__(self, dataset_name, db_name, question_data, concurrency=8):
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.question_data = question_data
        self.question = question_data['question']
        self.question_id = question_data['question_id']
        if self.dataset_name == "bird":
            self.evidence = question_data.get('evidence', '')
            self.difficulty = question_data.get('difficulty', '')
        self.validator = SLValidator(dataset_name, db_name)
        self.sg = SchemaGenerator()
        self.sl1 = TableSelector(self.question_data)
        self.sl2 = SubgraphSelector(dataset_name, db_name, self.question_data)
        self.sl3 = CandidateSelector(dataset_name, db_name, self.question_data)
        self.sl4 = FKFiller(dataset_name, db_name)
        self.logs = []
        self.hint = ''
        self.per_table_results = {}
        self.ultimate_answer = {}
        self.sl2_per_iterations = []
        self.sl3_iteration = 0
        self.concurrency = concurrency  # 控制二级并发的线程数
        self.log_lock = threading.Lock()  # 日志线程锁

    def log(self, msg):
        with self.log_lock:  # 保证多线程日志安全
            print(msg)
            self.logs.append(msg)

    def save_log(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        markdown_filename = os.path.join(config.SCHEMA_LINKING, "logs", self.dataset_name, self.db_name,
                                         f"{self.question_id} {timestamp}.md")
        os.makedirs(os.path.dirname(markdown_filename), exist_ok=True)
        with open(markdown_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(self.logs))

    def save_final_results(self):
        filename = os.path.join(config.SCHEMA_LINKING, "results", self.dataset_name, f"{self.db_name}.json")
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
        else:
            existing_results = {"results": []}

        current_result = {
            "question_id": self.question_id,
            "question": self.question,
            "schema_linking_result": self.per_table_results,
            "sl_iterations": {"sl2": self.sl2_per_iterations, "sl3": self.sl3_iteration},
            "final_results": self.ultimate_answer
        }
        existing_results["results"].append(current_result)

        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_results, f, indent=2, ensure_ascii=False)
        self.log(f"\n最终结果已保存至 {filename}")

    def save_sl_to_pipeline(self):
        filename = os.path.join(config.PROJECT_ROOT, "Results", f"{self.dataset_name}.json")
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
        else:
            existing_results = {}

        if self.db_name not in existing_results:
            existing_results[self.db_name] = {}

        existing_results[self.db_name][self.question_id] = {
            "question": self.question,
            "sl_iterations": {"sl2": self.sl2_per_iterations, "sl3": self.sl3_iteration},
            "schema_linking_results": self.ultimate_answer
        }

        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_results, f, indent=2, ensure_ascii=False)
        self.log(f"\n唯一结果已保存至 {filename}")

    def is_solved(self):
        filename = os.path.join(config.PROJECT_ROOT, "Results", f"{self.dataset_name}.json")
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
            if self.db_name in existing_results and str(self.question_id) in existing_results[self.db_name]:
                return True
        return False

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
        if self.validator.validate_entities(
                sl2_result["selected_columns"]) and self.validator.validate_foreign_keys(
            sl2_result["selected_reference_path"]):
            sl2_result = self.validator.validate_and_correct(sl2_result)
            self.log("迭代扩展结果:")
        else:
            sl2_result = self.validator.validate_and_correct(sl2_result)
            self.log("修正后的结果:")
        self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```")
        return sl2_result

    def iterate_until_solvable(self, question, sl2_result, max_iterations=10):
        is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
        self.log(f"初始 is_solvable: {is_solvable}\n")
        result_from_last_round = self.sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))
        iteration = 0
        prev_selected_tables = list(sl2_result["selected_columns"].keys())
        sl2_schema = self.sl2.generate_schema_description(prev_selected_tables)

        while not is_solvable and iteration < max_iterations:
            iteration += 1
            self.log(f"\n#### 第 {iteration} 轮迭代")

            if not sl2_result.get("selected_columns"):
                self.log("selected_columns 为空，终止循环。")
                break

            selected_tables = list(sl2_result["selected_columns"].keys())
            self.log(f"新选择的表:   \n{selected_tables}  \n")

            if self.sg.explorer.is_subgraph_connected(selected_tables):
                sl2_schema = self.sl2.generate_schema_description(selected_tables)
            else:
                self.log("子图不连通，沿用上一轮的 schema。")

            sl2_result = self.sl2.select_relevant_tables(
                sl2_schema, question, selected_tables, result_from_last_round, self.hint
            )

            if self.validator.validate_entities(sl2_result["selected_columns"]) and \
                    self.validator.validate_foreign_keys(sl2_result["selected_reference_path"]):
                sl2_result = self.validator.validate_and_correct(sl2_result)
                self.log("迭代扩展结果:")
            else:
                sl2_result = self.validator.validate_and_correct(sl2_result)
                self.log("修正后的结果:")

            self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```")

            is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
            self.log(f"当前 is_solvable: {is_solvable}")
            result_from_last_round = self.sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))

        return sl2_result, iteration

    def process_table(self, table, reasoning_json):
        """处理单个表的二级并行任务"""
        self.log(f"\n---\n## 起点表 `{table}` 的扩展与推理过程")
        sl2_result = self.expand_subgraph_once(self.question, table, reasoning_json)
        final_sl2_result, iteration = self.iterate_until_solvable(self.question, sl2_result)
        return final_sl2_result, iteration, table

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
            # 确保实体正确
            final_selected_result = self.validator.validate_and_correct(final_selected_result)
            is_solvable = final_selected_result.get("to_solve_the_question", {}).get("is_solvable", False)

        if not is_solvable:
            self.log("\n⚠️ 最终候选方案依然不可解析，请检查候选生成模块或人工介入。")
        # 得到sl3迭代次数
        self.sl3_iteration = iteration

        return final_selected_result, is_consistent

    def run(self):
        # 如果问题已经解决过，则跳过
        if self.is_solved():
            print(f"问题 '{self.question}' 已经解决过，跳过执行。")
            return

        self.log(f"# 数据集: {self.dataset_name}")
        self.log(f"# 数据库: {self.db_name}")
        self.log(f"# 自然语言问题:")
        self.log(f"`{self.question.strip()}`")
        # 统计初始联通分量
        components = self.sg.explorer.obtain_all_connected_components_in_database()
        if len(components) == 1:
            self.log("### 初始状态：数据库连通")
        else:
            self.log(f"### ⚠️初始状态：数据库中存在 {len(components)} 个不连通的分量")
            components_str = '  \n'.join(['`' + str(component) + '`' for component in components])
            self.log(f"#### 联通分量：  \n{components_str}")

        # 阶段一：获取所有初始选中的表
        selected_tables, sl1_result = self.select_initial_tables(self.question)
        if not selected_tables:
            self.save_log()
            return

        reasoning_json = json.dumps(sl1_result['reasoning'], indent=2, ensure_ascii=False)

        # 阶段二 & 三：遍历每个起点表，执行扩展与迭代
        solvable_count = 0
        self.per_table_results = {}
        self.sl2_per_iterations = []

        # 二级并行处理每个表
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {executor.submit(self.process_table, table, reasoning_json): table for table in selected_tables}
            for future in as_completed(futures):
                table = futures[future]
                try:
                    final_sl2_result, iteration, table = future.result()
                    self.sl2_per_iterations.append({table: iteration})
                    if final_sl2_result.get("to_solve_the_question", {}).get("is_solvable", False):
                        self.log(f"\n✅ 起点 `{table}` 成功生成可解析的 SQL 查询方案。")
                        solvable_count += 1
                    else:
                        self.log(f"\n❌ 起点 `{table}` 未能生成可解析 SQL 查询。")

                    # 保存每个起点的最终扩展结果（完整推理流程的结果）
                    self.per_table_results[table] = final_sl2_result
                except Exception as e:
                    self.log(f"处理表 `{table}` 时发生错误: {str(e)}")

        if solvable_count > 0:
            self.log(f"\n🎯 有效方案：{solvable_count}/{len(selected_tables)}个")
        else:
            self.log("\n🛑 所有起点均未能找到可解析方案，建议人工检查。")

        self.ultimate_answer, is_consistent = self.select_candidate(self.question)
        self.log("无需 LLM介入：" + str(is_consistent))
        self.log("# 最终选择的候选查询:")
        self.log("```json\n" + json.dumps(self.ultimate_answer, indent=2, ensure_ascii=False) + "\n```")
        # 保存日志和最终 JSON 结果
        self.save_log()
        self.save_final_results()
        # 保存到完整总流程的结果中
        self.save_sl_to_pipeline()


def process_single_sample(dataset_name, db_name, sample, concurrency):
    """处理单个样本的一级并行任务"""
    GraphLoader().load_graph(dataset_name, db_name)  # 确保图已加载（利用缓存）
    pipeline = SchemaLinkingPipeline(dataset_name, db_name, sample, concurrency=concurrency)
    pipeline.run()


def run_bird_dev(outer_concurrency=8, inner_concurrency=8):
    bird_loader = DataLoader("bird_dev")
    bird_dev_list = bird_loader.list_dbname()
    all_samples = bird_loader.filter_data(show_count=True)

    for db_name in bird_dev_list:
        if db_name != "card_games":
            continue

        GraphLoader().load_graph("bird", db_name)
        db_samples = [sample for sample in all_samples if sample["db_id"] == db_name]

        with ThreadPoolExecutor(max_workers=outer_concurrency) as executor:
            futures = []
            for sample in db_samples:
                future = executor.submit(process_single_sample, "bird", db_name, sample, inner_concurrency)
                futures.append(future)
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"处理样本时发生错误: {e}")


def run_spider_dev(outer_concurrency=8, inner_concurrency=8):
    spider_loader = DataLoader("spider_dev")
    spider_dev_list = spider_loader.list_dbname()
    data = spider_loader.filter_data(fields=["db_id", "sql", "question"], show_count=True)
    for question_id, d in enumerate(data):
        d['question_id'] = question_id

    for db_name in spider_dev_list:
        GraphLoader().load_graph("spider", db_name)
        db_data = [item for item in data if item["db_id"] == db_name]
        with ThreadPoolExecutor(max_workers=outer_concurrency) as executor:
            futures = []
            for sample in db_data:
                future = executor.submit(process_single_sample, "spider", db_name, sample, inner_concurrency)
                futures.append(future)
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"处理样本时发生错误: {e}")


if __name__ == "__main__":
    # 设置并发参数
    outer_concurrency = 10  # 一级并发：同时处理的问题数
    inner_concurrency = 5  # 二级并发：每个问题处理的表数

    # 运行完整数据集测试
    # run_bird_dev(outer_concurrency, inner_concurrency)
    run_spider_dev(outer_concurrency, inner_concurrency)

    # # 单个问题测试
    # GraphLoader().load_graph("bird", "card_games")
    # pipeline = SchemaLinkingPipeline(
    #     "bird", "card_games",
    #     {
    #         "question": """Please list the names of the cards in the set "Hauptset Zehnte Edition".""",
    #         "question_id": "10086"
    #     },
    #     concurrency=inner_concurrency
    # )
    # pipeline.run()
