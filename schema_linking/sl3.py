import json
from openai import OpenAI
import config
from schema_linking.candidate_filter import CandidateFilter
from schema_linking.validator import SLValidator


class CandidateSelector:
    def __init__(self, dataset_name, db_name):
        """
        初始化 CandidateSelector

        :param api_key: 用于调用 LLM 的 API key
        :param base_url: LLM 服务的基础 URL
        """
        self.api_key = config.DEEPSEEK_API
        self.base_url = "https://api.deepseek.com"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.validator = SLValidator(self.dataset_name, self.db_name)

    def select_candidate(self, candidate_result_input, question: str) -> (dict, bool):
        """
        对候选结果进行过滤并最终选择最佳候选结果

        :param candidate_result_input: 候选结果，可以是 JSON 字符串或字典
        :param question: 问题描述
        :return: 最终的候选结果（字典形式）
        """
        # 如果传入的是字符串则先解析为字典
        if isinstance(candidate_result_input, str):
            result_dict = json.loads(candidate_result_input)
        else:
            result_dict = candidate_result_input

        # 调用 CandidateFilter 进行候选结果的过滤与比较
        final_result, is_consistent = CandidateFilter.schema_linking_final_answer(result_dict)

        # 如果候选结果一致，直接返回最终结果
        if is_consistent:
            print("候选结果一致，直接输出最终结果：")
            # print(json.dumps(final_result, indent=4, ensure_ascii=False))
            return final_result, is_consistent
        else:
            # 候选结果不一致，将过滤后的候选结果交给 LLM 判断
            system_prompt = (
                "You are a database domain expert skilled at analyzing which database entities and relationships are needed "
                "to answer a natural language question. \nThe candidate results you receive come from traversing a database schema "
                "represented as a graph. \nThe LLM first selects several table nodes most relevant to the question, then iteratively "
                "expands subgraphs by including the most related entities and relationships. \nThe final candidates have passed strict "
                "validation to ensure all selected entities are consistent with the real database schema.\n\n"
                "### Task:\n"
                "Your task is critical: you must carefully analyze the question, all candidate results, and their reasoning.\n"
                "Your goal is to produce the most reasonable and complete final result.\n"
                "If necessary, you may combine the strengths of different candidates to create a unified answer."
                "This will help ensure that the downstream SQL generation process can produce accurate and executable queries.\n"
                "Return the chosen candidate result in JSON format, including all its fields "
                "(selected_columns, selected_reference_path, reasoning, to_solve_the_question).\n\n"
                """
### Required JSON Format:
```json
{{
  "selected_columns": {{
    "<selected_table>": ["<column>", ...],  /* REQUIRED unless empty */
    ...
    "<neighbor_table>": ["<column>", "<foreign_key>", ...],
    ...
  }},
  "selected_reference_path": {{
  "<table1.column=table2.column>": "<why this reference_path is needed>"
    ...
  }},
  "reasoning": {{
    "<selected_table>": "<why columns were selected>",
    ...
    "<neighbor_table>": "<why this table is needed>"
    ...
  }},
  "to_solve_the_question": {{
    "is_solvable": <true/false>,
    "question": <question>
    "reason": "<Describe the information needed for the currently selected entity and if it corresponds to the problem one by one IN Detail>"
  }}
}}
```
"""
                "### Question:\n"
                "{}\n".format(question)
            )

            user_prompt = (
                    "### Candidate Results :\n" +
                    json.dumps(final_result, indent=4, ensure_ascii=False)
                    + "\n### please return the chosen candidate result in JSON format:"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            print("候选结果不一致，调用 LLM 进行判断。")
            print("输入消息：")
            print(system_prompt)
            print(user_prompt)

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                response_format={'type': 'json_object'}
            )
            output = json.loads(response.choices[0].message.content)
            # print("候选结果不一致，LLM 判断后的最终结果：")
            # print(json.dumps(output, indent=4, ensure_ascii=False))
            return output, is_consistent


# 示例用法
if __name__ == "__main__":
    # 示例候选结果字符串
    candidate_result = """{
        "course": {
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
            "course.course_id=prereq.course_id": "To find the prerequisite course_id(s) for the course with title 'International Finance'.",
            "prereq.prereq_id=takes.course_id": "To find students who have taken the prerequisite course(s).",
            "takes.ID=student.ID": "To retrieve the names of the students who have taken the prerequisite course(s)."
          },
          "reasoning": {
            "course": "Selected 'course_id' to identify the course with title 'International Finance' and 'title' to filter by the course title.",
            "prereq": "Selected 'course_id' to join with 'course' and 'prereq_id' to identify the prerequisite courses.",
            "takes": "Selected 'ID' to join with 'student' and 'course_id' to join with 'prereq' to find students who have taken the prerequisite courses.",
            "student": "Selected 'ID' to join with 'takes' and 'name' to retrieve the names of the students."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "Find the name of students who have taken the prerequisite course of the course with title International Finance.",
            "reason": "The 'course' table provides the course_id for 'International Finance'. The 'prereq' table links this course_id to its prerequisite course_id(s). The 'takes' table connects these prerequisite course_id(s) to student IDs, and the 'student' table provides the names corresponding to these student IDs. Together, these tables and columns provide all necessary information to answer the question."
          }
        },
        "prereq": {
          "selected_columns": {
            "prereq": [
              "prereq_id"
            ],
            "course": [
              "course_id",
              "title"
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
            "prereq.prereq_id=course.course_id": "To link prerequisite courses to their details in the course table.",
            "takes.course_id=prereq.prereq_id": "To find students who have taken the prerequisite courses.",
            "student.ID=takes.ID": "To retrieve the names of the students who have taken the prerequisite courses."
          },
          "reasoning": {
            "prereq": "Selected 'prereq_id' to identify prerequisite courses for the course titled 'International Finance'.",
            "course": "Selected 'course_id' and 'title' to find the course with the title 'International Finance' and its prerequisites.",
            "takes": "Selected 'ID' and 'course_id' to find students who have taken the prerequisite courses identified from the 'prereq' table.",
            "student": "Selected 'ID' and 'name' to retrieve the names of the students found in the 'takes' table."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "Find the name of students who have taken the prerequisite course of the course with title International Finance.",
            "reason": "The selection now includes tables 'prereq', 'course', 'takes', and 'student', which together allow identifying the prerequisite courses for 'International Finance', finding students who have taken these prerequisites, and retrieving their names. This meets all the information needed to answer the question."
          }
        },
        "takes": {
          "selected_columns": {
            "takes": [
              "ID",
              "course_id"
            ],
            "student": [
              "ID",
              "name"
            ],
            "course": [
              "course_id",
              "title"
            ],
            "prereq": [
              "course_id",
              "prereq_id"
            ]
          },
          "selected_reference_path": {
            "takes.ID=student.ID": "To link students with their names",
            "takes.course_id=prereq.prereq_id": "To find prerequisite courses taken by students",
            "prereq.course_id=course.course_id": "To find the course with title 'International Finance'"
          },
          "reasoning": {
            "takes": "Selected 'ID' to identify students and 'course_id' to find courses taken by students",
            "student": "Selected 'ID' to join with 'takes' and 'name' to answer the question",
            "course": "Selected 'course_id' to join with 'prereq' and 'title' to identify 'International Finance'",
            "prereq": "Selected 'course_id' to join with 'course' and 'prereq_id' to find prerequisite courses"
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "Find the name of students who have taken the prerequisite course of the course with title International Finance.",
            "reason": "The 'takes' table alone does not suffice as it lacks information about course titles and prerequisites. By joining 'takes' with 'student', we can get student names. Joining 'takes' with 'prereq' via 'course_id' allows us to find prerequisite courses. Finally, joining 'prereq' with 'course' via 'course_id' enables us to identify the course titled 'International Finance' and its prerequisites."
          }
        },
        "student": {
          "selected_columns": {
            "student": [
              "ID",
              "name"
            ],
            "takes": [
              "ID",
              "course_id"
            ],
            "course": [
              "course_id",
              "title"
            ],
            "prereq": [
              "course_id",
              "prereq_id"
            ]
          },
          "selected_reference_path": {
            "takes.ID=student.ID": "To link students with their course enrollments.",
            "takes.course_id=course.course_id": "To find the course with the title 'International Finance'.",
            "prereq.course_id=course.course_id": "To identify the prerequisite course(s) for 'International Finance'.",
            "takes.course_id=prereq.prereq_id": "To find students who have taken the prerequisite course(s)."
          },
          "reasoning": {
            "student": "Selected 'ID' and 'name' to identify students and retrieve their names.",
            "takes": "Selected 'ID' to link with students and 'course_id' to find enrollments in prerequisite courses.",
            "course": "Selected 'course_id' and 'title' to identify the course 'International Finance' and its prerequisites.",
            "prereq": "Selected 'course_id' and 'prereq_id' to find the prerequisite courses for 'International Finance'."
          },
          "to_solve_the_question": {
            "is_solvable": true,
            "question": "Find the name of students who have taken the prerequisite course of the course with title International Finance.",
            "reason": "The 'student' table alone does not contain information about course enrollments or prerequisites. By expanding to the 'takes', 'course', and 'prereq' tables, we can trace the path from the course titled 'International Finance' to its prerequisites and then to the students who have taken those prerequisites. The selected columns and reference paths enable this tracing by linking students to their enrollments, enrollments to courses, and courses to their prerequisites."
          }
        }
      }"""

    # 定义问题
    question = "Find the name of students who have taken the prerequisite course of the course with title International Finance."

    # 初始化 CandidateSelector 实例
    selector = CandidateSelector("spider", "college_2")

    # 调用选择方法并获得最终结果
    final_candidate, is_consistent = selector.select_candidate(candidate_result, question)

    # 可以根据需要进一步处理 final_candidate
    print(f"一致性：{is_consistent}")
    print("最终选择的候选结果：")
    print(json.dumps(final_candidate, indent=4, ensure_ascii=False))
    # 调用验证器进行验证
    is_valid = selector.validator.validate_and_correct(final_candidate)
    print(f"验证结果：{is_valid}")
