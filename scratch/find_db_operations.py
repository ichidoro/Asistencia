import json

log_file = r"C:\Users\danie\.gemini\antigravity\brain\8cac5fb3-4c42-4b62-ab2f-0c59fac8d902\.system_generated\logs\transcript.jsonl"

with open(log_file, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        try:
            data = json.loads(line)
            # check inside write_to_file calls (CodeContent) or replace_file_content or commands
            for tc in data.get('tool_calls', []):
                args = tc.get('args') or tc.get('Arguments') or {}
                code = args.get('CodeContent', '') or args.get('ReplacementContent', '') or args.get('CommandLine', '')
                if 'delete' in code.lower() and ('sqlite' in code.lower() or 'db' in code.lower()):
                    print(f"Step {line_num} | Tool: {tc.get('name') or tc.get('ToolName')}")
                    print("--- Content Snippet ---")
                    lines = code.split('\n')
                    for l in lines:
                        if any(k in l.lower() for k in ['delete', 'sqlite', 'db']):
                            print(f"  {l.strip()}")
                    print("-" * 30)
        except Exception as e:
            pass
