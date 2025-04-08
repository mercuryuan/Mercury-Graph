import json
from typing import Dict
from schema_linking.surfing_in_graph import Neo4jExplorer
from schema_enricher.utils.fk_compare import extract_foreign_keys


class SLValidator:
    def __init__(self, dataset_name, db_name):
        self.explorer = Neo4jExplorer()
        self.valid_tables = {}
        self.dataset_name = dataset_name
        self.db_name = db_name

    def validate_entities(self, selected_columns: Dict) -> bool:
        """
        验证选择的列是否存在于数据库对应表中，并返回验证结果。
        """
        for table, columns in selected_columns.items():
            if table not in list(self.explorer.get_all_tables().keys()):
                return False
            gtcols = self.explorer.get_columns_for_table(table)
            # print(list(gtcols.keys()))
            # print(columns)
            # 验证columns 都在 gtcols 中
            if not all(col in gtcols for col in columns):
                # print(f"Error: Columns {columns} not found in table {table}.")
                return False
        return True

    # 过滤selected_columns中通过验证的表
    def filter_valid_tables(self, selected_columns: Dict) -> Dict:
        """
        过滤selected_columns中通过验证的表。
        """
        valid_tables = {}  # 存储通过验证的表
        for table, columns in selected_columns.items():
            if self.validate_entities({table: columns}):
                valid_tables[table] = columns
        return valid_tables

    # 输入selected_reference_path字典，分析并验证外键连接涉及的实体都属于valid_tables
    def validate_foreign_keys(self, selected_reference_path: Dict) -> bool:
        """
        验证外键连接涉及的实体都属于valid_tables。
        两侧的表列实体都要在valid_tables中找得到对应的表列结构
        如果有一个外键连接的两侧实体不在valid_tables中，则返回False。
        """
        try:
            # 注意在此之前要初始化好self.valid_tables
            for path, reason in selected_reference_path.items():
                # print(path)
                # print(reason)
                left_table, left_column = path.split("=")[0].split(".")
                right_table, right_column = path.split("=")[1].split(".")
                # 验证两侧的表列实体都在valid_tables中找得到对应的表列结构
                if left_table not in self.valid_tables or right_table not in self.valid_tables:
                    return False
                if left_column not in self.valid_tables[left_table] or right_column not in self.valid_tables[
                    right_table]:
                    return False
        except Exception as e:
            print(f"Validation Error: {e}")
            return False
        return True

    # 过滤出selected_reference_path中通过验证的外键连接
    def filter_valid_foreign_keys(self, selected_reference_path: Dict) -> Dict:
        """
        过滤出selected_reference_path中通过验证的外键连接。
        """
        valid_foreign_keys = {}  # 存储通过验证的外键连接
        for path, reason in selected_reference_path.items():
            if self.validate_foreign_keys({path: reason}):
                valid_foreign_keys[path] = reason
        return valid_foreign_keys

    # 过滤reasoning中在valid_tables中存在的推理
    def filter_valid_reasoning(self, reasoning: Dict) -> Dict:
        """
        过滤reasoning中在valid_tables中存在的推理。
        """
        valid_reasoning = {}  # 存储通过验证的推理
        for table, reason in reasoning.items():
            if table in self.valid_tables:
                valid_reasoning[table] = reason
        return valid_reasoning

    # 总函数，输入结果字典，输出验证并校正的结果
    def validate_and_correct(self, result: Dict) -> Dict:
        """
        Validate and correct the result dictionary.
        Add detailed failure reasons if validation fails.
        """
        selected_columns = result["selected_columns"]
        self.valid_tables = self.filter_valid_tables(selected_columns)
        selected_reference_path = result["selected_reference_path"]
        valid_foreign_keys = self.filter_valid_foreign_keys(selected_reference_path)
        reasoning = result["reasoning"]
        valid_reasoning = self.filter_valid_reasoning(reasoning)

        failure_reasons = []

        for table, columns in selected_columns.items():
            if table not in self.explorer.get_all_tables():
                failure_reasons.append(f"Table '{table}' does not exist in the database.Please check.")
            else:
                gtcols = self.explorer.get_columns_for_table(table)
                invalid_cols = [col for col in columns if col not in gtcols]
                if invalid_cols:
                    failure_reasons.append(
                        f"Table '{table}' does not contain columns: {', '.join(invalid_cols)}.Please check.")

        for table, columns in selected_columns.items():
            if not columns:
                failure_reasons.append(f"Table '{table}' must contain at least one selected column.Please check.")

        for path in selected_reference_path:
            try:
                left_table, left_column = path.split("=")[0].strip().split(".")
                right_table, right_column = path.split("=")[1].strip().split(".")
                left_exists = left_table in self.explorer.get_all_tables() and \
                              left_column in self.explorer.get_columns_for_table(left_table)
                right_exists = right_table in self.explorer.get_all_tables() and \
                               right_column in self.explorer.get_columns_for_table(right_table)
                if not (left_exists and right_exists):
                    failure_reasons.append(f"Path '{path}' contains entities not found in the database.")
            except Exception as e:
                failure_reasons.append(f"Path '{path}' cannot be parsed: {e}")

        for path in selected_reference_path:
            try:
                left_table, left_column = path.split("=")[0].strip().split(".")
                right_table, right_column = path.split("=")[1].strip().split(".")

                if left_table not in selected_columns or left_column not in selected_columns[left_table]:
                    failure_reasons.append(
                        f"Left entity of path '{path}' is not included in selected_columns.Please check.")

                if right_table not in selected_columns or right_column not in selected_columns[right_table]:
                    failure_reasons.append(
                        f"Right entity of path '{path}' is not included in selected_columns.Please check.")
            except Exception as e:
                failure_reasons.append(f"Error parsing path '{path}': {e}")

        if not failure_reasons:
            return result
        else:
            return {
                "selected_columns": self.valid_tables,
                "selected_reference_path": valid_foreign_keys,
                "reasoning": valid_reasoning,
                "to_solve_the_question": {
                    "is_solvable": False,
                    "failure_reasons": failure_reasons
                }
            }

    # 判断两表之间是否存在外键连接
    def is_fk_exists(self, path: str) -> bool:
        """
        判断给定路径所描述的两表之间是否存在外键连接。

        参数：
            path (str): 形如 "Nutrition.recipe_id=Recipe.recipe_id" 的字符串，表示一对潜在的外键连接。

        返回：
            bool: 如果该连接存在于当前数据库的外键集合中，则返回 True；否则返回 False。
        """
        # 提取左右表和列
        try:
            left_table, left_column = path.split("=")[0].strip().split(".")
            right_table, right_column = path.split("=")[1].strip().split(".")
        except Exception as e:
            print(f"Path 解析错误: {e}")
            return False

        # 调用外部函数获取当前数据库的所有外键连接
        foreign_keys = extract_foreign_keys(self.dataset_name, self.db_name)

        # 构造表示当前连接的 frozenset（两种方向都要考虑）
        pair1 = frozenset({(left_table, left_column), (right_table, right_column)})
        pair2 = frozenset({(right_table, right_column), (left_table, left_column)})

        # 判断是否存在匹配的外键连接（frozenset 是无序的，单个判断就够）
        return pair1 in foreign_keys


if __name__ == '__main__':
    validator = SLValidator("bird", "cookbook")
    result = """{
  "selected_columns": {
            "Nutrition": [
              "recipe_id",
              "total_fat",
              "sat_fat",
              "calories"
            ],
            "Recipe": [
              "recipe_id",
              "title"
            ]
          },
          "selected_reference_path": {
            "Nutrition.recipe_id=Recipe.recipe_id": "Link Nutrition data to Recipe titles to identify which recipe correlates with the high potential for weight gain."
          },
          "reasoning": {
            "Nutrition": "Selected columns (total_fat, sat_fat, calories) are necessary to determine the recipes that could lead to weight gain. The recipe_id is also needed to join with the Recipe table.",
            "Recipe": "Selected this table to get the title of the recipes, which is crucial to answering the question about which recipe is most likely to contribute to weight gain."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "What is the title of the recipe that is most likely to gain weight?",
            "reason": "To determine which recipe is most likely to cause weight gain, we need to analyze high total_fat, sat_fat, and calories from the Nutrition table and link this information to the corresponding recipe titles in the Recipe table."
          }
}"""
    result = json.loads(result)
    selected_columns = result["selected_columns"]
    referenced_paths = result["selected_reference_path"]
    # print(type(selected_columns))
    # print(selected_columns)
    # 验证selected_columns中的表列实体是否存在于数据库对应表中
    print(validator.validate_entities(selected_columns))
    # validator.valid_tables = validator.filter_valid_tables(selected_columns)
    # 验证referenced_paths中的外键连接是否存在于数据库对应表中
    print(referenced_paths)
    print(validator.validate_foreign_keys(referenced_paths))
    valid_foreign_keys = validator.filter_valid_foreign_keys(referenced_paths)
    # print(valid_foreign_keys)
    # reasoning = result["reasoning"]
    # print(json.dumps(validator.filter_valid_reasoning(reasoning), indent=2))
    # print()
    # print()
    # print()
    # 输出是否通过验证
    if validator.validate_foreign_keys(referenced_paths) and validator.validate_entities(selected_columns):
        print("不需修改")
    else:
        print("需要修改")
    print(json.dumps(validator.validate_and_correct(result), indent=2))
    # print(validator.explorer.get_all_tables())
    # print(validator.is_fk_exists("Nutrition.recipe_id=Recipe.recipe_id"))
