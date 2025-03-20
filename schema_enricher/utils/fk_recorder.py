import json

class FKRecorder:
    def __init__(self, dataset_name, db_name, missing_fk_dict_file,missing_fk_dict):
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.missing_fk_dict_file = missing_fk_dict_file
        self.missing_fk_dict = missing_fk_dict

    def update_missing_fks(self, result):
        """存储外键缺失信息，支持多个 frozenset 并避免重复"""
        if self.dataset_name not in self.missing_fk_dict:
            self.missing_fk_dict[self.dataset_name] = {}

        if self.db_name not in self.missing_fk_dict[self.dataset_name]:
            self.missing_fk_dict[self.dataset_name][self.db_name] = []

        # 遍历 result['missing_fks'] 里面的多个 frozenset
        for missing_fk_set in result["missing_fks"]:
            # 转换 frozenset 为有序列表
            missing_fk_list = [list(fk) for fk in sorted(missing_fk_set)]

            # **检查是否已经存在相同的外键组**
            if missing_fk_list not in self.missing_fk_dict[self.dataset_name][self.db_name]:
                self.missing_fk_dict[self.dataset_name][self.db_name].append(missing_fk_list)
            else:
                print(f"检测到重复的缺失外键，未添加: {missing_fk_list}")

    def save_missing_fks(self,missing_fk_dict,missing_fk_dict_file):
        """合并数据并保存到 JSON 文件"""
        try:
            # 1. 先读取 JSON 文件，获取已有数据
            try:
                with open(missing_fk_dict_file, 'r', encoding="utf-8") as f:
                    existing_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                existing_data = {}

            # 2. 逐层合并新数据，避免覆盖
            for dataset, db_dict in missing_fk_dict.items():
                if dataset not in existing_data:
                    existing_data[dataset] = {}

                for db, fk_list in db_dict.items():
                    if db not in existing_data[dataset]:
                        existing_data[dataset][db] = []

                    # 避免重复数据
                    for fk_set in fk_list:
                        if fk_set not in existing_data[dataset][db]:
                            existing_data[dataset][db].append(fk_set)

            # 3. 将合并后的数据写回 JSON 文件
            with open(self.missing_fk_dict_file, 'w', encoding="utf-8") as f:
                json.dump(existing_data, f, indent=4, ensure_ascii=False)

            print(f"外键缺失数据已成功合并并保存到 {self.missing_fk_dict_file}")

        except Exception as e:
            print(f"保存数据时出现错误: {e}")

    import json

    def load_missing_fks(self, missing_fk_dict_file):
        """从 JSON 读取数据并恢复为原始格式，返回嵌套字典格式"""
        try:
            with open(missing_fk_dict_file, 'r') as f:
                self.missing_fk_dict = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("文件不存在或解析错误，返回空数据")
            return {}

        results = {}
        if self.dataset_name in self.missing_fk_dict:
            dataset_data = self.missing_fk_dict[self.dataset_name]
            results[self.dataset_name] = {}

            if self.db_name in dataset_data:
                missing_fk_sets = []
                for fk_list in dataset_data[self.db_name]:
                    restored_frozenset = frozenset(tuple(fk) for fk in fk_list)
                    missing_fk_sets.append(restored_frozenset)

                results[self.dataset_name][self.db_name] = missing_fk_sets

        return results

    def format_missing_fks(self, missing_fk_sets):
        """
        格式化缺失的外键信息，将其转换为 'table1.column = table2.column' 形式的字符串列表。
        如果外键集合只有一个表，则格式化为 'table.column = table.column'。

        参数:
            missing_fk_sets (list): 由 frozenset 组成的列表，每个 frozenset 包含一个或两个 (表名, 列名) 元组。

        返回:
            list: 格式化后的外键字符串列表，例如 ['table1.column = table2.column'] 或 ['table.column = table.column']。
        """
        formatted_fks = []

        for fk_set in missing_fk_sets:
            fk_list = sorted(fk_set)  # 确保顺序一致
            if len(fk_list) == 2:
                (table1, column1), (table2, column2) = fk_list
                formatted_fks.append(f"{table1}.{column1} = {table2}.{column2}")
            elif len(fk_list) == 1:
                (table, column) = fk_list[0]
                formatted_fks.append(f"{table}.{column} = {table}.{column}")
            else:
                print(f"警告：检测到无法解析的外键集合 {fk_list}，请检查数据格式。")

        return formatted_fks


if __name__ == '__main__':
    # 初始化缺失外键存储字典
    missing_fk_dict = {}

    # 创建 FKRecorder 实例
    recorder = FKRecorder("dataset1", "database1", "missing_fk.json", missing_fk_dict)

    # 添加缺失外键信息
    recorder.update_missing_fks({
        "missing_fks": [
            frozenset({("Faculty", "FacID"), ("Student", "Advisor")}),
            frozenset({("Faculty_Participates_in", "actid")})
        ]
    })

    # 再次添加相同数据，不会重复存储
    recorder.update_missing_fks({
        "missing_fks": [
            frozenset({("Faculty", "FacID"), ("Student", "Advisor")})
        ]
    })

    # 保存数据到 JSON 文件
    recorder.save_missing_fks(missing_fk_dict, "missing_fk.json")

    # 重新加载数据
    restored_data = recorder.load_missing_fks("missing_fk.json")
    print("恢复的数据:", restored_data)
    print(recorder.format_missing_fks(restored_data["dataset1"]["database1"]))
    print("\n".join(recorder.format_missing_fks(restored_data["dataset1"]["database1"])))
