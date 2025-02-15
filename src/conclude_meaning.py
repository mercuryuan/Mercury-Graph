import os
import json

from neo4j import GraphDatabase

from llm import collect_response
from prompt_bank import column_meaning_prompt
import csv
import sqlite3
import tqdm
from utils.attributes_retriever import DatabaseGraphHandler
# import argparse

def get_prompts(db_root_path, table_json):
    prompt_dic = {}
    for i in tqdm.tqdm(range(len(table_json))):
        table_info = table_json[i]
        db_id = table_info['db_id']
        db_path = os.path.join(db_root_path, db_id, f'{db_id}.sqlite')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        csv_dir = os.path.join(db_root_path,db_id,'database_description')
        otn_list = table_info['table_names_original']
        tn_list = table_info['table_names']
        for i, otn in enumerate(otn_list):
            table_name = tn_list[i]
            csv_path = os.path.join(os.path.join(csv_dir, f"{otn}.csv"))
            csv_dict = csv.DictReader(open(csv_path, newline='', encoding="latin1"))
            
            for row in csv_dict:
                headers = list(row.keys())
                ocn_header = [h for h in headers if 'original_column_name' in h][0]  # remove BOM
                ocn, cn = row[ocn_header].strip(), row['column_name']
                column_description = row['column_description'].strip()
                column_type = row['data_format'].strip()
                column_name = cn if cn not in ['', ' '] else ocn
                value_description = row['value_description'].strip()
                column_description = None if (column_description in ['',' '] or column_description == ocn or column_description == column_name) else column_description
                value_description = None if (value_description in ['',' '] or value_description == ocn or value_description == column_name) else value_description
                column_type = None if column_type in ['', ' '] else column_type
                
                if column_type == None and column_description == None:
                    continue
                
                input_paras = f"database_id = '{db_id}', table_name = '{table_name}', column_name = '{column_name}', column_type = '{column_type}'"
                if column_description:
                    input_paras += f", column_description = '{column_description}'"
                if value_description:
                    input_paras += f", value_description = '{value_description}'"
                if column_type in ['text', 'date', 'datetime']:
                    sql = f'''SELECT DISTINCT "{ocn}" FROM `{otn}` where "{ocn}" IS NOT NULL ORDER BY RANDOM()'''
                    cursor.execute(sql)
                    values = cursor.fetchall()
                    if len(values) > 0 and len(values[0][0]) < 50:
                        if len(values) <= 10:
                            all_possible_values = [v[0] for v in values]
                            example_values = None
                        else:
                            all_possible_values = None
                            example_values = [v[0] for v in values[:3]]
                            
                    if example_values:
                        input_paras += f', example_values = {example_values}'
                    if all_possible_values:
                        input_paras += f', all_possible_values = {all_possible_values}'
                
                prompt_dic[f'{db_id}|{otn}|{ocn}'] = column_meaning_prompt.format(input_paras = input_paras)
    return prompt_dic

def conclude_each_column(prompt_dic, output_path):
    output_dic = {}
    for column, prompt in prompt_dic.items():
        output = collect_response(prompt, max_tokens = 800, stop = '\n')
        output_dic[column] = output
        
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                contents = json.loads(f.read())
        else:
            with open(output_path, 'a') as f:
                contents = {}
        contents.update(output_dic)
        json.dump(output_dic, open(output_path, 'w'), indent=4)




if __name__ == '__main__':
    # 创建 Neo4j 驱动连接
    uri = "bolt://localhost:7689"
    username = "neo4j"
    password = "12345678"
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # 使用 DatabaseGraphHandler 类
    handler = DatabaseGraphHandler(driver)
    try:
        # 通过表名获取表节点及其所有列节点属性
        # result = handler.get_table_and_all_column_nodes_by_table_name("Orders")
        result = handler.get_table_and_all_column_nodes_by_table_name("League")
        if result:
            for node_props in result:
                print(node_props)

    finally:
        # 确保正确关闭驱动连接
        driver.close()
