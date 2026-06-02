import json

log_file = r"C:\Users\danie\.gemini\antigravity\brain\8cac5fb3-4c42-4b62-ab2f-0c59fac8d902\.system_generated\logs\transcript.jsonl"

queries_found = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        try:
            data = json.loads(line)
            line_str = json.dumps(data).lower()
            if any(kw in line_str for kw in ['delete', 'update', 'drop', 'insert']):
                # Find where it was
                queries_found.append((line_num, data.get('type'), data.get('tool_calls')))
        except Exception as e:
            pass

print(f"Total matching steps: {len(queries_found)}")
for step in queries_found[-30:]: # Print last 30 matching steps
    print(f"Step {step[0]} | Type: {step[1]}")
    if step[2]:
        for tc in step[2]:
            args = tc.get('args') or tc.get('Arguments') or {}
            cmd = args.get('CommandLine', '')
            if cmd:
                print(f"  Command: {cmd}")
            else:
                print(f"  Tool: {tc.get('name') or tc.get('ToolName')} | Args keys: {list(args.keys())}")
