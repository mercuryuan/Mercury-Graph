import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing
from datetime import datetime

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
    def __init__(self, dataset_name, db_name, question_data):
        self.dataset_name = dataset_name
        self.db_name = db_name
        # 问题样例数据
        self.question_data = question_data
        self.question = question_data['question']
        self.question_id = question_data['question_id']
        if self.dataset_name == "bird":
            self.evidence = question_data.get('evidence', '')
            self.difficulty = question_data.get('difficulty', '')
        self.validator = SLValidator(dataset_name, db_name)
        self.sg = SchemaGenerator()
        self.sl1 = TableSelector(dataset_name, db_name, self.question_data)
        self.sl2 = SubgraphSelector(dataset_name, db_name, self.question_data)
        self.sl3 = CandidateSelector(dataset_name, db_name, self.question_data)
        self.sl4 = FKFiller(dataset_name, db_name)
        self.logs = []
        self.hint = ''
        self.reasoning = []
        self.per_table_results = {}  # 用于保存每个起点的最终子图选择结果
        self.ultimate_answer = {}
        self.sl2_per_iterations = []
        self.sl3_iteration = 0
        self.default_logger = self._default_logger

    def _default_logger(self, msg):
        print(msg)
        self.logs.append(msg)

    def log(self, msg, logger=None):
        if logger:
            logger(msg)
        else:
            self.default_logger(msg)

    def save_log(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        markdown_filename = os.path.join(config.SCHEMA_LINKING, "logs", self.dataset_name, self.db_name,
                                         f"{self.question_id} {timestamp}.md")
        os.makedirs(os.path.dirname(markdown_filename), exist_ok=True)
        with open(markdown_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(self.logs))

    def save_final_results(self):
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
            "question_id": self.question_id,
            "question": self.question,
            "reasoning": self.reasoning,
            "schema_linking_result": self.per_table_results,
            "sl_iterations": {"sl2": self.sl2_per_iterations, "sl3": self.sl3_iteration},
            "final_results": self.ultimate_answer
        }
        # 将当前结果追加到已有结果中
        existing_results["results"].append(current_result)

        # 确保路径存在后写入文件
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_results, f, indent=2, ensure_ascii=False)
        self.log(f"\n最终结果已保存至 {filename}", )

    def save_sl_to_pipeline(self):
        """
        将 SchemaLinkingPipeline 的结果保存到 完整流程的结果 中（一个问题一个结果）
        """
        filename = os.path.join(config.PROJECT_ROOT, "Results", f"{self.dataset_name}.json")

        # 读取已有结果
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
        else:
            existing_results = {}

        # 如果当前数据库还没有记录，则初始化
        if self.db_name not in existing_results:
            existing_results[self.db_name] = {}

        # 当前问题的结果（覆盖写入）
        existing_results[self.db_name][str(self.question_id)] = {
            "question": self.question,
            "reasoning": self.reasoning,
            "sl_iterations": {"sl2": self.sl2_per_iterations, "sl3": self.sl3_iteration},
            "schema_linking_results": self.ultimate_answer
        }

        # 确保路径存在后写入文件
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_results, f, indent=2, ensure_ascii=False)

        self.log(f"\n唯一结果已保存至 {filename}")

    def is_solved(self):
        """
        检查指定问题 ID 是否已经解决
        """
        filename = os.path.join(config.PROJECT_ROOT, "Results", f"{self.dataset_name}.json")
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
            if self.db_name in existing_results and str(self.question_id) in existing_results[self.db_name]:
                if existing_results[self.db_name][str(self.question_id)]["schema_linking_results"][
                    "to_solve_the_question"]["is_solvable"]:
                    self.log(f"问题 {self.question} 已解决，无需重新执行。")
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
        self.log("问题分解:")
        self.log("```json\n" + json.dumps(sl1_result['the steps of decomposed the question'], indent=2,
                                          ensure_ascii=False) + "\n```")
        return selected_tables, sl1_result

    def expand_subgraph_once(self, question, selected_table, reasoning_json, logger=None):
        self.log(f"\n### 起始表: {selected_table}", logger)
        self.log("#### 第一次子图扩展", logger)
        sl2_schema = self.sl2.generate_schema_description([selected_table])
        self.hint = self.sl2.generate_hint(reasoning_json)
        sl2_result = self.sl2.select_relevant_tables(sl2_schema, question, [selected_table], hint=self.hint)
        # 验证、修正结果
        if self.validator.validate_entities(
                sl2_result["selected_columns"]) and self.validator.validate_foreign_keys(
            sl2_result["selected_reference_path"]):
            sl2_result = self.validator.validate_and_correct(sl2_result)
            self.log("迭代扩展结果:", logger)
        else:
            sl2_result = self.validator.validate_and_correct(sl2_result)
            self.log("修正后的结果:", logger)
        self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```", logger)

        return sl2_result

    def iterate_until_solvable(self, question, sl2_result, max_iterations=10, logger=None):
        # 迭代直到达到最大轮数或生成可解析方案，返回最终的 sl2_result
        is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
        self.log(f"初始 is_solvable: {is_solvable}\n", logger)
        result_from_last_round = self.sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))
        iteration = 0
        prev_selected_tables = list(sl2_result["selected_columns"].keys())
        sl2_schema = self.sl2.generate_schema_description(prev_selected_tables)

        while not is_solvable and iteration < max_iterations:
            iteration += 1
            self.log(f"\n#### 第 {iteration} 轮迭代", logger)

            if not sl2_result.get("selected_columns"):
                self.log("selected_columns 为空，终止循环。", logger)
                raise ValueError("selected_columns 为空，无法继续迭代。")

            selected_tables = list(sl2_result["selected_columns"].keys())
            self.log(f"新选择的表:   \n{selected_tables}  \n", logger)

            # 如果子图连通，则重新生成 schema；否则使用上一轮的 schema
            if self.sg.explorer.is_subgraph_connected(selected_tables):
                sl2_schema = self.sl2.generate_schema_description(selected_tables)
            else:
                self.log("子图不连通，沿用上一轮的 schema。", logger)

            # 新一轮 schema linking
            sl2_result = self.sl2.select_relevant_tables(
                sl2_schema, question, selected_tables, result_from_last_round, self.hint
            )

            # 验证并修正结果
            if self.validator.validate_entities(sl2_result["selected_columns"]) and \
                    self.validator.validate_foreign_keys(sl2_result["selected_reference_path"]):
                sl2_result = self.validator.validate_and_correct(sl2_result)
                self.log("迭代扩展结果:", logger)
            else:
                self.log("原结果", logger)
                self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```", logger)
                self.log("修正后的结果:", logger)
                sl2_result = self.validator.validate_and_correct(sl2_result)

            self.log("```json\n" + json.dumps(sl2_result, indent=2, ensure_ascii=False) + "\n```", logger)

            is_solvable = sl2_result["to_solve_the_question"]["is_solvable"]
            self.log(f"当前 is_solvable: {is_solvable}")
            result_from_last_round = self.sl2.generate_result_from_last_round(json.dumps(sl2_result, indent=2))

        return sl2_result, iteration

    def select_candidate(self, question, recommend_tables):
        self.log("## 候选查询生成")

        candidates = self.per_table_results
        final_selected_result, is_consistent = self.sl3.select_candidate(candidates, question, recommend_tables)
        final_selected_result = self.validator.validate_and_correct(final_selected_result)

        is_solvable = final_selected_result.get("to_solve_the_question", {}).get("is_solvable", False)

        # 如果不可解析，最多迭代 3 次重新选择候选
        result_from_last_round = None
        iteration = 0
        while not is_solvable and iteration < 3:
            iteration += 1
            self.log(f"\n#### 候选选择第 {iteration} 次重试")
            if result_from_last_round:
                final_selected_result, is_consistent = self.sl3.select_candidate(candidates, question, recommend_tables,
                                                                                 result_from_last_round)
            else:
                final_selected_result, is_consistent = self.sl3.select_candidate(candidates, question, recommend_tables,
                                                                                 )
            # 确保实体正确
            final_selected_result = self.validator.validate_and_correct(final_selected_result)
            is_solvable = final_selected_result.get("to_solve_the_question", {}).get("is_solvable", False)
            # 如果验证后失败，则将失败结果作为下一轮迭代的辅助信息
            if not is_solvable:
                result_from_last_round = json.dumps(final_selected_result, indent=2, ensure_ascii=False)

        if not is_solvable:
            self.log("\n⚠️ 最终候选方案依然不可解析，请检查候选生成模块或人工介入。")
        # 得到sl3迭代次数
        self.sl3_iteration = iteration

        return final_selected_result, is_consistent

    def run(self):
        # 防止被api ban
        time.sleep(1)
        # 如果问题已经解决过，则跳过
        if self.is_solved():
            return
        self.log(f"# 数据集: {self.dataset_name}")
        self.log(f"# 数据库: {self.db_name}")
        self.log(f"# 自然语言问题:")
        self.log(f"`{self.question.strip()}`")
        # 统计初始联通分量
        components = self.sg.explorer.obtain_all_connected_components_in_database(
            f"{self.dataset_name}_{self.question_id}")
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
        self.reasoning = reasoning_json

        # 阶段二 & 三：并发处理每个起点表
        def process_start_table(table):
            local_log = []

            def local_logger(msg):
                local_log.append(msg)

            self.log(f"\n---\n## 起点表 `{table}` 的扩展与推理过程", logger=local_logger)

            # 执行首次扩展
            sl2_result = self.expand_subgraph_once(self.question, table, reasoning_json, logger=local_logger)
            final_sl2_result, iteration = self.iterate_until_solvable(self.question, sl2_result, logger=local_logger)

            self.sl2_per_iterations.append({table: iteration})
            self.per_table_results[table] = final_sl2_result

            is_solvable = final_sl2_result.get("to_solve_the_question", {}).get("is_solvable", False)
            if is_solvable:
                local_log.append(f"\n✅ 起点 `{table}` 成功生成可解析的 SQL 查询方案。")
            else:
                local_log.append(f"\n❌ 起点 `{table}` 未能生成可解析 SQL 查询。")

            return "\n".join(local_log), is_solvable

        self.log("### ⚙️ 并发执行每个起点表的推理过程\n")
        solvable_count = 0
        logs_per_table = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_table = {executor.submit(process_start_table, table): table for table in selected_tables}
            for future in as_completed(future_to_table):
                table = future_to_table[future]
                try:
                    local_log, is_solvable = future.result()
                    logs_per_table.append((table, local_log))
                    if is_solvable:
                        solvable_count += 1
                except Exception as exc:
                    logs_per_table.append((table, f"\n❌ 起点 `{table}` 执行失败: {exc}"))

        # 保证日志按原始顺序输出
        for table in selected_tables:
            for t, log_text in logs_per_table:
                if t == table:
                    self.log(log_text)
                    break

        # 总结
        if solvable_count > 0:
            self.log(f"\n🎯 有效方案：{solvable_count}/{len(selected_tables)}个")
        else:
            self.log("\n🛑 所有起点均未能找到可解析方案，建议人工检查。")
        # 阶段四：选择候选查询
        self.ultimate_answer, is_consistent = self.select_candidate(self.question, reasoning_json)
        self.log("无需 LLM介入：" + str(is_consistent))
        self.log("# 最终选择的候选查询:")
        self.log("```json\n" + json.dumps(self.ultimate_answer, indent=2, ensure_ascii=False) + "\n```")
        # 保存日志和最终 JSON 结果
        self.save_log()
        self.save_final_results()
        # 保存到完整总流程的结果中
        self.save_sl_to_pipeline()


def run_bird_dev():
    # 读取 BIRD 开发数据集
    bird_loader = DataLoader("bird_dev")
    bird_dev_list = bird_loader.list_dbname()
    all_samples = bird_loader.filter_data(show_count=True)

    for db_name in bird_dev_list:
        if db_name != "card_games":
            continue  # 跳过其他数据库，只跑 card_games

        # 只对 card_games 数据库处理
        db_samples = [sample for sample in all_samples if sample["db_id"] == db_name]

        # 加载图结构（一次即可）
        graph_loader = GraphLoader()
        graph_loader.load_graph("bird", db_name)

        for sample in db_samples:
            pipeline = SchemaLinkingPipeline("bird", db_name, sample)
            pipeline.run()
            # print(pipeline.question)
            # print(pipeline.question_id)
            break  # 测试用，先只跑一条


def process_sample_bird_with_retry(args, max_retries=2):
    dataset_name, db_name, sample = args
    for attempt in range(max_retries + 1):
        try:
            pipeline = SchemaLinkingPipeline(dataset_name, db_name, sample)
            pipeline.run()
            return None  # 表示成功，无错误信息
        except Exception as e:
            if attempt == max_retries:
                return {
                    "db_name": db_name,
                    "question_id": sample.get("question_id"),
                    "question": sample.get("question"),
                    "error": str(e)
                }


def run_bird_dev_bx():
    # 加载 BIRD 数据
    bird_loader = DataLoader("bird_dev")
    bird_dev_list = bird_loader.list_dbname()
    all_samples = bird_loader.filter_data(show_count=True)

    # 添加 question_id
    for question_id, sample in enumerate(all_samples):
        sample["question_id"] = question_id

    for db_name in bird_dev_list:
        # if db_name != "card_games":
        #     continue  # 只处理 card_games 数据库

        print(f"\n=== 开始处理数据库: {db_name} ===")

        # 加载图结构
        graph_loader = GraphLoader()
        graph_loader.load_graph("bird", db_name)

        # 准备任务
        db_samples = [sample for sample in all_samples if sample["db_id"] == db_name]
        task_list = [("bird", db_name, sample) for sample in db_samples]

        failed_logs = []
        max_workers = min(20, multiprocessing.cpu_count())
        progress_bar = tqdm(total=len(task_list), desc=f"{db_name} 进度", ncols=80)

        # 执行线程池 + 自动重试
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {executor.submit(process_sample_bird_with_retry, task): task for task in task_list}

            for future in as_completed(future_to_task):
                result = future.result()
                if result is not None:
                    failed_logs.append(result)
                progress_bar.update(1)

        progress_bar.close()
        print(f"=== ✅ 完成数据库: {db_name} ===")

        # 每个数据库处理后保存失败日志（追加模式）
        if failed_logs:
            file = os.path.join(config.PROJECT_ROOT, "Results", "bird.md")
            with open(file, "a", encoding="utf-8") as f:
                f.write(f"# ❌ 数据库 `{db_name}` 处理失败样本记录\n\n")
                for item in failed_logs:
                    f.write(f"## 问题 ID: {item['question_id']}\n")
                    f.write(f"**Question:** {item['question']}\n\n")
                    f.write(f"**Error:** `{item['error']}`\n\n---\n\n")
            print(f"⚠️ 错误日志已追加写入 `{file}`\n")


def run_spider_dev():
    # 读取 spider 开发数据集
    spider_loader = DataLoader("spider_dev")
    spider_dev_list = spider_loader.list_dbname()
    data = spider_loader.filter_data(fields=["db_id", "sql", "question"],
                                     show_count=True)
    # 给data添加一个question_id字段
    for question_id, d in enumerate(data):
        d['question_id'] = question_id

    for database in spider_dev_list:
        # if database != "tvshow":
        #     continue  # 跳过其他数据库
        graph_loader = GraphLoader()
        graph_loader.load_graph("spider", database)
        database_data = [item for item in data if item["db_id"] == database]
        for sample in database_data:
            pipeline = SchemaLinkingPipeline("spider", database, sample)
            pipeline.run()


def process_sample(args):
    dataset_name, database, sample = args
    pipeline = SchemaLinkingPipeline(dataset_name, database, sample)
    pipeline.run()


def run_spider_dev_bx():
    # 加载数据
    spider_loader = DataLoader("spider_dev")
    spider_dev_list = spider_loader.list_dbname()
    data = spider_loader.filter_data(fields=["db_id", "sql", "question"], show_count=True)

    for question_id, d in enumerate(data):
        d['question_id'] = question_id

    for database in spider_dev_list:
        print(f"\n=== 开始处理数据库: {database} ===")

        # 加载图结构
        graph_loader = GraphLoader()
        graph_loader.load_graph("spider", database)

        # 提取该数据库对应的样本
        database_data = [item for item in data if item["db_id"] == database]
        task_list = [("spider", database, sample) for sample in database_data]

        # 设置线程池 & 进度条
        max_workers = min(16, multiprocessing.cpu_count())
        progress_bar = tqdm(total=len(task_list), desc=f"{database} 进度", ncols=80)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sample = {executor.submit(process_sample, task): task for task in task_list}

            for future in as_completed(future_to_sample):
                try:
                    future.result()
                except Exception as e:
                    print(f"❌ 某个样本处理失败: {e}")
                finally:
                    progress_bar.update(1)

        progress_bar.close()
        print(f"=== ✅ 完成数据库: {database} ===\n")


if __name__ == "__main__":
    # run_bird_dev()
    # run_spider_dev()
    run_bird_dev_bx()
    # run_spider_dev_bx()

    # # 单个问题
    # GraphLoader().load_graph("bird", "card_games")
    # pipeline = SchemaLinkingPipeline("bird", "card_games",
    #                                  {
    #                                      "question": """Please list the names of the cards in the set "Hauptset Zehnte Edition".""",
    #                                      "question_id": "10086"})
    # pipeline.run()
