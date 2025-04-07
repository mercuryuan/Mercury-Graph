import json
from typing import Dict
from schema_linking.surfing_in_graph import Neo4jExplorer


class SLValidator:
    def __init__(self):
        self.explorer = Neo4jExplorer()
        self.valid_tables = {}

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
        """
        try:
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
            print(f"Error: {e}")
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
        验证并校正结果字典。
        """
        # 校正实体
        selected_columns = result["selected_columns"]
        self.valid_tables = self.filter_valid_tables(selected_columns)
        # 校正外键连接
        selected_reference_path = result["selected_reference_path"]
        valid_foreign_keys = self.filter_valid_foreign_keys(selected_reference_path)
        # 校正推理
        reasoning = result["reasoning"]

        valid_reasoning = self.filter_valid_reasoning(reasoning)
        if self.validate_foreign_keys(selected_reference_path) and self.validate_entities(selected_columns):
            return result
        else:
            to_solve_the_question = {"is_solvable": False}
            return {"selected_columns": self.valid_tables, "selected_reference_path": valid_foreign_keys,
                    "reasoning": valid_reasoning, "to_solve_the_question": to_solve_the_question}


if __name__ == '__main__':
    validator = SLValidator()
    result = """{
  "selected_columns": {
    "course": [
      "course_id",
      "title"
    ],
    "prereq": [
      "course_id",
      "prereq_id"
    ],
    "takes": [
      "ID",
      "course_id"
    ],
    "student": [
      "ID",
      "name"
    ]
  },
  "selected_reference_path": {
    "course.course_id=prereq.course_id": "To find the prerequisite course for 'International Finance'",
    "prereq.prereq_id=takes.course_id": "To identify students who have taken the prerequisite course",
    "takes.ID=student.ID": "To retrieve the names of students who have taken the prerequisite course"
  },
  "reasoning": {
    "course": "Selected course_id to identify the course with title 'International Finance' and needed the title for filtering.",
    "prereq": "Selected course_id to relate it to the course and prereq_id to find the students' courses from takes.",
    "takes": "Essential to link student IDs with the previously identified prereq course_id.",
    "student": "Needed to fetch student names using their IDs."
  },
  "to_solve_the_question": {
    "is_solvable": true,
    "Identify course ID for 'International Finance' from the course table.": true,
    "Determine the prerequisite course ID for this course from the prereq table.": true,
    "Use the takes table to find students who have taken the prerequisite course.": true,
    "Retrieve the names of these students from the student table.": true
  }
}"""
    result = json.loads(result)
    selected_columns = result["selected_columns"]
    referenced_paths = result["selected_reference_path"]
    # print(type(selected_columns))
    # print(selected_columns)
    # print(validator.validate_entities(selected_columns))
    # validator.valid_tables = validator.filter_valid_tables(selected_columns)
    # print(validator.validate_foreign_keys(referenced_paths))
    # valid_foreign_keys = validator.filter_valid_foreign_keys(referenced_paths)
    # print(valid_foreign_keys)
    # reasoning = result["reasoning"]
    # print(json.dumps(validator.filter_valid_reasoning(reasoning), indent=2))
    # print()
    # print()
    # print()
    print(json.dumps(validator.validate_and_correct(result), indent=2))
    print(validator.explorer.get_all_tables())
