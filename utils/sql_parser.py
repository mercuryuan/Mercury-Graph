import json
from sqlglot import parse_one, exp

# Function to extract involved entities and their relationships
def extract_entities_from_sql(sql):
    # Parse the SQL query
    parsed_sql = parse_one(sql)

    # Extract tables and their aliases
    table_aliases = {}
    for table in parsed_sql.find_all(exp.Table):
        alias = table.alias_or_name
        table_name = table.name
        # Only add to aliases if alias and table_name are different
        if alias != table_name:
            table_aliases[alias] = table_name

    # Extract columns and associate them with tables
    column_table_mapping = []
    for column in parsed_sql.find_all(exp.Column):
        # Determine the table name for the column
        table_prefix = column.table
        column_name = column.alias_or_name
        if table_prefix:
            # Use the alias to find the actual table name
            table_name = table_aliases.get(table_prefix, table_prefix)
            column_table_mapping.append(f"{table_name}.{column_name}")
        else:
            # If no prefix, assume it's part of a single table context
            column_table_mapping.append(column_name)

    # Extract projections in SELECT statements
    projections = []
    for select in parsed_sql.find_all(exp.Select):
        for projection in select.expressions:
            projections.append(projection.alias_or_name)

    return {
        'tables': list(set(table_aliases.values())),  # Ensure unique table names
        'columns': column_table_mapping,
        'projections': projections,
        'table_aliases': table_aliases
    }

# Function to process the JSON file and analyze the SQL queries
def analyze_books_json(json_file):
    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    for entry in data:
        sql = entry.get('SQL')
        entities = extract_entities_from_sql(sql)

        # Display the analysis for each entry
        print(f"Question: {entry.get('question')}")
        print(f"SQL: {sql}")
        print(f"Tables involved: {entities['tables']}")
        print(f"Columns involved: {entities['columns']}")
        # print(f"Projections: {entities['projections']}")
        print(f"Table aliases: {entities['table_aliases']}")
        print('-' * 80)

# Call the function with the path to the books.json file
analyze_books_json('../data/bird/books.json')
