"""
过滤逻辑：
遍历 result_json 中的所有候选结果，检查 to_solve_the_question.is_solvable 是否为 true。不满足的候选结果将被过滤，不参与后续比较，也不会出现在最终输出中。

候选结果数量判断：

如果过滤后候选结果只有一个，直接返回该候选结果（保留所有原始信息）。

如果有多个候选结果，则先对 selected_columns 与 selected_reference_path 进行标准化比较。

比较一致性：

如果所有候选结果一致，则返回第一个候选结果；

否则返回过滤后的所有候选结果（保证输出中只包含 is_solvable 为 true 的候选）。
"""
import json


class CandidateFilter:
    @staticmethod
    def parse_reference_path(path: str):
        """
        解析引用路径，返回一个 frozenset 表示无向连接，格式为 {(table, column), (table, column)}
        如果格式不对，则打印错误并返回 None
        """
        try:
            parts = path.split("=")
            if len(parts) != 2:
                print(f"Path 解析错误: {path} 格式不对")
                return None
            left_part = parts[0].strip().split(".")
            right_part = parts[1].strip().split(".")
            if len(left_part) != 2 or len(right_part) != 2:
                print(f"Path 解析错误: {path} 解析后左右部分不为2个元素")
                return None
            left_table, left_column = left_part
            right_table, right_column = right_part
            # 构造无向表示的 frozenset（方向无关）
            pair = frozenset({(left_table, left_column), (right_table, right_column)})
            return pair
        except Exception as e:
            print(f"Path 解析错误: {e}")
            return None

    @staticmethod
    def normalize_selected_columns(selected_columns: dict):
        """
        对 selected_columns 做标准化：对每个表的列列表进行排序
        """
        norm = {}
        for table, cols in selected_columns.items():
            norm[table] = sorted(cols)
        return norm

    @staticmethod
    def normalize_selected_reference_path(selected_reference_path: dict):
        """
        对 selected_reference_path 做标准化：转换每个连接为无向的 frozenset，并放入集合中
        """
        norm = set()
        for path in selected_reference_path.keys():
            normalized = CandidateFilter.parse_reference_path(path)
            if normalized is None:
                continue
            norm.add(normalized)
        return norm

    @staticmethod
    def schema_linking_final_answer(result_json: dict):
        """
        过滤掉 is_solvable 不为 true 的候选结果后：
          - 如果候选结果只有一个，则直接返回该候选结果（原封不动输出），同时返回一致标志 True。
          - 如果候选结果超过一个：
               * 如果所有候选结果在 selected_columns 与 selected_reference_path 上（无向比较）完全一致，
                 则返回第一个候选结果（原封不动输出），同时返回一致标志 True。
               * 如果不完全一致，则返回过滤后的所有候选结果（原输出只保留 is_solvable 为 true 的候选），
                 同时返回一致标志 False。
        返回值格式为 (最终结果, 是否一致的标志)
        """
        # 过滤掉 is_solvable 不为 true 的候选结果
        filtered_candidates = {}
        for candidate_key, candidate_value in result_json.items():
            to_solve = candidate_value.get("to_solve_the_question", {})
            if to_solve.get("is_solvable", False) is True:
                filtered_candidates[candidate_key] = candidate_value
            else:
                print(f"候选结果 '{candidate_key}' 被过滤掉，因为 is_solvable 不为 true。")

        # 如果过滤后的候选结果为空，返回空字典和 False 标志
        if not filtered_candidates:
            print("没有满足 is_solvable 为 true 的候选结果。")
            return {}, False

        candidate_keys = list(filtered_candidates.keys())

        # 如果候选结果只有一个，直接返回，并认为是一致的
        if len(candidate_keys) == 1:
            return filtered_candidates[candidate_keys[0]], True

        # 对多个候选结果进行标准化比较
        normalized_results = {}
        for candidate_key, candidate_value in filtered_candidates.items():
            sel_cols = candidate_value.get("selected_columns", {})
            sel_paths = candidate_value.get("selected_reference_path", {})
            norm_cols = CandidateFilter.normalize_selected_columns(sel_cols)
            norm_paths = CandidateFilter.normalize_selected_reference_path(sel_paths)
            normalized_results[candidate_key] = (norm_cols, norm_paths)

        # 取第一个候选结果作为参考进行比较
        first_value = None
        consistent = True
        for candidate, norm in normalized_results.items():
            if first_value is None:
                first_value = norm
            else:
                if norm != first_value:
                    consistent = False
                    break

        if consistent:
            # 所有候选结果一致，返回第一个候选结果，并标记为一致
            first_key = candidate_keys[0]
            return filtered_candidates[first_key], True
        else:
            # 候选结果不一致，返回过滤后的所有候选结果，并标记为不一致
            return filtered_candidates, False


if __name__ == '__main__':
    # 示例：解析给定的 JSON 字符串并调用函数
    result = """{
        "Recipe": {
          "selected_columns": {
            "Recipe": [
              "recipe_id",
              "cook_min"
            ],
            "Quantity": [
              "recipe_id",
              "ingredient_id"
            ],
            "Ingredient": [
              "ingredient_id",
              "name"
            ]
          },
          "selected_reference_path": {
            "Recipe.recipe_id=Quantity.recipe_id": "To link the recipe with its ingredients",
            "Quantity.ingredient_id=Ingredient.ingredient_id": "To get the names of the ingredients"
          },
          "reasoning": {
            "Recipe": "The 'cook_min' column is needed to identify the recipe with the longest cooking time. The 'recipe_id' is needed to link with the Quantity table.",
            "Quantity": "The 'recipe_id' and 'ingredient_id' columns are needed to find the ingredients associated with the identified recipe.",
            "Ingredient": "The 'ingredient_id' and 'name' columns are needed to get the names of the ingredients."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "What ingredients does the longest cooking time recipe have?",
            "reason": "The 'Recipe' table provides the cooking time to identify the longest cooking recipe. The 'Quantity' table links recipes to their ingredients, and the 'Ingredient' table provides the names of these ingredients. Together, these tables contain all necessary information to answer the question."
          }
        },
        "Quantity": {
          "selected_columns": {
            "Quantity": [
              "recipe_id",
              "ingredient_id"
            ],
            "Recipe": [
              "recipe_id",
              "cook_min"
            ],
            "Ingredient": [
              "ingredient_id",
              "name"
            ]
          },
          "selected_reference_path": {
            "Quantity.recipe_id=Recipe.recipe_id": "To link ingredients to their respective recipes for identifying the longest cooking time recipe.",
            "Quantity.ingredient_id=Ingredient.ingredient_id": "To get the names of the ingredients used in the identified recipe."
          },
          "reasoning": {
            "Quantity": "Selected 'recipe_id' and 'ingredient_id' to connect recipes with their ingredients.",
            "Recipe": "Needed 'cook_min' to determine the recipe with the longest cooking time and 'recipe_id' to join with Quantity.",
            "Ingredient": "Required 'name' to identify the ingredients and 'ingredient_id' to join with Quantity."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "What ingredients does the longest cooking time recipe have?",
            "reason": "The 'Quantity' table alone does not contain information about cooking times or ingredient names. By joining 'Quantity' with 'Recipe' via 'recipe_id', we can identify the recipe with the longest 'cook_min'. Then, by joining 'Quantity' with 'Ingredient' via 'ingredient_id', we can retrieve the names of the ingredients used in that recipe. This combination of tables and columns provides all necessary information to answer the question."
          }
        },
        "Ingredient": {
          "selected_columns": {
            "Ingredient": [
              "ingredient_id",
              "name"
            ],
            "Quantity": [
              "recipe_id",
              "ingredient_id"
            ],
            "Recipe": [
              "recipe_id",
              "cook_min"
            ]
          },
          "selected_reference_path": {
            "Quantity.ingredient_id=Ingredient.ingredient_id": "To link ingredients to their quantities in recipes",
            "Quantity.recipe_id=Recipe.recipe_id": "To link quantities to their respective recipes"
          },
          "reasoning": {
            "Ingredient": "Selected 'ingredient_id' and 'name' to identify and name the ingredients.",
            "Quantity": "Selected 'recipe_id' and 'ingredient_id' to associate ingredients with recipes.",
            "Recipe": "Selected 'recipe_id' and 'cook_min' to determine the recipe with the longest cooking time."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "What ingredients does the longest cooking time recipe have?",
            "reason": "The 'Ingredient' table alone does not contain information about recipes or cooking times. By expanding to the 'Quantity' and 'Recipe' tables, we can associate ingredients with recipes and identify the recipe with the longest cooking time. The 'Ingredient' table provides the names of the ingredients, the 'Quantity' table links ingredients to recipes, and the 'Recipe' table provides the cooking times necessary to determine the longest cooking time recipe."
          }
        }
    }"""

    result_dict = json.loads(result)
    final_result, is_consistent = CandidateFilter.schema_linking_final_answer(result_dict)
    print("输出是否一致:", is_consistent)
    print(json.dumps(final_result, indent=4, ensure_ascii=False))
