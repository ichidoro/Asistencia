import os

file_path = "frontend/index.html"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Targets to replace (handling both CRLF and LF)
    target1 = "                                 </div>\n                                 </div>\n                                 <!-- Tab Robot BioAlba -->"
    replacement1 = "                                 </div>\n                                 <!-- Tab Robot BioAlba -->"
    
    target2 = "                                 </div>\r\n                                 </div>\r\n                                 <!-- Tab Robot BioAlba -->"
    replacement2 = "                                 </div>\r\n                                 <!-- Tab Robot BioAlba -->"

    if target2 in content:
        content = content.replace(target2, replacement2)
        print("Replaced CRLF version successfully!")
    elif target1 in content:
        content = content.replace(target1, replacement1)
        print("Replaced LF version successfully!")
    else:
        # Let's try matching with more flexibility
        print("Target string not found directly. Checking with general spacing...")
        import re
        pattern = r"(</div>\s*</div>\s*<!-- Tab Robot BioAlba -->)"
        # Let's look around that area
        match = re.search(r"vista-seguridad-roles.*?(</div>\s*</div>\s*<!-- Tab Robot BioAlba -->)", content, re.DOTALL)
        if match:
            matched_text = match.group(1)
            # We want to replace </div>\s*</div>\s*<!-- Tab Robot BioAlba --> with </div>\s*<!-- Tab Robot BioAlba -->
            # But keep the indentation of the second one
            replacement = "</div>\n                                 <!-- Tab Robot BioAlba -->"
            if "\r\n" in matched_text:
                replacement = "</div>\r\n                                 <!-- Tab Robot BioAlba -->"
            content = content[:match.start(1)] + replacement + content[match.end(1):]
            print("Replaced via regex successfully!")
        else:
            print("Failed to find target via regex too!")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
else:
    print(f"File {file_path} not found.")
